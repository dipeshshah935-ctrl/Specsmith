from typing import Any, Dict, List, Literal, Optional, Set, TypedDict
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agents.api_arch import run_api_architect
from app.agents.db_arch import run_database_architect
from app.agents.product_arch import run_product_architect
from app.agents.req_analyst import run_requirement_analyst
from app.agents.validator_critic import run_validation_gate
from app.config import EngineSettings
from app.propagator import DAGChangePropagator
from app.schemas import (
    DefectSeverity,
    ProjectBlueprintState,
    ProjectPhase,
    ValidationDefect,
    ValidationStatus,
)

MAX_AUTO_RETRIES = 2


class OrchestratorGraphState(TypedDict):
    blueprint: dict
    gate_1_retries: int
    gate_2_retries: int
    blast_radius: Optional[Dict[str, List[str]]]
    version_history: List[dict]


def _extract_blast_sets(
    blast_dict: Optional[Dict[str, List[str]]],
) -> Optional[Dict[str, Set[str]]]:
    if not blast_dict:
        return None
    return {k: set(v) for k, v in blast_dict.items()}


def _extract_latest_defects(
    blueprint_state: ProjectBlueprintState,
    target_agent: Optional[str] = None,
) -> Optional[List[ValidationDefect]]:
    if not blueprint_state.validation_reports:
        return None
    latest_report = blueprint_state.validation_reports[-1]
    if latest_report.status == ValidationStatus.FAILED:
        if target_agent:
            return [d for d in latest_report.defects if d.target_agent == target_agent]
        return latest_report.defects
    return None


def _upsert_version_history(history: List[dict], blueprint_dict: dict) -> List[dict]:
    updated_history = list(history or [])
    curr_version = blueprint_dict.get("version")
    for i, item in enumerate(updated_history):
        if item.get("version") == curr_version:
            updated_history[i] = blueprint_dict
            return updated_history
    updated_history.append(blueprint_dict)
    return updated_history


# =====================================================================
# AGENT NODE WRAPPERS
# =====================================================================


def requirement_analyst_node(state: OrchestratorGraphState) -> Dict[str, Any]:
    blueprint_state = ProjectBlueprintState.model_validate(state["blueprint"])
    blast = _extract_blast_sets(state.get("blast_radius"))
    defects = _extract_latest_defects(blueprint_state, target_agent="RequirementAnalyst")

    updated = run_requirement_analyst(
        state=blueprint_state,
        blast_radius=blast,
        retry_defects=defects,
    )
    return {"blueprint": updated.model_dump(mode="json")}


def product_architect_node(state: OrchestratorGraphState) -> Dict[str, Any]:
    blueprint_state = ProjectBlueprintState.model_validate(state["blueprint"])
    blast = _extract_blast_sets(state.get("blast_radius"))
    defects = _extract_latest_defects(blueprint_state, target_agent="ProductArchitect")

    updated = run_product_architect(
        state=blueprint_state,
        blast_radius=blast,
        retry_defects=defects,
    )
    return {"blueprint": updated.model_dump(mode="json")}


def database_architect_node(state: OrchestratorGraphState) -> Dict[str, Any]:
    blueprint_state = ProjectBlueprintState.model_validate(state["blueprint"])
    blast = _extract_blast_sets(state.get("blast_radius"))
    defects = _extract_latest_defects(blueprint_state, target_agent="DatabaseArchitect")

    updated = run_database_architect(
        state=blueprint_state,
        blast_radius=blast,
        retry_defects=defects,
    )
    return {"blueprint": updated.model_dump(mode="json")}


def api_architect_node(state: OrchestratorGraphState) -> Dict[str, Any]:
    blueprint_state = ProjectBlueprintState.model_validate(state["blueprint"])
    blast = _extract_blast_sets(state.get("blast_radius"))
    defects = _extract_latest_defects(blueprint_state, target_agent="APIArchitect")

    updated = run_api_architect(
        state=blueprint_state,
        blast_radius=blast,
        retry_defects=defects,
    )
    return {"blueprint": updated.model_dump(mode="json")}


# =====================================================================
# VALIDATION GATE NODES
# =====================================================================


def validation_gate_1_node(state: OrchestratorGraphState) -> Dict[str, Any]:
    blueprint_state = ProjectBlueprintState.model_validate(state["blueprint"])
    updated = run_validation_gate(blueprint_state, gate_name="GATE_1")

    retries = state.get("gate_1_retries", 0)
    if updated.validation_reports and updated.validation_reports[-1].status == ValidationStatus.FAILED:
        retries += 1
    else:
        updated.current_phase = ProjectPhase.GATE_1_REVIEW

    updated_dict = updated.model_dump(mode="json")
    version_history = _upsert_version_history(state.get("version_history", []), updated_dict)

    return {
        "blueprint": updated_dict,
        "gate_1_retries": retries,
        "version_history": version_history,
    }


