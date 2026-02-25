#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/6] Generating synthetic logs..."
python simulator/log_generator.py --tokens 10 --seed 42

echo "[2/6] Normalizing logs..."
python ingestion/normalize.py

echo "[3/6] Running baseline profile..."
python detection/run_pipeline.py \
  --profile baseline \
  --alerts-jsonl data/alerts/alerts_baseline.jsonl \
  --alerts-csv data/alerts/alerts_baseline.csv \
  --baselines-output data/baselines/token_baselines_baseline.json

echo "[4/6] Running tuned profile..."
python detection/run_pipeline.py \
  --profile tuned \
  --alerts-jsonl data/alerts/alerts.jsonl \
  --alerts-csv data/alerts/alerts.csv \
  --baselines-output data/baselines/token_baselines.json

echo "[5/6] Evaluating baseline and tuned outputs..."
python evaluation/evaluate.py \
  --alerts data/alerts/alerts_baseline.jsonl \
  --output data/eval/metrics_baseline.json
python evaluation/evaluate.py \
  --alerts data/alerts/alerts.jsonl \
  --output data/eval/metrics.json

echo "[6/6] Demo run complete."
echo "Outputs:"
echo "  data/normalized_logs/api_logs_normalized.csv"
echo "  data/baselines/token_baselines.json"
echo "  data/alerts/alerts.jsonl"
echo "  data/alerts/alerts.csv"
echo "  data/eval/metrics.json"
