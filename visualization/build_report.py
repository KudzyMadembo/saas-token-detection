from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.express as px

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from visualization.data_prep import (  # noqa: E402
    default_alerts_path,
    default_normalized_path,
    prepare_visualization_datasets,
    report_output_path,
)


def _fig_to_html(fig) -> str:
    return fig.to_html(full_html=False, include_plotlyjs="cdn")


def _table_html(frame: pd.DataFrame, title: str) -> str:
    if frame.empty:
        return f"<h3>{title}</h3><p>No data available.</p>"
    return f"<h3>{title}</h3>{frame.to_html(index=False, border=0)}"


def _summary_cards(summary: dict) -> str:
    cards = [
        ("Rows", summary["rows"]),
        ("Tenants", summary["tenants"]),
        ("Tokens", summary["tokens"]),
        ("Pipeline anomaly windows", summary["pipeline_anomaly_windows"]),
        ("Raw-rule anomaly windows", summary["raw_rule_anomaly_windows"]),
        ("Severity-labeled logs", summary["severity_labeled_logs"]),
    ]
    blocks = []
    for label, value in cards:
        blocks.append(
            f"""
            <div class="card">
              <div class="label">{label}</div>
              <div class="value">{value}</div>
            </div>
            """
        )
    return "\n".join(blocks)