def validation_gate_2_node(state: OrchestratorGraphState) -> Dict[str, Any]:
    blueprint_state = ProjectBlueprintState.model_validate(state["blueprint"])
    updated = run_validation_gate(blueprint_state, gate_name="GATE_2")

    retries = state.get("gate_2_retries", 0)
    if updated.validation_reports and updated.validation_reports[-1].status == ValidationStatus.FAILED:
        retries += 1
    else:
        updated.current_phase = ProjectPhase.GATE_2_REVIEW

    updated_dict = updated.model_dump(mode="json")
    version_history = _upsert_version_history(state.get("version_history", []), updated_dict)

    return {
        "blueprint": updated_dict,
        "gate_2_retries": retries,
        "version_history": version_history,
    }


# =====================================================================
# CONDITIONAL ROUTERS
# =====================================================================


def route_after_gate_1(state: OrchestratorGraphState) -> str:
    blueprint_dict = state["blueprint"]
    reports = blueprint_dict.get("validation_reports") or []
    retries = state.get("gate_1_retries", 0)

    if not reports:
        return "human_checkpoint_1"

    latest_report = reports[-1]
    report_status = latest_report.get("status")

    # If passed/warnings or reached max retries, advance to human review
    if report_status not in (ValidationStatus.FAILED.value, ValidationStatus.FAILED):
        return "human_checkpoint_1"

    if retries >= MAX_AUTO_RETRIES:
        return "human_checkpoint_1"

    # Route backward to earliest responsible agent
    defects = latest_report.get("defects") or []
    blocking_agents = {
        d.get("target_agent")
        for d in defects
        if d.get("severity") in (DefectSeverity.BLOCKING.value, DefectSeverity.BLOCKING)
    }

    if "RequirementAnalyst" in blocking_agents:
        return "requirement_analyst"
    elif "ProductArchitect" in blocking_agents:
        return "product_architect"
    else:
        return "requirement_analyst"


def route_after_gate_2(state: OrchestratorGraphState) -> str:
    blueprint_dict = state["blueprint"]
    reports = blueprint_dict.get("validation_reports") or []
    retries = state.get("gate_2_retries", 0)

    if not reports:
        return "human_checkpoint_2"

    latest_report = reports[-1]
    report_status = latest_report.get("status")

    if report_status not in (ValidationStatus.FAILED.value, ValidationStatus.FAILED):
        return "human_checkpoint_2"

    if retries >= MAX_AUTO_RETRIES:
        return "human_checkpoint_2"

    defects = latest_report.get("defects") or []
    blocking_agents = {
        d.get("target_agent")
        for d in defects
        if d.get("severity") in (DefectSeverity.BLOCKING.value, DefectSeverity.BLOCKING)
    }

    if "DatabaseArchitect" in blocking_agents:
        return "database_architect"
    elif "APIArchitect" in blocking_agents:
        return "api_architect"
    else:
        return "database_architect"


# =====================================================================
# HUMAN CHECKPOINT NODES
# =====================================================================


def human_checkpoint_1_node(
    state: OrchestratorGraphState,
) -> Command[Literal["database_architect", "requirement_analyst", "product_architect"]]:
    blueprint_dict = state["blueprint"]
    current_state = ProjectBlueprintState.model_validate(blueprint_dict)
    current_state.current_phase = ProjectPhase.GATE_1_REVIEW
    blueprint_dict = current_state.model_dump(mode="json")

    version_history = _upsert_version_history(state.get("version_history", []), blueprint_dict)

    human_input = interrupt({
        "checkpoint": "human_checkpoint_1",
        "phase": ProjectPhase.GATE_1_REVIEW.value,
        "blueprint": blueprint_dict,
    })

    action = human_input.get("action", "APPROVE")
    if action == "APPROVE":
        current_state.current_phase = ProjectPhase.ARCHITECTURE
        approved_dict = current_state.model_dump(mode="json")
        updated_history = _upsert_version_history(version_history, approved_dict)

        # Preserve downstream blast radius (stale_tables, stale_endpoints) if present
        current_blast = state.get("blast_radius") or {}
        stale_tbls = current_blast.get("stale_tables") or []
        stale_eps = current_blast.get("stale_endpoints") or []
        downstream_blast = None
        if stale_tbls or stale_eps:
            downstream_blast = {
                "stale_tables": list(stale_tbls),
                "stale_endpoints": list(stale_eps),
            }

        return Command(
            goto="database_architect",
            update={
                "blueprint": approved_dict,
                "gate_1_retries": 0,
                "blast_radius": downstream_blast,
                "version_history": updated_history,
            },
        )
    else:
        # action == "REVISE"
        raw_mod_ids = set(human_input.get("modified_ids") or [])
        human_notes = human_input.get("feedback_notes", "")
        next_state, blast = DAGChangePropagator.create_next_version_snapshot(
            current_state=current_state,
            modified_ids=raw_mod_ids,
            human_notes=human_notes,
        )
        blast_as_lists = {k: list(v) for k, v in blast.items()}
        revised_dict = next_state.model_dump(mode="json")
        updated_history = _upsert_version_history(version_history, revised_dict)

        if any(mid.startswith("ACT-") or mid.startswith("REQ-") for mid in raw_mod_ids):
            target = "requirement_analyst"
        elif any(mid.startswith("FEAT-") for mid in raw_mod_ids):
            target = "product_architect"
        else:
            target = "requirement_analyst"

        return Command(
            goto=target,
            update={
                "blueprint": revised_dict,
                "gate_1_retries": 0,
                "blast_radius": blast_as_lists,
                "version_history": updated_history,
            },
        )


