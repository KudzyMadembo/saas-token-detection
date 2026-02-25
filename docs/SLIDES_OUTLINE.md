# Slides Outline

## 1. Problem
- Why long-lived API tokens are risky in SaaS systems
- Typical abuse patterns (credential theft, unusual endpoint access, geo drift)

## 2. Pipeline Overview
- Simulator -> Normalization -> Baselines -> Rules -> Correlation -> Controls -> Scoring -> Evaluation
- One-command run: `./scripts/run_demo.sh`

## 3. Simulator and Injected Anomalies
- Synthetic tenants/tokens with normal behavior
- Injected anomalies: `volume_spike`, `new_geo`, `new_endpoint`
- Labeled fields: `is_injected_anomaly`, `anomaly_type`

## 4. Detection Signals
- Volume spike rule
- New geography / new IP rule
- New endpoint rule (+ threshold)
- Optional off-hour signal

## 5. Correlation and False-Positive Controls
- Escalation: new geo + spike, sensitive endpoint novelty
- Downgrade: isolated new_ip
- Suppression: warm-up, allowlists, low-volume noise filters

## 6. Risk Scoring
- Weighted signal model + multipliers
- Correlation adjustments to final score
- Severity bands: high / medium / low

## 7. Example Alert
- Show one alert JSON with:
  - `signals`
  - `correlated_signals`
  - `final_risk_score`
  - `why`, `evidence`
  - `tenant_context`
  - `suppressed`

## 8. Evaluation Results
- TP / FP / FN
- Precision and recall
- Before vs after tuning summary

## 9. Limitations and Future Work
- Synthetic data realism limits
- IP intelligence and CIDR quality
- Token lifecycle context and user identity joins

## 10. Live Demo Steps
- Run `./scripts/run_demo.sh`
- Open `data/alerts/alerts.jsonl`
- Open `data/eval/metrics.json`
