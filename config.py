from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = BASE_DIR / "models"
DB_PATH = DATA_DIR / "amplitics.db"

for d in (DATA_DIR, RAW_DIR, PROCESSED_DIR, MODELS_DIR):
    d.mkdir(parents=True, exist_ok=True)

DATA_TYPES = ("measured", "estimated")
INPUT_METHODS = ("manual", "import")

# Single source of truth for ML feature order.
# Preprocessing pipelines are fitted against exactly this list.
FEATURES = [
    "target_units",
    "period_days",
    "elapsed_days",
    "days_remaining",
    "cumulative_units",
    "average_daily_units",
    "previous_period_units",
]

# Threshold used to convert classifier probability into a "warning" flag.
# This is a presentation decision, not a model parameter.
CLASSIFIER_WARNING_THRESHOLD = 0.70