def human_checkpoint_2_node(
    state: OrchestratorGraphState,
) -> Command[
    Literal[
        "requirement_analyst",
        "product_architect",
        "database_architect",
        "api_architect",
        "__end__",
    ]
]:
    blueprint_dict = state["blueprint"]
    current_state = ProjectBlueprintState.model_validate(blueprint_dict)
    current_state.current_phase = ProjectPhase.GATE_2_REVIEW
    blueprint_dict = current_state.model_dump(mode="json")

    version_history = _upsert_version_history(state.get("version_history", []), blueprint_dict)

    human_input = interrupt({
        "checkpoint": "human_checkpoint_2",
        "phase": ProjectPhase.GATE_2_REVIEW.value,
        "blueprint": blueprint_dict,
    })

    action = human_input.get("action", "APPROVE")
    if action == "APPROVE":
        current_state.current_phase = ProjectPhase.COMPLETED
        current_state.human_approved = True
        approved_dict = current_state.model_dump(mode="json")
        updated_history = _upsert_version_history(version_history, approved_dict)
        return Command(
            goto=END,
            update={
                "blueprint": approved_dict,
                "gate_2_retries": 0,
                "blast_radius": None,
                "version_history": updated_history,
            },
        )
    else:
        # action == "REVISE"
        raw_mod_ids = set(human_input.get("modified_ids") or [])
        human_notes = human_input.get("feedback_notes", "")
        next_state, blast = DAGChangePropagator.create_next_version_snapshot(
            current_state=current_state,
            modified_ids=raw_mod_ids,
            human_notes=human_notes,
        )
        blast_as_lists = {k: list(v) for k, v in blast.items()}
        revised_dict = next_state.model_dump(mode="json")
        updated_history = _upsert_version_history(version_history, revised_dict)

        if any(mid.startswith("ACT-") or mid.startswith("REQ-") for mid in raw_mod_ids):
            target = "requirement_analyst"
        elif any(mid.startswith("FEAT-") for mid in raw_mod_ids):
            target = "product_architect"
        elif any(mid.startswith("TBL-") for mid in raw_mod_ids):
            target = "database_architect"
        else:
            target = "api_architect"

        return Command(
            goto=target,
            update={
                "blueprint": revised_dict,
                "gate_2_retries": 0,
                "blast_radius": blast_as_lists,
                "version_history": updated_history,
            },
        )


# =====================================================================
# GRAPH BUILDER
# =====================================================================


def build_orchestrator_graph(checkpointer=None):
    """Compile and return the cyclic LangGraph orchestrator state machine."""
    if checkpointer is None:
        try:
            settings = EngineSettings()
        except ValueError:
            settings = None

        if settings and settings.MONGODB_URI:
            from langgraph.checkpoint.mongodb import MongoDBSaver
            from pymongo import MongoClient

            client = MongoClient(settings.MONGODB_URI)
            checkpointer = MongoDBSaver(client)
        else:
            checkpointer = MemorySaver()

    builder = StateGraph(OrchestratorGraphState)

    # 1. Register domain agent and gate nodes
    builder.add_node("requirement_analyst", requirement_analyst_node)
    builder.add_node("product_architect", product_architect_node)
    builder.add_node("validation_gate_1", validation_gate_1_node)
    builder.add_node("human_checkpoint_1", human_checkpoint_1_node)

    builder.add_node("database_architect", database_architect_node)
    builder.add_node("api_architect", api_architect_node)
    builder.add_node("validation_gate_2", validation_gate_2_node)
    builder.add_node("human_checkpoint_2", human_checkpoint_2_node)

    # 2. Wire Phase 1 edges (Discovery)
    builder.add_edge(START, "requirement_analyst")
    builder.add_edge("requirement_analyst", "product_architect")
    builder.add_edge("product_architect", "validation_gate_1")
    builder.add_conditional_edges(
        "validation_gate_1",
        route_after_gate_1,
        ["human_checkpoint_1", "requirement_analyst", "product_architect"],
    )

    # 3. Wire Phase 2 edges (Architecture)
    builder.add_edge("database_architect", "api_architect")
    builder.add_edge("api_architect", "validation_gate_2")
    builder.add_conditional_edges(
        "validation_gate_2",
        route_after_gate_2,
        ["human_checkpoint_2", "database_architect", "api_architect"],
    )

    return builder.compile(checkpointer=checkpointer)

