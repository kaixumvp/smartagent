import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Workflow, WorkflowInteraction, WorkflowNodeRun, WorkflowRun, WorkflowVersion
from ..schemas import (
    InteractionDecision,
    InteractionSubmit,
    WorkflowCreate,
    WorkflowDraftUpdate,
    WorkflowRunRequest,
)
from ..workflow_engine import (
    _node_output_context,
    queue_interaction_resume,
    _validate_json_value,
    start_run,
    validate_definition,
)

router = APIRouter(tags=["workflows"])

_STARTER_DEFINITION = {
    "schema_version": 1,
    "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    "output_schema": {"type": "object", "properties": {}, "additionalProperties": True},
    "nodes": [{"id": "start", "type": "start"}, {"id": "end", "type": "end", "output_mapping": {}}],
    "edges": [{"from": "start", "to": "end"}],
}


def _workflow_or_404(db: Session, workflow_id: uuid.UUID) -> Workflow:
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


def _draft(db: Session, workflow_id: uuid.UUID, *, lock: bool = False) -> WorkflowVersion | None:
    query = (
        db.query(WorkflowVersion)
        .filter_by(workflow_id=workflow_id, status="draft")
        .order_by(WorkflowVersion.version_no.desc())
    )
    if lock:
        query = query.with_for_update()
    return query.first()


def _version_view(version: WorkflowVersion | None) -> dict[str, Any] | None:
    if version is None:
        return None
    return {
        "id": str(version.id),
        "version_no": version.version_no,
        "status": version.status,
        "revision": version.revision,
        "definition": version.definition,
        "published_at": version.published_at.isoformat() if version.published_at else None,
    }


def _workflow_view(db: Session, workflow: Workflow) -> dict[str, Any]:
    active = db.get(WorkflowVersion, workflow.active_version_id) if workflow.active_version_id else None
    draft = _draft(db, workflow.id)
    return {
        "id": str(workflow.id),
        "name": workflow.name,
        "display_name": workflow.display_name,
        "description": workflow.description,
        "enabled": workflow.enabled,
        "active_version": _version_view(active),
        "draft": _version_view(draft),
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
        "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
    }


def _run_view(db: Session, run: WorkflowRun) -> dict[str, Any]:
    node_runs = (
        db.query(WorkflowNodeRun)
        .filter_by(workflow_run_id=run.id)
        .order_by(WorkflowNodeRun.started_at)
        .all()
    )
    interaction = (
        db.query(WorkflowInteraction)
        .filter_by(workflow_run_id=run.id, status="open")
        .order_by(WorkflowInteraction.id.desc())
        .first()
    )
    return {
        "workflow_run_id": str(run.id),
        "workflow_id": str(run.workflow_id),
        "workflow_version_id": str(run.workflow_version_id),
        "status": run.status,
        "current_node_id": run.current_node_id,
        "input": run.input_data,
        "output": run.output,
        "error": run.error,
        "correlation_id": run.correlation_id,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "interaction": {
            "id": str(interaction.id),
            "kind": interaction.kind,
            "title": interaction.title,
            "status": interaction.status,
        } if interaction else None,
        "node_runs": [
            {
                "node_id": item.node_id,
                "status": item.status,
                "input": item.input_data,
                "output": item.output,
                "error": item.error,
                "started_at": item.started_at.isoformat() if item.started_at else None,
                "finished_at": item.finished_at.isoformat() if item.finished_at else None,
            }
            for item in node_runs
        ],
    }


@router.post("/workflows", status_code=201)
def create_workflow(payload: WorkflowCreate, db: Session = Depends(get_db)):
    if db.query(Workflow).filter_by(name=payload.name).first():
        raise HTTPException(status_code=409, detail="Workflow name already exists")
    workflow = Workflow(
        name=payload.name,
        display_name=payload.display_name,
        description=payload.description,
    )
    db.add(workflow)
    db.flush()
    version = WorkflowVersion(
        workflow_id=workflow.id,
        version_no=1,
        status="draft",
        definition=payload.definition or _STARTER_DEFINITION,
    )
    db.add(version)
    db.commit()
    db.refresh(workflow)
    return _workflow_view(db, workflow)


@router.get("/workflows")
def list_workflows(db: Session = Depends(get_db)):
    return [_workflow_view(db, item) for item in db.query(Workflow).order_by(Workflow.updated_at.desc()).all()]


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: uuid.UUID, db: Session = Depends(get_db)):
    return _workflow_view(db, _workflow_or_404(db, workflow_id))


