param(
  [string]$InputPath = "data/raw_logs/AB_Tasty_Synthetic_30_Day_Logs.csv",
  [string]$PipelineProfile = "tuned"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "[1/2] Normalizing AB Tasty CSV..."
python ingestion/normalize.py --input $InputPath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[2/2] Running detection pipeline..."
python detection/run_pipeline.py --profile $PipelineProfile
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "AB Tasty analysis complete."
Write-Host "Outputs:"
Write-Host "  data/normalized_logs/api_logs_normalized.csv"
Write-Host "  data/baselines/token_baselines.json"
Write-Host "  data/alerts/alerts.jsonl"
Write-Host "  data/alerts/alerts.csv"
