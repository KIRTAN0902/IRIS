from datetime import UTC, datetime, timedelta

import pytest

from app.coworkers.computer_use import run_mock_demo
from app.coworkers.contracts import coworker_transition, transition
from app.coworkers.execution import recover_interrupted_tasks
from app.coworkers.execution import user_safe_task_error
from app.ai.provider import AIRateLimitError, AIConnectionError
from app.models.coworker import Coworker, CoworkerApproval, CoworkerEvent, CoworkerTask
from app.models.coding_project import CodingProject


def make_coworker(client, **overrides):
    payload={"name":"Researcher One","role":"Researcher","description":"Research",
             "specialisation":"evidence", "responsibilities":["compare sources"],
             "allowed_capabilities":["search_memory"],"permission_profile":{}}
    payload.update(overrides)
    response=client.post("/api/coworkers",json=payload)
    assert response.status_code==201,response.text
    return response.json()


def test_task_and_coworker_lifecycle_reject_invalid_transitions():
    assert transition("queued","running")=="running"
    assert coworker_transition("idle","assigned")=="assigned"
    with pytest.raises(ValueError): transition("completed","running")
    with pytest.raises(ValueError): coworker_transition("idle","completed")


def test_execution_failures_have_safe_actionable_task_messages():
    provider_error = AIRateLimitError(
        "API_KEY=private-value prompt=private-user-content provider response body"
    )
    rate_message = user_safe_task_error(provider_error)
    assert "rate limited" in rate_message
    assert "private-value" not in rate_message
    assert "private-user-content" not in rate_message

    network_message = user_safe_task_error(AIConnectionError("internal URL with credentials"))
    assert "Check connectivity" in network_message
    assert "credentials" not in network_message


def test_templates_custom_worker_and_task_assignment_are_persisted(client):
    templates=client.get("/api/coworkers/templates")
    assert templates.status_code==200
    assert {x["key"] for x in templates.json()} >= {"researcher","developer","analyst","writer","project_manager"}
    coworker=make_coworker(client)
    assigned=client.post(f"/api/coworkers/{coworker['id']}/tasks",json={
        "instruction":"Compare the supplied references", "objectives":["List evidence"],
        "acceptance_criteria":["Separate facts and inference"], "required_capabilities":["search_memory"],
        "run":False,
    })
    assert assigned.status_code==202,assigned.text
    task=assigned.json()
    assert task["status"]=="queued" and task["coworker_id"]==coworker["id"]
    events=client.get(f"/api/coworkers/tasks/{task['id']}/events").json()
    assert [x["type"] for x in events]==["task_assigned"]
    assert client.post(f"/api/coworkers/tasks/{task['id']}/cancel").status_code==200
    denied=client.post(f"/api/coworkers/{coworker['id']}/tasks",json={
        "instruction":"Do an ungranted action", "required_capabilities":["create_goal"],"run":False,
    })
    assert denied.status_code==403


def test_approval_is_action_scoped_and_rejection_cancels_only_task(client, db):
    coworker=make_coworker(client,allowed_capabilities=["create_goal"])
    task=client.post(f"/api/coworkers/{coworker['id']}/tasks",json={
        "instruction":"Create the requested goal","required_capabilities":["create_goal"],"run":False,
    }).json()
    row=db.query(CoworkerTask).filter_by(id=task["id"]).one(); row.status="running"
    db.query(Coworker).filter_by(id=coworker["id"]).one().status="working"; db.commit()
    requested=client.post(f"/api/coworkers/tasks/{task['id']}/capabilities/create_goal/invoke",json={"arguments":{"name":"Milestone test"}})
    assert requested.status_code==200,requested.text
    assert requested.json()["status"]=="awaiting_approval"
    approval_id=requested.json()["approval_id"]
    approval=client.get("/api/coworkers/approvals").json()[0]
    assert approval["id"]==approval_id and approval["action"]=={"name":"Milestone test"}
    decision=client.post(f"/api/coworkers/approvals/{approval_id}/decision?approved=false",json={"reason":"Not needed"})
    assert decision.status_code==200
    assert decision.json()["status"]=="rejected"
    db.refresh(row)
    assert row.status=="cancelled"
    assert db.query(CoworkerApproval).filter_by(id=approval_id).one().status=="rejected"


