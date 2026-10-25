from datetime import date
from config import DATA_TYPES, INPUT_METHODS


def validate_billing_period(start: date, end: date, target_units: float) -> list[str]:
    errors = []
    if end < start:
        errors.append("period_end_date must be on or after period_start_date")
    if target_units is None or target_units <= 0:
        errors.append("target_units must be a positive number")
    return errors


def validate_daily_record(
    rec_date: date,
    daily_units: float,
    data_type: str,
    input_method: str,
    period_start: date,
    period_end: date,
) -> list[str]:
    errors = []
    if daily_units is None or daily_units < 0:
        errors.append("daily_units must be >= 0")
    if data_type not in DATA_TYPES:
        errors.append(f"data_type must be one of {DATA_TYPES}")
    if input_method not in INPUT_METHODS:
        errors.append(f"input_method must be one of {INPUT_METHODS}")
    if not (period_start <= rec_date <= period_end):
        errors.append("date must fall inside the billing period")
    return errors


def validate_appliance(
    name: str,
    rated_power_watts: float,
    quantity: int,
    hours_per_day: float,
    days_per_week: float,
) -> list[str]:
    errors = []
    if not name or not name.strip():
        errors.append("appliance_name is required")
    if rated_power_watts is None or rated_power_watts <= 0:
        errors.append("rated_power_watts must be > 0")
    if quantity is None or quantity < 1:
        errors.append("quantity must be >= 1")
    if hours_per_day is None or hours_per_day < 0 or hours_per_day > 24:
        errors.append("hours_per_day must be between 0 and 24")
    if days_per_week is None or days_per_week < 0 or days_per_week > 7:
        errors.append("days_per_week must be between 0 and 7")
    return errors