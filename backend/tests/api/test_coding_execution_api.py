from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def test_task_requires_review_and_scoped_permissions(client, tmp_path, monkeypatch):
    path=tmp_path/"registered"; path.mkdir()
    project=client.post("/api/coding/projects",json={"name":"Demo","directory":str(path),"aliases":["demo"]})
    assert project.status_code==201
    pid=project.json()["id"]
    brief={"objective":"Add a small feature","project_id":pid,"agent_id":"antigravity-cli","acceptance_criteria":["Feature works"]}
    task=client.post("/api/coding/execution/tasks",json={"project_id":pid,"instruction":"Add a small feature","brief":brief})
    assert task.status_code==201
    assert task.json()["status"]=="awaiting_approval"
    assert task.json()["approval_state"]=="pending"
    tid=task.json()["id"]
    denied=client.post(f"/api/coding/execution/tasks/{tid}/approve",json={"prompt":"Implement the feature"})
    assert denied.status_code==403
    client.patch(f"/api/coding/projects/{pid}",json={"write_access":True,"command_access":True})

    class Adapter:
        def detect(self): return {"available":True}
        def launch(self,directory,prompt,session_id,permissions=None): return SimpleNamespace(key="demo")

    monkeypatch.setattr("app.coding.antigravity.coding_agents.get",lambda _:Adapter())
    approved=client.post(f"/api/coding/execution/tasks/{tid}/approve",json={"prompt":"Implement the approved feature in this workspace"})
    assert approved.status_code==200
    assert approved.json()["status"]=="running"
    assert approved.json()["approval_state"]=="approved"


def test_project_resolution_reports_ambiguous_alias(client,tmp_path):
    for name in ("One","Two"):
        path=tmp_path/name; path.mkdir()
        assert client.post("/api/coding/projects",json={"name":name,"directory":str(path),"aliases":["same"]}).status_code==201
    result=client.get("/api/coding/projects/resolve",params={"q":"same"})
    assert result.status_code==200
    assert result.json()["status"]=="ambiguous"

def test_active_workspace_is_exclusive(client,tmp_path):
    ids=[]
    for name in ("Alpha","Beta"):
        path=tmp_path/name;path.mkdir()
        ids.append(client.post("/api/coding/projects",json={"name":name,"directory":str(path)}).json()["id"])
    client.patch(f"/api/coding/projects/{ids[0]}",json={"is_active":True})
    client.patch(f"/api/coding/projects/{ids[1]}",json={"is_active":True})
    active=client.get("/api/coding/projects/active").json()["project"]
    assert active["id"]==ids[1]
    by_id={p["id"]:p["is_active"] for p in client.get("/api/coding/projects").json()}
    assert by_id=={ids[0]:False,ids[1]:True}


def test_completed_task_followup_persists_child_session(client,db,tmp_path,monkeypatch):
    from app.models.coding_task import CodingTaskRecord,CodingSessionRecord
    path=tmp_path/"followup";path.mkdir()
    project=client.post("/api/coding/projects",json={"name":"Followup","directory":str(path)}).json()
    client.patch(f"/api/coding/projects/{project['id']}",json={"write_access":True,"command_access":True})
    brief={"objective":"Make a feature","project_id":project["id"],"agent_id":"antigravity-cli"}
    task=client.post("/api/coding/execution/tasks",json={"project_id":project["id"],"instruction":"Make a feature","brief":brief}).json()

    class Adapter:
        def get_status(self,key):
            return {"active":False,"session":{"alive":False,"state":"IDLE","conversation_id":"conversation-1"}}
        def resume_session_id(self,directory,alias,conversation_id,permissions):
            assert conversation_id=="conversation-1"
            return SimpleNamespace(key="resumed-manager")
        def send_prompt(self,key,prompt): return {"key":key}

    monkeypatch.setattr("app.coding.antigravity.coding_agents.get",lambda _:Adapter())
    row=db.query(CodingTaskRecord).filter_by(id=task["id"]).one()
    row.status="completed";row.session_id="session-parent"
    db.add(CodingSessionRecord(id="session-parent",task_id=row.id,agent_id=row.agent_id,project_id=row.project_id,
        directory=str(path),manager_key="manager-key",external_session_id="conversation-1",status="agent_reported_completion"))
    db.commit()
    response=client.post(f"/api/coding/execution/tasks/{row.id}/follow-up",json={"prompt":"Add one more small change"})
    assert response.status_code==200,response.text
    child=response.json()
    assert child["parent_task_id"]==row.id
    assert child["status"]=="running"
    assert db.query(CodingSessionRecord).filter_by(task_id=child["id"]).one().manager_key=="resumed-manager"


