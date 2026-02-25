from typing import Dict, List


def apply_correlation_rules(alerts: List[Dict[str, object]]) -> List[Dict[str, object]]:
    correlated: List[Dict[str, object]] = []

    for alert in alerts:
        updated = dict(alert)
        signals = set(updated.get("signals", []))
        evidence = updated.get("evidence", {})
        tenant_context = updated.get("tenant_context", {})
        baseline_snapshot = updated.get("baseline_snapshot", {})
        reasons: List[str] = []
        correlated_signals: List[str] = []
        score_delta = 0

        if "new_country" in signals and "volume_spike" in signals:
            score_delta += 15
            correlated_signals.append("new_country+volume_spike")
            reasons.append("Escalated because new geography and volume spike happened in the same hour.")

        sensitive_endpoints = set(tenant_context.get("sensitive_endpoints", []))
        endpoint_values = evidence.get("new_endpoint", {}).get("new_values", [])
        hit_sensitive = []
        for endpoint_payload in endpoint_values:
            endpoint = endpoint_payload.get("endpoint")
            if endpoint in sensitive_endpoints:
                hit_sensitive.append(endpoint)
        if hit_sensitive:
            score_delta += 20
            correlated_signals.append("sensitive_endpoint_access")
            reasons.append(
                f"Escalated because endpoint novelty includes sensitive endpoint(s): {sorted(set(hit_sensitive))}."
            )

        # Auth method drift: elevate risky windows if auth behavior changed.
        auth_context = evidence.get("auth_method_context", {})
        window_methods = set(auth_context.get("window_auth_methods", []))
        baseline_methods = set(baseline_snapshot.get("known_auth_methods", []))
        auth_drift_methods = sorted(window_methods - baseline_methods) if baseline_methods else []
        risky_core_signals = {"volume_spike", "new_country", "new_endpoint"}
        if auth_drift_methods and (signals & risky_core_signals):
            score_delta += 10
            correlated_signals.append("auth_method_drift_with_risky_signal")
            reasons.append(
                f"Escalated because auth method drift {auth_drift_methods} co-occurred with risky signals {sorted(signals & risky_core_signals)}."
            )
        elif window_methods and not auth_drift_methods:
            reasons.append("Auth method usage in this window matches baseline expectations.")

        # Explicit downgrade checks for isolated new_ip.
        no_volume_spike = "volume_spike" not in signals
        no_new_endpoint = "new_endpoint" not in signals
        no_new_country = "new_country" not in signals
        has_new_ip = "new_ip" in signals
        no_auth_drift = not auth_drift_methods

        expected_countries = set(tenant_context.get("expected_countries", []))
        window_geo_values = set(evidence.get("window_summary", {}).get("geo_values", []))
        geo_expected_or_known = bool(window_geo_values) and (
            window_geo_values.issubset(expected_countries) if expected_countries else True
        )

        if (
            has_new_ip
            and no_volume_spike
            and no_new_endpoint
            and no_new_country
            and no_auth_drift
            and geo_expected_or_known
        ):
            score_delta -= 10
            correlated_signals.append("isolated_new_ip_normal_context")
            reasons.append(
                "Downgraded because new_ip occurred with expected geography, no volume spike, no endpoint novelty, and baseline auth method behavior."
            )

        initial_score = int(updated.get("risk_score", 0))
        final_score = max(0, min(100, initial_score + score_delta))
        updated["correlated_signals"] = correlated_signals
        updated["correlation_reason"] = " ".join(reasons) if reasons else "No correlation adjustments applied."
        updated["final_risk_score"] = final_score

        correlated.append(updated)

    return correlated
