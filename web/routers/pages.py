from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import UploadFile, File

import pandas as pd
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

import db
from billing_periods import format_billing_period_label
from alerts import ml_alert, rule_based_alerts
from calculations import (
    ConsumptionRecord,
    PREDICTED_DATA_TYPE,
    TAMIL_NADU_DOMESTIC_TARIFF_SLABS,
    calculate_summary,
    estimate_tamil_nadu_electricity_charge,
    fill_missing_daily_records,
)
from config import CLASSIFIER_WARNING_THRESHOLD
from model_loader import load_models, models_available, predict
from model_benchmarks import benchmark_models
from validation import (
    validate_billing_period, validate_daily_record,
)
from web.imports import read_daily_record_file
from web.deps import current_uid, pop_flash, set_flash

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")
templates.env.filters["billing_period_label"] = format_billing_period_label


@router.post("/consumption/import")
async def consumption_import(
    request: Request,
    bp_id: str = Form(...),
    file: UploadFile = File(...),
):
    uid = current_uid(request)
    if not uid:
        return RedirectResponse("/", 303)

    period = db.get_billing_period(bp_id)
    if not period or period["user_id"] != uid:
        set_flash(request, "error", "Invalid billing period.")
        return RedirectResponse("/consumption", 303)

    p_start = date.fromisoformat(period["period_start_date"])
    p_end = date.fromisoformat(period["period_end_date"])

    try:
        rows = read_daily_record_file(file.filename or "", await file.read())
    except ValueError as exc:
        set_flash(request, "error", str(exc))
        return RedirectResponse(f"/consumption?bp_id={bp_id}", 303)

    inserted, updated, rejected = 0, 0, []
    existing = {r["date"] for r in db.list_daily_records(bp_id)}

    for i, row in enumerate(rows, start=2):
        try:
            raw_date = row["date"]
            if isinstance(raw_date, datetime):
                rec_date = raw_date.date()
            elif isinstance(raw_date, date):
                rec_date = raw_date
            else:
                rec_date = date.fromisoformat(raw_date.strip())
            units = float(row["daily_units"])
            dtype = row["data_type"].strip()
            imethod = (row.get("input_method") or "import").strip()
        except (AttributeError, KeyError, TypeError, ValueError) as e:
            rejected.append(f"line {i}: {e}")
            continue

        errs = validate_daily_record(
            rec_date, units, dtype, imethod, p_start, p_end
        )
        if errs:
            rejected.append(f"line {i}: {'; '.join(errs)}")
            continue

        db.upsert_daily_record(
            uid, bp_id, rec_date.isoformat(), units, imethod, dtype, True
        )
        if rec_date.isoformat() in existing:
            updated += 1
        else:
            inserted += 1

    msg = f"Imported: {inserted} new, {updated} updated."
    if rejected:
        msg += f" {len(rejected)} rows rejected (first 3: {' | '.join(rejected[:3])})."
        set_flash(request, "warning", msg)
    else:
        set_flash(request, "success", msg)

    return RedirectResponse(f"/consumption?bp_id={bp_id}", 303)


def render(request: Request, name: str, **context):
    uid = current_uid(request)
    return templates.TemplateResponse(
        request=request,
        name=name,
        context={
            "flash": pop_flash(request),
            "current_user": db.get_user(uid) if uid else None,
            "households": db.list_users(),
            "today": date.today().isoformat(),
            **context,
        },
    )


def _records_for(bp_id: str) -> list[ConsumptionRecord]:
    return [
        ConsumptionRecord(
            household_id=r["user_id"],
            billing_period_id=r["billing_period_id"],
            date=date.fromisoformat(r["date"]),
            daily_units=float(r["daily_units"]),
            input_method=r["input_method"],
            data_type=r["data_type"],
            is_complete=bool(r["is_complete"]),
        )
        for r in db.list_daily_records(bp_id)
    ]


def _month_bounds(today: date) -> tuple[date, date]:
    start = today.replace(day=1)
    nxt = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    return start, nxt - timedelta(days=1)


# ---------- landing / auth ----------

@router.get("/")
def landing(request: Request):
    if current_uid(request):
        return RedirectResponse("/household", 303)
    return render(request, "landing.html")


@router.post("/register")
def register(
    request: Request,
    display_name: str = Form(...),
    email: str = Form(""),
    household_size: int = Form(3),
):
    if not display_name.strip():
        set_flash(request, "error", "Display name is required.")
        return RedirectResponse("/", 303)
    import uuid
    uid = "U-" + uuid.uuid4().hex[:8]
    try:
        db.create_user(uid, email.strip() or None, display_name.strip(), int(household_size))
    except Exception as e:
        set_flash(request, "error", f"Could not create household: {e}")
        return RedirectResponse("/", 303)
    request.session["user_id"] = uid
    set_flash(request, "success", f"Household {display_name.strip()} created.")
    return RedirectResponse("/household", 303)


