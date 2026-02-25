import argparse
import json
from pathlib import Path
from typing import Dict, Set, Tuple

import pandas as pd


WindowKey = Tuple[str, str, str]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_normalized_path() -> Path:
    return project_root() / "data" / "normalized_logs" / "api_logs_normalized.csv"


def load_ground_truth_windows(path: Path) -> Set[WindowKey]:
    frame = pd.read_csv(path)
    required = {"tenant_id", "token_id", "event_time", "is_injected_anomaly"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            f"Evaluation requires labeled normalized logs with columns {sorted(required)}. Missing: {sorted(missing)}"
        )

    frame["event_time"] = pd.to_datetime(frame["event_time"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["event_time"])
    frame["hour_bucket"] = frame["event_time"].dt.floor("h").dt.strftime("%Y-%m-%dT%H:00:00+00:00")
    frame["is_injected_anomaly"] = frame["is_injected_anomaly"].fillna(False).astype(bool)
    positives = frame[frame["is_injected_anomaly"]]
    return set(
        zip(
            positives["tenant_id"].astype(str),
            positives["token_id"].astype(str),
            positives["hour_bucket"].astype(str),
        )
    )


def load_predicted_windows(path: Path, min_score: int) -> Set[WindowKey]:
    predicted: Set[WindowKey] = set()
    if not path.exists():
        return predicted

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            suppressed = bool(payload.get("suppressed", False))
            score = int(payload.get("final_risk_score", payload.get("risk_score", 0)))
            if suppressed or score < min_score:
                continue
            predicted.add(
                (
                    str(payload.get("tenant_id", "")),
                    str(payload.get("token_id", "")),
                    str(payload.get("hour_bucket", "")),
                )
            )
    return predicted


def evaluate(ground_truth: Set[WindowKey], predicted: Set[WindowKey]) -> Dict[str, object]:
    tp = len(ground_truth & predicted)
    fp = len(predicted - ground_truth)
    fn = len(ground_truth - predicted)
    precision = (tp / (tp + fp)) if (tp + fp) else 0.0
    recall = (tp / (tp + fn)) if (tp + fn) else 0.0
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "ground_truth_positive_windows": len(ground_truth),
        "predicted_positive_windows": len(predicted),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate alert quality against injected anomalies.")
    parser.add_argument(
        "--normalized",
        default=str(default_normalized_path()),
        help="Normalized CSV with injected anomaly labels.",
    )
    parser.add_argument(
        "--alerts",
        default=str(project_root() / "data" / "alerts" / "alerts.jsonl"),
        help="Alert JSONL file.",
    )
    parser.add_argument(
        "--output",
        default=str(project_root() / "data" / "eval" / "metrics.json"),
        help="Output metrics path.",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=40,
        help="Minimum final risk score to count as a positive prediction.",
    )
    args = parser.parse_args()

    ground_truth = load_ground_truth_windows(Path(args.normalized))
    predicted = load_predicted_windows(Path(args.alerts), min_score=args.min_score)
    metrics = evaluate(ground_truth, predicted)
    metrics["min_score_threshold"] = int(args.min_score)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)

    print(f"Wrote metrics to {output_path}")
    print(metrics)


if __name__ == "__main__":
    main()
