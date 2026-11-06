"""Pull public banking / macro data from free APIs."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd

from etl import config
from etl.http_client import get_json

log = logging.getLogger(__name__)


def extract_frankfurter() -> pd.DataFrame:
    """USD cross rates via Frankfurter (ECB)."""
    end = date.today()
    start = end - timedelta(days=365)
    url = f"{config.FRANKFURTER_BASE}/{start}..{end}"
    payload = get_json(url, {"from": "USD", "to": "EUR,GBP,JPY,CAD,CHF,INR,CNY,AUD"})
    rows = []
    for d, rates in sorted(payload.get("rates", {}).items()):
        for ccy, val in rates.items():
            rows.append({"date": d, "base": "USD", "currency": ccy, "rate": float(val), "source": "frankfurter"})
    df = pd.DataFrame(rows)
    log.info("Frankfurter rows=%s", len(df))
    return df


def extract_fred() -> pd.DataFrame:
    """Interest / rate series from FRED."""
    if not config.FRED_API_KEY:
        log.warning("FRED_API_KEY missing — skipping FRED extract")
        return pd.DataFrame(columns=["date", "series_id", "series_name", "value", "source"])

    rows: list[dict[str, Any]] = []
    start = (date.today() - timedelta(days=365 * 3)).isoformat()
    for name, series_id in config.FRED_SERIES.items():
        url = f"{config.FRED_BASE}/series/observations"
        payload = get_json(
            url,
            {
                "series_id": series_id,
                "api_key": config.FRED_API_KEY,
                "file_type": "json",
                "observation_start": start,
                "sort_order": "asc",
            },
        )
        for obs in payload.get("observations", []):
            val = obs.get("value")
            if val in (None, "."):
                continue
            rows.append(
                {
                    "date": obs["date"],
                    "series_id": series_id,
                    "series_name": name,
                    "value": float(val),
                    "source": "fred",
                }
            )
    df = pd.DataFrame(rows)
    log.info("FRED rows=%s", len(df))
    return df


def extract_treasury() -> pd.DataFrame:
    """Daily Treasury yield curve from Fiscal Data API."""
    url = f"{config.TREASURY_BASE}/v2/accounting/od/avg_interest_rates"
    # Prefer average interest rates on Treasury securities; also try yield curve endpoint
    rows: list[dict[str, Any]] = []
    try:
        payload = get_json(
            url,
            {
                "sort": "-record_date",
                "page[size]": 500,
                "filter": f"record_date:gte:{(date.today() - timedelta(days=400)).isoformat()}",
            },
        )
        for item in payload.get("data", []):
            rows.append(
                {
                    "date": item.get("record_date"),
                    "security_desc": item.get("security_desc") or item.get("security_type_desc"),
                    "avg_interest_rate_amt": _to_float(item.get("avg_interest_rate_amt")),
                    "source": "us_treasury_fiscal",
                }
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("Treasury avg rates failed: %s — trying yield rates", exc)

    yld_url = f"{config.TREASURY_BASE}/v2/accounting/od/avg_interest_rates"
    if not rows:
        # Fallback: debt-to-penny style rates not available — use interest expense rates endpoint already tried
        pass

    # Secondary: Treasury daily yield curve rates (FiscalData)
    try:
        yurl = f"{config.TREASURY_BASE}/v1/accounting/od/rates_of_exchange"
        # rates_of_exchange is FX; use interest rates endpoint already used
    except Exception:
        pass

    # Use Fiscal Data Treasury yield curve if available
    try:
        curl = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/avg_interest_rates"
        payload = get_json(
            curl,
            {
                "fields": "record_date,security_desc,avg_interest_rate_amt,security_type_desc",
                "sort": "-record_date",
                "page[size]": 300,
            },
        )
        if not rows:
            for item in payload.get("data", []):
                rows.append(
                    {
                        "date": item.get("record_date"),
                        "security_desc": item.get("security_desc") or item.get("security_type_desc"),
                        "avg_interest_rate_amt": _to_float(item.get("avg_interest_rate_amt")),
                        "source": "us_treasury_fiscal",
                    }
                )
    except Exception as exc:  # noqa: BLE001
        log.warning("Treasury secondary failed: %s", exc)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.dropna(subset=["date"]).drop_duplicates()
    log.info("Treasury rows=%s", len(df))
    return df


def extract_fdic() -> pd.DataFrame:
    """Aggregate US bank financials from FDIC BankFind Suite API."""
    # Community Banking / institutions financials summary via SOD / RIS-like endpoint
    url = f"{config.FDIC_BASE}/financials"
    # Pull latest available quarter aggregates for large sample of banks, then aggregate
    filters = 'ACTIVE:1 AND STALP:"NY"'  # sample state then nationwide via total
    params = {
        "filters": "ACTIVE:1",
        "fields": "CERT,NAME,REPDTE,ASSET,NETINC,ROA,EEFFR,NCLNLSR,DEP,EQTOT",
        "sort_by": "REPDTE",
        "sort_order": "DESC",
        "limit": 10000,
        "offset": 0,
        "format": "json",
    }
    try:
        payload = get_json(url, params)
    except Exception as exc:  # noqa: BLE001
        log.warning("FDIC financials failed (%s); trying institutions", exc)
        payload = get_json(
            f"{config.FDIC_BASE}/institutions",
            {
                "filters": "ACTIVE:1",
                "fields": "CERT,NAME,ASSET,DEP,ROA,NETINC,EQTOT",
                "limit": 10000,
                "format": "json",
            },
        )

    data = payload.get("data") or []
    rows = []
    for item in data:
        d = item.get("data", item)
        rows.append(
            {
                "cert": d.get("CERT"),
                "name": d.get("NAME"),
                "report_date": _fmt_repdte(d.get("REPDTE")),
                "assets": _to_float(d.get("ASSET")),
                "deposits": _to_float(d.get("DEP")),
                "net_income": _to_float(d.get("NETINC")),
                "roa": _to_float(d.get("ROA")),
                "npl_ratio": _to_float(d.get("NCLNLSR")),
                "equity": _to_float(d.get("EQTOT")),
                "efficiency_ratio": _to_float(d.get("EEFFR")),
                "source": "fdic",
            }
        )
    df = pd.DataFrame(rows)
    log.info("FDIC rows=%s", len(df))
    return df


def extract_world_bank() -> pd.DataFrame:
    """US banking system indicators from World Bank."""
    rows = []
    for name, code in config.WB_INDICATORS.items():
        url = f"{config.WORLD_BANK_BASE}/country/USA/indicator/{code}"
        payload = get_json(url, {"format": "json", "per_page": 60, "date": "2000:2025"})
        # World Bank returns [meta, data]
        series = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        for item in series or []:
            val = item.get("value")
            if val is None:
                continue
            rows.append(
                {
                    "year": int(item["date"]),
                    "indicator_code": code,
                    "indicator_name": name,
                    "country": "USA",
                    "value": float(val),
                    "source": "world_bank",
                }
            )
    df = pd.DataFrame(rows)
    log.info("World Bank rows=%s", len(df))
    return df


def _to_float(v: Any) -> float | None:
    if v is None or v == "" or v == ".":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_repdte(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v)
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s
