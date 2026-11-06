"""SQLite warehouse load + KPI view materialization."""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from etl import config

log = logging.getLogger(__name__)

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS fx_rates (
  date TEXT NOT NULL,
  base TEXT NOT NULL,
  currency TEXT NOT NULL,
  rate REAL NOT NULL,
  source TEXT,
  PRIMARY KEY (date, base, currency)
);

CREATE TABLE IF NOT EXISTS interest_rates (
  date TEXT NOT NULL,
  series_id TEXT NOT NULL,
  series_name TEXT NOT NULL,
  value REAL NOT NULL,
  source TEXT,
  PRIMARY KEY (date, series_id)
);

CREATE TABLE IF NOT EXISTS treasury_rates (
  date TEXT NOT NULL,
  security_desc TEXT,
  avg_interest_rate_amt REAL,
  source TEXT
);

CREATE TABLE IF NOT EXISTS bank_financials (
  cert TEXT,
  name TEXT,
  report_date TEXT,
  assets REAL,
  deposits REAL,
  net_income REAL,
  roa REAL,
  npl_ratio REAL,
  equity REAL,
  efficiency_ratio REAL,
  source TEXT
);

CREATE TABLE IF NOT EXISTS world_bank_indicators (
  year INTEGER NOT NULL,
  indicator_code TEXT NOT NULL,
  indicator_name TEXT NOT NULL,
  country TEXT,
  value REAL,
  source TEXT,
  PRIMARY KEY (year, indicator_code)
);

CREATE TABLE IF NOT EXISTS data_quality_log (
  checked_at TEXT,
  dataset TEXT,
  payload_json TEXT
);

CREATE TABLE IF NOT EXISTS etl_runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT,
  finished_at TEXT,
  status TEXT,
  notes TEXT
);
"""

VIEWS_SQL = """
CREATE VIEW IF NOT EXISTS v_latest_rates AS
SELECT series_name, series_id, value, date, source
FROM interest_rates ir
WHERE date = (
  SELECT MAX(date) FROM interest_rates ir2 WHERE ir2.series_id = ir.series_id
);

CREATE VIEW IF NOT EXISTS v_rate_trends AS
SELECT date, series_name, value
FROM interest_rates
ORDER BY date;

CREATE VIEW IF NOT EXISTS v_fx_latest AS
SELECT currency, rate, date, base
FROM fx_rates f
WHERE date = (SELECT MAX(date) FROM fx_rates);

CREATE VIEW IF NOT EXISTS v_bank_system_kpis AS
SELECT
  COUNT(*) AS bank_count,
  SUM(assets) AS total_assets,
  SUM(deposits) AS total_deposits,
  SUM(net_income) AS total_net_income,
  AVG(roa) AS avg_roa,
  AVG(npl_ratio) AS avg_npl_ratio,
  AVG(efficiency_ratio) AS avg_efficiency,
  MAX(report_date) AS as_of_date
FROM bank_financials
WHERE report_date = (SELECT MAX(report_date) FROM bank_financials WHERE report_date IS NOT NULL);

CREATE VIEW IF NOT EXISTS v_wb_latest AS
SELECT indicator_name, indicator_code, value, year
FROM world_bank_indicators w
WHERE year = (SELECT MAX(year) FROM world_bank_indicators w2 WHERE w2.indicator_code = w.indicator_code);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.executescript(VIEWS_SQL)
    conn.commit()


def replace_table(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> int:
    conn.execute(f"DELETE FROM {table}")
    if df is None or df.empty:
        conn.commit()
        return 0
    df.to_sql(table, conn, if_exists="append", index=False)
    conn.commit()
    return len(df)


def log_quality(conn: sqlite3.Connection, reports: list[dict[str, Any]]) -> None:
    ts = datetime.utcnow().isoformat() + "Z"
    for r in reports:
        conn.execute(
            "INSERT INTO data_quality_log(checked_at, dataset, payload_json) VALUES (?,?,?)",
            (ts, r.get("dataset"), json.dumps(r)),
        )
    conn.commit()


def export_dashboard_payload(conn: sqlite3.Connection, quality: dict[str, Any]) -> dict[str, Any]:
    """Build JSON consumed by the static dashboard."""

    def q(sql: str) -> list[dict[str, Any]]:
        cur = conn.execute(sql)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    latest_rates = q("SELECT * FROM v_latest_rates ORDER BY series_name")
    rate_history = q(
        """
        SELECT date, series_name, value FROM interest_rates
        WHERE date >= date('now', '-365 day')
        ORDER BY date
        """
    )
    fx_latest = q("SELECT * FROM v_fx_latest ORDER BY currency")
    fx_history = q(
        """
        SELECT date, currency, rate FROM fx_rates
        WHERE currency IN ('EUR','GBP','JPY','INR')
          AND date >= date('now', '-180 day')
        ORDER BY date
        """
    )
    bank = q("SELECT * FROM v_bank_system_kpis")
    bank_row = bank[0] if bank else {}
    wb = q("SELECT * FROM v_wb_latest ORDER BY indicator_name")
    treasury = q(
        """
        SELECT date, security_desc, avg_interest_rate_amt
        FROM treasury_rates
        WHERE avg_interest_rate_amt IS NOT NULL
        ORDER BY date DESC
        LIMIT 40
        """
    )

    # Top banks by assets (latest report date)
    top_banks = q(
        """
        SELECT name, assets, deposits, net_income, roa, npl_ratio, report_date
        FROM bank_financials
        WHERE report_date = (SELECT MAX(report_date) FROM bank_financials WHERE report_date IS NOT NULL)
          AND assets IS NOT NULL
        ORDER BY assets DESC
        LIMIT 15
        """
    )

    kpis = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "rates": {r["series_name"]: {"value": r["value"], "date": r["date"], "series_id": r["series_id"]} for r in latest_rates},
        "rate_history": rate_history,
        "fx_latest": fx_latest,
        "fx_history": fx_history,
        "bank_system": bank_row,
        "top_banks": top_banks,
        "world_bank": wb,
        "treasury_sample": treasury,
        "quality": quality,
    }
    return kpis
