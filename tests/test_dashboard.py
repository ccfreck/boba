from pathlib import Path
import sys

import pytest
import yaml

from boba.events.models import SecurityEvent
from boba.events.storage import EventStore


def test_dashboard_empty_and_real_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).resolve().parents[1]
    config = tmp_path / "config.yaml"
    database = tmp_path / "events.db"
    config.write_text(yaml.safe_dump({
        "version": 1, "policy": str(root / "config/policies.yaml"), "database": str(database),
        "downstream": {"name": "demo-filesystem", "args": []},
    }))
    monkeypatch.setattr(sys, "argv", ["app.py", "--config", str(config)])
    app = AppTest.from_file(str(root / "src/boba/dashboard/app.py"), default_timeout=30)
    app.run()
    assert not app.exception
    assert [metric.value for metric in app.metric] == ["0", "0", "0", "0"]
    assert not database.exists()
    store = EventStore(database)
    store.save(SecurityEvent(agent_id="demo-agent", server="demo-filesystem", tool="read_file",
                             decision="block", reason="Protected credential path", rule_ids=["BOBA-PATH"],
                             alerts=["RATE"], outcome="blocked"))
    app.run()
    assert not app.exception
    assert [metric.value for metric in app.metric] == ["1", "0", "1", "1"]
    app.sidebar.multiselect[2].set_value([]).run()
    assert not app.exception
    assert app.metric[0].value == "0"