def build_report(
    normalized_path: Optional[Path] = None,
    alerts_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
) -> Path:
    datasets = prepare_visualization_datasets(
        normalized_path=normalized_path,
        alerts_path=alerts_path,
        min_pipeline_score=40,
        include_low_severity=True,
    )
    summary = datasets["summary"]
    daily_counts = datasets["daily_counts"]
    pipeline_anomalies = datasets["pipeline_anomalies"]
    raw_rule_anomalies = datasets["raw_rule_anomalies"]
    labeled_events = datasets["labeled_events"]

    if daily_counts.empty:
        timeline = pd.DataFrame(
            [{"date": "n/a", "severity": "low", "log_count": 0}]
        )
    else:
        timeline = daily_counts.melt(
            id_vars=["date"],
            value_vars=["low_logs", "medium_logs", "high_logs"],
            var_name="severity",
            value_name="log_count",
        )
        timeline["severity"] = timeline["severity"].str.replace("_logs", "", regex=False)
    fig_timeline = px.bar(
        timeline,
        x="date",
        y="log_count",
        color="severity",
        barmode="stack",
        title="Low vs Medium vs High Logs by Day",
        category_orders={"severity": ["low", "medium", "high"]},
    )

    pipeline_daily = (
        pipeline_anomalies.groupby("date", as_index=False)
        .size()
        .rename(columns={"size": "pipeline_windows"})
        if not pipeline_anomalies.empty
        else pd.DataFrame(columns=["date", "pipeline_windows"])
    )
    raw_daily = (
        raw_rule_anomalies.groupby("date", as_index=False)
        .size()
        .rename(columns={"size": "raw_rule_windows"})
        if not raw_rule_anomalies.empty
        else pd.DataFrame(columns=["date", "raw_rule_windows"])
    )
    windows_daily = pipeline_daily.merge(raw_daily, on="date", how="outer").fillna(0)
    if windows_daily.empty:
        windows_daily = pd.DataFrame([{"date": "n/a", "pipeline_windows": 0, "raw_rule_windows": 0}])
    windows_daily = windows_daily.sort_values("date")
    windows_long = windows_daily.melt(
        id_vars=["date"],
        value_vars=["pipeline_windows", "raw_rule_windows"],
        var_name="source",
        value_name="window_count",
    )
    fig_windows = px.line(
        windows_long,
        x="date",
        y="window_count",
        color="source",
        markers=True,
        title="Anomaly Windows by Source and Day",
    )

    severity = datasets["pipeline_severity"]
    if severity.empty:
        severity = pd.DataFrame([{"severity": "none", "count": 0}])
    fig_severity = px.pie(severity, names="severity", values="count", title="Pipeline Severity Mix")
    severity_compare = datasets["severity_comparison"]
    fig_severity_compare = px.bar(
        severity_compare,
        x="severity",
        y="windows",
        color="severity",
        title="High vs Medium vs Low (Window Counts)",
        category_orders={"severity": ["high", "medium", "low"]},
    )

    top_endpoints = datasets["top_severity_endpoints"]
    if top_endpoints.empty:
        top_endpoints = pd.DataFrame([{"endpoint": "none", "events": 0}])
    fig_endpoints = px.bar(
        top_endpoints,
        x="endpoint",
        y="events",
        title="Top Endpoints in Severity-Labeled Logs",
    )

    top_geos = datasets["top_severity_geos"]
    if top_geos.empty:
        top_geos = pd.DataFrame([{"geo_country": "none", "events": 0}])
    fig_geos = px.bar(
        top_geos,
        x="geo_country",
        y="events",
        title="Top Geographies in Severity-Labeled Logs",
    )

    sample_by_severity = labeled_events[labeled_events["event_severity"].isin(["low", "medium", "high"])].head(20)[
        ["event_time", "tenant_id", "token_id", "endpoint", "geo_country", "event_severity"]
    ]
    api_modules = pd.DataFrame(
        [
            {
                "API Module": "Public API",
                "Purpose": "Administrative orchestration of tests and account assets",
                "Base URL": "https://api.abtasty.com/",
            },
            {
                "API Module": "Decision API v2",
                "Purpose": "Real-time feature flag and variation assignment",
                "Base URL": "https://decision.flagship.io/v2/",
            },
            {
                "API Module": "Data Explorer API",
                "Purpose": "Raw hits and computed metrics extraction",
                "Base URL": "Public token-authenticated endpoint",
            },
            {
                "API Module": "Universal Data Connector",
                "Purpose": "External audience/segment ingestion",
                "Base URL": "https://api-data-connector.abtasty.com/",
            },
            {
                "API Module": "Recommendations API",
                "Purpose": "Personalized product/content retrieval",
                "Base URL": "https://uc-info.eu.abtasty.com/v1/reco",
            },
            {
                "API Module": "Search/Autocomplete APIs",
                "Purpose": "Search ranking and real-time suggestions",
                "Base URL": "/search (v0.3), /autocomplete (v0.2)",
            },
        ]
    )

    html = f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8"/>
      <title>AB Tasty Analysis Report</title>
      <style>
        body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }}
        h1, h2, h3 {{ margin-top: 1.2rem; }}
        .meta {{ color: #4b5563; margin-bottom: 16px; }}
        .cards {{ display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 12px; margin: 16px 0; }}
        .card {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; }}
        .label {{ color: #6b7280; font-size: 0.9rem; }}
        .value {{ font-size: 1.4rem; font-weight: 700; }}
        table {{ border-collapse: collapse; width: 100%; margin: 8px 0 16px; }}
        th, td {{ border: 1px solid #e5e7eb; padding: 8px; text-align: left; font-size: 0.9rem; }}
        th {{ background: #f9fafb; }}
        .diagram {{ background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; white-space: pre-wrap; }}
      </style>
    </head>
    <body>
      <h1>AB Tasty Visualization and Anomaly Report</h1>
      <div class="meta">
        Date range: {summary["date_min"]} to {summary["date_max"]}
      </div>
      <div class="cards">{_summary_cards(summary)}</div>

      <h2>Low vs Medium vs High Logs</h2>
      {_fig_to_html(fig_timeline)}

      <h2>Anomaly Windows by Source</h2>
      {_fig_to_html(fig_windows)}

      <h2>Pipeline Anomaly Breakdown</h2>
      {_fig_to_html(fig_severity)}
      <h3>Severity Difference (High vs Medium vs Low)</h3>
      <p>Severity bands use final risk score: <strong>high >= 70</strong>, <strong>medium = 40..69</strong>, <strong>low < 40</strong>.</p>
      {_fig_to_html(fig_severity_compare)}
      {_table_html(severity_compare, "Severity Comparison Table (Counts, Percentages, Score Ranges)")}
      {_table_html(datasets["severity_samples"], "Sample Pipeline Windows per Severity")}
      {_table_html(datasets["pipeline_signal_counts"], "Top Pipeline Primary Signals")}

      <h2>Raw-rule Anomaly Breakdown</h2>
      {_table_html(datasets["top_raw_rule_tenants"], "Top Tenants by Raw-rule Windows")}
      {_table_html(datasets["top_raw_rule_tokens"], "Top Tokens by Raw-rule Windows")}

      <h2>Suspicious Entities (Severity-Labeled Logs)</h2>
      {_fig_to_html(fig_endpoints)}
      {_fig_to_html(fig_geos)}
      {_table_html(sample_by_severity, "Sample Low/Medium/High Log Rows")}

      <h2>AB Tasty API Ecosystem Overview</h2>
      {_table_html(api_modules, "Core API Modules")}
      <div class="diagram">
Data flow:
AB Tasty Raw Logs -> Normalization -> Detection Pipeline -> Alerts + Scores -> Visualization Layer (HTML, Notebook, Streamlit)

Security and governance:
- OAuth2 Client Credentials for Public API access
- RBAC and credential revocation controls
- Decision API for low-latency runtime assignments
      </div>
    </body>
    </html>
    """

    target = output_path or report_output_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HTML visualization report for AB Tasty analysis.")
    parser.add_argument("--normalized", default=str(default_normalized_path()), help="Normalized CSV input path.")
    parser.add_argument("--alerts", default=str(default_alerts_path()), help="Alerts JSONL input path.")
    parser.add_argument("--output", default=str(report_output_path()), help="HTML report output path.")
    args = parser.parse_args()

    output = build_report(
        normalized_path=Path(args.normalized),
        alerts_path=Path(args.alerts),
        output_path=Path(args.output),
    )
    print(f"Wrote visualization report to {output}")


if __name__ == "__main__":
    main()
