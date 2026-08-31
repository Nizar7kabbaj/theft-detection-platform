from __future__ import annotations

import pytest

from app.shared import gate


@pytest.fixture(autouse=True)
def gate_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "gate_is_raised", lambda: False)
    monkeypatch.setattr(gate, "gate_set", lambda reason: None)
    monkeypatch.setattr(gate, "gate_clear", lambda: None)
    monkeypatch.setattr(gate, "gate_refresh", lambda: None)