@router.post("/switch")
def switch_household(request: Request, uid: str = Form(...)):
    if db.get_user(uid):
        request.session["user_id"] = uid
    return RedirectResponse("/household", 303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", 303)


# ---------- household ----------

@router.get("/household")
def household_page(request: Request):
    uid = current_uid(request)
    if not uid:
        return RedirectResponse("/", 303)
    user = db.get_user(uid)
    if not user:
        request.session.clear()
        return RedirectResponse("/", 303)
    return render(request, "household.html", user=user)


@router.post("/household/update")
def household_update(
    request: Request,
    display_name: str = Form(...),
    email: str = Form(""),
    household_size: int = Form(3),
):
    uid = current_uid(request)
    if not uid:
        return RedirectResponse("/", 303)
    name = display_name.strip()
    if not name:
        set_flash(request, "error", "Holder name is required.")
        return RedirectResponse("/household", 303)
    if household_size < 1 or household_size > 20:
        set_flash(request, "error", "Household size must be between 1 and 20.")
        return RedirectResponse("/household", 303)
    email_val = email.strip() or None
    if not db.update_user(uid, email_val, name, int(household_size)):
        set_flash(request, "error", "Could not update household.")
        return RedirectResponse("/household", 303)
    set_flash(request, "success", "Household updated.")
    return RedirectResponse("/household", 303)


@router.post("/household/delete")
def household_delete(request: Request):
    uid = current_uid(request)
    if not uid:
        return RedirectResponse("/", 303)
    user = db.get_user(uid)
    name = user["display_name"] if user else uid
    if db.delete_user(uid):
        request.session.clear()
        set_flash(
            request,
            "success",
            f"Household “{name}” deleted, including billing periods, "
            f"daily records, and appliances.",
        )
        return RedirectResponse("/", 303)
    set_flash(request, "error", "Could not delete household.")
    return RedirectResponse("/household", 303)


# ---------- billing ----------

@router.get("/billing")
def billing_page(request: Request):
    uid = current_uid(request)
    if not uid:
        return RedirectResponse("/", 303)
    periods = db.list_billing_periods(uid)
    today = date.today()
    d_start, d_end = _month_bounds(today)
    return render(
        request, "billing.html",
        periods=periods,
        default_start=d_start.isoformat(),
        default_end=d_end.isoformat(),
    )


@router.post("/billing/create")
def billing_create(
    request: Request,
    start: str = Form(...),
    end: str = Form(...),
    target: float = Form(...),
):
    uid = current_uid(request)
    if not uid:
        return RedirectResponse("/", 303)
    try:
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
    except ValueError:
        set_flash(request, "error", "Invalid date format.")
        return RedirectResponse("/billing", 303)
    errors = validate_billing_period(s, e, target)
    if errors:
        for err in errors:
            set_flash(request, "error", err)
        return RedirectResponse("/billing", 303)
    prior = db.previous_completed_period(uid, s.isoformat())
    prev_units = float(prior["actual_final_units"]) if prior else None
    bp_id = f"{uid}-{s.isoformat()}"
    try:
        db.create_billing_period(bp_id, uid, s, e, float(target), prev_units)
    except Exception as ex:
        set_flash(request, "error", f"Could not create period: {ex}")
        return RedirectResponse("/billing", 303)
    set_flash(
        request,
        "success",
        f"Billing period {format_billing_period_label(start, end)} created.",
    )
    return RedirectResponse("/billing", 303)


@router.post("/billing/target")
def billing_update_target(request: Request, bp_id: str = Form(...), target: float = Form(...)):
    uid = current_uid(request)
    if not uid:
        return RedirectResponse("/", 303)
    period = db.get_billing_period(bp_id)
    if not period or period["user_id"] != uid:
        set_flash(request, "error", "Invalid billing period.")
        return RedirectResponse("/billing", 303)
    if target <= 0:
        set_flash(request, "error", "Target must be positive.")
        return RedirectResponse("/billing", 303)
    db.update_billing_target(bp_id, float(target))
    set_flash(request, "success", "Target updated.")
    return RedirectResponse("/billing", 303)


@router.post("/billing/delete")
def billing_delete(request: Request, bp_id: str = Form(...)):
    uid = current_uid(request)
    if not uid:
        return RedirectResponse("/", 303)
    period = db.get_billing_period(bp_id)
    if db.delete_billing_period(bp_id, uid):
        label = (
            format_billing_period_label(
                period["period_start_date"], period["period_end_date"]
            )
            if period
            else "Billing period"
        )
        set_flash(
            request,
            "success",
            f"{label} deleted (including its daily records).",
        )
    else:
        set_flash(request, "error", "Could not delete billing period.")
    return RedirectResponse("/billing", 303)


# ---------- bill estimator ----------

@router.get("/bill-estimator")
def bill_estimator_page(request: Request, bp_id: Optional[str] = None):
    uid = current_uid(request)
    if not uid:
        return RedirectResponse("/", 303)
    periods = db.list_billing_periods(uid)
    if not periods:
        set_flash(request, "info", "Create a billing period to estimate your bill.")
        return RedirectResponse("/billing", 303)

    period = next((p for p in periods if p["billing_period_id"] == bp_id), periods[0])
    p_start = date.fromisoformat(period["period_start_date"])
    p_end = date.fromisoformat(period["period_end_date"])
    period_days = (p_end - p_start).days + 1
    previous_units = period.get("previous_period_units")
    historical_daily = (
        float(previous_units) / period_days
        if previous_units is not None and period_days > 0
        else None
    )

    def predict_missing(
        _day: date, cumulative: float, _elapsed: int, days_remaining: int
    ) -> float:
        return (
            max(0.0, float(period["target_units"]) - cumulative) / days_remaining
            if days_remaining > 0
            else 0.0
        )

    filled = fill_missing_daily_records(
        household_id=uid,
        billing_period_id=period["billing_period_id"],
        period_start=p_start,
        period_end=p_end,
        as_of=p_end,
        records=_records_for(period["billing_period_id"]),
        historical_daily=historical_daily,
        predict_daily=predict_missing,
    )
    daily_data = [
        {
            "date": record.date.isoformat(),
            "units": record.daily_units,
            "data_type": record.data_type,
        }
        for record in filled
    ]
    projected_period_units = sum(record.daily_units for record in filled)
    projected_final_bill = estimate_tamil_nadu_electricity_charge(
        projected_period_units
    )

    return render(
        request,
        "bill_estimator.html",
        periods=periods,
        period=period,
        daily_data=daily_data,
        tariff_slabs=TAMIL_NADU_DOMESTIC_TARIFF_SLABS,
        projected_period_units=projected_period_units,
        projected_final_bill=projected_final_bill,
    )


# ---------- consumption ----------

@router.get("/consumption")
def consumption_page(request: Request, bp_id: Optional[str] = None):
    uid = current_uid(request)
    if not uid:
        return RedirectResponse("/", 303)
    periods = db.list_billing_periods(uid)
    if not periods:
        set_flash(request, "info", "Create a billing period first.")
        return RedirectResponse("/billing", 303)
    selected = next((p for p in periods if p["billing_period_id"] == bp_id), periods[0])
    records = db.list_daily_records(selected["billing_period_id"])
    return render(
        request, "consumption.html",
        periods=periods, selected=selected, records=records,
    )


@router.post("/consumption/save")
def consumption_save(
    request: Request,
    bp_id: str = Form(...),
    date_str: str = Form(...),
    units: float = Form(...),
    data_type: str = Form(...),
    input_method: str = Form("manual"),
):
    uid = current_uid(request)
    if not uid:
        return RedirectResponse("/", 303)
    period = db.get_billing_period(bp_id)
    if not period or period["user_id"] != uid:
        set_flash(request, "error", "Invalid billing period.")
        return RedirectResponse("/consumption", 303)
    try:
        rec_date = date.fromisoformat(date_str)
    except ValueError:
        set_flash(request, "error", "Invalid date.")
        return RedirectResponse(f"/consumption?bp_id={bp_id}", 303)
    p_start = date.fromisoformat(period["period_start_date"])
    p_end = date.fromisoformat(period["period_end_date"])
    errors = validate_daily_record(rec_date, float(units), data_type, input_method, p_start, p_end)
    if errors:
        for err in errors:
            set_flash(request, "error", err)
        return RedirectResponse(f"/consumption?bp_id={bp_id}", 303)
    db.upsert_daily_record(uid, bp_id, rec_date.isoformat(), float(units), input_method, data_type, True)
    set_flash(request, "success", "Record saved.")
    return RedirectResponse(f"/consumption?bp_id={bp_id}", 303)


@router.post("/consumption/delete")
def consumption_delete(request: Request, bp_id: str = Form(...), date_str: str = Form(...)):
    if not current_uid(request):
        return RedirectResponse("/", 303)
    db.delete_daily_record(bp_id, date_str)
    set_flash(request, "success", "Record deleted.")
    return RedirectResponse(f"/consumption?bp_id={bp_id}", 303)


# ---------- dashboard ----------

@router.get("/model-benchmark")
def model_benchmark_page(request: Request):
    if not current_uid(request):
        return RedirectResponse("/", 303)
    return render(
        request,
        "model_benchmark.html",
        benchmarks=benchmark_models(),
    )


@router.get("/dashboard")
def dashboard(
    request: Request,
    bp_id: Optional[str] = None,
    today: Optional[str] = None,
):
    uid = current_uid(request)
    if not uid:
        return RedirectResponse("/", 303)
    periods = db.list_billing_periods(uid)
    if not periods:
        set_flash(request, "info", "Create a billing period to see your dashboard.")
        return RedirectResponse("/billing", 303)

    period = next((p for p in periods if p["billing_period_id"] == bp_id), periods[0])
    p_start = date.fromisoformat(period["period_start_date"])
    p_end = date.fromisoformat(period["period_end_date"])
    target = float(period["target_units"])
    period_days = (p_end - p_start).days + 1

    # Date picker: use selected date when valid, else clamp calendar today into period
    if today:
        try:
            picked = date.fromisoformat(today)
        except ValueError:
            picked = date.today()
    else:
        picked = date.today()
    effective_today = min(max(picked, p_start), p_end)

    records = _records_for(period["billing_period_id"])
    prev_raw = period.get("previous_period_units")
    prev = float(prev_raw) if prev_raw is not None else None

    # Historical daily baseline from previous period total (if known)
    historical_daily = (prev / period_days) if prev is not None and period_days > 0 else None

    reg = clf = meta = None
    if models_available():
        reg, clf, meta = load_models()

    def _predict_missing_from_target(
        day: date, cumulative: float, elapsed: int, days_remaining: int
    ) -> float:
        """No-history fallback: allocate remaining target-based forecast over remaining days."""
        if reg is not None and clf is not None:
            avg = cumulative / elapsed if elapsed > 0 else 0.0
            feats = {
                "target_units": target,
                "period_days": period_days,
                "elapsed_days": elapsed,
                "days_remaining": days_remaining,
                "cumulative_units": cumulative,
                "average_daily_units": avg,
                "previous_period_units": prev,
            }
            ml_final_est, _ = predict(reg, clf, feats)
            remaining = max(0.0, ml_final_est - cumulative)
            return remaining / days_remaining if days_remaining > 0 else 0.0
        # Models unavailable: pace from billing-period target
        remaining = max(0.0, target - cumulative)
        return remaining / days_remaining if days_remaining > 0 else 0.0

    filled = fill_missing_daily_records(
        household_id=uid,
        billing_period_id=period["billing_period_id"],
        period_start=p_start,
        period_end=p_end,
        as_of=effective_today,
        records=records,
        historical_daily=historical_daily,
        predict_daily=_predict_missing_from_target,
    )

    summary = calculate_summary(
        target_units=target,
        period_start=p_start, period_end=p_end,
        today=effective_today, records=filled,
    )
    billable_units = summary.cumulative_including_today
    electricity_bill_estimate = estimate_tamil_nadu_electricity_charge(
        billable_units
    )
    projected_final_bill_estimate = estimate_tamil_nadu_electricity_charge(
        summary.baseline_projected_final_units
    )
    rule_alerts = rule_based_alerts(summary)

    ml_final = None
    ml_proba = None
    ml_alert_obj = None
    if reg is not None and clf is not None:
        feats = {
            "target_units": summary.target_units,
            "period_days": summary.period_days,
            "elapsed_days": summary.elapsed_days_including_today,
            "days_remaining": summary.days_remaining_including_today,
            "cumulative_units": summary.cumulative_including_today,
            "average_daily_units": summary.average_daily_units,
            "previous_period_units": prev,
        }
        ml_final, ml_proba = predict(reg, clf, feats)
        ml_alert_obj = ml_alert(ml_proba, CLASSIFIER_WARNING_THRESHOLD)

    daily_series = [
        {
            "date": r.date.isoformat(),
            "units": r.daily_units,
            "data_type": r.data_type,
            "source": "predicted" if r.data_type == PREDICTED_DATA_TYPE else "actual",
        }
        for r in filled
    ]
    # Also show future actual records beyond as_of in the table context? No —
    # dashboard is as-of selected date. Future stored rows stay out of KPIs/charts.
    missing_count = sum(1 for r in filled if r.data_type == PREDICTED_DATA_TYPE)

    return render(
        request, "dashboard.html",
        periods=periods, period=period, summary=summary,
        billable_units=billable_units,
        electricity_bill_estimate=electricity_bill_estimate,
        projected_final_bill_estimate=projected_final_bill_estimate,
        rule_alerts=rule_alerts,
        ml_final=ml_final, ml_proba=ml_proba, ml_alert_obj=ml_alert_obj,
        model_meta=meta,
        missing_count=missing_count,
        chart_payload={
            "period_start": p_start.isoformat(),
            "period_end": p_end.isoformat(),
            "as_of": effective_today.isoformat(),
            "target": target,
            "records": daily_series,
        },
        p_start=p_start.isoformat(), p_end=p_end.isoformat(),
        effective_today=effective_today.isoformat(),
    )