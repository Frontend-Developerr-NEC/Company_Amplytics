from datetime import date


def format_billing_period_label(start: str, end: str) -> str:
    period_start = date.fromisoformat(start)
    period_end = date.fromisoformat(end)
    start_label = period_start.strftime("%B %Y")
    end_label = period_end.strftime("%B %Y")
    if start_label == end_label:
        return start_label
    return f"{start_label} – {end_label}"
