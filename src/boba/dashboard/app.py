"""Run with streamlit run src/boba/dashboard/app.py -- --config config/boba.yaml."""

import argparse
import json
from pathlib import Path
import sqlite3

import pandas as pd
import streamlit as st

from boba.config import Settings, load_yaml
from boba.security.policy_engine import Policy

MASCOT = Path(__file__).parent / "assets" / "boba.png"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config/boba.yaml"))
    options, _ = parser.parse_known_args()
    st.set_page_config(page_title="Boba Security Dashboard", page_icon=str(MASCOT), layout="wide")
    mascot, heading = st.columns([1, 5])
    with mascot:
        st.image(str(MASCOT), width=160)
    with heading:
        st.title("Boba Security Dashboard")
        st.markdown("**Your AI agent's security bouncer.**")
        st.caption("Boba checks the tools. You control the access.")
        st.button("Refresh", type="primary")
    st.divider()
    st.sidebar.title("Your security view")
    st.sidebar.caption("Filter real MCP activity. Every request gets checked at the door.")
    try:
        config_path = options.config.resolve(strict=True)
        config = Settings.load(config_path)
        policy = Policy.model_validate(load_yaml(config_path.parent / config.policy))
        database = (config_path.parent / config.database).resolve()
        if database.exists():
            # Read-only connection: opening the dashboard never creates an event database.
            with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
                events = pd.read_sql_query("SELECT * FROM events ORDER BY timestamp DESC", db)
        else:
            events = pd.DataFrame()
    except Exception:
        st.error("Unable to read configuration or event database.")
        return

    st.header("Overview")
    if events.empty:
        for column, label in zip(st.columns(4), ["Total MCP tool calls", "Allowed requests", "Blocked requests", "Security alerts"]):
            column.metric(label, 0)
        st.info("Boba is ready at the door. Run the demo client through Boba, then refresh to see real security events.")
    else:
        for field in ("rule_ids", "alerts"):
            events[field] = events[field].map(json.loads)
        for field in ("severity", "tool", "decision"):
            choices = sorted(events[field].unique())
            selected = st.sidebar.multiselect(field.title(), choices, default=choices)
            events = events[events[field].isin(selected)]
        st.caption("Metrics and tables reflect the selected filters. Allowed means authorized; check outcome for execution success.")
        metrics = [len(events), int((events.decision == "allow").sum()),
                   int((events.decision == "block").sum()), int(events.alerts.map(len).sum())]
        for column, label, value in zip(st.columns(4), ["Total MCP tool calls", "Allowed requests", "Blocked requests", "Security alerts"], metrics):
            column.metric(label, value)
        columns = ["timestamp", "tool", "decision", "severity", "reason", "rule_ids", "alerts", "outcome", "duration_ms"]
        st.header("Recent Security Events")
        st.dataframe(events[columns].head(500), hide_index=True)
        st.header("Blocked Requests")
        st.dataframe(events.loc[events.decision == "block", columns].head(500), hide_index=True)
        st.header("Threat Activity")
        suspicious = events[(events.decision == "block") | events.alerts.map(bool)].copy()
        if not suspicious.empty:
            suspicious["minute"] = pd.to_datetime(suspicious.timestamp, utc=True).dt.floor("min")
            st.bar_chart(suspicious.groupby("minute").size().rename("Suspicious requests"))
        else:
            st.info("No suspicious activity in this view.")
        st.subheader("Most frequently used tools")
        st.bar_chart(events.tool.value_counts())
        st.subheader("Most frequently triggered security rules")
        rules = (events.rule_ids + events.alerts).explode().dropna()
        if not rules.empty:
            st.bar_chart(rules.value_counts())
    st.header("Security Rules")
    st.caption("Configured policy on disk; restart the gateway after changes. Built-in path, schema, command, and default-deny protections also apply.")
    st.json(policy.model_dump())


if __name__ == "__main__":
    main()
