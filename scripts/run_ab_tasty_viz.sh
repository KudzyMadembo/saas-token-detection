#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

INPUT="${1:-data/raw_logs/AB_Tasty_Synthetic_30_Day_Logs.csv}"
PROFILE="${2:-tuned}"
REPORT_OUTPUT="${3:-data/reports/ab_tasty_report.html}"

echo "[1/3] Normalizing AB Tasty CSV..."
python ingestion/normalize.py --input "$INPUT"

echo "[2/3] Running detection pipeline..."
python detection/run_pipeline.py --profile "$PROFILE"

echo "[3/3] Building HTML visualization report..."
python visualization/build_report.py --output "$REPORT_OUTPUT"

echo "Visualization run complete."
echo "Outputs:"
echo "  data/normalized_logs/api_logs_normalized.csv"
echo "  data/alerts/alerts.jsonl"
echo "  $REPORT_OUTPUT"
echo
echo "Optional:"
echo "  streamlit run visualization/app.py"
echo "  Open notebooks/ab_tasty_visualization.ipynb"
