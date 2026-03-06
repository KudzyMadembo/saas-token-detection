param(
  [string]$InputPath = "data/raw_logs/AB_Tasty_Synthetic_30_Day_Logs.csv",
  [string]$PipelineProfile = "tuned",
  [string]$ReportOutput = "data/reports/ab_tasty_report.html"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "[1/3] Normalizing AB Tasty CSV..."
python ingestion/normalize.py --input $InputPath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[2/3] Running detection pipeline..."
python detection/run_pipeline.py --profile $PipelineProfile
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[3/3] Building HTML visualization report..."
python visualization/build_report.py --output $ReportOutput
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Visualization run complete."
Write-Host "Outputs:"
Write-Host "  data/normalized_logs/api_logs_normalized.csv"
Write-Host "  data/alerts/alerts.jsonl"
Write-Host "  $ReportOutput"
Write-Host ""
Write-Host "Optional:"
Write-Host "  streamlit run visualization/app.py"
Write-Host "  Open notebooks/ab_tasty_visualization.ipynb"