def test_approved_tool_executes_only_stored_action(client, db):
    from app.models.goal import Goal
    coworker=make_coworker(client,allowed_capabilities=["create_goal"])
    task=client.post(f"/api/coworkers/{coworker['id']}/tasks",json={"instruction":"Create a scoped test goal",
        "required_capabilities":["create_goal"],"run":False}).json()
    db.query(CoworkerTask).filter_by(id=task["id"]).update({"status":"running"})
    db.commit()
    request=client.post(f"/api/coworkers/tasks/{task['id']}/capabilities/create_goal/invoke",
        json={"arguments":{"name":"Approved coworker goal","area":"STARTUP"}}).json()
    result=client.post(f"/api/coworkers/approvals/{request['approval_id']}/decision?approved=true",json={})
    assert result.status_code==200,result.text
    assert result.json()["status"]=="approved"
    assert result.json()["execution"]["success"] is True
    assert db.query(Goal).filter_by(name="Approved coworker goal").count()==1


def test_pending_approval_expires_and_is_not_reusable(client, db):
    coworker=make_coworker(client,allowed_capabilities=["create_goal"])
    task=client.post(f"/api/coworkers/{coworker['id']}/tasks",json={"instruction":"Create goal","required_capabilities":["create_goal"],"run":False}).json()
    row=db.query(CoworkerTask).filter_by(id=task["id"]).one(); row.status="running"; db.commit()
    req=client.post(f"/api/coworkers/tasks/{task['id']}/capabilities/create_goal/invoke",json={"arguments":{"name":"Expire"}}).json()
    approval=db.query(CoworkerApproval).filter_by(id=req["approval_id"]).one()
    approval.expires_at=datetime.now(UTC)-timedelta(seconds=1); db.commit()
    response=client.post(f"/api/coworkers/approvals/{approval.id}/decision?approved=true",json={})
    assert response.status_code==410
    db.refresh(approval)
    assert approval.status=="expired"


def test_workspace_scoped_capabilities_deny_host_execution(client, db):
    coworker=make_coworker(client,allowed_capabilities=["run_laptop_terminal_command"])
    task=client.post(f"/api/coworkers/{coworker['id']}/tasks",json={"instruction":"Run command","required_capabilities":["run_laptop_terminal_command"],"run":False}).json()
    row=db.query(CoworkerTask).filter_by(id=task["id"]).one(); row.status="running"; db.commit()
    response=client.post(f"/api/coworkers/tasks/{task['id']}/capabilities/run_laptop_terminal_command/invoke",json={"arguments":{"command":"whoami"}})
    assert response.status_code==403
    assert db.query(CoworkerApproval).filter_by(task_id=task["id"]).count()==0
    assert db.query(CoworkerEvent).filter_by(task_id=task["id"],event_type="capability_denied").count()==1


def test_restart_recovery_surfaces_running_task_without_retry(db):
    from app.core.security import get_current_user
    user=get_current_user(db)
    coworker=Coworker(id="c1",user_id=user.id,name="Researcher",role="Researcher",description="",specialisation="research",
        responsibilities=[],system_instructions="",allowed_capabilities=[],permission_profile={},status="working",availability=True,config_version=1)
    db.add(coworker); db.flush()
    task=CoworkerTask(id="t1",user_id=user.id,coworker_id=coworker.id,instruction="Work",objectives=[],acceptance_criteria=[],
        required_capabilities=[],dependencies=[],permission_scope={},status="running")
    db.add(task); db.commit()
    assert recover_interrupted_tasks(db)==1
    db.refresh(task)
    assert task.status=="interrupted"
    assert "restarted" in task.error
    assert recover_interrupted_tasks(db)==0


def test_mock_computer_use_demo_is_explicitly_simulated():
    import asyncio
    result=asyncio.run(run_mock_demo("unit-test"))
    assert result.is_mock is True
    assert result.status=="completed"
    assert result.evidence[0]["is_mock"] is True
    assert [e.kind for e in result.events][-2:]==["execution_stopped","environment_released"]


