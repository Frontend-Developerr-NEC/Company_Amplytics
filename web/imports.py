import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_DAILY_RECORD_COLUMNS = {"date", "daily_units", "data_type"}
SUPPORTED_IMPORT_EXTENSIONS = {".csv", ".json", ".xls", ".xlsx"}


def read_daily_record_file(filename: str, content: bytes) -> list[dict[str, Any]]:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_IMPORT_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_IMPORT_EXTENSIONS))
        raise ValueError(f"Unsupported file type. Choose one of: {supported}.")

    if extension == ".csv":
        try:
            text = content.decode("utf-8-sig")
            rows = list(csv.DictReader(io.StringIO(text)))
        except (UnicodeDecodeError, csv.Error) as exc:
            raise ValueError(f"Could not read CSV: {exc}") from exc
    elif extension == ".json":
        try:
            data = json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not read JSON: {exc}") from exc
        if isinstance(data, dict):
            data = data.get("records")
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise ValueError(
                "JSON must contain an array of record objects, or an object "
                "with a 'records' array."
            )
        rows = data
    else:
        try:
            dataframe = pd.read_excel(io.BytesIO(content), sheet_name=0)
        except (ImportError, OSError, ValueError, zipfile.BadZipFile) as exc:
            raise ValueError(f"Could not read Excel file: {exc}") from exc
        rows = dataframe.astype(object).where(pd.notna(dataframe), None).to_dict(
            orient="records"
        )

    columns = set(rows[0]) if rows else set()
    missing = REQUIRED_DAILY_RECORD_COLUMNS - columns
    if missing:
        required = ", ".join(sorted(REQUIRED_DAILY_RECORD_COLUMNS))
        raise ValueError(
            f"File must include columns: {required} "
            f"(optional: input_method). Missing: {', '.join(sorted(missing))}."
        )
    return rows
