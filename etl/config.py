"""Central configuration for ETL pipelines."""
from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATA_RAW = ROOT / "data" / "raw"
DATA_WAREHOUSE = ROOT / "data" / "warehouse"
DASHBOARD_DATA = ROOT / "dashboard" / "data"
SQL_DIR = ROOT / "sql"

DB_PATH = DATA_WAREHOUSE / "banking_kpis.db"
KPI_JSON = DASHBOARD_DATA / "kpis.json"
QUALITY_JSON = DASHBOARD_DATA / "quality.json"
META_JSON = DASHBOARD_DATA / "meta.json"

def _normalize_fred_key(raw: str) -> str:
    """Accept bare keys or common paste mistakes like 'FRED_API_KEY:...' / 'api_key=...'."""
    key = (raw or "").strip().strip('"').strip("'")
    if not key:
        return ""
    for prefix in ("FRED_API_KEY:", "FRED_API_KEY=", "api_key:", "api_key="):
        if key.upper().startswith(prefix.upper()):
            key = key[len(prefix) :].strip()
            break
    # FRED keys are 32 hex chars; if a longer string embeds one, take the hex run
    if len(key) != 32:
        m = re.search(r"(?i)\b([a-f0-9]{32})\b", key)
        if m:
            key = m.group(1)
    return key.strip()


FRED_API_KEY = _normalize_fred_key(os.getenv("FRED_API_KEY", ""))
FRED_BASE = os.getenv("FRED_BASE_URL", "https://api.stlouisfed.org/fred").rstrip("/")
FRANKFURTER_BASE = os.getenv("FRANKFURTER_BASE_URL", "https://api.frankfurter.app").rstrip("/")
TREASURY_BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
FDIC_BASE = "https://banks.data.fdic.gov/api"
WORLD_BANK_BASE = "https://api.worldbank.org/v2"

# FRED series used for rate KPIs
FRED_SERIES = {
    "fed_funds": "FEDFUNDS",
    "sofr": "SOFR",
    "treasury_10y": "DGS10",
    "mortgage_30y": "MORTGAGE30US",
    "prime_rate": "DPRIME",
}

# World Bank indicators (US)
WB_INDICATORS = {
    "bank_capital_to_assets": "FB.BNK.CAPA.ZS",
    "npl_ratio": "FB.AST.NPER.ZS",
    "domestic_credit_pct_gdp": "FS.AST.DOMS.GD.ZS",
}

REQUEST_TIMEOUT = 45
USER_AGENT = "live-banking-kpi-dashboard/1.0 (+portfolio)"

for p in (DATA_RAW, DATA_WAREHOUSE, DASHBOARD_DATA):
    p.mkdir(parents=True, exist_ok=True)