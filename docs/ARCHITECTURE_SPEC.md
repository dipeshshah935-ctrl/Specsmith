# Multi-Agent Technical Blueprint Engine — Master Architecture Specification

## 1. System Overview & Core Topology

This document defines the canonical engineering specification for the **5 Domain Agents + 1 Orchestrator** Technical Blueprint Engine built on a polyglot **MERN (MongoDB, Express, React, Node.js) + Python (FastAPI, LangGraph, Pydantic v2)** stack.

### 1.1 Architectural Principles
1. **Design by Contract (Strict Schema Enforcement):** Every agent reads a strict slice of `ProjectBlueprintState` and writes a validated Pydantic v2 model via LLM structured outputs (`with_structured_output`).
2. **Immutable Version Snapshots (`v1`, `v2`, `v3`):** Agents never mutate state in place. Revisions create a new immutable snapshot in MongoDB while preserving version history for side-by-side diffs.
3. **Bidirectional Requirements Traceability Matrix (RTM):** Every downstream artifact (`Feature`, `DatabaseEntity`, `EndpointSpec`) must declare `upstream_ids: List[str]`, forming a Directed Acyclic Graph (DAG).
4. **Hybrid Two-Tier Validation:** Validation Gate 1 and Gate 2 execute a deterministic Python static linter first (`DeterministicLinter`) before invoking the LLM semantic critic (`ValidationAgent`).
5. **Bounded Auto-Retry Circuit Breakers:** Automated self-correction loops between the Validation Agent and domain agents are strictly capped at `MAX_AUTO_RETRIES = 2` before escalating to a human-in-the-loop (`interrupt()`) checkpoint.

### 1.2 Service Responsibilities

| Service Layer | Technology Stack | Primary Responsibilities |
| :--- | :--- | :--- |
| **Agent & Orchestration Engine** | Python 3.12, FastAPI, LangGraph, Pydantic v2 | Manages the cyclic state machine, executes the 5 domain agents, runs static + semantic validation gates, computes DAG blast radius on human edits, and persists checkpoints to MongoDB. |
| **API Gateway & User Backend** | Node.js, Express, TypeScript, Mongoose | Handles authentication, project metadata, SSE event streaming from FastAPI to the browser, and direct read queries against MongoDB version snapshots. |
| **Interactive Blueprint Studio** | React, Vite, TypeScript, Tailwind CSS, React Flow | Renders the step-by-step phase progress, interactive traceability DAG (`REQ -> FEAT -> TBL -> EP`), validation defect inspector, human approval drawer, and version diff viewer. |

## 2. Step 1: Canonical State & Traceability Schema (`app/schemas.py`)

