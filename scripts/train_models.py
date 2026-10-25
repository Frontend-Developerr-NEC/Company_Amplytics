"""Train HistGradientBoosting models on ml_training_data.csv.

- Groups snapshots by billing_period_id to avoid leakage across related snapshots.
- Evaluates on a grouped holdout, then fits production pipelines on all rows.
- Saves pipelines and the holdout metrics.
- Does NOT retrain automatically.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error,
    accuracy_score, precision_score, recall_score, f1_score, confusion_matrix,
)

from config import PROCESSED_DIR, MODELS_DIR, FEATURES

REG_PATH = MODELS_DIR / "hist_gradient_boosting_regressor.joblib"
CLF_PATH = MODELS_DIR / "hist_gradient_boosting_classifier.joblib"
META_PATH = MODELS_DIR / "model_metadata.json"


def make_regressor():
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", HistGradientBoostingRegressor(random_state=42)),
    ])


def make_classifier():
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", HistGradientBoostingClassifier(random_state=42)),
    ])


def main():
    df = pd.read_csv(PROCESSED_DIR / "ml_training_data.csv")
    if df.empty:
        raise SystemExit("ml_training_data.csv is empty — run build_training_data first.")

    gss = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
    train_idx, test_idx = next(gss.split(df, groups=df["billing_period_id"]))
    train_df, test_df = df.iloc[train_idx], df.iloc[test_idx]

    # ---- regression ----
    reg = make_regressor()
    reg.fit(train_df[FEATURES], train_df["actual_final_units"])
    reg_pred = reg.predict(test_df[FEATURES])
    reg_mae = mean_absolute_error(test_df["actual_final_units"], reg_pred)
    reg_rmse = float(np.sqrt(mean_squared_error(test_df["actual_final_units"], reg_pred)))

    # ---- baseline (average_daily_units * period_days) ----
    baseline_pred = test_df["average_daily_units"] * test_df["period_days"]
    base_mae = mean_absolute_error(test_df["actual_final_units"], baseline_pred)
    base_rmse = float(np.sqrt(mean_squared_error(test_df["actual_final_units"], baseline_pred)))

    # ---- classification ----
    clf = make_classifier()
    clf.fit(train_df[FEATURES], train_df["target_exceeded"])
    clf_proba = clf.predict_proba(test_df[FEATURES])[:, 1]
    clf_pred = (clf_proba >= 0.5).astype(int)

    precision = precision_score(test_df["target_exceeded"], clf_pred, zero_division=0)
    recall = recall_score(test_df["target_exceeded"], clf_pred, zero_division=0)
    f1 = f1_score(test_df["target_exceeded"], clf_pred, zero_division=0)
    cm = confusion_matrix(test_df["target_exceeded"], clf_pred).tolist()

    reg.fit(df[FEATURES], df["actual_final_units"])
    clf.fit(df[FEATURES], df["target_exceeded"])
    joblib.dump(reg, REG_PATH)
    joblib.dump(clf, CLF_PATH)

    metadata = {
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_source": "synthetic",
        "regressor": "HistGradientBoostingRegressor",
        "classifier": "HistGradientBoostingClassifier",
        "n_train_rows": int(len(train_df)),
        "n_production_train_rows": int(len(df)),
        "n_test_rows": int(len(test_df)),
        "n_train_periods": int(train_df["billing_period_id"].nunique()),
        "n_test_periods": int(test_df["billing_period_id"].nunique()),
        "features": FEATURES,
        "regression": {
            "hist_gradient_boosting_regressor": {"mae": reg_mae, "rmse": reg_rmse},
            "baseline_projection": {"mae": base_mae, "rmse": base_rmse},
        },
        "classification": {
            "accuracy": float(accuracy_score(test_df["target_exceeded"], clf_pred)),
            "precision": float(precision),
            "recall": float(recall),
            "f1": float(f1),
            "confusion_matrix": cm,
        },
        "limitations": (
            "Model trained on SYNTHETIC data. Metrics describe only this synthetic "
            "distribution. Do not present as real-world accuracy. "
            "Models are NOT retrained on user input; retraining is a separate process."
        ),
    }
    META_PATH.write_text(json.dumps(metadata, indent=2))

    print("Training complete.")
    print(json.dumps(metadata["regression"], indent=2))
    print(json.dumps(metadata["classification"], indent=2))


if __name__ == "__main__":
    main()