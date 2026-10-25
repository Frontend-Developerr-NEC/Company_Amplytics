from datetime import date
import pytest

from calculations import (
    ConsumptionRecord,
    PREDICTED_DATA_TYPE,
    calculate_summary,
    estimate_tamil_nadu_electricity_charge,
    fill_missing_daily_records,
    tamil_nadu_tariff_slab,
)


def rec(d, u, data_type="measured"):
    return ConsumptionRecord(
        household_id="H", billing_period_id="BP",
        date=d, daily_units=u, input_method="manual",
        data_type=data_type, is_complete=True,
    )


@pytest.mark.parametrize(
    ("units", "expected_charge"),
    [
        (0, 0),
        (200, 0),
        (201, 4.70),
        (400, 940),
        (401, 946.30),
        (500, 1570),
        (501, 2048.40),
        (600, 2880),
        (601, 2889.45),
        (800, 4770),
        (801, 4780.50),
        (1000, 6870),
        (1001, 6881.55),
    ],
)
def test_tamil_nadu_electricity_charge_by_tariff_slab(units, expected_charge):
    assert estimate_tamil_nadu_electricity_charge(units) == pytest.approx(
        expected_charge
    )


def test_tamil_nadu_electricity_charge_rejects_negative_units():
    with pytest.raises(ValueError, match="units must be a finite value >= 0"):
        estimate_tamil_nadu_electricity_charge(-1)


@pytest.mark.parametrize(
    ("units", "expected_slab", "expected_rate"),
    [
        (113.23, "101–200 units", 0.0),
        (400, "201–400 units", 4.70),
        (500, "401–500 units", 6.30),
        (501, "501–600 units", 8.40),
        (1042.18, "Above 1000 units", 11.55),
    ],
)
def test_tamil_nadu_tariff_slab_uses_cumulative_units(
    units, expected_slab, expected_rate
):
    slab, rate = tamil_nadu_tariff_slab(units)
    assert slab == expected_slab
    assert rate == expected_rate


def test_selected_date_charge_does_not_use_future_projected_consumption():
    summary = calculate_summary(
        target_units=1100,
        period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 3),
        today=date(2024, 1, 1),
        records=[
            rec(date(2024, 1, 1), 113.23),
            rec(date(2024, 1, 2), 928.95, PREDICTED_DATA_TYPE),
        ],
    )
    full_period_units = 1042.18

    assert summary.cumulative_including_today == pytest.approx(113.23)
    assert summary.predicted_cumulative_units == 0
    assert estimate_tamil_nadu_electricity_charge(
        summary.cumulative_including_today
    ) == 0
    assert estimate_tamil_nadu_electricity_charge(full_period_units) == pytest.approx(
        7357.18
    )


def test_before_period():
    s = calculate_summary(
        target_units=100, period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 31), today=date(2023, 12, 31),
        records=[],
    )
    assert s.cumulative_including_today == 0
    assert s.elapsed_days_including_today == 0
    assert s.days_remaining_including_today == 31
    assert s.todays_target_pace_allowance == 0


def test_midperiod():
    recs = [rec(date(2024, 1, 1), 10), rec(date(2024, 1, 2), 8)]
    s = calculate_summary(
        target_units=100, period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 10), today=date(2024, 1, 2),
        records=recs,
    )
    assert s.cumulative_before_today == 10
    assert s.units_today == 8
    assert s.cumulative_including_today == 18
    assert s.elapsed_days_including_today == 2
    assert s.days_remaining_including_today == 9
    assert s.remaining_target_units == 82
    # (100 - 10) / 9 = 10.0; minus 8 used = 2.0 remaining
    assert s.todays_target_pace_allowance == pytest.approx(10.0)
    assert s.remaining_allowance_today == pytest.approx(2.0)
    assert s.average_daily_units == pytest.approx(9.0)
    assert s.baseline_projected_final_units == pytest.approx(90.0)


def test_target_exceeded():
    recs = [rec(date(2024, 1, 1), 60), rec(date(2024, 1, 2), 60)]
    s = calculate_summary(
        target_units=100, period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 3), today=date(2024, 1, 2),
        records=recs,
    )
    assert s.cumulative_including_today == 120
    assert s.remaining_target_units == 0
    assert s.excess_units == 20
    assert s.target_exceeded


def test_after_period():
    recs = [rec(date(2024, 1, 1), 10)]
    s = calculate_summary(
        target_units=100, period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 31), today=date(2024, 2, 5),
        records=recs,
    )
    assert s.elapsed_days_including_today == 31
    assert s.days_remaining_including_today == 0
    assert s.todays_target_pace_allowance == 0


def test_estimated_excluded():
    recs = [rec(date(2024, 1, 1), 5, "measured"),
            rec(date(2024, 1, 2), 7, "estimated")]
    s = calculate_summary(
        target_units=100, period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 10), today=date(2024, 1, 2),
        records=recs, include_estimated=False,
    )
    assert s.cumulative_including_today == 5
    assert s.measured_cumulative_units == 5


def test_invalid_target():
    with pytest.raises(ValueError):
        calculate_summary(
            target_units=0, period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 2), today=date(2024, 1, 1),
            records=[],
        )


def test_fill_missing_prefers_historical_over_predictor():
    """Once actual readings exist, gaps use historical average — not target predictor."""
    recs = [rec(date(2024, 1, 1), 10), rec(date(2024, 1, 3), 12)]
    filled = fill_missing_daily_records(
        household_id="H",
        billing_period_id="BP",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 5),
        as_of=date(2024, 1, 4),
        records=recs,
        predict_daily=lambda day, cum, elapsed, rem: 99.0,
    )
    assert [r.date for r in filled] == [
        date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4),
    ]
    assert filled[0].data_type == "measured" and filled[0].daily_units == 10
    # After day 1 (10), missing day 2 uses historical avg = 10
    assert filled[1].data_type == PREDICTED_DATA_TYPE and filled[1].daily_units == pytest.approx(10.0)
    assert filled[2].data_type == "measured" and filled[2].daily_units == 12
    # After days 1+3 actual (avg 11), missing day 4 uses 11 — not predictor 99
    assert filled[3].data_type == PREDICTED_DATA_TYPE and filled[3].daily_units == pytest.approx(11.0)

    s = calculate_summary(
        target_units=100,
        period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 5),
        today=date(2024, 1, 4),
        records=filled,
    )
    assert s.cumulative_including_today == pytest.approx(43.0)
    assert s.predicted_cumulative_units == pytest.approx(21.0)
    assert s.measured_cumulative_units == pytest.approx(22.0)


def test_fill_missing_uses_historical_daily_baseline():
    filled = fill_missing_daily_records(
        household_id="H",
        billing_period_id="BP",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 3),
        as_of=date(2024, 1, 2),
        records=[],
        historical_daily=8.5,
        predict_daily=lambda *a: 99.0,
    )
    assert all(r.data_type == PREDICTED_DATA_TYPE for r in filled)
    assert filled[0].daily_units == pytest.approx(8.5)
    assert filled[1].daily_units == pytest.approx(8.5)


def test_fill_missing_falls_back_to_target_predictor_when_no_history():
    filled = fill_missing_daily_records(
        household_id="H",
        billing_period_id="BP",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 3),
        as_of=date(2024, 1, 2),
        records=[],
        historical_daily=None,
        predict_daily=lambda day, cum, elapsed, rem: 7.0,
    )
    assert filled[0].daily_units == pytest.approx(7.0)
    assert filled[1].daily_units == pytest.approx(7.0)