"""Generate synthetic electricity data for the Amplytics prototype.

ALL DATA PRODUCED HERE IS SYNTHETIC. It is designed only to let the prototype
run end-to-end. Do NOT interpret any model metric derived from this data as
evidence of real-world performance.
"""

import json
from datetime import date, timedelta
import numpy as np
import pandas as pd

from config import RAW_DIR

RNG = np.random.default_rng(42)
N_HOUSEHOLDS = 30
N_COMPLETED_PERIODS = 3
PERIOD_START = date(2024, 1, 1)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def main():
    billing_rows, daily_rows, appliance_rows = [], [], []

    for h in range(1, N_HOUSEHOLDS + 1):
        hid = f"H{h:03d}"
        household_size = int(RNG.integers(1, 6))
        # typical daily usage grows with household size
        mu = 6.0 + household_size * 2.5 + RNG.normal(0, 1.5)
        mu = max(2.0, mu)
        sigma = max(0.8, RNG.normal(2.0, 0.5))

        # appliances (informational only)
        for name, atype, watts, qty, hours, days in [
            ("Fridge", "cooling", 150, 1, 24, 7),
            ("TV", "electronics", 100, 1, 4, 7),
            ("Washing machine", "laundry", 500, 1, 1, 3),
        ]:
            appliance_rows.append({
                "household_id": hid,
                "appliance_name": name,
                "appliance_type": atype,
                "rated_power_watts": watts,
                "quantity": qty,
                "hours_per_day": hours,
                "days_per_week": days,
                "data_source": "synthetic",
            })

        previous_final = None
        for p in range(N_COMPLETED_PERIODS):
            year = PERIOD_START.year + (PERIOD_START.month - 1 + p) // 12
            month = (PERIOD_START.month - 1 + p) % 12 + 1
            p_start, p_end = month_bounds(year, month)
            period_days = (p_end - p_start).days + 1

            days = pd.date_range(p_start, p_end, freq="D")
            daily_units = np.clip(RNG.normal(mu, sigma, size=len(days)), 0.1, None)

            for d, u in zip(days, daily_units):
                daily_rows.append({
                    "household_id": hid,
                    "billing_period_id": f"{hid}-P{p+1}",
                    "date": d.date().isoformat(),
                    "daily_units": round(float(u), 3),
                    "input_method": "manual",
                    "data_type": "measured",
                    "is_complete": 1,
                    "data_source": "synthetic",
                })

            actual_final = float(daily_units.sum())
            # target set around actual final with +/- 15% (synthetic)
            factor = RNG.uniform(0.85, 1.15)
            target = max(30.0, round(actual_final * factor, 1))

            billing_rows.append({
                "household_id": hid,
                "household_size": household_size,
                "billing_period_id": f"{hid}-P{p+1}",
                "period_start_date": p_start.isoformat(),
                "period_end_date": p_end.isoformat(),
                "target_units": target,
                "previous_period_units": previous_final,
                "actual_final_units": round(actual_final, 3),
                "data_source": "synthetic",
            })
            previous_final = round(actual_final, 3)

    pd.DataFrame(billing_rows).to_csv(RAW_DIR / "synthetic_household_billing.csv", index=False)
    pd.DataFrame(daily_rows).to_csv(RAW_DIR / "synthetic_daily_consumption.csv", index=False)
    pd.DataFrame(appliance_rows).to_csv(RAW_DIR / "synthetic_appliances.csv", index=False)

    meta = {
        "data_source": "synthetic",
        "generator": "scripts/generate_synthetic_data.py",
        "seed": 42,
        "n_households": N_HOUSEHOLDS,
        "n_completed_periods_per_household": N_COMPLETED_PERIODS,
        "note": (
            "This data is SYNTHETIC and only supports prototyping. "
            "Targets and final consumption are simulated; any model metric derived "
            "from this data does not describe real households."
        ),
    }
    (RAW_DIR / "synthetic_metadata.json").write_text(json.dumps(meta, indent=2))
    print(f"Wrote {len(billing_rows)} billing periods, "
          f"{len(daily_rows)} daily rows, {len(appliance_rows)} appliance rows.")


if __name__ == "__main__":
    main()