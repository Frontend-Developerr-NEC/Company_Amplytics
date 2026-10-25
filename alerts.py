from calculations import ConsumptionSummary
from config import CLASSIFIER_WARNING_THRESHOLD

# Modified from the original implementation
def rule_based_alerts(summary: ConsumptionSummary) -> list[dict]:
    """Rule-based alerts. These are deterministic and independent of ML."""
    alerts = []

    if summary.target_exceeded:
        alerts.append({
            "level": "danger",
            "title": "Target exceeded",
            "message": (
                f"You have exceeded your target by "
                f"{summary.excess_units:.2f} units so far."
            ),
        })
    elif summary.percent_target_consumed >= 90:
        alerts.append({
            "level": "warning",
            "title": "Near target",
            "message": (
                f"You have used {summary.percent_target_consumed:.0f}% of your target."
            ),
        })

    if summary.baseline_projected_final_units > summary.target_units and not summary.target_exceeded:
        alerts.append({
            "level": "warning",
            "title": "Baseline projection exceeds target",
            "message": (
                f"At your current average pace you are projected to end at "
                f"{summary.baseline_projected_final_units:.2f} units "
                f"(target {summary.target_units:.2f})."
            ),
        })

    if summary.remaining_allowance_today <= 0 and summary.days_remaining_including_today > 0:
        alerts.append({
            "level": "info",
            "title": "Today's allowance used",
            "message": (
                "You have already used today's target-pace allowance. "
                "Consumption from here increases the risk of exceeding your target."
            ),
        })

    if summary.estimated_cumulative_units > 0:
        alerts.append({
            "level": "info",
            "title": "Estimated units included",
            "message": (
                f"{summary.estimated_cumulative_units:.2f} units of your cumulative "
                f"total are estimated, not measured."
            ),
        })

    if summary.predicted_cumulative_units > 0:
        alerts.append({
            "level": "info",
            "title": "Predicted missing days",
            "message": (
                f"{summary.predicted_cumulative_units:.2f} units come from predicted "
                f"fills for days with no recorded reading (historical average when "
                f"available; otherwise target / remaining-days estimate)."
            ),
        })

    return alerts


def ml_alert(probability: float, threshold: float = CLASSIFIER_WARNING_THRESHOLD) -> dict:
    """ML-based warning, always labelled as an estimate."""
    if probability >= threshold:
        return {
            "level": "ml_warning",
            "title": "ML estimate: high risk of exceeding target",
            "message": (
                f"Model estimated probability of exceeding your target: "
                f"{probability*100:.1f}% (threshold {threshold*100:.0f}%). "
                f"This is an estimate, not a guarantee."
            ),
        }
    return {
        "level": "ml_ok",
        "title": "ML estimate: lower risk",
        "message": (
            f"Model estimated probability of exceeding your target: "
            f"{probability*100:.1f}%. This is an estimate, not a guarantee."
        ),
    }