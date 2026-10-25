from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite
from typing import Callable, Iterable

# the consumption engine

PREDICTED_DATA_TYPE = "predicted"

TAMIL_NADU_DOMESTIC_TARIFF_SLABS = {
    "up_to_500": ((100, 0.0), (100, 0.0), (200, 4.70), (100, 6.30)),
    "above_500": (
        (100, 0.0),
        (300, 4.70),
        (100, 6.30),
        (100, 8.40),
        (200, 9.45),
        (200, 10.50),
        (None, 11.55),
    ),
}


def estimate_tamil_nadu_electricity_charge(units: float) -> float:
    """Estimate energy charges from the Tamil Nadu tariff schedule in use.

    Usage up to 500 units uses the up-to-500 schedule; usage above 500 units
    uses the higher-consumption schedule. Fixed charges and taxes are excluded.
    """
    if not isfinite(units) or units < 0:
        raise ValueError("units must be a finite value >= 0")

    slabs = (
        TAMIL_NADU_DOMESTIC_TARIFF_SLABS["up_to_500"]
        if units <= 500
        else TAMIL_NADU_DOMESTIC_TARIFF_SLABS["above_500"]
    )

    remaining = units
    charge = 0.0
    for slab_units, rate in slabs:
        billed_units = min(
            remaining, slab_units if slab_units is not None else remaining
        )
        charge += billed_units * rate
        remaining -= billed_units
        if remaining <= 0:
            break

    return round(charge, 2)


def tamil_nadu_tariff_slab(units: float) -> tuple[str, float]:
    """Return the applicable progressive tariff slab label and rate for units."""
    if not isfinite(units) or units < 0:
        raise ValueError("units must be a finite value >= 0")

    slabs = (
        TAMIL_NADU_DOMESTIC_TARIFF_SLABS["up_to_500"]
        if units <= 500
        else TAMIL_NADU_DOMESTIC_TARIFF_SLABS["above_500"]
    )
    lower_bound = 0
    for slab_units, rate in slabs:
        upper_bound = (
            lower_bound + slab_units if slab_units is not None else float("inf")
        )
        if units <= upper_bound:
            label = (
                f"{lower_bound if lower_bound == 0 else lower_bound + 1}"
                f"–{int(upper_bound)} units"
                if slab_units is not None
                else f"Above {lower_bound} units"
            )
            return label, rate
        lower_bound = int(upper_bound)

    raise RuntimeError("Tariff schedule does not cover the supplied units")


@dataclass(frozen=True)
class ConsumptionRecord:
    household_id: str
    billing_period_id: str
    date: date
    daily_units: float
    input_method: str
    data_type: str
    is_complete: bool


@dataclass(frozen=True)
class ConsumptionSummary:
    target_units: float
    cumulative_before_today: float
    units_today: float
    cumulative_including_today: float
    measured_cumulative_units: float
    estimated_cumulative_units: float
    predicted_cumulative_units: float
    remaining_target_units: float
    excess_units: float
    percent_target_consumed: float
    period_days: int
    elapsed_days_including_today: int
    days_remaining_including_today: int
    todays_target_pace_allowance: float
    remaining_allowance_today: float
    average_daily_units: float
    baseline_projected_final_units: float
    target_exceeded: bool


