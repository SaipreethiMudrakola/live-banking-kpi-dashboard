-- SQLite warehouse schema for Live Banking KPI Dashboard
-- Applied programmatically by etl/warehouse.py

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

CREATE VIEW IF NOT EXISTS v_latest_rates AS
SELECT series_name, series_id, value, date, source
FROM interest_rates ir
WHERE date = (
  SELECT MAX(date) FROM interest_rates ir2 WHERE ir2.series_id = ir.series_id
);

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
