"""End-to-end daily ETL: extract → clean → quality → warehouse → JSON export."""
from __future__ import annotations

import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Allow `python etl/pipeline.py` from repo root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl import config
from etl.extractors import (
    extract_fdic,
    extract_frankfurter,
    extract_fred,
    extract_treasury,
    extract_world_bank,
)
from etl.quality import profile_frame, summarize_quality
from etl.transform import clean_fdic, clean_fx, clean_rates, clean_treasury, clean_wb
from etl.warehouse import connect, export_dashboard_payload, init_db, log_quality, replace_table

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("pipeline")


def run() -> dict:
    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    started = datetime.utcnow().isoformat() + "Z"
    log.info("ETL start run_id=%s", run_id)

    fx = clean_fx(extract_frankfurter())
    rates = clean_rates(extract_fred())
    treasury = clean_treasury(extract_treasury())
    banks = clean_fdic(extract_fdic())
    wb = clean_wb(extract_world_bank())

    # Persist raw snapshots (optional audit)
    for name, df in (
        ("fx_rates", fx),
        ("interest_rates", rates),
        ("treasury_rates", treasury),
        ("bank_financials", banks),
        ("world_bank", wb),
    ):
        path = config.DATA_RAW / f"{name}.csv"
        if df is not None and not df.empty:
            df.to_csv(path, index=False)

    reports = [
        profile_frame("fx_rates", fx, "date"),
        profile_frame("interest_rates", rates, "date"),
        profile_frame("treasury_rates", treasury, "date"),
        profile_frame("bank_financials", banks, "report_date"),
        profile_frame("world_bank_indicators", wb, None),
    ]
    # World Bank freshness via year
    if not wb.empty:
        latest_year = int(wb["year"].max())
        days = max(0, (datetime.utcnow().year - latest_year) * 365)
        reports[-1]["freshness"] = {
            "latest_date": str(latest_year),
            "days_stale": days,
            "status": "fresh" if days <= 500 else ("aging" if days <= 900 else "stale"),
        }
        # recompute simple score tweak already set; leave as-is

    quality = summarize_quality(reports)

    conn = connect()
    try:
        init_db(conn)
        conn.execute(
            "INSERT OR REPLACE INTO etl_runs(run_id, started_at, finished_at, status, notes) VALUES (?,?,?,?,?)",
            (run_id, started, None, "running", None),
        )
        conn.commit()

        replace_table(conn, "fx_rates", fx)
        replace_table(conn, "interest_rates", rates)
        replace_table(conn, "treasury_rates", treasury)
        replace_table(conn, "bank_financials", banks)
        replace_table(conn, "world_bank_indicators", wb)
        log_quality(conn, reports)

        payload = export_dashboard_payload(conn, quality)
        config.KPI_JSON.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        config.QUALITY_JSON.write_text(json.dumps(quality, indent=2, default=str), encoding="utf-8")
        meta = {
            "run_id": run_id,
            "generated_at": payload["generated_at"],
            "sources": {
                "frankfurter": len(fx),
                "fred": len(rates),
                "treasury": len(treasury),
                "fdic": len(banks),
                "world_bank": len(wb),
            },
            "fred_key_present": bool(config.FRED_API_KEY),
            "quality_status": quality.get("status"),
            "overall_quality_score": quality.get("overall_score"),
        }
        config.META_JSON.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        finished = datetime.utcnow().isoformat() + "Z"
        conn.execute(
            "UPDATE etl_runs SET finished_at=?, status=?, notes=? WHERE run_id=?",
            (finished, "success", json.dumps(meta), run_id),
        )
        conn.commit()
        log.info("ETL success %s", meta)
        return meta
    except Exception as exc:  # noqa: BLE001
        log.exception("ETL failed")
        try:
            conn.execute(
                "UPDATE etl_runs SET finished_at=?, status=?, notes=? WHERE run_id=?",
                (datetime.utcnow().isoformat() + "Z", "failed", str(exc), run_id),
            )
            conn.commit()
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run()
