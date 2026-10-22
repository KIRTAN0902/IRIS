"""Antigravity bridge HTTP transport."""

from __future__ import annotations

from app.services.agy_bridge import AgySession, agy_manager


def _session() -> AgySession:
    session = AgySession(key="iris", directory=r"C:\kirtan\IRIS", alias="iris")
    session.state = "IDLE"
    session.buffer.append("ready")
    return session


def test_agy_workspaces_and_sessions(client):
    workspaces = client.get("/api/agy/workspaces")
    assert workspaces.status_code == 200
    aliases = {item["alias"] for item in workspaces.json()["workspaces"]}
    assert "iris" in aliases

    sessions = client.get("/api/agy/sessions")
    assert sessions.status_code == 200
    assert "sessions" in sessions.json()


def test_agy_attach_and_status(client, monkeypatch):
    session = _session()
    monkeypatch.setattr(agy_manager, "spawn_or_attach", lambda *args, **kwargs: session)
    monkeypatch.setattr(agy_manager, "find_session", lambda key: session)

    attached = client.post("/api/agy/attach", json={"directory": "iris"})
    assert attached.status_code == 200
    assert attached.json()["session"]["key"] == "iris"
    assert "ready" in attached.json()["recent_output"]

    status = client.get("/api/agy/session/iris")
    assert status.status_code == 200
    assert status.json()["session"]["alias"] == "iris"


def test_agy_input_routes_commands(client, monkeypatch):
    sent: dict[str, str] = {}

    def raw(key, payload):
        sent["raw"] = payload
        return {"session": _session().to_dict()}

    def prompt(key, payload):
        sent["prompt"] = payload
        return {"session": _session().to_dict()}

    monkeypatch.setattr(agy_manager, "send_raw_input", raw)
    monkeypatch.setattr(agy_manager, "send_prompt", prompt)

    slash = client.post("/api/agy/slash", json={"command": "models"})
    assert slash.status_code == 200
    assert sent["raw"] == "/models"

    text = client.post("/api/agy/input", json={"input": "fix the build"})
    assert text.status_code == 200
    assert sent["prompt"] == "fix the build"


def test_agy_missing_session_is_404(client, monkeypatch):
    monkeypatch.setattr(agy_manager, "find_session", lambda key: None)
    assert client.get("/api/agy/session/nope").status_code == 404
    assert client.delete("/api/agy/session/nope").status_code == 404
