import json
from pathlib import Path
import joblib
import pandas as pd
import numpy as np

from config import FEATURES, MODELS_DIR

REG_PATH = MODELS_DIR / "hist_gradient_boosting_regressor.joblib"
CLF_PATH = MODELS_DIR / "hist_gradient_boosting_classifier.joblib"
META_PATH = MODELS_DIR / "model_metadata.json"


def models_available() -> bool:
    return REG_PATH.exists() and CLF_PATH.exists() and META_PATH.exists()


def load_models():
    if not models_available():
        return None, None, None
    return joblib.load(REG_PATH), joblib.load(CLF_PATH), json.loads(META_PATH.read_text())


def predict(reg, clf, features_dict: dict) -> tuple[float, float]:
    """Return (ml_predicted_final_units, probability_of_exceeding_target)."""
    X = pd.DataFrame([features_dict])[FEATURES]
    final_units = float(reg.predict(X)[0])
    # Guard against negative regression output
    final_units = max(0.0, final_units)
    proba = float(clf.predict_proba(X)[0, 1])
    return final_units, proba