def test_coworker_execution_uses_existing_provider_and_persists_result(client, monkeypatch):
    from app.ai.providers.mock import MockProvider
    import app.coworkers.execution as execution
    monkeypatch.setattr(execution,"get_ai_provider",lambda *args,**kwargs:MockProvider(
        default_response_generator=lambda **_: {"message":"Draft prepared; no external actions were performed."}))
    coworker=make_coworker(client,allowed_capabilities=[])
    task=client.post(f"/api/coworkers/{coworker['id']}/tasks",json={"instruction":"Prepare a concise draft", "run":True})
    assert task.status_code==202,task.text
    tasks=client.get("/api/coworkers/tasks?status=completed").json()
    result=next(t for t in tasks if t["id"]==task.json()["id"])
    assert result["output"]=="Draft prepared; no external actions were performed."
    assert result["verification"]["state"]=="deliverable_persisted"
    assert result["verification"]["independently_verified"] is False
    assert result["verification"]["checks"][0]["passed"] is True


def test_acceptance_criteria_require_user_review_before_completion(client, monkeypatch):
    from app.ai.providers.mock import MockProvider
    import app.coworkers.execution as execution
    monkeypatch.setattr(execution,"get_ai_provider",lambda *args,**kwargs:MockProvider(
        default_response_generator=lambda **_: {"message":"Draft prepared."}))
    coworker=make_coworker(client,allowed_capabilities=[])
    response=client.post(f"/api/coworkers/{coworker['id']}/tasks",json={
        "instruction":"Prepare the requested draft", "acceptance_criteria":["Covers all requested points"], "run":True})
    task_id=response.json()["id"]
    task=next(t for t in client.get("/api/coworkers/tasks").json() if t["id"]==task_id)
    assert task["status"]=="completed_with_issues"
    assert task["verification"]["state"]=="awaiting_user_review"
    assert task["verification"]["unresolved_items"]==["Covers all requested points"]
    reviewed=client.post(f"/api/coworkers/tasks/{task_id}/review",json={
        "accepted":True,"reason":"Reviewed against the requested points."})
    assert reviewed.status_code==200,reviewed.text
    assert reviewed.json()["status"]=="completed"
    assert reviewed.json()["verification"]["state"]=="user_reviewed"
    assert reviewed.json()["verification"]["independently_verified"] is False


def test_developer_coworker_hands_off_to_reviewed_coding_workflow(client, db):
    from tests.conftest import _TMP_DIR
    from app.core.security import get_current_user
    user=get_current_user(db)
    workspace=_TMP_DIR/"coworker-sample-workspace"; workspace.mkdir(exist_ok=True)
    project=CodingProject(user_id=user.id,name="Sample",directory=str(workspace),aliases=[],description="test project",
        read_access=True,write_access=False,command_access=False,allowed_commands=[],allowed_domains=[],network_access=False,
        active=True,is_active=False)
    db.add(project); db.commit(); db.refresh(project)
    coworker=make_coworker(client,name="Dev",role="Developer",project_id=project.id,allowed_capabilities=[])
    response=client.post(f"/api/coworkers/{coworker['id']}/tasks",json={
        "instruction":"Add a greeting feature", "objectives":["Implement the feature"],
        "acceptance_criteria":["Greeting is visible"], "run":True,
    })
    assert response.status_code==202,response.text
    task=client.get(f"/api/coworkers/{coworker['id']}").json()["tasks"][0]
    assert task["status"]=="waiting_input"
    assert task["coding_task_id"]
    assert task["verification"]["state"]=="awaiting_user_approval"
    from app.models.coding_task import CodingTaskRecord
    coding=db.query(CodingTaskRecord).filter_by(id=task["coding_task_id"]).one()
    assert coding.status=="awaiting_approval"
    assert coding.approved_prompt is None


