#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

INPUT="${1:-data/raw_logs/AB_Tasty_Synthetic_30_Day_Logs.csv}"
PROFILE="${2:-tuned}"

echo "[1/2] Normalizing AB Tasty CSV..."
python ingestion/normalize.py --input "$INPUT"

echo "[2/2] Running detection pipeline..."
python detection/run_pipeline.py --profile "$PROFILE"

echo "AB Tasty analysis complete."
echo "Outputs:"
echo "  data/normalized_logs/api_logs_normalized.csv"
echo "  data/baselines/token_baselines.json"
echo "  data/alerts/alerts.jsonl"
echo "  data/alerts/alerts.csv"
