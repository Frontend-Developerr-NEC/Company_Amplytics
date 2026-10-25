from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

import db
from alerts import ml_alert, rule_based_alerts
from calculations import (
    ConsumptionRecord,
    calculate_summary,
    estimate_tamil_nadu_electricity_charge,
    tamil_nadu_tariff_slab,
)
from config import CLASSIFIER_WARNING_THRESHOLD
from model_loader import load_models, models_available, predict

router = APIRouter(tags=["data"])


def _uid(request: Request) -> str:
    uid = request.session.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="No household selected")
    return uid


def _summary_for(uid: str, bp_id: str, as_of: date | None = None):
    period = db.get_billing_period(bp_id)
    if not period or period["user_id"] != uid:
        raise HTTPException(404, "Billing period not found")
    p_start = date.fromisoformat(period["period_start_date"])
    p_end = date.fromisoformat(period["period_end_date"])
    selected_date = min(max(as_of or date.today(), p_start), p_end)
    records = [
        ConsumptionRecord(
            household_id=r["user_id"], billing_period_id=r["billing_period_id"],
            date=date.fromisoformat(r["date"]), daily_units=float(r["daily_units"]),
            input_method=r["input_method"], data_type=r["data_type"],
            is_complete=bool(r["is_complete"]),
        )
        for r in db.list_daily_records(bp_id)
    ]
    summary = calculate_summary(
        target_units=float(period["target_units"]),
        period_start=p_start, period_end=p_end, today=selected_date, records=records,
    )
    return period, summary, selected_date


def _charge_fields(cumulative_units: float, projected_units: float) -> dict:
    slab, rate = tamil_nadu_tariff_slab(cumulative_units)
    return {
        "cumulative_electricity_charge": estimate_tamil_nadu_electricity_charge(
            cumulative_units
        ),
        "cumulative_tariff_slab": slab,
        "cumulative_tariff_rate_per_unit": rate,
        "baseline_projected_final_electricity_charge":
            estimate_tamil_nadu_electricity_charge(projected_units),
    }


@router.get("/summary")
def get_summary(
    request: Request,
    bp_id: str = Query(...),
    as_of: date | None = Query(None),
):
    uid = _uid(request)
    _, s, selected_date = _summary_for(uid, bp_id, as_of)
    return {
        "as_of": selected_date.isoformat(),
        "target_units": s.target_units,
        "cumulative_including_today": s.cumulative_including_today,
        "remaining_target_units": s.remaining_target_units,
        "excess_units": s.excess_units,
        "percent_target_consumed": s.percent_target_consumed,
        "elapsed_days_including_today": s.elapsed_days_including_today,
        "days_remaining_including_today": s.days_remaining_including_today,
        "todays_target_pace_allowance": s.todays_target_pace_allowance,
        "remaining_allowance_today": s.remaining_allowance_today,
        "baseline_projected_final_units": s.baseline_projected_final_units,
        "target_exceeded": s.target_exceeded,
        "measured_cumulative_units": s.measured_cumulative_units,
        "estimated_cumulative_units": s.estimated_cumulative_units,
        "predicted_cumulative_units": s.predicted_cumulative_units,
        **_charge_fields(
            s.cumulative_including_today, s.baseline_projected_final_units
        ),
    }


@router.get("/predict")
def get_prediction(
    request: Request,
    bp_id: str = Query(...),
    as_of: date | None = Query(None),
):
    uid = _uid(request)
    period, s, selected_date = _summary_for(uid, bp_id, as_of)
    if not models_available():
        return {
            "as_of": selected_date.isoformat(),
            "models_available": False,
            "baseline_projected_final_units": s.baseline_projected_final_units,
            **_charge_fields(
                s.cumulative_including_today, s.baseline_projected_final_units
            ),
        }
    reg, clf, meta = load_models()
    prev = period.get("previous_period_units")
    feats = {
        "target_units": s.target_units,
        "period_days": s.period_days,
        "elapsed_days": s.elapsed_days_including_today,
        "days_remaining": s.days_remaining_including_today,
        "cumulative_units": s.cumulative_including_today,
        "average_daily_units": s.average_daily_units,
        "previous_period_units": float(prev) if prev is not None else None,
    }
    ml_final, ml_proba = predict(reg, clf, feats)
    return {
        "as_of": selected_date.isoformat(),
        "models_available": True,
        "baseline_projected_final_units": s.baseline_projected_final_units,
        **_charge_fields(
            s.cumulative_including_today, s.baseline_projected_final_units
        ),
        "ml_predicted_final_units": ml_final,
        "ml_predicted_final_electricity_charge":
            estimate_tamil_nadu_electricity_charge(ml_final),
        "ml_probability_exceed": ml_proba,
        "threshold": CLASSIFIER_WARNING_THRESHOLD,
        "model_metadata": {
            "data_source": meta.get("data_source"),
            "trained_at": meta.get("trained_at"),
            "regressor": meta.get("regressor"),
            "classifier": meta.get("classifier"),
        },
        "rule_alerts": rule_based_alerts(s),
        "ml_alert": ml_alert(ml_proba, CLASSIFIER_WARNING_THRESHOLD),
    }