"""Data quality profiling for dashboard transparency."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd


def profile_frame(name: str, df: pd.DataFrame, date_col: str | None = None) -> dict[str, Any]:
    total = int(len(df))
    missing = {c: int(df[c].isna().sum()) for c in df.columns} if total else {}
    dupes = int(df.duplicated().sum()) if total else 0
    odd: dict[str, int] = {}
    for c in df.select_dtypes(include="number").columns:
        s = df[c]
        odd[c] = int(((s < 0) | (s.abs() > 1e7)).sum()) if len(s) else 0

    freshness = {"latest_date": None, "days_stale": None, "status": "unknown"}
    if date_col and total and date_col in df.columns:
        parsed = pd.to_datetime(df[date_col], errors="coerce")
        latest = parsed.max()
        if pd.notna(latest):
            days = (pd.Timestamp(date.today()) - latest.normalize()).days
            freshness = {
                "latest_date": latest.date().isoformat(),
                "days_stale": int(days),
                "status": "fresh" if days <= 7 else ("aging" if days <= 45 else "stale"),
            }

    score = 100.0
    if total == 0:
        score = 0.0
    else:
        miss_rate = sum(missing.values()) / max(total * max(len(df.columns), 1), 1)
        score -= min(40.0, miss_rate * 100)
        score -= min(20.0, dupes / total * 100)
        if freshness.get("status") == "stale":
            score -= 25
        elif freshness.get("status") == "aging":
            score -= 10
        if freshness.get("status") == "unknown" and date_col:
            score -= 5
    score = max(0.0, round(score, 1))

    return {
        "dataset": name,
        "row_count": total,
        "column_count": int(df.shape[1]) if total or df.shape[1] else 0,
        "missing_values": missing,
        "duplicate_rows": dupes,
        "odd_values": odd,
        "freshness": freshness,
        "quality_score": score,
        "checked_at": datetime.utcnow().isoformat() + "Z",
    }


def summarize_quality(reports: list[dict[str, Any]]) -> dict[str, Any]:
    if not reports:
        return {"overall_score": 0, "datasets": [], "status": "fail"}
    scores = [r["quality_score"] for r in reports]
    overall = round(sum(scores) / len(scores), 1)
    status = "pass" if overall >= 80 else ("warn" if overall >= 60 else "fail")
    return {"overall_score": overall, "status": status, "datasets": reports}
