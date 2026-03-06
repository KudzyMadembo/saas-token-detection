# How To Run (Beginner)

This guide is copy-paste friendly for Windows PowerShell.

## 1) Prerequisites

- Python 3.11+ installed
- Git installed
- Run commands from project root:
  - `c:\Users\kudzy\OneDrive\Desktop\saas-token-detection`

If scripts are blocked in PowerShell:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 2) First-time setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r ingestion/requirements.txt -r simulator/requirements.txt -r visualization/requirements.txt
```

## 3) Quick run options

### Option A: AB Tasty analysis only

Default dataset:

```powershell
.\scripts\run_ab_tasty_analysis.ps1
```

Custom input:

```powershell
.\scripts\run_ab_tasty_analysis.ps1 -InputPath "data/raw_logs/AB_Tasty_Synthetic_30_Day_Logs.csv" -PipelineProfile tuned
```

### Option B: AB Tasty analysis + HTML visualization (recommended)

```powershell
.\scripts\run_ab_tasty_viz.ps1
```

Custom input/report path:

```powershell
.\scripts\run_ab_tasty_viz.ps1 -InputPath "data/raw_logs/AB_Tasty_Best_90_Day_Logs.csv" -PipelineProfile tuned -ReportOutput "data/reports/ab_tasty_report.html"
```

### Option C: Full simulator demo flow

```powershell
.\scripts\run_demo.ps1
```

Optional parameters:

```powershell
.\scripts\run_demo.ps1 -Tokens 10 -Seed 42
```

## 4) Generate a large enriched AB Tasty dataset

```powershell
python scripts/generate_best_ab_tasty_csv.py --rows 300000 --seed 77 --days 90 --output data/raw_logs/AB_Tasty_Best_90_Day_Logs.csv
```

Then run visualization on it:

```powershell
.\scripts\run_ab_tasty_viz.ps1 -InputPath "data/raw_logs/AB_Tasty_Best_90_Day_Logs.csv"
```

## 5) Open outputs

- Normalized data: `data/normalized_logs/api_logs_normalized.csv`
- Alerts: `data/alerts/alerts.jsonl` and `data/alerts/alerts.csv`
- Baselines: `data/baselines/token_baselines.json`
- HTML report: `data/reports/ab_tasty_report.html`

## 6) Interactive views

### Streamlit dashboard

```powershell
streamlit run visualization/app.py
```

### Notebook

Open:

- `notebooks/ab_tasty_visualization.ipynb`

## 7) Manual run (if you do not want scripts)

```powershell
python ingestion/normalize.py --input data/raw_logs/AB_Tasty_Synthetic_30_Day_Logs.csv
python detection/run_pipeline.py --profile tuned
python visualization/build_report.py
```

## 8) Troubleshooting

- **`python` not found**
  - Try `py` instead of `python`.
- **PowerShell blocks scripts**
  - Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- **File not found errors**
  - Make sure you are in repo root before running commands.
- **Dashboard won’t start**
  - Reinstall deps in active venv:
    - `pip install -r visualization/requirements.txt`
- **Unexpected results**
  - Re-run full visualization script to refresh normalized/baseline/alerts/report together.
