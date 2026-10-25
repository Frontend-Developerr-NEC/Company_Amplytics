"""Derive ml_training_data.csv from the raw synthetic data.

Prediction-date snapshots are built with the same calculation engine the UI
uses. Only records with date <= prediction_date are visible to the snapshot.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date
import pandas as pd

from config import RAW_DIR, PROCESSED_DIR
from calculations import ConsumptionRecord
from features import build_snapshot

SNAPSHOT_FRACTIONS = (0.25, 0.50, 0.75, 0.90)


def main():
    billing = pd.read_csv(RAW_DIR / "household_billing.csv")
    daily   = pd.read_csv(RAW_DIR / "daily_consumption.csv")
    
    # billing = pd.read_csv(RAW_DIR / "synthetic_household_billing.csv")
    # daily = pd.read_csv(RAW_DIR / "synthetic_daily_consumption.csv")

    daily["date"] = pd.to_datetime(daily["date"]).dt.date
    billing["period_start_date"] = pd.to_datetime(billing["period_start_date"]).dt.date
    billing["period_end_date"] = pd.to_datetime(billing["period_end_date"]).dt.date

    records_by_bp: dict[str, list[ConsumptionRecord]] = {}
    for _, row in daily.iterrows():
        records_by_bp.setdefault(row["billing_period_id"], []).append(
            ConsumptionRecord(
                household_id=row["household_id"],
                billing_period_id=row["billing_period_id"],
                date=row["date"],
                daily_units=float(row["daily_units"]),
                input_method=row["input_method"],
                data_type=row["data_type"],
                is_complete=bool(row["is_complete"]),
            )
        )
    for bp in records_by_bp.values():
        bp.sort(key=lambda r: r.date)

    snapshots = []
    for _, period in billing.iterrows():
        if pd.isna(period["actual_final_units"]):
            continue

        period_days = (period["period_end_date"] - period["period_start_date"]).days + 1
        prev = period["previous_period_units"]
        prev = None if pd.isna(prev) else float(prev)

        for frac in SNAPSHOT_FRACTIONS:
            offset = max(0, int(round(frac * period_days)) - 1)
            pdate = period["period_start_date"] + pd.Timedelta(days=offset)
            if pdate > period["period_end_date"]:
                pdate = period["period_end_date"]

            snap = build_snapshot(
                household_id=period["household_id"],
                billing_period_id=period["billing_period_id"],
                period_start=period["period_start_date"],
                period_end=period["period_end_date"],
                target_units=float(period["target_units"]),
                previous_period_units=prev,
                prediction_date=pdate,
                records=records_by_bp.get(period["billing_period_id"], []),
            )
            snap["actual_final_units"] = float(period["actual_final_units"])
            snap["target_exceeded"] = int(
                period["actual_final_units"] > period["target_units"]
            )
            snapshots.append(snap)

    out = pd.DataFrame(snapshots)
    out.to_csv(PROCESSED_DIR / "ml_training_data.csv", index=False)
    print(f"Wrote {len(out)} snapshots to ml_training_data.csv")


if __name__ == "__main__":
    main()