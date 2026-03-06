from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from visualization.data_prep import prepare_visualization_datasets  # noqa: E402


@st.cache_data(show_spinner=False)
def load_data() -> dict:
    return prepare_visualization_datasets(min_pipeline_score=40, include_low_severity=True)


def apply_filters(frame: pd.DataFrame, tenant: str, token: str, date_start, date_end) -> pd.DataFrame:
    filtered = frame.copy()
    if tenant != "All":
        filtered = filtered[filtered["tenant_id"] == tenant]
    if token != "All":
        filtered = filtered[filtered["token_id"] == token]
    if "event_time" in filtered.columns:
        filtered = filtered[
            (filtered["event_time"].dt.date >= date_start) & (filtered["event_time"].dt.date <= date_end)
        ]
    if "hour_bucket" in filtered.columns:
        filtered = filtered[
            (filtered["hour_bucket"].dt.date >= date_start) & (filtered["hour_bucket"].dt.date <= date_end)
        ]
    return filtered


def main() -> None:
    st.set_page_config(page_title="AB Tasty Visualization", layout="wide")
    st.title("AB Tasty Visualization Dashboard")

    datasets = load_data()
    labeled_events = datasets["labeled_events"]
    pipeline = datasets["pipeline_anomalies"]
    raw_rules = datasets["raw_rule_anomalies"]

    if labeled_events.empty:
        st.warning("No normalized logs found. Run normalization and pipeline first.")
        return

    min_date = labeled_events["event_time"].dt.date.min()
    max_date = labeled_events["event_time"].dt.date.max()

    with st.sidebar:
        st.header("Filters")
        tenant_options = ["All"] + sorted(labeled_events["tenant_id"].astype(str).unique().tolist())
        token_options = ["All"] + sorted(labeled_events["token_id"].astype(str).unique().tolist())
        tenant = st.selectbox("Tenant", tenant_options, index=0)
        token = st.selectbox("Token", token_options, index=0)
        date_range = st.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
        anomaly_source = st.selectbox("Anomaly source", ["both", "pipeline", "raw"])
        severity = st.multiselect("Pipeline severity", ["low", "medium", "high"], default=["medium", "high"])

    if isinstance(date_range, tuple):
        date_start, date_end = date_range
    else:
        date_start = date_end = date_range

    events_filtered = apply_filters(labeled_events, tenant, token, date_start, date_end)
    pipeline_filtered = apply_filters(pipeline, tenant, token, date_start, date_end)
    raw_filtered = apply_filters(raw_rules, tenant, token, date_start, date_end)
    if severity:
        pipeline_filtered = pipeline_filtered[pipeline_filtered["severity"].isin(severity)]

    tabs = st.tabs(["Overview", "Severity Logs", "API Ecosystem", "Sample Alerts"])

    with tabs[0]:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Rows", len(events_filtered))
        severity_events = int(events_filtered["event_severity"].isin(["low", "medium", "high"]).sum())
        c2.metric("Severity-labeled logs", severity_events)
        c3.metric("Pipeline windows", len(pipeline_filtered))
        c4.metric("Raw-rule windows", len(raw_filtered))

        events_with_date = events_filtered.copy()
        events_with_date["date"] = events_with_date["event_time"].dt.date.astype(str)
        severity_only = events_with_date[events_with_date["event_severity"].isin(["low", "medium", "high"])].copy()
        daily = (
            severity_only.groupby(["date", "event_severity"], as_index=False)
            .size()
            .rename(columns={"size": "count"})
        )
        if daily.empty:
            daily = pd.DataFrame([{"date": "n/a", "event_severity": "low", "count": 0}])
        fig = px.bar(
            daily,
            x="date",
            y="count",
            color="event_severity",
            barmode="stack",
            title="Low vs Medium vs High Logs",
            category_orders={"event_severity": ["low", "medium", "high"]},
        )
        st.plotly_chart(fig, use_container_width=True)

    with tabs[1]:
        if anomaly_source in {"both", "pipeline"} and not pipeline_filtered.empty:
            st.subheader("Pipeline Anomalies")
            st.caption("Severity bands: high >= 70, medium = 40..69, low < 40")
            severity_table = (
                pipeline_filtered.groupby("severity", as_index=False)
                .agg(
                    windows=("severity", "size"),
                    score_min=("final_risk_score", "min"),
                    score_max=("final_risk_score", "max"),
                    score_avg=("final_risk_score", "mean"),
                )
                .assign(score_avg=lambda d: d["score_avg"].round(2))
            )
            all_levels = pd.DataFrame({"severity": ["high", "medium", "low"]})
            severity_table = all_levels.merge(severity_table, on="severity", how="left").fillna(0)
            severity_table["windows"] = severity_table["windows"].astype(int)
            severity_table["score_min"] = severity_table["score_min"].astype(int)
            severity_table["score_max"] = severity_table["score_max"].astype(int)
            total_windows = int(severity_table["windows"].sum()) or 1
            severity_table["percentage"] = (severity_table["windows"] / total_windows * 100).round(2)

            mc1, mc2, mc3 = st.columns(3)
            high_count = int(severity_table.loc[severity_table["severity"] == "high", "windows"].iloc[0])
            med_count = int(severity_table.loc[severity_table["severity"] == "medium", "windows"].iloc[0])
            low_count = int(severity_table.loc[severity_table["severity"] == "low", "windows"].iloc[0])
            mc1.metric("High windows", high_count)
            mc2.metric("Medium windows", med_count)
            mc3.metric("Low windows", low_count)

            fig = px.histogram(
                pipeline_filtered,
                x="severity",
                color="severity",
                title="Pipeline Severity Distribution",
                category_orders={"severity": ["high", "medium", "low"]},
            )
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(
                severity_table[["severity", "windows", "percentage", "score_min", "score_max", "score_avg"]],
                use_container_width=True,
            )
            sample_by_severity = (
                pipeline_filtered.sort_values("hour_bucket", ascending=False)
                .groupby("severity", group_keys=False)
                .head(5)
            )
            st.dataframe(
                sample_by_severity[
                    ["hour_bucket", "tenant_id", "token_id", "severity", "final_risk_score", "signals"]
                ],
                use_container_width=True,
            )
            st.dataframe(
                pipeline_filtered[
                    ["hour_bucket", "tenant_id", "token_id", "severity", "final_risk_score", "signals"]
                ].sort_values("hour_bucket", ascending=False),
                use_container_width=True,
            )

        if anomaly_source in {"both", "raw"} and not raw_filtered.empty:
            st.subheader("Raw-rule Anomalies")
            raw_signal_counts = raw_filtered["signal_count"].value_counts().sort_index().reset_index()
            raw_signal_counts.columns = ["signal_count", "windows"]
            fig = px.bar(raw_signal_counts, x="signal_count", y="windows", title="Raw-rule Signal Count per Window")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(
                raw_filtered[["hour_bucket", "tenant_id", "token_id", "signal_count", "signals"]]
                .sort_values("hour_bucket", ascending=False),
                use_container_width=True,
            )

    with tabs[2]:
        st.subheader("AB Tasty API Ecosystem")
        modules = pd.DataFrame(
            [
                ["Public API", "Admin orchestration", "https://api.abtasty.com/"],
                ["Decision API v2", "Real-time assignments", "https://decision.flagship.io/v2/"],
                ["Data Explorer API", "Raw hits and computed metrics", "Public token-authenticated endpoint"],
                ["Universal Data Connector", "External segment ingestion", "https://api-data-connector.abtasty.com/"],
                ["Recommendations API", "Personalized recommendations", "https://uc-info.eu.abtasty.com/v1/reco"],
                ["Search/Autocomplete APIs", "Search ranking and suggestions", "/search, /autocomplete"],
            ],
            columns=["Module", "Purpose", "Base URL"],
        )
        st.dataframe(modules, use_container_width=True)
        st.markdown(
            """
**Flow**

Raw AB Tasty logs -> Normalization -> Detection pipeline -> Alerts + scores -> Visualizations.

**Security**

- OAuth2 client credentials for Public API access  
- RBAC for least-privilege credentials  
- Immediate credential revocation support
            """
        )

    with tabs[3]:
        severity_rows = events_filtered[events_filtered["event_severity"].isin(["low", "medium", "high"])].copy()
        st.dataframe(
            severity_rows[["event_time", "tenant_id", "token_id", "endpoint", "geo_country", "event_severity"]]
            .sort_values("event_time", ascending=False)
            .head(100),
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
