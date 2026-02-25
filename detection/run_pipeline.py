import json
import argparse
from pathlib import Path
import sys
from typing import Dict

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detection.baseline import (
    TokenKey,
    baselines_output_path,
    build_token_baselines,
    load_normalized_logs,
    normalized_input_path,
    project_root,
    write_token_baselines,
)
from detection.rules import detect_anomaly_windows
from detection.scoring import DEFAULT_SIGNAL_WEIGHTS, score_windows_to_alerts, severity_for_score
from detection.correlation import apply_correlation_rules
from detection.controls import apply_false_positive_controls


def alerts_dir() -> Path:
    return project_root() / "data" / "alerts"


def alerts_jsonl_path() -> Path:
    return alerts_dir() / "alerts.jsonl"


def alerts_csv_path() -> Path:
    return alerts_dir() / "alerts.csv"


def tenant_context_path() -> Path:
    return project_root() / "config" / "tenant_context.json"


def load_tenant_context(path: Path) -> Dict[str, Dict[str, object]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    tenants = payload.get("tenants", [])
    mapping: Dict[str, Dict[str, object]] = {}
    for tenant in tenants:
        tenant_id = tenant.get("tenant_id")
        if tenant_id:
            mapping[str(tenant_id)] = tenant
    return mapping


def profile_settings(profile_name: str) -> Dict[str, object]:
    if profile_name == "baseline":
        return {
            "endpoint_min_hits": 3,
            "volume_sigma": 3.0,
            "offhour_ratio_threshold": 0.05,
            "signal_weights": dict(DEFAULT_SIGNAL_WEIGHTS),
            "min_history_hours": 1,
            "tiny_request_threshold": 1,
        }

    tuned_weights = dict(DEFAULT_SIGNAL_WEIGHTS)
    tuned_weights["new_ip"] = 10
    tuned_weights["off_hour"] = 15
    return {
        "endpoint_min_hits": 4,
        "volume_sigma": 3.5,
        "offhour_ratio_threshold": 0.03,
        "signal_weights": tuned_weights,
        "min_history_hours": 2,
        "tiny_request_threshold": 2,
    }


def validate_tenant_isolation(frame: pd.DataFrame) -> None:
    token_tenant_counts = frame.groupby("token_id")["tenant_id"].nunique()
    collisions = token_tenant_counts[token_tenant_counts > 1]
    if not collisions.empty:
        examples = collisions.index.tolist()[:5]
        print(
            "WARNING: token_id appears in multiple tenants for these examples: "
            f"{examples}. Pipeline still scores by (tenant_id, token_id) to avoid context mixing."
        )


def write_alerts_jsonl(path: Path, alerts: list[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for alert in alerts:
            handle.write(json.dumps(alert))
            handle.write("\n")


def write_alerts_csv(path: Path, alerts: list[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not alerts:
        pd.DataFrame(
            columns=[
                "tenant_id",
                "token_id",
                "hour_bucket",
                "severity",
                "risk_score",
                "final_risk_score",
                "signal_count",
                "signals",
                "why",
                "correlated_signals",
                "correlation_reason",
                "suppressed",
                "suppression_reason",
            ]
        ).to_csv(path, index=False)
        return

    flattened = []
    for alert in alerts:
        flattened.append(
            {
                "tenant_id": alert["tenant_id"],
                "token_id": alert["token_id"],
                "hour_bucket": alert["hour_bucket"],
                "severity": alert["severity"],
                "risk_score": alert["risk_score"],
                "final_risk_score": alert.get("final_risk_score", alert["risk_score"]),
                "signal_count": alert["signal_count"],
                "signals": "|".join(alert["signals"]),
                "why": " | ".join(alert["why"]),
                "correlated_signals": "|".join(alert.get("correlated_signals", [])),
                "correlation_reason": alert.get("correlation_reason", ""),
                "suppressed": alert.get("suppressed", False),
                "suppression_reason": alert.get("suppression_reason", ""),
                "evidence": json.dumps(alert["evidence"]),
                "baseline_snapshot": json.dumps(alert["baseline_snapshot"]),
                "tenant_context": json.dumps(alert.get("tenant_context", {})),
            }
        )

    pd.DataFrame(flattened).to_csv(path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run baseline/anomaly detection pipeline.")
    parser.add_argument(
        "--profile",
        choices=["baseline", "tuned"],
        default="tuned",
        help="Detection profile used for thresholds and scoring.",
    )
    parser.add_argument(
        "--alerts-jsonl",
        default=str(alerts_jsonl_path()),
        help="Path for JSONL alert output.",
    )
    parser.add_argument(
        "--alerts-csv",
        default=str(alerts_csv_path()),
        help="Path for CSV alert output.",
    )
    parser.add_argument(
        "--baselines-output",
        default=str(baselines_output_path()),
        help="Path for baseline JSON output.",
    )
    parser.add_argument(
        "--context-config",
        default=str(tenant_context_path()),
        help="Path to tenant context JSON file.",
    )
    args = parser.parse_args()

    source = normalized_input_path()
    baselines_path = Path(args.baselines_output)
    jsonl_path = Path(args.alerts_jsonl)
    csv_path = Path(args.alerts_csv)
    context_path = Path(args.context_config)
    settings = profile_settings(args.profile)

    frame = load_normalized_logs(source)
    validate_tenant_isolation(frame)
    tenant_context = load_tenant_context(context_path)
    baselines: Dict[TokenKey, Dict[str, object]] = build_token_baselines(frame)
    write_token_baselines(baselines_path, baselines)

    windows = detect_anomaly_windows(
        frame=frame,
        baselines=baselines,
        endpoint_min_hits=int(settings["endpoint_min_hits"]),
        volume_sigma=float(settings["volume_sigma"]),
        offhour_ratio_threshold=float(settings["offhour_ratio_threshold"]),
    )
    scored_alerts = score_windows_to_alerts(
        windows=windows,
        baselines=baselines,
        tenant_context=tenant_context,
        signal_weights=settings["signal_weights"],
    )
    correlated_alerts = apply_correlation_rules(scored_alerts)
    alerts = apply_false_positive_controls(
        correlated_alerts,
        baselines=baselines,
        min_history_hours=int(settings["min_history_hours"]),
        tiny_request_threshold=int(settings["tiny_request_threshold"]),
    )
    for alert in alerts:
        alert["severity"] = severity_for_score(int(alert.get("final_risk_score", 0)))

    write_alerts_jsonl(jsonl_path, alerts)
    write_alerts_csv(csv_path, alerts)

    unsuppressed = [alert for alert in alerts if not bool(alert.get("suppressed", False))]
    severity_counts = pd.DataFrame(unsuppressed)["severity"].value_counts().to_dict() if unsuppressed else {}
    print(f"Input rows: {len(frame)}")
    print(f"Profile: {args.profile}")
    print(f"Baselines generated: {len(baselines)} -> {baselines_path}")
    print(f"Correlated anomaly windows: {len(windows)}")
    print(f"Alerts generated: {len(alerts)} -> {jsonl_path} and {csv_path}")
    print(f"Unsuppressed alerts: {len(unsuppressed)}")
    print(f"Unsuppressed alerts by severity: {severity_counts}")


if __name__ == "__main__":
    main()