```python
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class ProjectPhase(str, Enum):
    DISCOVERY = "DISCOVERY"
    GATE_1_REVIEW = "GATE_1_REVIEW"
    ARCHITECTURE = "ARCHITECTURE"
    GATE_2_REVIEW = "GATE_2_REVIEW"
    COMPLETED = "COMPLETED"


class Priority(str, Enum):
    MUST_HAVE = "MUST_HAVE"
    SHOULD_HAVE = "SHOULD_HAVE"
    COULD_HAVE = "COULD_HAVE"


class ValidationStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    WARNINGS = "WARNINGS"


class DefectSeverity(str, Enum):
    BLOCKING = "BLOCKING"
    WARNING = "WARNING"


# =====================================================================
# LAYER 1: REQUIREMENTS (Requirement Analyst) — IEEE 830 / ISO 29148
# =====================================================================

class GlossaryTerm(BaseModel):
    term: str = Field(description="Canonical domain noun e.g. 'Workspace', 'Tenant'")
    definition: str = Field(description="Exact ubiquitous language definition")


class Actor(BaseModel):
    id: str = Field(description="Deterministic ID e.g. ACT-01")
    name: str = Field(description="Role name e.g. 'OrganizationAdmin', 'Customer'")
    description: str
    permissions_summary: List[str]


class Requirement(BaseModel):
    id: str = Field(description="Deterministic ID e.g. REQ-01")
    actor_id: str = Field(description="References Actor.id")
    title: str
    description: str = Field(description="Atomic, testable requirement statement")
    priority: Priority
    acceptance_criteria: List[str] = Field(description="Quantifiable, verifiable conditions")


class RequirementAnalystOutput(BaseModel):
    glossary: List[GlossaryTerm]
    actors: List[Actor]
    requirements: List[Requirement]


# =====================================================================
# LAYER 2: PRODUCT SPECIFICATION (Product Architect) — DDD & FSM
# =====================================================================

class StateTransition(BaseModel):
    from_state: str
    to_state: str
    trigger_action: str
    guard_condition: Optional[str] = None


class Feature(BaseModel):
    id: str = Field(description="Deterministic ID e.g. FEAT-01")
    upstream_ids: List[str] = Field(description="References one or more REQ-*.id")
    module_name: str = Field(description="DDD Bounded Context name e.g. 'Billing'")
    name: str
    description: str
    happy_path: List[str] = Field(description="Ordered steps for primary user journey")
    edge_cases: List[str] = Field(description="Explicit failure and boundary conditions")
    state_machine: Optional[List[StateTransition]] = Field(
        default=None,
        description="Required when the feature governs a stateful domain entity"
    )


class ProductArchitectOutput(BaseModel):
    features: List[Feature]


# =====================================================================
# LAYER 3: DATABASE ARCHITECTURE (Database Architect) — 3NF & ACID
# =====================================================================

class ColumnDefinition(BaseModel):
    name: str
    data_type: str = Field(description="SQL/NoSQL type e.g. UUID, VARCHAR(255), TIMESTAMPTZ")
    is_primary_key: bool = False
    is_nullable: bool = False
    is_unique: bool = False
    is_pii: bool = Field(default=False, description="Privacy by Design flag for sensitive data")


class EntityRelationship(BaseModel):
    foreign_key_column: str
    references_entity: str
    references_column: str
    on_delete: str = Field(default="RESTRICT", description="RESTRICT, CASCADE, or SET NULL")


class DatabaseEntity(BaseModel):
    id: str = Field(description="Deterministic ID e.g. TBL-01")
    upstream_ids: List[str] = Field(description="References one or more FEAT-*.id")
    table_name: str = Field(description="Snake_case plural table name aligned with glossary")
    columns: List[ColumnDefinition]
    relationships: List[EntityRelationship] = []
    indexes: List[str] = Field(description="Single or composite index definitions")


class DatabaseArchitectOutput(BaseModel):
    database_entities: List[DatabaseEntity]


# =====================================================================
# LAYER 4: API ARCHITECTURE (API Architect) — OpenAPI 3.1 & RFC 7807
# =====================================================================

class EndpointSpec(BaseModel):
    id: str = Field(description="Deterministic ID e.g. EP-01")
    upstream_ids: List[str] = Field(description="References FEAT-*.id and TBL-*.id")
    http_method: str = Field(description="GET, POST, PUT, PATCH, DELETE")
    path: str = Field(description="REST resource URI e.g. /api/v1/orders/{order_id}")
    summary: str
    allowed_actor_ids: List[str] = Field(description="References Actor.id list")
    is_idempotent: bool = Field(default=False)
    request_dto_schema: Optional[Dict[str, Any]] = None
    response_dto_schema: Dict[str, Any]
    error_codes: List[int] = Field(description="Standard HTTP error codes e.g. [400, 401, 403, 404, 409]")


class APIArchitectOutput(BaseModel):
    endpoints: List[EndpointSpec]


# =====================================================================
# LAYER 5: HYBRID VALIDATION (Validation Agent) — RTM & QA
# =====================================================================

class ValidationDefect(BaseModel):
    rule_code: str = Field(description="e.g. ERR_ORPHAN_REQUIREMENT, ERR_DANGLING_FOREIGN_KEY")
    severity: DefectSeverity
    target_agent: str = Field(
        description="RequirementAnalyst | ProductArchitect | DatabaseArchitect | APIArchitect"
    )
    target_item_id: Optional[str] = None
    message: str
    suggested_fix: str


class ValidationReport(BaseModel):
    gate_name: str = Field(description="GATE_1 or GATE_2")
    status: ValidationStatus
    defects: List[ValidationDefect] = []
    traceability_coverage_percent: float


# =====================================================================
# ROOT CANONICAL STATE
# =====================================================================

class ProjectBlueprintState(BaseModel):
    project_id: str
    version: int = 1
    current_phase: ProjectPhase = ProjectPhase.DISCOVERY
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_initial_prompt: str

    glossary: List[GlossaryTerm] = []
    actors: List[Actor] = []
    requirements: List[Requirement] = []
    features: List[Feature] = []
    database_entities: List[DatabaseEntity] = []
    endpoints: List[EndpointSpec] = []
    validation_reports: List[ValidationReport] = []

    human_approved: bool = False
    human_feedback_notes: Optional[str] = None
```