@router.put("/workflows/{workflow_id}/draft")
def save_draft(
    workflow_id: uuid.UUID,
    payload: WorkflowDraftUpdate,
    db: Session = Depends(get_db),
):
    workflow = _workflow_or_404(db, workflow_id)
    draft = _draft(db, workflow.id)
    if draft is None:
        previous = db.get(WorkflowVersion, workflow.active_version_id) if workflow.active_version_id else None
        draft = WorkflowVersion(
            workflow_id=workflow.id,
            version_no=(previous.version_no if previous else 0) + 1,
            status="draft",
            definition=previous.definition if previous else _STARTER_DEFINITION,
        )
        db.add(draft)
        db.flush()
    if draft.revision != payload.revision:
        raise HTTPException(status_code=409, detail="Draft changed; reload before saving")
    saved = db.execute(
        update(WorkflowVersion)
        .where(
            WorkflowVersion.id == draft.id,
            WorkflowVersion.status == "draft",
            WorkflowVersion.revision == payload.revision,
        )
        .values(definition=payload.definition, revision=WorkflowVersion.revision + 1)
    )
    if saved.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Draft changed; reload before saving")
    db.commit()
    db.refresh(draft)
    return _workflow_view(db, workflow)


@router.post("/workflows/{workflow_id}/validate")
def validate_workflow(workflow_id: uuid.UUID, db: Session = Depends(get_db)):
    workflow = _workflow_or_404(db, workflow_id)
    draft = _draft(db, workflow.id)
    if draft is None:
        raise HTTPException(status_code=409, detail="Workflow has no draft")
    try:
        validate_definition(db, draft.definition)
    except ValueError as exc:
        return {"valid": False, "errors": [str(exc)]}
    return {"valid": True, "errors": []}


@router.post("/workflows/{workflow_id}/publish")
def publish_workflow(workflow_id: uuid.UUID, db: Session = Depends(get_db)):
    workflow = _workflow_or_404(db, workflow_id)
    draft = _draft(db, workflow.id, lock=True)
    if draft is None:
        raise HTTPException(status_code=409, detail="Workflow has no draft")
    try:
        validate_definition(db, draft.definition)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    draft.status = "published"
    draft.published_at = datetime.now(timezone.utc)
    workflow.active_version_id = draft.id
    workflow.enabled = True
    db.commit()
    db.refresh(workflow)
    return _workflow_view(db, workflow)


@router.post("/workflows/{workflow_id}/disable")
def disable_workflow(workflow_id: uuid.UUID, db: Session = Depends(get_db)):
    workflow = _workflow_or_404(db, workflow_id)
    workflow.enabled = False
    db.commit()
    return _workflow_view(db, workflow)


@router.post("/workflows/{workflow_id}/enable")
def enable_workflow(workflow_id: uuid.UUID, db: Session = Depends(get_db)):
    workflow = _workflow_or_404(db, workflow_id)
    if workflow.active_version_id is None:
        raise HTTPException(status_code=409, detail="Publish a Workflow before enabling it")
    workflow.enabled = True
    db.commit()
    return _workflow_view(db, workflow)


def _execute_workflow(
    db: Session,
    workflow: Workflow,
    version: WorkflowVersion,
    payload: WorkflowRunRequest,
):
    return start_run(
        db,
        workflow,
        version,
        payload.arguments,
        payload.context,
        payload.idempotency_key,
        payload.correlation_id,
    )


@router.post("/workflows/{workflow_id}/test-runs")
def test_run(workflow_id: uuid.UUID, payload: WorkflowRunRequest, db: Session = Depends(get_db)):
    workflow = _workflow_or_404(db, workflow_id)
    version = _draft(db, workflow.id)
    if version is None:
        raise HTTPException(status_code=409, detail="Workflow has no draft")
    try:
        validate_definition(db, version.definition)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = _execute_workflow(db, workflow, version, payload)
    return result


@router.post("/workflows/{workflow_id}/runs")
def run_workflow(workflow_id: uuid.UUID, payload: WorkflowRunRequest, db: Session = Depends(get_db)):
    workflow = _workflow_or_404(db, workflow_id)
    if not workflow.enabled or not workflow.active_version_id:
        raise HTTPException(status_code=409, detail="Workflow is not enabled and published")
    version = db.get(WorkflowVersion, workflow.active_version_id)
    if version is None or version.status != "published":
        raise HTTPException(status_code=409, detail="Published Workflow version is unavailable")
    return _execute_workflow(db, workflow, version, payload)


@router.get("/workflows/{workflow_id}/runs")
def list_workflow_runs(workflow_id: uuid.UUID, db: Session = Depends(get_db)):
    _workflow_or_404(db, workflow_id)
    runs = (
        db.query(WorkflowRun)
        .filter_by(workflow_id=workflow_id)
        .order_by(WorkflowRun.started_at.desc())
        .limit(100)
        .all()
    )
    return [_run_view(db, item) for item in runs]


