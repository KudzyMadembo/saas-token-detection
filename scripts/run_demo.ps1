param(
  [int]$Tokens = 10,
  [int]$Seed = 42
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "[1/6] Generating synthetic logs..."
python simulator/log_generator.py --tokens $Tokens --seed $Seed

Write-Host "[2/6] Normalizing logs..."
python ingestion/normalize.py

Write-Host "[3/6] Running baseline profile..."
python detection/run_pipeline.py `
  --profile baseline `
  --alerts-jsonl data/alerts/alerts_baseline.jsonl `
  --alerts-csv data/alerts/alerts_baseline.csv `
  --baselines-output data/baselines/token_baselines_baseline.json

Write-Host "[4/6] Running tuned profile..."
python detection/run_pipeline.py `
  --profile tuned `
  --alerts-jsonl data/alerts/alerts.jsonl `
  --alerts-csv data/alerts/alerts.csv `
  --baselines-output data/baselines/token_baselines.json

Write-Host "[5/6] Evaluating baseline and tuned outputs..."
python evaluation/evaluate.py `
  --alerts data/alerts/alerts_baseline.jsonl `
  --output data/eval/metrics_baseline.json
python evaluation/evaluate.py `
  --alerts data/alerts/alerts.jsonl `
  --output data/eval/metrics.json

Write-Host "[6/6] Demo run complete."
Write-Host "Outputs:"
Write-Host "  data/normalized_logs/api_logs_normalized.csv"
Write-Host "  data/baselines/token_baselines.json"
Write-Host "  data/alerts/alerts.jsonl"
Write-Host "  data/alerts/alerts.csv"
Write-Host "  data/eval/metrics.json"
