import pandas as pd

from etl.warehouse import connect, export_dashboard_payload, init_db, replace_table


def test_warehouse_roundtrip(tmp_path):
    db = tmp_path / "t.db"
    conn = connect(db)
    init_db(conn)
    rates = pd.DataFrame(
        [
            {"date": "2024-06-01", "series_id": "FEDFUNDS", "series_name": "fed_funds", "value": 5.25, "source": "fred"},
            {"date": "2024-07-01", "series_id": "FEDFUNDS", "series_name": "fed_funds", "value": 5.33, "source": "fred"},
        ]
    )
    replace_table(conn, "interest_rates", rates)
    payload = export_dashboard_payload(conn, {"overall_score": 90, "status": "pass", "datasets": []})
    assert payload["rates"]["fed_funds"]["value"] == 5.33
    conn.close()
