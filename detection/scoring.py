from typing import Dict, List, Optional, Tuple

from detection.baseline import TokenKey

DEFAULT_SIGNAL_WEIGHTS = {
    "new_country": 40,
    "new_ip": 15,
    "volume_spike": 30,
    "new_endpoint": 25,
    "off_hour": 20,
}


def multiplier_for_signal_count(signal_count: int) -> float:
    if signal_count <= 1:
        return 1.0
    if signal_count == 2:
        return 1.2
    return 1.5


def severity_for_score(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _why_for_signal(signal_name: str) -> str:
    explanations = {
        "new_country": "Token appeared from a country not seen in historical behavior.",
        "new_ip": "Token used IP addresses not seen in historical behavior.",
        "volume_spike": "Hourly request volume exceeded historical threshold.",
        "new_endpoint": "Token accessed an endpoint outside historical endpoint usage.",
        "off_hour": "Requests occurred in uncommon hours for this token.",
    }
    return explanations.get(signal_name, f"Signal triggered: {signal_name}")


def score_windows_to_alerts(
    windows: List[Dict[str, object]],
    baselines: Dict[TokenKey, Dict[str, object]],
    tenant_context: Optional[Dict[str, Dict[str, object]]] = None,
    signal_weights: Optional[Dict[str, int]] = None,
) -> List[Dict[str, object]]:
    alerts: List[Dict[str, object]] = []
    weights = signal_weights or DEFAULT_SIGNAL_WEIGHTS
    context_by_tenant = tenant_context or {}

    for window in windows:
        tenant_id = str(window["tenant_id"])
        token_id = str(window["token_id"])
        signals = list(window.get("signals", []))

        base_score = sum(weights.get(signal, 0) for signal in signals)
        multiplier = multiplier_for_signal_count(len(signals))
        risk_score = min(100, int(round(base_score * multiplier)))
        severity = severity_for_score(risk_score)

        baseline = baselines.get((tenant_id, token_id), {})
        tenant_info = context_by_tenant.get(tenant_id, {})
        token_type = "unknown"
        token_map = tenant_info.get("tokens", {})
        token_payload: Dict[str, object] = {}
        if isinstance(token_map, dict):
            token_payload = token_map.get(token_id, {})
            if isinstance(token_payload, dict):
                token_type = str(token_payload.get("token_type", "unknown"))
        baseline_snapshot = {
            "volume_mean": baseline.get("volume_mean"),
            "volume_std": baseline.get("volume_std"),
            "volume_p95": baseline.get("volume_p95"),
            "known_geos_count": len(baseline.get("known_geos", [])),
            "known_ips_count": len(baseline.get("known_ips", [])),
            "known_endpoints_count": len(baseline.get("known_endpoints", [])),
            "known_auth_methods": baseline.get("known_auth_methods", []),
            "dominant_auth_method": baseline.get("dominant_auth_method", "unknown"),
            "top_endpoints": baseline.get("top_endpoints", {}),
            "hour_histogram": baseline.get("hour_histogram", {}),
        }

        alert = {
            "tenant_id": tenant_id,
            "token_id": token_id,
            "hour_bucket": window.get("hour_bucket"),
            "signals": signals,
            "signal_count": len(signals),
            "risk_score": risk_score,
            "final_risk_score": risk_score,
            "severity": severity,
            "weights": {signal: weights.get(signal, 0) for signal in signals},
            "multiplier": multiplier,
            "why": [_why_for_signal(signal) for signal in signals],
            "evidence": window.get("evidence", {}),
            "baseline_snapshot": baseline_snapshot,
            "tenant_context": {
                "tenant_tier": tenant_info.get("tenant_tier", "unknown"),
                "timezone": tenant_info.get("timezone", "UTC"),
                "expected_countries": tenant_info.get("expected_countries", []),
                "known_ip_ranges": tenant_info.get("known_ip_ranges", []),
                "sensitive_endpoints": tenant_info.get("sensitive_endpoints", []),
                "token_type": token_type,
                "token": token_payload if isinstance(token_payload, dict) else {},
            },
            "correlated_signals": [],
            "correlation_reason": "No correlation adjustments applied.",
            "suppressed": False,
            "suppression_reason": "",
            "window_request_count": int(window.get("window_request_count", 0)),
        }
        alerts.append(alert)

    alerts.sort(
        key=lambda item: (
            int(item["final_risk_score"]),
            int(item.get("signal_count", 0)),
            str(item.get("hour_bucket", "")),
        ),
        reverse=True,
    )
    return alerts