## 3. Step 2: Domain Agent Contracts & System Prompts

### 3.1 Agent Read/Write Isolation Matrix

| Agent Name | Input Slice Read from `ProjectBlueprintState` | Structured Output Schema | Primary Engineering Standard |
| :--- | :--- | :--- | :--- |
| **RequirementAnalyst** | `user_initial_prompt`, `human_feedback_notes`, existing `requirements` (if partial edit) | `RequirementAnalystOutput` | IEEE 830 / ISO 29148, INVEST, Ubiquitous Language |
| **ProductArchitect** | `glossary`, `actors`, `requirements`, `stale_features` (if selective edit) | `ProductArchitectOutput` | Domain-Driven Design (Bounded Contexts), Finite State Machines |
| **DatabaseArchitect** | `glossary`, `features`, `stale_tables` (if selective edit) | `DatabaseArchitectOutput` | 3rd Normal Form (3NF), Referential Integrity, Privacy by Design |
| **APIArchitect** | `glossary`, `actors`, `features`, `database_entities`, `stale_endpoints` | `APIArchitectOutput` | OpenAPI 3.1, Idempotency, Least Privilege RBAC, RFC 7807 |
| **ValidationAgent** | Full `ProjectBlueprintState` snapshot + `gate_name` (`GATE_1` or `GATE_2`) | `List[ValidationDefect]` | Requirements Traceability Matrix (RTM), FMEA |

### 3.2 Agent System Prompts

#### 1. Requirement Analyst Prompt
```text
You are a Principal Requirements Engineer following IEEE 830 / ISO 29148 standards.
Given the user's project idea and optional revision feedback:
1. Establish a strict Ubiquitous Language glossary of core domain nouns.
2. Identify all distinct Actors (ACT-01, ACT-02...) and summarize their permissions.
3. Decompose the scope into atomic, testable Requirements (REQ-01, REQ-02...).
   - Every requirement must link to a valid actor_id.
   - Never use vague adjectives ("fast", "intuitive", "secure") without measurable acceptance criteria.
   - If selective revision IDs are provided, update only the targeted items and preserve untouched IDs.
```

#### 2. Product Architect Prompt
```text
You are a Principal Product Architect applying Domain-Driven Design (DDD).
Using ONLY the Glossary, Actors, and Requirements provided:
1. Organize functionality into cohesive DDD Bounded Context modules (module_name).
2. Design Features (FEAT-01, FEAT-02...) where every feature links its upstream_ids to at least one REQ-*.id.
3. Every MUST_HAVE requirement must be covered by at least one feature.
4. Define explicit happy_path steps and concrete edge_cases / failure conditions for every feature.
5. For any feature managing a stateful domain concept (e.g., Order, Booking, Subscription, Ticket), define a complete state_machine with initial, intermediate, and terminal states.
```

#### 3. Database Architect Prompt
```text
You are a Principal Database Architect enforcing Third Normal Form (3NF) and ACID integrity.
Using the Glossary and Features:
1. Design normalized relational entities (TBL-01, TBL-02...) using snake_case plural table names matching the glossary.
2. Link every table's upstream_ids to the FEAT-*.id items it supports.
3. Define primary keys, foreign key relationships with explicit on_delete rules (RESTRICT, CASCADE, SET NULL), and columns required to persist every feature's state_machine.
4. Flag any column containing personal or sensitive data with is_pii=True.
5. Define indexes for all foreign keys, unique lookups, and state/status filter columns.
```

