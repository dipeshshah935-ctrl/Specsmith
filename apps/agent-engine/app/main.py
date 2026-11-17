import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.config import EngineSettings
from app.orchestrator import build_orchestrator_graph
from app.schemas import ProjectBlueprintState, ProjectPhase

# Global compiled orchestrator graph instance
orchestrator_graph = None


def get_settings() -> EngineSettings:
    """Safely obtain EngineSettings, defaulting to mock mode if env variables are incomplete."""
    try:
        return EngineSettings()
    except Exception:
        return EngineSettings(USE_MOCK_LLM=True)


def get_graph():
    """Lazily initialize or retrieve the global compiled orchestrator graph."""
    global orchestrator_graph
    if orchestrator_graph is None:
        orchestrator_graph = build_orchestrator_graph()
    return orchestrator_graph


def _get_active_checkpoint(state_snapshot) -> Optional[str]:
    """Inspect pending interrupts to determine current active human checkpoint phase."""
    if not state_snapshot or not state_snapshot.tasks:
        return None
    for task in state_snapshot.tasks:
        if task.interrupts:
            val = task.interrupts[0].value
            if isinstance(val, dict):
                return val.get("phase") or val.get("checkpoint")
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager initializing the LangGraph state machine on startup."""
    global orchestrator_graph
    orchestrator_graph = build_orchestrator_graph()
    yield


app = FastAPI(
    title="Specsmith Blueprint Orchestrator Engine",
    description="Multi-Agent Technical Blueprint Engine API powered by LangGraph, FastAPI, and Pydantic v2.",
    version="1.0.0",
    lifespan=lifespan,
)

# 1. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 2. RFC 7807 Problem Details Exception Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": "about:blank",
            "title": exc.detail if isinstance(exc.detail, str) else "HTTP Error",
            "status": exc.status_code,
            "detail": exc.detail,
        },
        headers={"Content-Type": "application/problem+json"},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "type": "about:blank",
            "title": "Unprocessable Entity",
            "status": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "detail": exc.errors(),
        },
        headers={"Content-Type": "application/problem+json"},
    )


# =====================================================================
# REQUEST & RESPONSE DTOs
# =====================================================================


class StartProjectRequest(BaseModel):
    project_id: Optional[str] = None
    user_initial_prompt: str = Field(min_length=1)


class ResumeProjectRequest(BaseModel):
    action: Literal["APPROVE", "REVISE"]
    modified_ids: List[str] = Field(default_factory=list)
    feedback_notes: Optional[str] = None


# =====================================================================
# ENDPOINTS
# =====================================================================


@app.get("/health")
def health_check() -> Dict[str, Any]:
    """Health check endpoint indicating mock mode status."""
    settings = get_settings()
    return {"status": "ok", "mock_llm": settings.USE_MOCK_LLM}


@app.post("/orchestrator/start", status_code=status.HTTP_201_CREATED)
def start_project(request: StartProjectRequest) -> Dict[str, Any]:
    """Start a new project blueprint generation workflow, advancing until Checkpoint 1."""
    pid = request.project_id or str(uuid.uuid4())
    graph = get_graph()
    config = {"configurable": {"thread_id": pid}}

    initial_blueprint = ProjectBlueprintState(
        project_id=pid,
        user_initial_prompt=request.user_initial_prompt,
    )

    graph.invoke(
        {
            "blueprint": initial_blueprint.model_dump(mode="json"),
            "gate_1_retries": 0,
            "gate_2_retries": 0,
            "blast_radius": None,
            "version_history": [],
        },
        config=config,
    )

    state_snapshot = graph.get_state(config)
    values = state_snapshot.values or {}
    active_cp = _get_active_checkpoint(state_snapshot) or "GATE_1_REVIEW"

    return {
        "project_id": pid,
        "active_checkpoint": active_cp,
        "state": values.get("blueprint"),
        "versions": values.get("version_history", []),
    }


@app.post("/orchestrator/{project_id}/resume")
def resume_project(project_id: str, request: ResumeProjectRequest) -> Dict[str, Any]:
    """Resume execution from an active human checkpoint with APPROVE or REVISE."""
    graph = get_graph()
    config = {"configurable": {"thread_id": project_id}}
    state_snapshot = graph.get_state(config)

    if not state_snapshot.values:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    curr_bp = state_snapshot.values.get("blueprint", {})
    if curr_bp.get("current_phase") in ("COMPLETED", ProjectPhase.COMPLETED.value):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project workflow is already COMPLETED.",
        )

    if request.action == "REVISE" and len(request.modified_ids) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="modified_ids cannot be empty when action is REVISE.",
        )

    resume_payload = {
        "action": request.action,
        "modified_ids": request.modified_ids,
        "feedback_notes": request.feedback_notes,
    }

    graph.invoke(Command(resume=resume_payload), config=config)

    new_snapshot = graph.get_state(config)
    new_values = new_snapshot.values or {}
    active_cp = _get_active_checkpoint(new_snapshot)

    return {
        "project_id": project_id,
        "active_checkpoint": active_cp,
        "state": new_values.get("blueprint"),
        "versions": new_values.get("version_history", []),
    }


@app.get("/orchestrator/{project_id}/state")
def get_project_state(project_id: str) -> Dict[str, Any]:
    """Retrieve the current blueprint state and active checkpoint for a project."""
    graph = get_graph()
    config = {"configurable": {"thread_id": project_id}}
    state_snapshot = graph.get_state(config)

    if not state_snapshot.values:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    return {
        "project_id": project_id,
        "active_checkpoint": _get_active_checkpoint(state_snapshot),
        "state": state_snapshot.values.get("blueprint"),
    }


@app.get("/orchestrator/{project_id}/versions")
def get_project_versions(project_id: str) -> List[Dict[str, Any]]:
    """Retrieve the complete version snapshot history for side-by-side diffing."""
    graph = get_graph()
    config = {"configurable": {"thread_id": project_id}}
    state_snapshot = graph.get_state(config)

    if not state_snapshot.values:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    return state_snapshot.values.get("version_history", [])

