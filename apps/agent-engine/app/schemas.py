from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, TypedDict
from pydantic import BaseModel, ConfigDict, Field


# =====================================================================
# STRICT CONTRACT BASE MODEL
# =====================================================================

class StrictContractModel(BaseModel):
    """Base class enforcing strict schema adherence and forbidding extra fields."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )


# =====================================================================
# ENUMS
# =====================================================================

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


class HTTPMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class OnDeleteAction(str, Enum):
    RESTRICT = "RESTRICT"
    CASCADE = "CASCADE"
    SET_NULL = "SET NULL"


# =====================================================================
# LAYER 1: REQUIREMENTS (Requirement Analyst) — IEEE 830 / ISO 29148
# =====================================================================

class GlossaryTerm(StrictContractModel):
    term: str = Field(min_length=2, description="Canonical domain noun e.g. 'Workspace', 'Tenant'")
    definition: str = Field(min_length=2, description="Exact ubiquitous language definition")


class Actor(StrictContractModel):
    id: str = Field(
        pattern=r"^ACT-\d{2,4}$",
        description="Deterministic ID e.g. ACT-01",
    )
    name: str = Field(min_length=1, description="Role name e.g. 'OrganizationAdmin', 'Customer'")
    description: str
    permissions_summary: List[str] = Field(default_factory=list)


class Requirement(StrictContractModel):
    id: str = Field(
        pattern=r"^REQ-\d{2,4}$",
        description="Deterministic ID e.g. REQ-01",
    )
    actor_id: str = Field(
        pattern=r"^ACT-\d{2,4}$",
        description="References Actor.id",
    )
    title: str = Field(min_length=1)
    description: str = Field(min_length=1, description="Atomic, testable requirement statement")
    priority: Priority
    acceptance_criteria: List[str] = Field(
        min_length=1,
        description="Quantifiable, verifiable conditions",
    )


class RequirementAnalystOutput(StrictContractModel):
    glossary: List[GlossaryTerm] = Field(default_factory=list)
    actors: List[Actor] = Field(default_factory=list)
    requirements: List[Requirement] = Field(default_factory=list)


# =====================================================================
# LAYER 2: PRODUCT SPECIFICATION (Product Architect) — DDD & FSM
# =====================================================================

class StateTransition(StrictContractModel):
    from_state: str = Field(min_length=1)
    to_state: str = Field(min_length=1)
    trigger_action: str = Field(min_length=1)
    guard_condition: Optional[str] = None


class Feature(StrictContractModel):
    id: str = Field(
        pattern=r"^FEAT-\d{2,4}$",
        description="Deterministic ID e.g. FEAT-01",
    )
    upstream_ids: List[str] = Field(
        default_factory=list,
        description="References one or more REQ-*.id",
    )
    module_name: str = Field(min_length=1, description="DDD Bounded Context name e.g. 'Billing'")
    name: str = Field(min_length=1)
    description: str
    happy_path: List[str] = Field(
        min_length=1,
        description="Ordered steps for primary user journey",
    )
    edge_cases: List[str] = Field(
        default_factory=list,
        description="Explicit failure and boundary conditions",
    )
    state_machine: Optional[List[StateTransition]] = Field(
        default=None,
        description="Required when the feature governs a stateful domain entity",
    )


class ProductArchitectOutput(StrictContractModel):
    features: List[Feature] = Field(default_factory=list)


# =====================================================================
# LAYER 3: DATABASE ARCHITECTURE (Database Architect) — 3NF & ACID
# =====================================================================

class ColumnDefinition(StrictContractModel):
    name: str = Field(min_length=1)
    data_type: str = Field(min_length=1, description="SQL/NoSQL type e.g. UUID, VARCHAR(255), TIMESTAMPTZ")
    is_primary_key: bool = False
    is_nullable: bool = False
    is_unique: bool = False
    is_pii: bool = Field(default=False, description="Privacy by Design flag for sensitive data")


class EntityRelationship(StrictContractModel):
    foreign_key_column: str = Field(min_length=1)
    references_entity: str = Field(min_length=1)
    references_column: str = Field(min_length=1)
    on_delete: OnDeleteAction = Field(default=OnDeleteAction.RESTRICT, description="RESTRICT, CASCADE, or SET NULL")


class DatabaseEntity(StrictContractModel):
    id: str = Field(
        pattern=r"^TBL-\d{2,4}$",
        description="Deterministic ID e.g. TBL-01",
    )
    upstream_ids: List[str] = Field(
        default_factory=list,
        description="References one or more FEAT-*.id",
    )
    table_name: str = Field(
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Snake_case plural table name aligned with glossary",
    )
    columns: List[ColumnDefinition] = Field(
        min_length=1,
        description="Entity column definitions",
    )
    relationships: List[EntityRelationship] = Field(default_factory=list)
    indexes: List[str] = Field(default_factory=list, description="Single or composite index definitions")


class DatabaseArchitectOutput(StrictContractModel):
    database_entities: List[DatabaseEntity] = Field(default_factory=list)


# =====================================================================
# LAYER 4: API ARCHITECTURE (API Architect) — OpenAPI 3.1 & RFC 7807
# =====================================================================

class EndpointSpec(StrictContractModel):
    id: str = Field(
        pattern=r"^EP-\d{2,4}$",
        description="Deterministic ID e.g. EP-01",
    )
    upstream_ids: List[str] = Field(
        default_factory=list,
        description="References FEAT-*.id and TBL-*.id",
    )
    http_method: HTTPMethod = Field(description="GET, POST, PUT, PATCH, DELETE")
    path: str = Field(
        pattern=r"^/api/v\d+/[a-z0-9_/\-{}]*$",
        description="REST resource URI e.g. /api/v1/orders/{order_id}",
    )
    summary: str = Field(min_length=1)
    allowed_actor_ids: List[str] = Field(
        default_factory=list,
        description="References Actor.id list",
    )
    is_idempotent: bool = Field(default=False)
    request_dto_schema: Optional[Dict[str, Any]] = None
    response_dto_schema: Dict[str, Any] = Field(default_factory=dict)
    error_codes: List[int] = Field(
        default_factory=lambda: [400, 401, 403, 404, 500],
        description="Standard HTTP error codes e.g. [400, 401, 403, 404, 409]",
    )


class APIArchitectOutput(StrictContractModel):
    endpoints: List[EndpointSpec] = Field(default_factory=list)


# =====================================================================
# LAYER 5: HYBRID VALIDATION (Validation Agent) — RTM & QA
# =====================================================================

class ValidationDefect(StrictContractModel):
    rule_code: str = Field(description="e.g. ERR_ORPHAN_REQUIREMENT, ERR_DANGLING_FOREIGN_KEY")
    severity: DefectSeverity
    target_agent: str = Field(
        description="RequirementAnalyst | ProductArchitect | DatabaseArchitect | APIArchitect",
    )
    target_item_id: Optional[str] = None
    message: str
    suggested_fix: str


class ValidationReport(StrictContractModel):
    gate_name: str = Field(description="GATE_1 or GATE_2")
    status: ValidationStatus
    defects: List[ValidationDefect] = Field(default_factory=list)
    traceability_coverage_percent: float


class ValidationCriticOutput(StrictContractModel):
    defects: List[ValidationDefect] = Field(default_factory=list)


# =====================================================================
# ROOT CANONICAL STATE
# =====================================================================

class ProjectBlueprintState(StrictContractModel):
    project_id: str
    version: int = 1
    current_phase: ProjectPhase = ProjectPhase.DISCOVERY
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_initial_prompt: str

    glossary: List[GlossaryTerm] = Field(default_factory=list)
    actors: List[Actor] = Field(default_factory=list)
    requirements: List[Requirement] = Field(default_factory=list)
    features: List[Feature] = Field(default_factory=list)
    database_entities: List[DatabaseEntity] = Field(default_factory=list)
    endpoints: List[EndpointSpec] = Field(default_factory=list)
    validation_reports: List[ValidationReport] = Field(default_factory=list)

    human_approved: bool = False
    human_feedback_notes: Optional[str] = None


# =====================================================================
# ORCHESTRATOR GRAPH STATE
# =====================================================================

class OrchestratorGraphState(TypedDict):
    blueprint: ProjectBlueprintState
    gate_1_retries: int
    gate_2_retries: int
    blast_radius: Optional[Dict[str, Set[str]]]
