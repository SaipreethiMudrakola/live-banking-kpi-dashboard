"""Clean and validate extracted frames."""
from __future__ import annotations

import pandas as pd


def clean_fx(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["rate"] = pd.to_numeric(out["rate"], errors="coerce")
    out = out.dropna(subset=["date", "currency", "rate"])
    out = out[out["rate"] > 0]
    return out.drop_duplicates(subset=["date", "base", "currency"])


def clean_rates(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["date", "series_id", "value"])
    # rates should be plausible percentages
    out = out[(out["value"] > -1) & (out["value"] < 100)]
    return out.drop_duplicates(subset=["date", "series_id"])


def clean_treasury(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["avg_interest_rate_amt"] = pd.to_numeric(out["avg_interest_rate_amt"], errors="coerce")
    out = out.dropna(subset=["date"])
    return out.drop_duplicates()


def clean_fdic(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if "report_date" in out.columns:
        out["report_date"] = pd.to_datetime(out["report_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    for c in ("assets", "deposits", "net_income", "roa", "npl_ratio", "equity", "efficiency_ratio"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    # Keep rows with at least assets or name
    out = out.dropna(subset=["name"], how="all") if "name" in out.columns else out
    return out.drop_duplicates(subset=[c for c in ("cert", "report_date") if c in out.columns] or None)


def clean_wb(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["year"] = pd.to_numeric(out["year"], errors="coerce").astype("Int64")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["year", "indicator_code", "value"])
    return out.drop_duplicates(subset=["year", "indicator_code"])