def calculate_summary(
    *,
    target_units: float,
    period_start: date,
    period_end: date,
    today: date,
    records: Iterable[ConsumptionRecord],
    include_estimated: bool = True,
) -> ConsumptionSummary:
    """Target-pace calculation. Inclusive date convention:
    period_days = (end - start).days + 1
    elapsed_days_including_today = (today - start).days + 1
    days_remaining_including_today = (end - today).days + 1
    This is not a guarantee the user can consume the allowance without exceeding target.
    """
    if target_units <= 0:
        raise ValueError("target_units must be > 0")
    if period_end < period_start:
        raise ValueError("period_end must be on/after period_start")

    period_days = (period_end - period_start).days + 1
    period_records = [
        r
        for r in records
        if period_start <= r.date <= period_end
        and (include_estimated or r.data_type == "measured")
    ]
    cumulative_records = [r for r in period_records if r.date <= today]

    if today < period_start:
        elapsed_days = 0
        days_remaining = period_days
        cumulative_before = 0.0
        units_today = 0.0
        todays_allowance = 0.0
    elif today > period_end:
        elapsed_days = period_days
        days_remaining = 0
        cumulative_before = sum(r.daily_units for r in period_records)
        units_today = 0.0
        todays_allowance = 0.0
    else:
        elapsed_days = (today - period_start).days + 1
        days_remaining = (period_end - today).days + 1
        cumulative_before = sum(r.daily_units for r in period_records if r.date < today)
        units_today = sum(r.daily_units for r in period_records if r.date == today)
        todays_allowance = (
            max(0.0, target_units - cumulative_before) / days_remaining
            if days_remaining > 0
            else 0.0
        )

    cumulative = cumulative_before + units_today
    measured = sum(
        r.daily_units for r in cumulative_records if r.data_type == "measured"
    )
    estimated = sum(
        r.daily_units for r in cumulative_records if r.data_type == "estimated"
    )
    predicted = sum(
        r.daily_units for r in cumulative_records if r.data_type == PREDICTED_DATA_TYPE
    )

    remaining_target = max(0.0, target_units - cumulative)
    excess = max(0.0, cumulative - target_units)
    percent = (cumulative / target_units * 100.0) if target_units > 0 else 0.0

    remaining_today = max(0.0, todays_allowance - units_today)

    average_daily = cumulative / elapsed_days if elapsed_days > 0 else 0.0
    baseline_projected = average_daily * period_days

    return ConsumptionSummary(
        target_units=target_units,
        cumulative_before_today=cumulative_before,
        units_today=units_today,
        cumulative_including_today=cumulative,
        measured_cumulative_units=measured,
        estimated_cumulative_units=estimated,
        predicted_cumulative_units=predicted,
        remaining_target_units=remaining_target,
        excess_units=excess,
        percent_target_consumed=percent,
        period_days=period_days,
        elapsed_days_including_today=elapsed_days,
        days_remaining_including_today=days_remaining,
        todays_target_pace_allowance=todays_allowance,
        remaining_allowance_today=remaining_today,
        average_daily_units=average_daily,
        baseline_projected_final_units=baseline_projected,
        target_exceeded=cumulative > target_units,
    )


def fill_missing_daily_records(
    *,
    household_id: str,
    billing_period_id: str,
    period_start: date,
    period_end: date,
    as_of: date,
    records: Iterable[ConsumptionRecord],
    historical_daily: float | None = None,
    predict_daily: Callable[[date, float, int, int], float] | None = None,
) -> list[ConsumptionRecord]:
    """Build an inclusive day-by-day series from period_start through as_of.

    Actual stored records are kept as-is. Missing days are filled in this order:
    1. Running average of actual readings seen so far in this period (historical)
    2. ``historical_daily`` baseline (e.g. previous period average), if provided
    3. ``predict_daily(...)`` fallback (target / remaining-days style), if provided
    4. Otherwise 0

    Filled rows use data_type ``predicted``.
    """
    as_of = min(max(as_of, period_start), period_end)
    by_date: dict[date, ConsumptionRecord] = {}
    for r in records:
        if period_start <= r.date <= as_of:
            # Prefer measured over estimated if duplicates ever appear
            existing = by_date.get(r.date)
            if existing is None or (
                existing.data_type != "measured" and r.data_type == "measured"
            ):
                by_date[r.date] = r

    filled: list[ConsumptionRecord] = []
    cumulative = 0.0
    known_sum = 0.0
    known_count = 0
    day = period_start
    while day <= as_of:
        elapsed = (day - period_start).days + 1
        days_remaining = (period_end - day).days + 1
        if day in by_date:
            rec = by_date[day]
            filled.append(rec)
            cumulative += rec.daily_units
            known_sum += rec.daily_units
            known_count += 1
        else:
            if known_count > 0:
                # Prefer historical usage from actual readings in this period
                units = known_sum / known_count
            elif historical_daily is not None and historical_daily > 0:
                # Prior-period / external historical baseline
                units = float(historical_daily)
            elif predict_daily is not None:
                # No history: fall back to target / remaining-days style prediction
                units = float(predict_daily(day, cumulative, elapsed, days_remaining))
            else:
                units = 0.0
            units = max(0.0, units)
            filled.append(
                ConsumptionRecord(
                    household_id=household_id,
                    billing_period_id=billing_period_id,
                    date=day,
                    daily_units=units,
                    input_method="ml",
                    data_type=PREDICTED_DATA_TYPE,
                    is_complete=False,
                )
            )
            cumulative += units
        day += timedelta(days=1)
    return filled