#### 4. API Architect Prompt
```text
You are a Principal API Architect designing OpenAPI 3.1 RESTful contracts.
Using the Glossary, Actors, Features, and Database Entities:
1. Design REST endpoints (EP-01, EP-02...) linking upstream_ids to both FEAT-* and TBL-* IDs.
2. Use plural resource nouns in paths (/api/v1/resources/{id}) and standard HTTP methods.
3. Enforce Least Privilege by listing only permitted Actor IDs in allowed_actor_ids.
4. Ensure every state transition in a Feature's state_machine has a corresponding mutating endpoint.
5. Mark GET, PUT, DELETE, and state-mutating/financial POST routes with is_idempotent=True, and include RFC 7807 error status codes (400, 401, 403, 404, 409).
```

## 4. Step 3: Hybrid Validation Engine (`app/linter.py`)

```python
from typing import List, Set
from app.schemas import (
    ProjectBlueprintState,
    ValidationDefect,
    DefectSeverity,
    ValidationReport,
    ValidationStatus,
)


class DeterministicLinter:
    """Tier 1 zero-token static verifier for graph integrity and referential rules."""

    @staticmethod
    def lint_gate_1(state: ProjectBlueprintState) -> List[ValidationDefect]:
        defects: List[ValidationDefect] = []
        req_ids: Set[str] = {r.id for r in state.requirements}
        actor_ids: Set[str] = {a.id for a in state.actors}
        covered_reqs: Set[str] = set()

        for req in state.requirements:
            if req.actor_id not in actor_ids:
                defects.append(ValidationDefect(
                    rule_code="ERR_DANGLING_ACTOR",
                    severity=DefectSeverity.BLOCKING,
                    target_agent="RequirementAnalyst",
                    target_item_id=req.id,
                    message=f"Requirement {req.id} references unknown actor '{req.actor_id}'.",
                    suggested_fix="Assign a valid Actor.id from state.actors."
                ))

        for feat in state.features:
            if not feat.upstream_ids:
                defects.append(ValidationDefect(
                    rule_code="ERR_UNLINKED_FEATURE",
                    severity=DefectSeverity.BLOCKING,
                    target_agent="ProductArchitect",
                    target_item_id=feat.id,
                    message=f"Feature {feat.id} has no upstream requirement links.",
                    suggested_fix="Populate upstream_ids with valid REQ-* IDs."
                ))
            for up_id in feat.upstream_ids:
                if up_id not in req_ids:
                    defects.append(ValidationDefect(
                        rule_code="ERR_INVALID_UPSTREAM_REQ",
                        severity=DefectSeverity.BLOCKING,
                        target_agent="ProductArchitect",
                        target_item_id=feat.id,
                        message=f"Feature {feat.id} references non-existent requirement '{up_id}'.",
                        suggested_fix="Reference only declared REQ-* IDs."
                    ))
                else:
                    covered_reqs.add(up_id)

        for req in state.requirements:
            if req.id not in covered_reqs:
                sev = DefectSeverity.BLOCKING if req.priority == "MUST_HAVE" else DefectSeverity.WARNING
                defects.append(ValidationDefect(
                    rule_code="ERR_ORPHAN_REQUIREMENT",
                    severity=sev,
                    target_agent="ProductArchitect",
                    target_item_id=req.id,
                    message=f"Requirement {req.id} ('{req.title}') is not covered by any feature.",
                    suggested_fix="Add or update a Feature with this REQ ID in upstream_ids."
                ))

        return defects

    @staticmethod
    def lint_gate_2(state: ProjectBlueprintState) -> List[ValidationDefect]:
        defects: List[ValidationDefect] = []
        feat_ids: Set[str] = {f.id for f in state.features}
        actor_ids: Set[str] = {a.id for a in state.actors}
        table_map = {t.table_name: t for t in state.database_entities}
        table_ids: Set[str] = {t.id for t in state.database_entities}

        for tbl in state.database_entities:
            for up_id in tbl.upstream_ids:
                if up_id not in feat_ids:
                    defects.append(ValidationDefect(
                        rule_code="ERR_INVALID_UPSTREAM_FEATURE",
                        severity=DefectSeverity.BLOCKING,
                        target_agent="DatabaseArchitect",
                        target_item_id=tbl.id,
                        message=f"Table '{tbl.table_name}' links to unknown feature '{up_id}'.",
                        suggested_fix="Link upstream_ids to valid FEAT-* IDs."
                    ))
            for rel in tbl.relationships:
                if rel.references_entity not in table_map:
                    defects.append(ValidationDefect(
                        rule_code="ERR_DANGLING_FOREIGN_KEY",
                        severity=DefectSeverity.BLOCKING,
                        target_agent="DatabaseArchitect",
                        target_item_id=tbl.id,
                        message=f"Table '{tbl.table_name}' references missing table '{rel.references_entity}'.",
                        suggested_fix="Create the target table or fix references_entity name."
                    ))
                else:
                    target_cols = {c.name for c in table_map[rel.references_entity].columns}
                    if rel.references_column not in target_cols:
                        defects.append(ValidationDefect(
                            rule_code="ERR_DANGLING_FK_COLUMN",
                            severity=DefectSeverity.BLOCKING,
                            target_agent="DatabaseArchitect",
                            target_item_id=tbl.id,
                            message=(
                                f"FK '{rel.foreign_key_column}' in '{tbl.table_name}' targets missing "
                                f"column '{rel.references_column}' on '{rel.references_entity}'."
                            ),
                            suggested_fix="Ensure target column exists on referenced table."
                        ))

        valid_ep_upstreams = feat_ids.union(table_ids)
        for ep in state.endpoints:
            for act_id in ep.allowed_actor_ids:
                if act_id not in actor_ids:
                    defects.append(ValidationDefect(
                        rule_code="ERR_UNKNOWN_ACTOR_PERMISSION",
                        severity=DefectSeverity.BLOCKING,
                        target_agent="APIArchitect",
                        target_item_id=ep.id,
                        message=f"Endpoint '{ep.http_method} {ep.path}' permits unknown actor '{act_id}'.",
                        suggested_fix="Use valid ACT-* IDs from state.actors."
                    ))
            for up_id in ep.upstream_ids:
                if up_id not in valid_ep_upstreams:
                    defects.append(ValidationDefect(
                        rule_code="ERR_ORPHAN_ENDPOINT",
                        severity=DefectSeverity.BLOCKING,
                        target_agent="APIArchitect",
                        target_item_id=ep.id,
                        message=f"Endpoint '{ep.id}' references unknown upstream ID '{up_id}'.",
                        suggested_fix="Link endpoint upstream_ids to valid FEAT-* or TBL-* IDs."
                    ))

        return defects
```

