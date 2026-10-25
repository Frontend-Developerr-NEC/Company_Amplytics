# Amplytics

Amplytics is a household electricity monitoring and planning prototype built with Python. It helps households record daily usage, compare consumption to a billing-period target, estimate tariff charges, and view both baseline projections and optional machine-learning forecasts.

The project is designed as a local, self-contained prototype for analysing household electricity behaviour without depending on live IoT devices or external cloud services.

## Overview

Amplytics provides a full prototype workflow:

- Register one or more households
- Create monthly or custom billing periods
- Track daily electricity consumption against a target
- Review target-pace calculations and projected end-of-period totals
- Estimate electricity charges using a Tamil Nadu domestic tariff model
- Import daily usage from CSV, JSON, or Excel files
- View rule-based alerts and optional ML-based exceedance warnings
- Train and use a baseline + ML prediction layer when model artifacts are present

## Key features

### Household and billing management
- Create households with display name, email, and household size
- Create billing periods with a target in kWh
- Maintain a history of completed and active billing periods
- Track previous-period consumption for context and trend analysis

### Consumption tracking
- Record daily electricity usage by date
- Support manual entry and imported data
- Differentiate measured vs estimated vs predicted records
- Keep target-progress calculations separate from ML estimations

### Tariff and target calculations
- Compute daily pace, remaining allowance, percent consumed, and excess usage
- Estimate projected final consumption from the current average daily usage
- Calculate electricity charge using the Tamil Nadu domestic slab schedule
- Expose both summary and charge data through the FastAPI API

### Machine learning layer
- Train a HistGradientBoostingRegressor for projected final usage
- Train a HistGradientBoostingClassifier for exceedance probability
- Keep model metadata and metrics in JSON for transparency
- Use model predictions only as estimates; models are not retrained automatically from user input

### Dashboard and API
- Web application with FastAPI and Jinja2 templates
- A REST API for summary and prediction data
- Static assets and browser-based interface under web/

## Project status and limitations

This project is intentionally a prototype and is not production-grade infrastructure.

Important notes:

- The provided datasets and model metrics are synthetic unless you explicitly replace them with real-world data.
- The project does not connect to real meters or sensor hardware.
- Model training is a separate step and is not triggered automatically when records are added.
- ML outputs are estimates, not assured future bills or official predictions.
- Appliance estimates are informational only and are not treated as meter-based consumption.

## Technology stack

### Core application
- Python 3.11+
- FastAPI
- Uvicorn
- Jinja2
- Python-multipart
- SQLite
- Starlette session middleware

### Data and analysis
- pandas
- NumPy
- openpyxl
- joblib
- scikit-learn

### Frontend
- HTML / Jinja templates
- CSS
- JavaScript
- Chart.js
- Tailwind CSS (CDN)

### Testing
- pytest

## Repository structure

```text
Amplytics/
├── README.md                   # Project documentation
├── TechStacks.md               # Technology summary
├── requirements.txt            # Python dependencies
├── alerts.py                   # Rule-based and ML alert logic
├── billing_periods.py          # Billing period helpers
├── calculations.py             # Core target, tariff, and summary logic
├── config.py                   # Global configuration and paths
├── db.py                       # SQLite database schema and access logic
├── features.py                 # Feature construction for ML snapshots
├── model_loader.py             # Model loading and prediction helper
├── validation.py               # Input validation rules
├── data/
│   ├── amplitics.db           # SQLite database
│   ├── processed/
│   │   └── ml_training_data.csv
│   └── raw/
│       ├── daily_consumption.csv
│       ├── dataset_metadata.json
│       ├── household_billing.csv
│       └── uci_load_diagrams.zip
├── models/
│   ├── hist_gradient_boosting_regressor.joblib
│   ├── hist_gradient_boosting_classifier.joblib
│   └── model_metadata.json
├── MD/
│   ├── Dashboard_Baseline_projection.md
│   ├── Dashboard_ML_Prediction.md
│   └── Q&A.md
├── scripts/
│   ├── build_training_data.py
│   ├── convert_uci_load_diagrams.py
│   ├── generate_synthetic_data.py
│   └── train_models.py
├── tests/
│   ├── test_billing_periods.py
│   ├── test_calculations.py
│   ├── test_imports.py
│   └── test_validation.py
├── Training_Datasets/
│   ├── CSV/
│   ├── Excel/
│   └── JSON/
└── web/
    ├── __init__.py
    ├── deps.py
    ├── imports.py
    ├── main.py                 # FastAPI application entry point
    ├── routers/
    │   ├── api.py
    │   └── pages.py
    ├── static/
    └── templates/
```

## Local setup

### 1) Clone and enter the project

```bash
cd Amplytics
```

### 2) Create a virtual environment

```bash
python -m venv .venv
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

### 3) Install dependencies

```bash
pip install -r requirements.txt
```

### 4) Prepare or regenerate data

If you want to run the project with the included synthetic data, you can skip this step if the data files are already present. Otherwise, generate the sample dataset:

```bash
python scripts/generate_synthetic_data.py
```

If you also want to rebuild the ML training artifacts:

```bash
python scripts/build_training_data.py
python -m scripts.train_models
```

The repository also includes a public dataset conversion workflow under scripts/convert_uci_load_diagrams.py for a larger UCI-style electricity dataset flow.

## Running the application

The active web app is served through the FastAPI project under web/main.py.

```bash
uvicorn web.main:app --reload --port 8000
```

Then open:

```text
http://127.0.0.1:8000
```

The API is exposed at:

- /health
- /api/summary
- /api/predict

## Running tests

```bash
pytest -q
```

This repository contains tests for calculations, validation, imports, and billing period logic.

## Architecture overview

### Request flow

1. A household is created and stored in SQLite.
2. A billing period is created with a target and optional previous-period reference.
3. Daily usage rows are inserted manually or imported from a file.
4. The calculation engine computes target pace, remaining allowance, projected usage, and tariff estimates.
5. If model artifacts exist, the app loads them and compares baseline predictions with ML predictions.
6. Alerts are generated from the rule-based engine and, when available, the classifier probability.

### Main modules

- web/main.py: modern FastAPI application entry point
- db.py: database logic and persistence
- calculations.py: all consumption and tariff calculations
- alerts.py: alert and risk-generation logic
- scripts/train_models.py: model training workflow
- model_loader.py: loads saved joblib models and produces predictions

## Data model and training notes

The project includes a data pipeline for feature generation:

- raw consumption and billing data live in data/raw/
- processed snapshots are built for model training in data/processed/
- model metadata is stored in models/model_metadata.json

The ML pipeline uses features such as:

- target_units
- period_days
- elapsed_days
- days_remaining
- cumulative_units
- average_daily_units
- previous_period_units

The training workflow intentionally isolates groups by billing period to avoid data leakage across related snapshots.

## Important developer guidance

- Do not treat model metrics as real-world performance unless the input data is a trusted real dataset.
- Do not retrain models during normal app usage; use the dedicated training script.
- Keep baseline and ML outputs visually distinct so users understand they are separate estimates.
- When extending the project, preserve the separation between measured, estimated, and predicted consumption records.

## License

This repository does not currently include a project license file. If you plan to distribute or publish the project, add a license before doing so.

## Summary

Amplytics combines household energy tracking, billing-period planning, data imports, target calculations, and machine-learning forecasting into a single local prototype. It is a practical demonstration project for analysing consumption behaviour and comparing simple baseline projections with model-based estimates.
