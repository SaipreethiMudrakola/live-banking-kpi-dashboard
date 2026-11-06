import pandas as pd

from etl.quality import profile_frame, summarize_quality
from etl.transform import clean_fx, clean_rates, clean_wb


def test_clean_fx_drops_bad_rows():
    df = pd.DataFrame(
        [
            {"date": "2024-01-01", "base": "USD", "currency": "EUR", "rate": 0.9, "source": "t"},
            {"date": "bad", "base": "USD", "currency": "EUR", "rate": 0.9, "source": "t"},
            {"date": "2024-01-02", "base": "USD", "currency": "EUR", "rate": -1, "source": "t"},
        ]
    )
    out = clean_fx(df)
    assert len(out) == 1
    assert out.iloc[0]["rate"] == 0.9


def test_clean_rates_bounds():
    df = pd.DataFrame(
        [
            {"date": "2024-01-01", "series_id": "A", "series_name": "a", "value": 5.0, "source": "fred"},
            {"date": "2024-01-01", "series_id": "B", "series_name": "b", "value": 500.0, "source": "fred"},
        ]
    )
    out = clean_rates(df)
    assert list(out["series_id"]) == ["A"]


def test_quality_score_empty():
    r = profile_frame("empty", pd.DataFrame(), "date")
    assert r["quality_score"] == 0
    s = summarize_quality([r])
    assert s["status"] == "fail"


def test_clean_wb():
    df = pd.DataFrame(
        [
            {"year": 2020, "indicator_code": "X", "indicator_name": "x", "country": "USA", "value": 1.2, "source": "wb"},
            {"year": None, "indicator_code": "X", "indicator_name": "x", "country": "USA", "value": 1.2, "source": "wb"},
        ]
    )
    out = clean_wb(df)
    assert len(out) == 1
