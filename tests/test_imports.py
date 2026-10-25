import json
from io import BytesIO

import pandas as pd
import pytest

from web.imports import read_daily_record_file


def test_read_csv_daily_records():
    rows = read_daily_record_file(
        "usage.csv",
        b"date,daily_units,data_type\n2026-10-01,12.5,measured\n",
    )

    assert rows == [
        {"date": "2026-10-01", "daily_units": "12.5", "data_type": "measured"}
    ]


def test_read_json_daily_records_in_records_object():
    content = json.dumps(
        {"records": [{"date": "2026-10-01", "daily_units": 12.5, "data_type": "measured"}]}
    ).encode()

    assert read_daily_record_file("usage.json", content) == [
        {"date": "2026-10-01", "daily_units": 12.5, "data_type": "measured"}
    ]


def test_read_excel_daily_records():
    content = BytesIO()
    pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-10-01"),
                "daily_units": 12.5,
                "data_type": "measured",
            }
        ]
    ).to_excel(content, index=False)

    rows = read_daily_record_file("usage.xlsx", content.getvalue())

    assert rows[0]["date"] == pd.Timestamp("2026-10-01")
    assert rows[0]["daily_units"] == 12.5


def test_reject_unsupported_file_type():
    with pytest.raises(ValueError, match="Unsupported file type"):
        read_daily_record_file("usage.txt", b"")


def test_reject_json_without_required_columns():
    with pytest.raises(ValueError, match="Missing: data_type"):
        read_daily_record_file("usage.json", b'[{"date":"2026-10-01","daily_units":12}]')
