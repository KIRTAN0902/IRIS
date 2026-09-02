"""Project endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.core.errors import NotFoundError
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


def _to_out(db: Session, project: Project) -> ProjectOut:
    out = ProjectOut.model_validate(project)

    out.task_count = len(project.tasks) if "tasks" in project.__dict__ else 0
    return out


@router.get("", response_model=list[ProjectOut])
def list_projects(
    area: str | None = None,
    project_status: str | None = Query(None, alias="status"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Project).filter(Project.user_id == user.id)
    if area:
        q = q.filter(Project.area == area)
    if project_status:
        q = q.filter(Project.status == project_status)
    projects = q.order_by(Project.created_at.desc()).all()
    for p in projects:
        p.task_count = len(p.tasks)
    return [ProjectOut.model_validate(p) for p in projects]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    project = Project(user_id=user.id, **data.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    project.task_count = 0
    return ProjectOut.model_validate(project)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user.id).first()
    if not project:
        raise NotFoundError("Project not found.", code="PROJECT_NOT_FOUND")
    project.task_count = len(project.tasks)
    return ProjectOut.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    data: ProjectUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user.id).first()
    if not project:
        raise NotFoundError("Project not found.", code="PROJECT_NOT_FOUND")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    project.task_count = len(project.tasks)
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user.id).first()
    if not project:
        raise NotFoundError("Project not found.", code="PROJECT_NOT_FOUND")
    db.delete(project)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
