from typing import Any, Dict, List, Optional, Set
from app.agents.base import invoke_structured_agent
from app.config import EngineSettings
from app.propagator import DAGChangePropagator
from app.schemas import (
    Actor,
    GlossaryTerm,
    Priority,
    ProjectBlueprintState,
    Requirement,
    RequirementAnalystOutput,
    ValidationDefect,
)

REQUIREMENTS_SYSTEM_PROMPT = """You are a Principal Requirements Engineer adhering strictly to IEEE 830 / ISO 29148 standards.

Given the product concept, domain constraints, and optional revision notes:
1. Ubiquitous Language: Define canonical domain nouns in the glossary (min length 2).
2. Actors: Identify distinct actors with deterministic IDs (ACT-01, ACT-02...) and summarize permissions.
3. Atomic Requirements: Decompose product capabilities into testable, unambiguous requirements (REQ-01, REQ-02...).
   - Every requirement must link its actor_id to an existing ACT-* identifier.
   - Acceptance criteria must be quantifiable and verifiable (never use vague adjectives like 'fast' or 'intuitive' without measurable limits).
   - If selective revision notes and stale IDs are provided, regenerate only the stale requirements while preserving untouched requirements.
"""


def _mock_requirement_analyst(payload: Dict[str, Any]) -> RequirementAnalystOutput:
    """Deterministic mock builder for Requirement Analyst adhering to StrictContractModel."""
    stale_reqs: Set[str] = set(payload.get("stale_requirements") or [])
    feedback: Optional[str] = payload.get("human_feedback_notes")

    glossary = [
        GlossaryTerm(
            term="Order",
            definition="A commercial purchase order placed by a customer containing selected items.",
        ),
        GlossaryTerm(
            term="Workspace",
            definition="A shared collaborative environment for organization members and administrative control.",
        ),
    ]

    actors = [
        Actor(
            id="ACT-01",
            name="Admin",
            description="Organization administrator with full workspace and policy management privileges.",
            permissions_summary=["manage_workspace", "manage_orders", "view_audit_logs"],
        ),
        Actor(
            id="ACT-02",
            name="Customer",
            description="End-user purchasing services and tracking order statuses.",
            permissions_summary=["create_order", "view_order", "cancel_pending_order"],
        ),
    ]

    # Reconstruct from existing requirements if present, or use standard defaults
    existing_raw = payload.get("existing_requirements") or []
    if existing_raw:
        requirements: List[Requirement] = [
            Requirement.model_validate(r) for r in existing_raw
        ]
    else:
        requirements = [
            Requirement(
                id="REQ-01",
                actor_id="ACT-02",
                title="Place Order",
                description="Customer can submit an order with selected line items and shipping details.",
                priority=Priority.MUST_HAVE,
                acceptance_criteria=[
                    "Order is persisted with status PENDING",
                    "Confirmation email is dispatched within 5 seconds",
                ],
            ),
            Requirement(
                id="REQ-02",
                actor_id="ACT-01",
                title="Manage Workspace",
                description="Admin can configure workspace settings and member access permissions.",
                priority=Priority.SHOULD_HAVE,
                acceptance_criteria=[
                    "Workspace configuration changes are audited",
                    "Settings take effect immediately upon saving",
                ],
            ),
        ]

    # Apply selective revision feedback to targeted stale requirements
    if feedback and stale_reqs:
        revised_requirements: List[Requirement] = []
        for req in requirements:
            if req.id in stale_reqs:
                revised_req = req.model_copy(deep=True)
                revised_req.description += f" [Revised: {feedback}]"
                revised_req.acceptance_criteria.append(
                    f"Requirement updated: {feedback} [Revised: {feedback}]"
                )
                revised_requirements.append(revised_req)
            else:
                revised_requirements.append(req)
        requirements = revised_requirements

    return RequirementAnalystOutput(
        glossary=glossary,
        actors=actors,
        requirements=requirements,
    )


def run_requirement_analyst(
    state: ProjectBlueprintState,
    blast_radius: Optional[Dict[str, Set[str]]] = None,
    retry_defects: Optional[List[ValidationDefect]] = None,
    settings: Optional[EngineSettings] = None,
) -> ProjectBlueprintState:
    """Execute Agent 1 (Requirement Analyst) with strict Read Contract isolation and selective merging."""
    stale_reqs: Set[str] = set((blast_radius or {}).get("stale_requirements", set()))

    # STRICT READ CONTRACT: Extract ONLY allowed fields.
    # Never read features, database_entities, or endpoints.
    user_payload: Dict[str, Any] = {
        "user_initial_prompt": state.user_initial_prompt,
        "human_feedback_notes": state.human_feedback_notes,
        "existing_glossary": [g.model_dump() for g in state.glossary],
        "existing_actors": [a.model_dump() for a in state.actors],
        "existing_requirements": [r.model_dump() for r in state.requirements],
        "stale_requirements": sorted(list(stale_reqs)),
        "retry_defects": [
            d.model_dump()
            for d in (retry_defects or [])
            if d.target_agent == "RequirementAnalyst"
        ],
    }

    output: RequirementAnalystOutput = invoke_structured_agent(
        schema_cls=RequirementAnalystOutput,
        system_prompt=REQUIREMENTS_SYSTEM_PROMPT,
        user_payload=user_payload,
        mock_builder=_mock_requirement_analyst,
        settings=settings,
    )

    # Immutable update on cloned state
    new_state = state.model_copy(deep=True)

    if output.glossary:
        new_state.glossary = output.glossary
    if output.actors:
        new_state.actors = output.actors

    # SELECTIVE MERGE: Merge requirements if state already has items and stale_requirements are present
    if new_state.requirements and stale_reqs:
        new_state.requirements = DAGChangePropagator.merge_regenerated_slice(
            existing_items=new_state.requirements,
            new_items=output.requirements,
            stale_ids=stale_reqs,
        )
    else:
        new_state.requirements = output.requirements

    return new_state