def test_resume_refuses_to_duplicate_live_agent_session(client,db,tmp_path,monkeypatch):
    from app.models.coding_task import CodingTaskRecord,CodingSessionRecord
    path=tmp_path/"resume";path.mkdir()
    project=client.post("/api/coding/projects",json={"name":"Resume","directory":str(path)}).json()
    client.patch(f"/api/coding/projects/{project['id']}",json={"write_access":True,"command_access":True})
    brief={"objective":"Make a feature","project_id":project["id"],"agent_id":"antigravity-cli"}
    task=client.post("/api/coding/execution/tasks",json={"project_id":project["id"],"instruction":"Make a feature","brief":brief}).json()
    row=db.query(CodingTaskRecord).filter_by(id=task["id"]).one()
    row.status="running";row.session_id="session-running"
    db.add(CodingSessionRecord(id="session-running",task_id=row.id,agent_id=row.agent_id,project_id=row.project_id,
        directory=str(path),manager_key="manager-key",external_session_id="conversation-1",status="running"));db.commit()

    class Adapter:
        def get_status(self,key): return {"active":True}
        def resume_session_id(self,*args): raise AssertionError("must not start a duplicate session")

    monkeypatch.setattr("app.coding.antigravity.coding_agents.get",lambda _:Adapter())
    response=client.post(f"/api/coding/execution/tasks/{row.id}/resume",json={})
    assert response.status_code==409
    assert "still running" in response.json()["error"]["message"]


def test_background_persistence_captures_completion_without_api_poll(client,db,tmp_path,monkeypatch):
    from app.models.coding_task import CodingTaskRecord,CodingSessionRecord
    from app.coding.persistence import persist_headless_sessions
    path=tmp_path/"persist";path.mkdir()
    project=client.post("/api/coding/projects",json={"name":"Persist","directory":str(path)}).json()
    brief={"objective":"Create a file","project_id":project["id"],"agent_id":"antigravity-cli"}
    task=client.post("/api/coding/execution/tasks",json={"project_id":project["id"],"instruction":"Create a file","brief":brief}).json()
    row=db.query(CodingTaskRecord).filter_by(id=task["id"]).one()
    row.status="running";row.session_id="session-persist"
    db.add(CodingSessionRecord(id="session-persist",task_id=row.id,agent_id=row.agent_id,project_id=row.project_id,
        directory=str(path),manager_key="manager-persist",status="running"));db.commit()
    snapshot={"state":"IDLE","conversation_id":"conversation-persist","last_result":{"status":"SUCCESS","response":"Created output."},
        "recent_output":"Created output.","warnings":[],"event_total":3,"events":[
            {"event":"init","conversation_id":"conversation-persist"},
            {"event":"step_update","step_update":{"step_type":"tool","tool_name":"write_file","state":"DONE","tool_info":{"parameters":{"Path":str(path/"output.txt")}}}},
            {"event":"result","result":{"status":"SUCCESS","response":"Created output."}}]}
    live=SimpleNamespace(key="manager-persist",snapshot=lambda:snapshot)
    monkeypatch.setattr("app.coding.headless.headless_manager.list_sessions",lambda:[live])
    persist_headless_sessions()
    db.refresh(row)
    session=db.query(CodingSessionRecord).filter_by(id="session-persist").one()
    assert row.status=="completed"
    assert session.external_session_id=="conversation-persist"
    assert "Created output." in session.output
    assert row.result["changed_files_reported_by_tools"]==[str(path/"output.txt")]


def test_interrupted_session_can_be_inspected_and_resumed(client,db,tmp_path,monkeypatch):
    from app.models.coding_task import CodingTaskRecord,CodingSessionRecord
    path=tmp_path/"restart";path.mkdir()
    project=client.post("/api/coding/projects",json={"name":"Restart","directory":str(path)}).json()
    client.patch(f"/api/coding/projects/{project['id']}",json={"write_access":True,"command_access":True})
    brief={"objective":"Make a feature","project_id":project["id"],"agent_id":"antigravity-cli"}
    task=client.post("/api/coding/execution/tasks",json={"project_id":project["id"],"instruction":"Make a feature","brief":brief}).json()
    row=db.query(CodingTaskRecord).filter_by(id=task["id"]).one()
    row.status="running";row.session_id="session-restart"
    db.add(CodingSessionRecord(id="session-restart",task_id=row.id,agent_id=row.agent_id,project_id=row.project_id,
        directory=str(path),manager_key="old-manager",external_session_id="conversation-restart",status="running",output="Saved before restart"));db.commit()

    class Adapter:
        def get_status(self,key): return {"active":False}
        def resume_session_id(self,*args): return SimpleNamespace(key="new-manager")

    monkeypatch.setattr("app.coding.antigravity.coding_agents.get",lambda _:Adapter())
    inspected=client.get(f"/api/coding/execution/tasks/{row.id}/session")
    assert inspected.status_code==200
    assert inspected.json()["task"]["status"]=="interrupted"
    assert inspected.json()["session"]["persisted_output"]=="Saved before restart"
    resumed=client.post(f"/api/coding/execution/tasks/{row.id}/resume",json={})
    assert resumed.status_code==200,resumed.text
    assert resumed.json()["status"]=="running"
    assert db.query(CodingSessionRecord).filter_by(id="session-restart").one().manager_key=="new-manager"
