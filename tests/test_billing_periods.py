from billing_periods import format_billing_period_label


def test_billing_period_label_for_single_month():
    assert format_billing_period_label("2026-10-01", "2026-10-31") == "October 2026"


def test_billing_period_label_for_multiple_months():
    assert (
        format_billing_period_label("2026-12-15", "2027-01-14")
        == "December 2026 – January 2027"
    )
