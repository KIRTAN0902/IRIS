"""Run a real Antigravity task/follow-up against a disposable workspace."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
ARTIFACTS=Path(os.environ.get("IRIS_CODING_E2E_DIR",str(ROOT/"backend"/".pytest-tmp"/"coding-e2e"))).expanduser().resolve()
ARTIFACTS.mkdir(parents=True,exist_ok=True)
os.environ["DATABASE_URL"]=f"sqlite:///{(ARTIFACTS/'e2e.db').as_posix()}"
os.environ["AI_PROVIDER"]="mock"

import app.models  # noqa: E402,F401
from app.core.database import Base,engine  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
workspace=ARTIFACTS/"selected-project"
workspace.mkdir(exist_ok=True)
target=workspace/"iris-e2e-result.txt"
target.unlink(missing_ok=True)
with TestClient(app) as client:
    project=client.post("/api/coding/projects",json={"name":"Milestone Demo","directory":str(workspace),"aliases":["milestone-demo"]})
    assert project.status_code==201,project.text
    project_id=project.json()["id"]
    client.patch(f"/api/coding/projects/{project_id}",json={"write_access":True,"command_access":True})
    assert client.get("/api/coding/agents").json()[0]["available"]
    brief={"objective":"Create iris-e2e-result.txt containing exactly FIRST_OK.","project_id":project_id,"agent_id":"antigravity-cli",
        "architecture":"A disposable empty workspace.","acceptance_criteria":["File exists","File contains FIRST_OK"],
        "tests":["IRIS independently reads the generated file"],"restrictions":["Do not modify other paths"]}
    created=client.post("/api/coding/execution/tasks",json={"project_id":project_id,"agent_id":"antigravity-cli","instruction":"Create a one-line result file","brief":brief})
    assert created.status_code==201,created.text
    task_id=created.json()["id"]
    approved=client.post(f"/api/coding/execution/tasks/{task_id}/approve",json={"prompt":f"Create {target} with exactly one line: FIRST_OK. Do not run commands or edit other files."})
    assert approved.status_code==200,approved.text
    deadline=time.time()+180
    state=None
    while time.time()<deadline:
        response=client.get(f"/api/coding/execution/tasks/{task_id}/session")
        assert response.status_code==200,response.text
        state=response.json()
        status=state["task"]["status"]
        if status in {"completed","failed","interrupted","waiting_for_user"}:break
        time.sleep(2)
    assert state is not None
    if state["task"]["status"]=="failed" and "authentication" in str(state["task"].get("result",{})).lower():
        print("E2E blocked: sign in with the installed Antigravity CLI, then rerun this script.")
        raise SystemExit(2)
    assert state["task"]["status"]=="completed",json.dumps(state,indent=2)
    assert target.read_text(encoding="utf-8").strip()=="FIRST_OK"
    follow=client.post(f"/api/coding/execution/tasks/{task_id}/follow-up",json={"prompt":f"Append a second line containing exactly SECOND_OK to {target}; do not change the first line."})
    assert follow.status_code==200,follow.text
    child_id=follow.json()["id"]
    assert follow.json()["parent_task_id"]==task_id
    child_state=None
    deadline=time.time()+180
    while time.time()<deadline:
        response=client.get(f"/api/coding/execution/tasks/{child_id}/session")
        child_state=response.json()
        if child_state["task"]["status"] in {"completed","failed","interrupted","waiting_for_user"}:break
        time.sleep(2)
    assert child_state and child_state["task"]["status"]=="completed",json.dumps(child_state,indent=2)
    assert target.read_text(encoding="utf-8").splitlines()==["FIRST_OK","SECOND_OK"]
    print(json.dumps({"project_id":project_id,"task_id":task_id,"task_status":state["task"]["status"],
        "session_id":state["task"]["session_id"],"conversation_id":state["session"].get("session",{}).get("conversation_id"),
        "followup_task_id":child_id,"followup_status":child_state["task"]["status"],"file":str(target),"contents":target.read_text(encoding="utf-8")},indent=2))
