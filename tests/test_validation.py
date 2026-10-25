from datetime import date

from validation import (
    validate_appliance, validate_billing_period, validate_daily_record,
)


def test_billing_period_ok():
    assert validate_billing_period(date(2024, 1, 1), date(2024, 1, 31), 100) == []


def test_billing_period_bad_range():
    errs = validate_billing_period(date(2024, 2, 1), date(2024, 1, 1), 100)
    assert errs


def test_billing_period_bad_target():
    assert validate_billing_period(date(2024, 1, 1), date(2024, 1, 31), 0)


def test_daily_record_ok():
    assert validate_daily_record(
        date(2024, 1, 5), 3.0, "measured", "manual",
        date(2024, 1, 1), date(2024, 1, 31),
    ) == []


def test_daily_record_outside():
    assert validate_daily_record(
        date(2024, 2, 5), 3.0, "measured", "manual",
        date(2024, 1, 1), date(2024, 1, 31),
    )


def test_daily_record_bad_type():
    assert validate_daily_record(
        date(2024, 1, 5), 3.0, "actual", "manual",
        date(2024, 1, 1), date(2024, 1, 31),
    )


def test_appliance_ok():
    assert validate_appliance("TV", 100, 1, 4, 7) == []


def test_appliance_bad_hours():
    assert validate_appliance("TV", 100, 1, 30, 7)