# Slides Outline

## 1. Problem
- Why long-lived API tokens are risky in SaaS systems
- Typical abuse patterns (credential theft, unusual endpoint access, geo drift)

## 2. Pipeline Overview
- AB Tasty CSV -> Normalization -> Baselines -> Rules -> Correlation -> Controls -> Scoring
- Visualization layer: HTML report + Streamlit dashboard + notebook
- One-command run: `./scripts/run_ab_tasty_viz.ps1` (Windows) or `./scripts/run_ab_tasty_viz.sh` (bash)

## 3. Simulator and Injected Anomalies
- AB Tasty synthetic dataset mapped into canonical pipeline schema
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
- Severity bands for presentation:
  - `high >= 70`
  - `medium = 40..69`
  - `low < 40`

## 7. Example Alert
- Show one alert JSON with:
  - `signals`
  - `correlated_signals`
  - `final_risk_score`
  - `why`, `evidence`
  - `tenant_context`
  - `suppressed`

## 8. Severity Difference View (Presentation)
- Compare `high` vs `medium` vs `low` counts
- Show percentages and sample windows by severity
- Use HTML report section "Severity Difference (High vs Medium vs Low)"

## 9. Limitations and Future Work
- Synthetic data realism limits
- IP intelligence and CIDR quality
- Token lifecycle context and user identity joins

## 10. Live Demo Steps
- Run `./scripts/run_ab_tasty_viz.ps1` (or `.sh`)
- Open `data/reports/ab_tasty_report.html`
- (Optional) Launch dashboard: `streamlit run visualization/app.py`
- Highlight severity comparison tables/charts (`high`, `medium`, `low`)
