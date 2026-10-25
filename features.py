from datetime import date, timedelta
import pandas as pd

from calculations import ConsumptionRecord, calculate_summary
from config import FEATURES


def build_snapshot(
    *,
    household_id: str,
    billing_period_id: str,
    period_start: date,
    period_end: date,
    target_units: float,
    previous_period_units: float | None,
    prediction_date: date,
    records: list[ConsumptionRecord],
) -> dict:
    """Uses ONLY records with date <= prediction_date via the calculation engine.
    Never uses final consumption or future records."""
    visible = [r for r in records if r.date <= prediction_date]
    summary = calculate_summary(
        target_units=target_units,
        period_start=period_start,
        period_end=period_end,
        today=prediction_date,
        records=visible,
        include_estimated=True,
    )
    return {
        "household_id": household_id,
        "billing_period_id": billing_period_id,
        "prediction_date": prediction_date.isoformat(),
        "target_units": summary.target_units,
        "period_days": summary.period_days,
        "elapsed_days": summary.elapsed_days_including_today,
        "days_remaining": summary.days_remaining_including_today,
        "cumulative_units": summary.cumulative_including_today,
        "average_daily_units": summary.average_daily_units,
        "previous_period_units": previous_period_units,
    }


def snapshot_feature_frame(snapshots: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(snapshots)[FEATURES]