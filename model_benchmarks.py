"""Evaluate the supported regression and classification models on a grouped holdout."""
import numpy as np
import pandas as pd
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from config import FEATURES, PROCESSED_DIR


def _pipeline(estimator, scale: bool = False) -> Pipeline:
    steps = [("imputer", SimpleImputer(strategy="median"))]
    if scale:
        steps.append(("scaler", StandardScaler()))
    steps.append(("model", estimator))
    return Pipeline(steps)


def benchmark_models() -> dict:
    """Return comparable holdout metrics for all four models, grouped by billing period."""
    data_path = PROCESSED_DIR / "ml_training_data.csv"
    data = pd.read_csv(data_path)
    if data.empty:
        raise ValueError(f"{data_path} is empty; build the training data before benchmarking.")

    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
    train_indices, test_indices = next(
        splitter.split(data, groups=data["billing_period_id"])
    )
    train, test = data.iloc[train_indices], data.iloc[test_indices]
    x_train, x_test = train[FEATURES], test[FEATURES]
    regression_target = "actual_final_units"
    classification_target = "target_exceeded"

    regressors = [
        (
            "HistGradientBoostingRegressor",
            _pipeline(HistGradientBoostingRegressor(random_state=42)),
        ),
        ("Linear Regression", _pipeline(LinearRegression(), scale=True)),
    ]
    regression_results = []
    for name, model in regressors:
        model.fit(x_train, train[regression_target])
        predictions = model.predict(x_test)
        regression_results.append({
            "name": name,
            "mae": float(mean_absolute_error(test[regression_target], predictions)),
            "rmse": float(np.sqrt(mean_squared_error(test[regression_target], predictions))),
            "r2": float(r2_score(test[regression_target], predictions)),
        })

    classifiers = [
        (
            "HistGradientBoostingClassifier",
            _pipeline(HistGradientBoostingClassifier(random_state=42)),
        ),
        (
            "Logistic Regression classifier",
            _pipeline(
                LogisticRegression(max_iter=1000, class_weight="balanced"),
                scale=True,
            ),
        ),
    ]
    classification_results = []
    for name, model in classifiers:
        model.fit(x_train, train[classification_target])
        predictions = model.predict(x_test)
        classification_results.append({
            "name": name,
            "accuracy": float(accuracy_score(test[classification_target], predictions)),
            "precision": float(
                precision_score(test[classification_target], predictions, zero_division=0)
            ),
            "recall": float(
                recall_score(test[classification_target], predictions, zero_division=0)
            ),
            "f1": float(f1_score(test[classification_target], predictions, zero_division=0)),
        })

    return {
        "data_source": "synthetic",
        "n_test_rows": len(test),
        "regression": regression_results,
        "regression_recommendation": min(regression_results, key=lambda result: result["mae"]),
        "classification": classification_results,
        "classification_recommendation": max(
            classification_results, key=lambda result: result["f1"]
        ),
    }
