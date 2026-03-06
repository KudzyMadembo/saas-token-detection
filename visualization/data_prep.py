from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from detection.baseline import build_token_baselines
from detection.rules import detect_anomaly_windows
from detection.run_pipeline import profile_settings


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_normalized_path() -> Path:
    return project_root() / "data" / "normalized_logs" / "api_logs_normalized.csv"


def default_alerts_path() -> Path:
    return project_root() / "data" / "alerts" / "alerts.jsonl"


def report_output_path() -> Path:
    return project_root() / "data" / "reports" / "ab_tasty_report.html"


def _window_key_series(frame: pd.DataFrame, timestamp_col: str) -> pd.Series:
    hour_bucket = pd.to_datetime(frame[timestamp_col], utc=True, errors="coerce").dt.floor("h")
    return (
        frame["tenant_id"].astype(str)
        + "|"
        + frame["token_id"].astype(str)
        + "|"
        + hour_bucket.dt.strftime("%Y-%m-%dT%H:00:00+00:00")
    )


def load_normalized_logs(path: Optional[Path] = None) -> pd.DataFrame:
    source = path or default_normalized_path()
    frame = pd.read_csv(source)
    frame["event_time"] = pd.to_datetime(frame["event_time"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["event_time"]).copy()
    frame["tenant_id"] = frame["tenant_id"].astype(str)
    frame["token_id"] = frame["token_id"].astype(str)
    frame["hour_bucket"] = frame["event_time"].dt.floor("h")
    frame["date"] = frame["event_time"].dt.date.astype(str)
    frame["window_key"] = _window_key_series(frame, "event_time")
    return frame


def load_alerts(path: Optional[Path] = None) -> pd.DataFrame:
    source = path or default_alerts_path()
    if not source.exists():
        return pd.DataFrame(
            columns=[
                "tenant_id",
                "token_id",
                "hour_bucket",
                "severity",
                "signals",
                "final_risk_score",
                "suppressed",
                "window_key",
            ]
        )

    rows: List[Dict[str, object]] = []
    with source.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            rows.append(payload)

    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows)
    frame["tenant_id"] = frame["tenant_id"].astype(str)
    frame["token_id"] = frame["token_id"].astype(str)
    frame["hour_bucket"] = pd.to_datetime(frame["hour_bucket"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["hour_bucket"]).copy()
    frame["suppressed"] = frame.get("suppressed", False).fillna(False).astype(bool)
    frame["severity"] = frame.get("severity", "low").fillna("low").astype(str)
    frame["final_risk_score"] = (
        frame.get("final_risk_score", frame.get("risk_score", 0)).fillna(0).astype(int)
    )
    frame["signals"] = frame.get("signals", [[] for _ in range(len(frame))])
    frame["window_key"] = (
        frame["tenant_id"]
        + "|"
        + frame["token_id"]
        + "|"
        + frame["hour_bucket"].dt.strftime("%Y-%m-%dT%H:00:00+00:00")
    )
    frame["date"] = frame["hour_bucket"].dt.date.astype(str)
    return frame


def derive_pipeline_anomalies(
    alerts_frame: pd.DataFrame,
    min_score: int = 40,
    include_low: bool = True,
) -> pd.DataFrame:
    if alerts_frame.empty:
        return alerts_frame.copy()

    filtered = alerts_frame[(~alerts_frame["suppressed"]) & (alerts_frame["final_risk_score"] >= min_score)].copy()
    if not include_low:
        filtered = filtered[filtered["severity"].isin(["medium", "high"])].copy()
    filtered["anomaly_source"] = "pipeline"
    return filtered


def derive_raw_rule_anomalies(normalized_frame: pd.DataFrame) -> pd.DataFrame:
    if normalized_frame.empty:
        return pd.DataFrame(columns=["tenant_id", "token_id", "hour_bucket", "signals", "signal_count", "window_key"])

    tuned = profile_settings("tuned")
    baselines = build_token_baselines(normalized_frame)
    windows = detect_anomaly_windows(
        frame=normalized_frame,
        baselines=baselines,
        endpoint_min_hits=int(tuned["endpoint_min_hits"]),
        volume_sigma=float(tuned["volume_sigma"]),
        offhour_ratio_threshold=float(tuned["offhour_ratio_threshold"]),
    )
    raw_frame = pd.DataFrame(windows)
    if raw_frame.empty:
        return raw_frame
    raw_frame["tenant_id"] = raw_frame["tenant_id"].astype(str)
    raw_frame["token_id"] = raw_frame["token_id"].astype(str)
    raw_frame["hour_bucket"] = pd.to_datetime(raw_frame["hour_bucket"], utc=True, errors="coerce")
    raw_frame = raw_frame.dropna(subset=["hour_bucket"]).copy()
    raw_frame["signal_count"] = raw_frame["signals"].apply(lambda values: len(values) if isinstance(values, list) else 0)
    raw_frame["window_key"] = (
        raw_frame["tenant_id"]
        + "|"
        + raw_frame["token_id"]
        + "|"
        + raw_frame["hour_bucket"].dt.strftime("%Y-%m-%dT%H:00:00+00:00")
    )
    raw_frame["date"] = raw_frame["hour_bucket"].dt.date.astype(str)
    raw_frame["anomaly_source"] = "raw_rule"
    return raw_frame


def build_event_labels(
    normalized_frame: pd.DataFrame,
    pipeline_frame: pd.DataFrame,
    raw_rule_frame: pd.DataFrame,
) -> pd.DataFrame:
    labeled = normalized_frame.copy()
    pipeline_keys = set(pipeline_frame["window_key"].tolist()) if not pipeline_frame.empty else set()
    raw_keys = set(raw_rule_frame["window_key"].tolist()) if not raw_rule_frame.empty else set()
    labeled["is_pipeline_anomaly"] = labeled["window_key"].isin(pipeline_keys)
    labeled["is_raw_rule_anomaly"] = labeled["window_key"].isin(raw_keys)

    severity_order = {"low": 1, "medium": 2, "high": 3}
    if pipeline_frame.empty:
        pipeline_severity_map: Dict[str, str] = {}
    else:
        per_window = (
            pipeline_frame[["window_key", "severity"]]
            .dropna()
            .copy()
            .assign(_score=lambda frame: frame["severity"].map(severity_order).fillna(0))
            .sort_values(["window_key", "_score"], ascending=[True, False])
            .drop_duplicates(subset=["window_key"], keep="first")
        )
        pipeline_severity_map = dict(zip(per_window["window_key"], per_window["severity"]))

    def resolve_event_severity(window_key: str) -> str:
        if window_key in pipeline_severity_map:
            return pipeline_severity_map[window_key]
        if window_key in raw_keys:
            return "low"
        return "none"

    labeled["event_severity"] = labeled["window_key"].astype(str).apply(resolve_event_severity)
    labeled["is_any_anomaly"] = labeled["event_severity"] != "none"
    return labeled


def aggregate_daily_counts(labeled_events: pd.DataFrame) -> pd.DataFrame:
    if labeled_events.empty:
        return pd.DataFrame(
            columns=["date", "low_logs", "medium_logs", "high_logs", "total_severity_logs", "high_share"]
        )
    severity_only = labeled_events[labeled_events["event_severity"].isin(["low", "medium", "high"])].copy()
    if severity_only.empty:
        return pd.DataFrame(
            columns=["date", "low_logs", "medium_logs", "high_logs", "total_severity_logs", "high_share"]
        )
    grouped = (
        severity_only.groupby(["date", "event_severity"])
        .size()
        .unstack(fill_value=0)
        .rename_axis(None, axis=1)
        .reset_index()
    )
    for level in ["low", "medium", "high"]:
        if level not in grouped.columns:
            grouped[level] = 0
    grouped = grouped.rename(columns={"low": "low_logs", "medium": "medium_logs", "high": "high_logs"})
    grouped["total_severity_logs"] = grouped["low_logs"] + grouped["medium_logs"] + grouped["high_logs"]
    grouped["high_share"] = (
        (grouped["high_logs"] / grouped["total_severity_logs"]).fillna(0.0).round(4)
    )
    return grouped.sort_values("date").reset_index(drop=True)


def top_counts(frame: pd.DataFrame, column: str, limit: int = 10, name: str = "count") -> pd.DataFrame:
    if frame.empty or column not in frame.columns:
        return pd.DataFrame(columns=[column, name])
    return (
        frame[column]
        .astype(str)
        .value_counts()
        .head(limit)
        .rename_axis(column)
        .reset_index(name=name)
    )


def severity_comparison(frame: pd.DataFrame) -> pd.DataFrame:
    base = pd.DataFrame({"severity": ["high", "medium", "low"]})
    if frame.empty:
        base["windows"] = 0
        base["percentage"] = 0.0
        base["score_min"] = 0
        base["score_max"] = 0
        base["score_avg"] = 0.0
        return base

    grouped = (
        frame.groupby("severity", as_index=False)
        .agg(
            windows=("severity", "size"),
            score_min=("final_risk_score", "min"),
            score_max=("final_risk_score", "max"),
            score_avg=("final_risk_score", "mean"),
        )
    )
    total = int(grouped["windows"].sum()) or 1
    grouped["percentage"] = (grouped["windows"] / total * 100).round(2)
    grouped["score_avg"] = grouped["score_avg"].round(2)
    merged = base.merge(grouped, on="severity", how="left").fillna(0)
    merged["windows"] = merged["windows"].astype(int)
    merged["score_min"] = merged["score_min"].astype(int)
    merged["score_max"] = merged["score_max"].astype(int)
    return merged


def sample_windows_by_severity(frame: pd.DataFrame, per_severity: int = 5) -> pd.DataFrame:
    columns = ["hour_bucket", "tenant_id", "token_id", "severity", "final_risk_score", "signals"]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    samples: List[pd.DataFrame] = []
    for severity in ["high", "medium", "low"]:
        slice_frame = frame[frame["severity"] == severity].sort_values("hour_bucket", ascending=False).head(per_severity)
        if not slice_frame.empty:
            samples.append(slice_frame[columns])
    if not samples:
        return pd.DataFrame(columns=columns)
    return pd.concat(samples, ignore_index=True)


def prepare_visualization_datasets(
    normalized_path: Optional[Path] = None,
    alerts_path: Optional[Path] = None,
    min_pipeline_score: int = 40,
    include_low_severity: bool = True,
) -> Dict[str, object]:
    normalized = load_normalized_logs(normalized_path)
    alerts = load_alerts(alerts_path)
    pipeline_anomalies = derive_pipeline_anomalies(
        alerts, min_score=min_pipeline_score, include_low=include_low_severity
    )
    raw_rule_anomalies = derive_raw_rule_anomalies(normalized)
    labeled_events = build_event_labels(normalized, pipeline_anomalies, raw_rule_anomalies)
    daily_counts = aggregate_daily_counts(labeled_events)

    summary = {
        "rows": int(len(normalized)),
        "date_min": str(normalized["event_time"].min()) if len(normalized) else "n/a",
        "date_max": str(normalized["event_time"].max()) if len(normalized) else "n/a",
        "tenants": int(normalized["tenant_id"].nunique()) if len(normalized) else 0,
        "tokens": int(normalized["token_id"].nunique()) if len(normalized) else 0,
        "pipeline_anomaly_windows": int(len(pipeline_anomalies)),
        "raw_rule_anomaly_windows": int(len(raw_rule_anomalies)),
        "severity_labeled_logs": int(labeled_events["is_any_anomaly"].sum()) if len(labeled_events) else 0,
    }

    return {
        "summary": summary,
        "normalized": normalized,
        "alerts": alerts,
        "pipeline_anomalies": pipeline_anomalies,
        "raw_rule_anomalies": raw_rule_anomalies,
        "labeled_events": labeled_events,
        "daily_counts": daily_counts,
        "pipeline_severity": top_counts(pipeline_anomalies, "severity", limit=10, name="count"),
        "severity_comparison": severity_comparison(pipeline_anomalies),
        "severity_samples": sample_windows_by_severity(pipeline_anomalies, per_severity=5),
        "pipeline_signal_counts": top_counts(
            pipeline_anomalies.assign(
                primary_signal=pipeline_anomalies["signals"].apply(
                    lambda values: values[0] if isinstance(values, list) and values else "none"
                )
            ),
            "primary_signal",
            limit=10,
            name="count",
        ),
        "top_pipeline_tenants": top_counts(pipeline_anomalies, "tenant_id", limit=10, name="windows"),
        "top_pipeline_tokens": top_counts(pipeline_anomalies, "token_id", limit=10, name="windows"),
        "top_raw_rule_tenants": top_counts(raw_rule_anomalies, "tenant_id", limit=10, name="windows"),
        "top_raw_rule_tokens": top_counts(raw_rule_anomalies, "token_id", limit=10, name="windows"),
        "top_severity_endpoints": top_counts(
            labeled_events[labeled_events["event_severity"].isin(["low", "medium", "high"])],
            "endpoint",
            limit=10,
            name="events",
        ),
        "top_severity_geos": top_counts(
            labeled_events[labeled_events["event_severity"].isin(["low", "medium", "high"])],
            "geo_country",
            limit=10,
            name="events",
        ),
    }