@router.get("/workflow-runs/{run_id}")
def get_workflow_run(run_id: uuid.UUID, db: Session = Depends(get_db)):
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return _run_view(db, run)


@router.get("/workflow-runs/{run_id}/interactions")
def list_run_interactions(run_id: uuid.UUID, db: Session = Depends(get_db)):
    if db.get(WorkflowRun, run_id) is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return [
        {
            "id": str(item.id),
            "node_id": item.node_id,
            "kind": item.kind,
            "status": item.status,
            "title": item.title,
            "revision": item.revision,
        }
        for item in db.query(WorkflowInteraction).filter_by(workflow_run_id=run_id).order_by(WorkflowInteraction.id).all()
    ]


@router.get("/interactions")
def list_interactions(status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(WorkflowInteraction)
    if status:
        query = query.filter_by(status=status)
    return [
        {
            "id": str(item.id),
            "workflow_run_id": str(item.workflow_run_id),
            "node_id": item.node_id,
            "kind": item.kind,
            "status": item.status,
            "title": item.title,
            "prompt": item.prompt,
            "form_schema": item.form_schema,
            "display_data": item.display_data,
            "due_at": item.due_at.isoformat() if item.due_at else None,
            "revision": item.revision,
        }
        for item in query.order_by(WorkflowInteraction.due_at, WorkflowInteraction.id).limit(200).all()
    ]


@router.get("/interactions/{interaction_id}")
def get_interaction(interaction_id: uuid.UUID, db: Session = Depends(get_db)):
    interaction = db.get(WorkflowInteraction, interaction_id)
    if interaction is None:
        raise HTTPException(status_code=404, detail="Workflow interaction not found")
    return {
        "id": str(interaction.id),
        "workflow_run_id": str(interaction.workflow_run_id),
        "node_id": interaction.node_id,
        "kind": interaction.kind,
        "status": interaction.status,
        "title": interaction.title,
        "prompt": interaction.prompt,
        "form_schema": interaction.form_schema,
        "display_data": interaction.display_data,
        "due_at": interaction.due_at.isoformat() if interaction.due_at else None,
        "revision": interaction.revision,
    }


def _ensure_not_expired(item: WorkflowInteraction) -> None:
    if item.due_at and item.due_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="Interaction has expired")


@router.post("/interactions/{interaction_id}/submit")
def submit_interaction(
    interaction_id: uuid.UUID,
    payload: InteractionSubmit,
    db: Session = Depends(get_db),
):
    item = db.get(WorkflowInteraction, interaction_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Workflow interaction not found")
    if item.kind != "input":
        raise HTTPException(status_code=409, detail="This interaction requires an approval decision")
    _ensure_not_expired(item)
    try:
        _validate_json_value(payload.response, item.form_schema or {"type": "object"})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    run = db.get(WorkflowRun, item.workflow_run_id)
    if run is None:
        raise HTTPException(status_code=409, detail="Workflow run is unavailable")
    try:
        _node_output_context(item.resume_context, item.node_id, payload.response)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    if payload.revision != item.revision:
        raise HTTPException(status_code=409, detail="Interaction changed; reload before submitting")
    result = queue_interaction_resume(db, item, payload.response, payload.comment)
    return result


@router.post("/interactions/{interaction_id}/decide")
def decide_interaction(
    interaction_id: uuid.UUID,
    payload: InteractionDecision,
    db: Session = Depends(get_db),
):
    item = db.get(WorkflowInteraction, interaction_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Workflow interaction not found")
    if item.kind != "approval":
        raise HTTPException(status_code=409, detail="This interaction requires a form submission")
    _ensure_not_expired(item)
    if payload.decision == "return":
        run = db.get(WorkflowRun, item.workflow_run_id)
        version = db.get(WorkflowVersion, run.workflow_version_id) if run else None
        if version is None or _next_edge(version.definition, item.node_id, "returned") is None:
            raise HTTPException(status_code=422, detail="This approval node has no return path")
    try:
        _node_output_context(
            item.resume_context,
            item.node_id,
            {"decision": payload.decision, "comment": payload.comment},
        )
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    if payload.revision != item.revision:
        raise HTTPException(status_code=409, detail="Interaction changed; reload before deciding")
    result = queue_interaction_resume(
        db,
        item,
        {"decision": payload.decision},
        payload.comment,
        payload.decision,
    )
    return result


def _next_edge(definition: dict[str, Any], node_id: str, branch: str) -> dict[str, Any] | None:
    return next(
        (edge for edge in definition.get("edges", []) if edge.get("from") == node_id and edge.get("branch") == branch),
        None,
    )