def test_developer_completion_without_independent_verification_requires_review(client, db):
    from tests.conftest import _TMP_DIR
    from app.core.security import get_current_user
    from app.models.coding_task import CodingTaskRecord
    user=get_current_user(db)
    workspace=_TMP_DIR/"coworker-review-workspace"; workspace.mkdir(exist_ok=True)
    project=CodingProject(user_id=user.id,name="Review Sample",directory=str(workspace),aliases=[],description="test project",
        read_access=True,write_access=False,command_access=False,allowed_commands=[],allowed_domains=[],network_access=False,
        active=True,is_active=False)
    db.add(project); db.commit(); db.refresh(project)
    coworker=make_coworker(client,name="Dev Review",role="Developer",project_id=project.id,allowed_capabilities=[])
    created=client.post(f"/api/coworkers/{coworker['id']}/tasks",json={"instruction":"Implement a feature","run":True}).json()
    handed_off=client.get(f"/api/coworkers/{coworker['id']}").json()["tasks"][0]
    coding=db.query(CodingTaskRecord).filter_by(id=handed_off["coding_task_id"]).one()
    coding.status="completed"; coding.result={"summary":"Implemented"}; coding.verification={"state":"agent_reported","independently_verified":False}
    db.commit()
    first=client.get(f"/api/coworkers/{coworker['id']}").json()["tasks"][0]
    assert first["status"]=="completed_with_issues"
    accepted=client.post(f"/api/coworkers/tasks/{first['id']}/review",json={"reason":"I reviewed the coding report."})
    assert accepted.status_code==200 and accepted.json()["status"]=="completed"
    again=client.get(f"/api/coworkers/{coworker['id']}").json()["tasks"][0]
    assert again["status"]=="completed"


def test_computer_use_demo_endpoint_labels_simulation(client):
    providers=client.get("/api/coworkers/computer-use/providers")
    assert providers.status_code==200 and providers.json()[0]["is_mock"] is True
    result=client.post("/api/coworkers/computer-use/demo",json={"task_id":"test"})
    assert result.status_code==200
    assert result.json()["is_mock"] is True
    assert result.json()["evidence"][0]["kind"]=="simulated_ui_state"


def test_supervisor_recommendation_uses_specialisation_and_availability(client):
    writer=make_coworker(client,name="Writer",role="Writer",specialisation="documentation and prose")
    analyst=make_coworker(client,name="Analyst",role="Analyst",specialisation="data comparisons")
    response=client.post("/api/coworkers/recommend",json={"instruction":"Compare two datasets and analyse the numbers"})
    assert response.status_code==200
    assert response.json()["recommendation"]["coworker_id"]==analyst["id"]
    assert response.json()["recommendation"]["requires_user_choice"] is False
    assert writer["id"]!=analyst["id"]


def test_dependencies_block_until_parent_and_propagate_failure(client):
    first=make_coworker(client,name="First",role="Analyst")
    second=make_coworker(client,name="Second",role="Writer")
    parent=client.post(f"/api/coworkers/{first['id']}/tasks",json={"instruction":"Prepare input","run":False}).json()
    child=client.post(f"/api/coworkers/{second['id']}/tasks",json={"instruction":"Use the prepared input",
        "parent_task_id":parent["id"],"dependencies":[parent["id"]],"run":False})
    assert child.status_code==202,child.text
    before=client.post(f"/api/coworkers/tasks/{child.json()['id']}/run")
    assert before.status_code==409
    assert client.post(f"/api/coworkers/tasks/{parent['id']}/cancel").status_code==200
    after=client.post(f"/api/coworkers/tasks/{child.json()['id']}/run")
    assert after.status_code==202 and after.json()["status"]=="failed"
    assert "Dependency" in after.json()["error"]


def test_archiving_coworker_preserves_task_history(client):
    coworker=make_coworker(client)
    task=client.post(f"/api/coworkers/{coworker['id']}/tasks",json={"instruction":"Retained history","run":False}).json()
    client.post(f"/api/coworkers/tasks/{task['id']}/cancel")
    archived=client.delete(f"/api/coworkers/{coworker['id']}")
    assert archived.status_code==200 and archived.json()["status"]=="stopped"
    detail=client.get(f"/api/coworkers/{coworker['id']}")
    assert detail.status_code==200 and detail.json()["tasks"][0]["id"]==task["id"]
