"""Tests for Milestone G: Conversational Coworker, Message Stream, and Stop Control."""
import pytest
from types import SimpleNamespace
from app.models.coworker import Coworker, CoworkerTask
from app.models.coding_project import CodingProject
from app.coding.antigravity import coding_agents


@pytest.fixture
def chat_coworker_setup(client, db, tmp_path):
    # Create git repo
    repo = tmp_path / "chat_repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Chat Repo\n", encoding="utf-8")
    (repo / "package.json").write_text('{"name": "test-pkg"}\n', encoding="utf-8")

    import subprocess
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@iris.local"], cwd=str(repo), check=True)
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), check=True)

    # Register project
    p_res = client.post("/api/coding/projects", json={
        "name": "Chat Project",
        "directory": str(repo),
        "aliases": ["chat-repo"]
    })
    assert p_res.status_code == 201
    pid = p_res.json()["id"]
    client.patch(f"/api/coding/projects/{pid}", json={"write_access": True, "command_access": True})

    # Create coworker
    c_res = client.post("/api/coworkers?template=coding_coworker", json={
        "name": "Dev Partner",
        "role": "Coding Coworker",
        "project_id": pid
    })
    assert c_res.status_code == 201
    cid = c_res.json()["id"]

    return {"project_id": pid, "repo": repo, "coworker_id": cid}


def test_coworker_chat_endpoint_dispatches_task(client, chat_coworker_setup):
    cid = chat_coworker_setup["coworker_id"]
    pid = chat_coworker_setup["project_id"]

    # Send natural chat message
    res = client.post(f"/api/coworkers/{cid}/chat", json={
        "message": "Add a photo gallery to the homepage",
        "project_id": pid,
        "engine": "antigravity-cli"
    })
    assert res.status_code == 202
    data = res.json()
    assert data["action"] == "dispatched"
    assert data["task_id"] is not None
    assert data["task"]["instruction"] == "Add a photo gallery to the homepage"


def test_coworker_messages_endpoint_returns_turns(client, chat_coworker_setup):
    cid = chat_coworker_setup["coworker_id"]
    pid = chat_coworker_setup["project_id"]

    # Post message
    client.post(f"/api/coworkers/{cid}/chat", json={
        "message": "Implement responsive dark navigation bar",
        "project_id": pid
    })

    # Query messages
    msg_res = client.get(f"/api/coworkers/{cid}/messages")
    assert msg_res.status_code == 200
    messages = msg_res.json()
    assert len(messages) >= 2
    user_msg = messages[0]
    coworker_turn = messages[1]

    assert user_msg["role"] == "user"
    assert user_msg["content"] == "Implement responsive dark navigation bar"
    assert coworker_turn["role"] == "coworker"
    assert coworker_turn["task_id"] == user_msg["task_id"]


def test_conversational_stop_intent_cancels_running_task(client, chat_coworker_setup, db):
    cid = chat_coworker_setup["coworker_id"]
    pid = chat_coworker_setup["project_id"]

    # Manually create a running task
    from uuid import uuid4
    task_id = str(uuid4())
    task = CoworkerTask(
        id=task_id,
        user_id=1,
        coworker_id=cid,
        project_id=pid,
        instruction="Generate large assets",
        status="running"
    )
    db.add(task)
    coworker = db.query(Coworker).filter_by(id=cid).first()
    coworker.status = "working"
    db.commit()

    # User says "Stop"
    stop_res = client.post(f"/api/coworkers/{cid}/chat", json={
        "message": "Stop",
        "project_id": pid
    })
    assert stop_res.status_code == 202
    data = stop_res.json()
    assert data["action"] == "stopped"
    assert data["task_id"] == task_id

    # Verify task status is cancelled
    db.refresh(task)
    assert task.status == "cancelled"
    db.refresh(coworker)
    assert coworker.status == "idle"


def test_stop_endpoint_stops_coworker_task(client, chat_coworker_setup, db):
    cid = chat_coworker_setup["coworker_id"]
    pid = chat_coworker_setup["project_id"]

    from uuid import uuid4
    task_id = str(uuid4())
    task = CoworkerTask(
        id=task_id,
        user_id=1,
        coworker_id=cid,
        project_id=pid,
        instruction="Long running compilation",
        status="running"
    )
    db.add(task)
    db.commit()

    # Call stop endpoint
    stop_res = client.post(f"/api/coworkers/{cid}/stop")
    assert stop_res.status_code == 200
    res_data = stop_res.json()
    assert res_data["status"] == "cancelled"

    db.refresh(task)
    assert task.status == "cancelled"
