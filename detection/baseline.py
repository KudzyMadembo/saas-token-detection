import json
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

REQUIRED_COLUMNS = [
    "event_time",
    "tenant_id",
    "token_id",
    "endpoint",
    "http_method",
    "status_code",
    "ip_address",
    "geo_country",
    "auth_method",
]
OPTIONAL_COLUMNS = ["is_injected_anomaly", "anomaly_type"]

TokenKey = Tuple[str, str]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def normalized_input_path() -> Path:
    return project_root() / "data" / "normalized_logs" / "api_logs_normalized.csv"


def baselines_output_path() -> Path:
    return project_root() / "data" / "baselines" / "token_baselines.json"


def load_normalized_logs(source: Path) -> pd.DataFrame:
    if not source.exists():
        raise FileNotFoundError(f"Normalized dataset not found: {source}")

    frame = pd.read_csv(source)
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    selected_columns = REQUIRED_COLUMNS + [
        column for column in OPTIONAL_COLUMNS if column in frame.columns
    ]
    normalized = frame[selected_columns].copy()
    normalized["event_time"] = pd.to_datetime(normalized["event_time"], utc=True, errors="coerce")
    normalized = normalized.dropna(subset=["event_time"])
    if "is_injected_anomaly" in normalized.columns:
        normalized["is_injected_anomaly"] = normalized["is_injected_anomaly"].fillna(False).astype(bool)
    if "anomaly_type" in normalized.columns:
        normalized["anomaly_type"] = normalized["anomaly_type"].fillna("none").astype(str)
    normalized["hour_bucket"] = normalized["event_time"].dt.floor("h")
    normalized = normalized.sort_values("event_time").reset_index(drop=True)
    return normalized


def build_token_baselines(frame: pd.DataFrame, top_n_endpoints: int = 5) -> Dict[TokenKey, Dict[str, object]]:
    baselines: Dict[TokenKey, Dict[str, object]] = {}

    grouped = frame.groupby(["tenant_id", "token_id"], sort=True)
    for (tenant_id, token_id), group in grouped:
        hourly_counts = group.groupby("hour_bucket").size().astype(float)
        hour_hist = (
            group["event_time"]
            .dt.hour.value_counts()
            .reindex(range(24), fill_value=0)
            .sort_index()
            .to_dict()
        )
        endpoint_counts = group["endpoint"].value_counts()
        auth_method_counts = group["auth_method"].astype(str).value_counts()
        dominant_auth_method = str(auth_method_counts.index[0]) if not auth_method_counts.empty else "unknown"

        baselines[(tenant_id, token_id)] = {
            "tenant_id": tenant_id,
            "token_id": token_id,
            "volume_mean": round(float(hourly_counts.mean()), 4),
            "volume_std": round(float(hourly_counts.std(ddof=0)), 4),
            "volume_p95": round(float(hourly_counts.quantile(0.95)), 4),
            "known_geos": sorted(group["geo_country"].astype(str).unique().tolist()),
            "known_ips": sorted(group["ip_address"].astype(str).unique().tolist()),
            "known_endpoints": sorted(group["endpoint"].astype(str).unique().tolist()),
            "known_auth_methods": sorted(group["auth_method"].astype(str).unique().tolist()),
            "auth_method_distribution": auth_method_counts.to_dict(),
            "dominant_auth_method": dominant_auth_method,
            "top_endpoints": endpoint_counts.head(top_n_endpoints).to_dict(),
            "hour_histogram": {str(hour): int(count) for hour, count in hour_hist.items()},
            "total_events": int(len(group)),
            "hour_buckets_seen": int(hourly_counts.shape[0]),
        }

    return baselines


def write_token_baselines(path: Path, baselines: Dict[TokenKey, Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized: List[Dict[str, object]] = [baselines[key] for key in sorted(baselines.keys())]
    with path.open("w", encoding="utf-8") as handle:
        json.dump(serialized, handle, indent=2)
