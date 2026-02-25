from collections import defaultdict
from typing import Dict, List, Tuple

import pandas as pd

from detection.baseline import TokenKey

WindowKey = Tuple[str, str, str]


def _window_key(tenant_id: str, token_id: str, hour_bucket: pd.Timestamp) -> WindowKey:
    return (tenant_id, token_id, hour_bucket.isoformat())


def _round(value: float) -> float:
    return round(float(value), 4)


def detect_anomaly_windows(
    frame: pd.DataFrame,
    baselines: Dict[TokenKey, Dict[str, object]],
    endpoint_min_hits: int = 3,
    volume_sigma: float = 3.0,
    offhour_ratio_threshold: float = 0.05,
) -> List[Dict[str, object]]:
    windows: Dict[WindowKey, Dict[str, object]] = defaultdict(
        lambda: {"signals": set(), "evidence": {}, "window_request_count": 0}
    )

    grouped = frame.groupby(["tenant_id", "token_id"], sort=True)
    for (tenant_id, token_id), token_frame in grouped:
        token_frame = token_frame.sort_values("event_time")
        baseline = baselines.get((tenant_id, token_id), {})
        token_hours = token_frame.groupby("hour_bucket", sort=True)

        # Rule 1: Volume spike against historical hourly behavior.
        hourly_counts = token_hours.size().sort_index()
        history_counts: List[float] = []
        for hour_bucket, count in hourly_counts.items():
            if history_counts:
                mean = float(pd.Series(history_counts).mean())
                std = float(pd.Series(history_counts).std(ddof=0))
                p95 = float(pd.Series(history_counts).quantile(0.95))
            else:
                mean = float(baseline.get("volume_mean", 0.0))
                std = float(baseline.get("volume_std", 0.0))
                p95 = float(baseline.get("volume_p95", 0.0))

            threshold = max(p95, mean + (volume_sigma * std))
            if threshold > 0 and float(count) > threshold and history_counts:
                key = _window_key(tenant_id, token_id, hour_bucket)
                windows[key]["signals"].add("volume_spike")
                windows[key]["window_request_count"] = int(count)
                windows[key]["evidence"]["volume_spike"] = {
                    "hour_count": int(count),
                    "threshold": _round(threshold),
                    "baseline_mean": _round(mean),
                    "baseline_std": _round(std),
                    "baseline_p95": _round(p95),
                    "history_hours": len(history_counts),
                }

            history_counts.append(float(count))

        # Rule 2 + 3: unseen geo/IP + unseen endpoint with per-hour threshold.
        seen_geos = set()
        seen_ips = set()
        seen_endpoints = set()
        seen_auth_methods = set()

        for hour_bucket, hour_group in token_hours:
            key = _window_key(tenant_id, token_id, hour_bucket)
            current_geos = set(hour_group["geo_country"].astype(str))
            current_ips = set(hour_group["ip_address"].astype(str))
            current_endpoint_counts = hour_group["endpoint"].astype(str).value_counts()
            current_auth_counts = hour_group["auth_method"].astype(str).value_counts()
            current_auth_methods = set(current_auth_counts.index.tolist())
            dominant_auth_method_window = (
                str(current_auth_counts.index[0]) if not current_auth_counts.empty else "unknown"
            )
            windows[key]["window_request_count"] = int(len(hour_group))
            windows[key]["evidence"]["window_summary"] = {
                "window_request_count": int(len(hour_group)),
                "geo_values": sorted(current_geos),
                "endpoint_values": sorted(current_endpoint_counts.index.tolist()),
                "auth_methods": sorted(current_auth_methods),
                "auth_method_counts": current_auth_counts.to_dict(),
                "dominant_auth_method_window": dominant_auth_method_window,
            }
            windows[key]["evidence"]["auth_method_context"] = {
                "window_auth_methods": sorted(current_auth_methods),
                "known_auth_before": sorted(seen_auth_methods),
                "new_auth_methods": sorted(current_auth_methods - seen_auth_methods)
                if seen_auth_methods
                else [],
            }

            unseen_geos = sorted(current_geos - seen_geos) if seen_geos else []
            if unseen_geos:
                windows[key]["signals"].add("new_country")
                windows[key]["evidence"]["new_country"] = {
                    "new_values": unseen_geos,
                    "known_before_count": len(seen_geos),
                }

            unseen_ips = sorted(current_ips - seen_ips) if seen_ips else []
            if unseen_ips:
                windows[key]["signals"].add("new_ip")
                windows[key]["evidence"]["new_ip"] = {
                    "new_values": unseen_ips,
                    "known_before_count": len(seen_ips),
                }

            new_endpoints = []
            if seen_endpoints:
                for endpoint, count in current_endpoint_counts.items():
                    if endpoint not in seen_endpoints and int(count) >= endpoint_min_hits:
                        new_endpoints.append({"endpoint": endpoint, "hour_count": int(count)})
            if new_endpoints:
                windows[key]["signals"].add("new_endpoint")
                windows[key]["evidence"]["new_endpoint"] = {
                    "new_values": new_endpoints,
                    "min_hits_threshold": endpoint_min_hits,
                    "known_before_count": len(seen_endpoints),
                }

            hour_value = int(hour_bucket.hour)
            baseline_hour_hist = baseline.get("hour_histogram", {})
            total_hour_events = sum(int(value) for value in baseline_hour_hist.values()) or 0
            hour_count = int(baseline_hour_hist.get(str(hour_value), 0))
            hour_ratio = (hour_count / total_hour_events) if total_hour_events else 0.0
            if total_hour_events and hour_ratio <= offhour_ratio_threshold:
                windows[key]["signals"].add("off_hour")
                windows[key]["evidence"]["off_hour"] = {
                    "hour": hour_value,
                    "hour_ratio": _round(hour_ratio),
                    "ratio_threshold": _round(offhour_ratio_threshold),
                    "hour_count_in_baseline": hour_count,
                    "total_baseline_events": total_hour_events,
                }

            seen_geos.update(current_geos)
            seen_ips.update(current_ips)
            seen_endpoints.update(set(current_endpoint_counts.index.tolist()))
            seen_auth_methods.update(current_auth_methods)

    correlated: List[Dict[str, object]] = []
    for (tenant_id, token_id, hour_bucket), payload in sorted(windows.items()):
        if not payload["signals"]:
            continue
        correlated.append(
            {
                "tenant_id": tenant_id,
                "token_id": token_id,
                "hour_bucket": hour_bucket,
                "signals": sorted(payload["signals"]),
                "evidence": payload["evidence"],
                "signal_count": len(payload["signals"]),
                "window_request_count": int(payload.get("window_request_count", 0)),
            }
        )

    return correlated