## 5. Step 4: DAG Change Propagator & LangGraph Orchestrator

### 5.1 Selective Blast-Radius Calculator (`app/propagator.py`)

```python
from typing import Dict, Set, Tuple
from app.schemas import ProjectBlueprintState


class DAGChangePropagator:
    """Computes downstream impact across REQ -> FEAT -> TBL -> EP when human edits occur."""

    @staticmethod
    def compute_blast_radius(
        state: ProjectBlueprintState,
        modified_ids: Set[str]
    ) -> Dict[str, Set[str]]:
        stale_features: Set[str] = set()
        stale_tables: Set[str] = set()
        stale_endpoints: Set[str] = set()

        for feat in state.features:
            if feat.id in modified_ids or any(uid in modified_ids for uid in feat.upstream_ids):
                stale_features.add(feat.id)

        l2_triggers = modified_ids.union(stale_features)
        for tbl in state.database_entities:
            if tbl.id in modified_ids or any(uid in l2_triggers for uid in tbl.upstream_ids):
                stale_tables.add(tbl.id)

        l3_triggers = l2_triggers.union(stale_tables)
        for ep in state.endpoints:
            if ep.id in modified_ids or any(uid in l3_triggers for uid in ep.upstream_ids):
                stale_endpoints.add(ep.id)

        return {
            "stale_features": stale_features,
            "stale_tables": stale_tables,
            "stale_endpoints": stale_endpoints,
        }

    @staticmethod
    def create_next_version_snapshot(
        current_state: ProjectBlueprintState,
        modified_ids: Set[str],
        human_notes: str
    ) -> Tuple[ProjectBlueprintState, Dict[str, Set[str]]]:
        blast = DAGChangePropagator.compute_blast_radius(current_state, modified_ids)
        next_state = current_state.model_copy(deep=True)
        next_state.version += 1
        next_state.human_approved = False
        next_state.human_feedback_notes = human_notes
        return next_state, blast
```

### 5.2 Cross-Phase Checkpoints & Routing (`app/orchestrator.py`)

