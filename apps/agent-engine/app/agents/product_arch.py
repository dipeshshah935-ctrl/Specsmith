from typing import Any, Dict, List, Optional, Set
from app.agents.base import invoke_structured_agent
from app.config import EngineSettings
from app.propagator import DAGChangePropagator
from app.schemas import (
    Feature,
    ProductArchitectOutput,
    ProjectBlueprintState,
    StateTransition,
    ValidationDefect,
)

PRODUCT_SYSTEM_PROMPT = """You are a Principal Product Architect applying Domain-Driven Design (DDD) principles.

Using ONLY the Glossary, Actors, and Requirements provided:
1. Deterministic IDs: Assign IDs strictly matching pattern ^FEAT-\\d{2,4}$ (e.g. 'FEAT-01', 'FEAT-02').
2. DDD Bounded Contexts: Organize features into cohesive modules (module_name e.g. 'OrderManagement', 'Billing', 'Identity').
3. Bidirectional Traceability: Link every feature's upstream_ids to at least one valid REQ-*.id.
4. 100% MUST_HAVE Coverage: Every MUST_HAVE requirement must be fulfilled by at least one feature.
5. Concrete Paths: Declare explicit, ordered happy_path steps and concrete edge_cases / boundary failure conditions.
6. Finite State Machines (FSM): For stateful domain entities, define a complete state_machine with distinct from_state and to_state values (never a self-loop).
"""


def _mock_product_architect(payload: Dict[str, Any]) -> ProductArchitectOutput:
    """Deterministic mock builder for Product Architect adhering to StrictContractModel."""
    stale_feats: Set[str] = set(payload.get("stale_features") or [])
    feedback: Optional[str] = payload.get("human_feedback_notes")
    raw_reqs: List[Dict[str, Any]] = payload.get("requirements") or []

    req_ids = [r["id"] for r in raw_reqs if isinstance(r, dict) and "id" in r]
    feat1_upstreams = [req_ids[0]] if req_ids else ["REQ-01"]
    feat2_upstreams = req_ids[1:] if len(req_ids) > 1 else feat1_upstreams

    existing_raw = payload.get("existing_features") or []
    if existing_raw:
        features = [Feature.model_validate(f) for f in existing_raw]
    else:
        features = [
            Feature(
                id="FEAT-01",
                upstream_ids=feat1_upstreams,
                module_name="OrderManagement",
                name="Order Checkout Flow",
                description="End-to-end checkout flow creating and submitting customer orders.",
                happy_path=[
                    "Select items from catalog",
                    "Specify shipping address and payment method",
                    "Confirm order and receive receipt",
                ],
                edge_cases=[
                    "Item inventory depleted during checkout",
                    "Payment gateway timeout or decline",
                    "Invalid shipping address format",
                ],
                state_machine=[
                    StateTransition(
                        from_state="DRAFT",
                        to_state="PENDING",
                        trigger_action="SUBMIT_ORDER",
                    ),
                    StateTransition(
                        from_state="PENDING",
                        to_state="PAID",
                        trigger_action="CONFIRM_PAYMENT",
                    ),
                    StateTransition(
                        from_state="PENDING",
                        to_state="CANCELLED",
                        trigger_action="CANCEL_ORDER",
                    ),
                ],
            ),
            Feature(
                id="FEAT-02",
                upstream_ids=feat2_upstreams,
                module_name="WorkspaceManagement",
                name="Workspace Administration",
                description="Administrative configuration of workspace settings and membership policies.",
                happy_path=[
                    "Open admin settings console",
                    "Update member permissions and security policies",
                    "Save configuration changes",
                ],
                edge_cases=[
                    "Removing the last workspace admin is rejected",
                    "Inviting an existing active member displays duplicate error",
                    "Session expiration during configuration update",
                ],
                state_machine=None,
            ),
        ]

    # Reflect human feedback on stale features when revising
    if feedback and stale_feats:
        revised: List[Feature] = []
        for feat in features:
            if feat.id in stale_feats:
                rf = feat.model_copy(deep=True)
                rf.description += f" [Revised: {feedback}]"
                rf.happy_path.append(f"Execute revised step: {feedback} [Revised: {feedback}]")
                revised.append(rf)
            else:
                revised.append(feat)
        features = revised

    return ProductArchitectOutput(features=features)


def run_product_architect(
    state: ProjectBlueprintState,
    blast_radius: Optional[Dict[str, Set[str]]] = None,
    retry_defects: Optional[List[ValidationDefect]] = None,
    settings: Optional[EngineSettings] = None,
) -> ProjectBlueprintState:
    """Execute Agent 2 (Product Architect) with strict Read Contract isolation and selective merging."""
    stale_features: Set[str] = set((blast_radius or {}).get("stale_features", set()))

    # STRICT READ CONTRACT: Only read glossary, actors, requirements, existing features
    # (when blast_radius is present), stale_features, human_feedback_notes, and retry_defects.
    # Never read database_entities or endpoints.
    user_payload: Dict[str, Any] = {
        "glossary": [g.model_dump() for g in state.glossary],
        "actors": [a.model_dump() for a in state.actors],
        "requirements": [r.model_dump() for r in state.requirements],
        "existing_features": [f.model_dump() for f in state.features] if stale_features else [],
        "stale_features": sorted(list(stale_features)),
        "human_feedback_notes": state.human_feedback_notes,
        "retry_defects": [
            d.model_dump()
            for d in (retry_defects or [])
            if d.target_agent == "ProductArchitect"
        ],
    }

    output: ProductArchitectOutput = invoke_structured_agent(
        schema_cls=ProductArchitectOutput,
        system_prompt=PRODUCT_SYSTEM_PROMPT,
        user_payload=user_payload,
        mock_builder=_mock_product_architect,
        settings=settings,
    )

    # Immutable update on cloned state
    new_state = state.model_copy(deep=True)

    # SELECTIVE MERGE: Merge features if state already has items and stale_features are present
    if new_state.features and stale_features:
        new_state.features = DAGChangePropagator.merge_regenerated_slice(
            existing_items=new_state.features,
            new_items=output.features,
            stale_ids=stale_features,
        )
    else:
        new_state.features = output.features

    return new_state

