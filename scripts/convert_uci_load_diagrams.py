
"""Convert UCI Electricity Load Diagrams 2011-2014 to Amplytics schema.

Source : https://archive.ics.uci.edu/ml/datasets/ElectricityLoadDiagrams20112014
License: CC BY 4.0
Format : semicolon-separated, decimal comma, 15-minute interval, kW average power.

What is REAL:
  - daily_units            (aggregated from real 15-min readings)
  - household_id           (client IDs MT_001..MT_370)
  - previous_period_units  (sum of prior real period)
  - actual_final_units     (sum of real daily units)

What is DERIVED (not in source, must be disclosed):
  - billing period dates   (calendar months)
  - target_units           (prior_period_units x multiplier drawn from N(1.0, 0.10), clipped [0.85, 1.15])
  - target_exceeded        (actual_final_units > target_units)
  - household_size         (placeholder 3)
  - appliances             (empty; users enter in app)

The FIRST calendar month of each household is skipped because there is no
previous_period_units to derive a target from.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from config import RAW_DIR, PROCESSED_DIR

URL = "https://archive.ics.uci.edu/ml/machine-learning-databases/00321/LD2011_2014.txt.zip"
RAW_SUBDIR = RAW_DIR / "uci_load_diagrams"
RAW_SUBDIR.mkdir(parents=True, exist_ok=True)
SEED = 42
MIN_DAILY_KWH = 0.01
MAX_CLIENTS = 100  # subsample for faster iteration; set None to use all 370


def download() -> Path:
    zip_path = RAW_SUBDIR / "LD2011_2014.txt.zip"
    if not zip_path.exists():
        print(f"Downloading {URL} ... (~300 MB)")
        urllib.request.urlretrieve(URL, zip_path)
    return zip_path


def load_daily(zip_path: Path) -> pd.DataFrame:
    print("Reading zip (this can take a minute)...")
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if n.endswith(".txt"))
        with z.open(name) as f:
            df = pd.read_csv(f, sep=";", decimal=",", index_col=0, parse_dates=True)
    # 15-min kW -> kWh per interval = kW * 0.25 h; sum per day = daily kWh
    daily = (df.resample("D").sum() * 0.25).round(3)
    daily.index.name = "date"
    print(f"Daily shape: {daily.shape} (clients x days)")
    return daily


def derive_periods(daily: pd.DataFrame, rng: np.random.Generator):
    if MAX_CLIENTS is not None:
        cols = daily.columns[:MAX_CLIENTS]
        daily = daily[cols]

    billing_rows, daily_rows = [], []

    for hid in daily.columns:
        series = daily[hid].dropna()
        series = series[series > MIN_DAILY_KWH]
        if series.empty:
            continue

        # month bucket
        months = series.index.to_period("M")
        prev_final = None
        for m in sorted(months.unique()):
            in_month = series[months == m]
            if in_month.empty:
                continue

            if prev_final is None:
                # skip first month per household: no prior period to derive target
                prev_final = float(in_month.sum())
                continue

            start = in_month.index.min().date()
            end = in_month.index.max().date()
            actual_final = float(in_month.sum())

            factor = float(np.clip(rng.normal(1.0, 0.10), 0.85, 1.15))
            target = max(30.0, round(prev_final * factor, 1))

            bp_id = f"{hid}-{m.strftime('%Y%m')}"
            billing_rows.append({
                "household_id": hid,
                "household_size": 3,                       # placeholder
                "billing_period_id": bp_id,
                "period_start_date": start.isoformat(),
                "period_end_date": end.isoformat(),
                "target_units": target,                    # DERIVED
                "previous_period_units": round(prev_final, 3),
                "actual_final_units": round(actual_final, 3),
                "data_source": "real_consumption_derived_target",
            })

            for d, u in in_month.items():
                daily_rows.append({
                    "household_id": hid,
                    "billing_period_id": bp_id,
                    "date": d.date().isoformat(),
                    "daily_units": float(u),
                    "input_method": "import",
                    "data_type": "measured",
                    "is_complete": 1,
                    "data_source": "real_consumption",
                })
            prev_final = actual_final

    return pd.DataFrame(billing_rows), pd.DataFrame(daily_rows)


def main():
    rng = np.random.default_rng(SEED)
    zip_path = download()
    daily = load_daily(zip_path)
    billing, daily_rows = derive_periods(daily, rng)

    billing_path = RAW_DIR / "household_billing.csv"
    daily_path = RAW_DIR / "daily_consumption.csv"
    appliances_path = RAW_DIR / "appliances.csv"

    billing.to_csv(billing_path, index=False)
    daily_rows.to_csv(daily_path, index=False)
    # appliances: empty file with correct header (users add in the app)
    pd.DataFrame(columns=[
        "household_id", "appliance_name", "appliance_type", "rated_power_watts",
        "quantity", "hours_per_day", "days_per_week", "data_source",
    ]).to_csv(appliances_path, index=False)

    meta = {
        "primary_source": "UCI Electricity Load Diagrams 2011-2014",
        "url": "https://archive.ics.uci.edu/ml/datasets/ElectricityLoadDiagrams20112014",
        "license": "CC BY 4.0",
        "seed": SEED,
        "max_clients_used": MAX_CLIENTS,
        "n_households": int(billing["household_id"].nunique()),
        "n_billing_periods": int(len(billing)),
        "n_daily_rows": int(len(daily_rows)),
        "real_fields": [
            "daily_units", "household_id", "previous_period_units",
            "actual_final_units",
        ],
        "derived_fields": {
            "target_units": "prior_period_units * clip(N(1.0, 0.10), 0.85, 1.15), min 30",
            "target_exceeded": "actual_final_units > target_units",
            "period_start_date/end_date": "first/last observed day of the calendar month",
            "household_size": "placeholder 3",
            "appliances": "empty — users enter in app",
        },
        "limitations": [
            "Targets are derived, not real. The target-exceedance model therefore "
            "learns a synthetic label. Do not present its metrics as real-world "
            "exceedance prediction accuracy.",
            "The first calendar month per household is dropped (no prior period).",
            "Data represents 15-minute average kW; daily kWh is 0.25 * sum over intervals.",
        ],
    }
    (RAW_DIR / "dataset_metadata.json").write_text(json.dumps(meta, indent=2))

    print(f"Wrote {len(billing)} billing periods, {len(daily_rows)} daily rows.")
    print(f"Households: {billing['household_id'].nunique()}")


if __name__ == "__main__":
    main()