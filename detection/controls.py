import ipaddress
from typing import Dict, List


def _new_ip_values(alert: Dict[str, object]) -> List[str]:
    evidence = alert.get("evidence", {})
    new_ip = evidence.get("new_ip", {})
    values = new_ip.get("new_values", [])
    return [str(value) for value in values]


def _new_endpoint_values(alert: Dict[str, object]) -> List[str]:
    evidence = alert.get("evidence", {})
    new_endpoint = evidence.get("new_endpoint", {})
    values = new_endpoint.get("new_values", [])
    endpoints = []
    for item in values:
        endpoint = item.get("endpoint")
        if endpoint:
            endpoints.append(str(endpoint))
    return endpoints


def _ip_in_ranges(ip_value: str, ranges: List[str]) -> bool:
    try:
        ip_addr = ipaddress.ip_address(ip_value)
    except ValueError:
        return False
    for cidr in ranges:
        try:
            if ip_addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def apply_false_positive_controls(
    alerts: List[Dict[str, object]],
    baselines: Dict[tuple[str, str], Dict[str, object]],
    min_history_hours: int = 2,
    tiny_request_threshold: int = 2,
) -> List[Dict[str, object]]:
    controlled: List[Dict[str, object]] = []

    for alert in alerts:
        updated = dict(alert)
        updated["suppressed"] = False
        updated["suppression_reason"] = ""

        tenant_id = str(updated.get("tenant_id", ""))
        token_id = str(updated.get("token_id", ""))
        signals = set(updated.get("signals", []))
        baseline = baselines.get((tenant_id, token_id), {})
        hour_buckets_seen = int(baseline.get("hour_buckets_seen", 0))
        tenant_context = updated.get("tenant_context", {})
        token_context = tenant_context.get("token", {})

        if hour_buckets_seen < min_history_hours:
            updated["suppressed"] = True
            updated["suppression_reason"] = (
                f"Suppressed: warm-up period (hour_buckets_seen={hour_buckets_seen}, min_required={min_history_hours})."
            )
            controlled.append(updated)
            continue

        if "new_endpoint" in signals and int(updated.get("window_request_count", 0)) <= tiny_request_threshold:
            updated["suppressed"] = True
            updated["suppression_reason"] = (
                f"Suppressed: tiny request volume in window ({updated.get('window_request_count', 0)} <= {tiny_request_threshold})."
            )
            controlled.append(updated)
            continue

        endpoint_allowlist = []
        if isinstance(token_context, dict):
            endpoint_allowlist = token_context.get("endpoint_allowlist", []) or []
        new_endpoints = _new_endpoint_values(updated)
        if new_endpoints and endpoint_allowlist and all(
            endpoint in endpoint_allowlist for endpoint in new_endpoints
        ):
            updated["suppressed"] = True
            updated["suppression_reason"] = "Suppressed: all endpoint novelties are token-allowlisted."
            controlled.append(updated)
            continue

        known_ranges = tenant_context.get("known_ip_ranges", []) or []
        new_ips = _new_ip_values(updated)
        if new_ips and all(_ip_in_ranges(ip_value, known_ranges) for ip_value in new_ips):
            if signals == {"new_ip"}:
                updated["suppressed"] = True
                updated["suppression_reason"] = "Suppressed: isolated new_ip entirely within tenant allowlisted CIDR ranges."
                controlled.append(updated)
                continue

        controlled.append(updated)

    return controlled