```python
from typing import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from app.schemas import ProjectBlueprintState, ProjectPhase, ValidationStatus
from app.propagator import DAGChangePropagator

MAX_AUTO_RETRIES = 2


def human_checkpoint_1_node(
    state: dict
) -> Command[Literal["database_architect", "requirement_analyst", "product_architect"]]:
    blueprint: ProjectBlueprintState = state["blueprint"]
    blueprint.current_phase = ProjectPhase.GATE_1_REVIEW

    decision = interrupt({
        "checkpoint": "GATE_1_REVIEW",
        "version": blueprint.version,
        "blueprint": blueprint.model_dump(),
        "latest_validation": blueprint.validation_reports[-1].model_dump()
    })

    if decision.get("action") == "APPROVE":
        blueprint.current_phase = ProjectPhase.ARCHITECTURE
        return Command(update={"blueprint": blueprint, "gate_1_retries": 0}, goto="database_architect")

    modified_ids = set(decision.get("modified_ids", []))
    next_bp, blast = DAGChangePropagator.create_next_version_snapshot(
        blueprint, modified_ids, decision.get("feedback_notes", "")
    )
    target = (
        "requirement_analyst"
        if any(i.startswith(("REQ-", "ACT-")) for i in modified_ids)
        else "product_architect"
    )
    return Command(
        update={"blueprint": next_bp, "blast_radius": blast, "gate_1_retries": 0},
        goto=target
    )


def human_checkpoint_2_node(
    state: dict
) -> Command[Literal["__end__", "requirement_analyst", "product_architect", "database_architect", "api_architect"]]:
    blueprint: ProjectBlueprintState = state["blueprint"]
    blueprint.current_phase = ProjectPhase.GATE_2_REVIEW

    decision = interrupt({
        "checkpoint": "GATE_2_REVIEW",
        "version": blueprint.version,
        "blueprint": blueprint.model_dump(),
        "latest_validation": blueprint.validation_reports[-1].model_dump()
    })

    if decision.get("action") == "APPROVE":
        blueprint.human_approved = True
        blueprint.current_phase = ProjectPhase.COMPLETED
        return Command(update={"blueprint": blueprint, "gate_2_retries": 0}, goto=END)

    modified_ids = set(decision.get("modified_ids", []))
    next_bp, blast = DAGChangePropagator.create_next_version_snapshot(
        blueprint, modified_ids, decision.get("feedback_notes", "")
    )

    # Route backward to the earliest layer touched by the human's edit
    if any(i.startswith(("REQ-", "ACT-")) for i in modified_ids):
        target = "requirement_analyst"
    elif any(i.startswith("FEAT-") for i in modified_ids):
        target = "product_architect"
    elif any(i.startswith("TBL-") for i in modified_ids):
        target = "database_architect"
    else:
        target = "api_architect"

    return Command(
        update={"blueprint": next_bp, "blast_radius": blast, "gate_2_retries": 0},
        goto=target
    )
```

## 6. Step 5: Vertical-Slice Build Sequence for Antigravity

| Slice | Target Folder | Deliverable Files | Verification Command |
| :--- | :--- | :--- | :--- |
| **Slice 1** | `apps/agent-engine` | `app/schemas.py`, `app/linter.py`, `app/propagator.py`, `tests/test_core_logic.py` | `pytest tests/test_core_logic.py -q` |
| **Slice 2** | `apps/agent-engine` | `app/agents/*.py` (all 5 agents with `USE_MOCK_LLM` toggle), `tests/test_agents.py` | `USE_MOCK_LLM=true pytest tests/test_agents.py -q` |
| **Slice 3** | `apps/agent-engine` | `app/orchestrator.py`, `app/main.py` (FastAPI), `tests/test_orchestrator_flow.py` | `USE_MOCK_LLM=true pytest tests/test_orchestrator_flow.py -q` |
| **Slice 4** | `apps/api-gateway` | `src/server.ts`, `src/routes/projects.ts`, `src/models/Project.ts` | `npm test` (Express-to-FastAPI integration) |
| **Slice 5** | `apps/web` | `src/pages/ProjectWorkspace.tsx`, `src/components/CheckpointReview.tsx` | `npm run build` + UI checkpoint verification |
| **Slice 6** | `apps/web` | `src/components/TraceabilityGraph.tsx` (`@xyflow/react`), `VersionDiffViewer.tsx` | `npm run build` + interactive blast-radius test |
