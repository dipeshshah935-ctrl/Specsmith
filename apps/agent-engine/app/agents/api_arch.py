from typing import Any, Dict, List, Optional, Set
from app.agents.base import invoke_structured_agent
from app.config import EngineSettings
from app.propagator import DAGChangePropagator
from app.schemas import (
    APIArchitectOutput,
    EndpointSpec,
    HTTPMethod,
    ProjectBlueprintState,
    ValidationDefect,
)

API_SYSTEM_PROMPT = """You are a Principal API Architect designing enterprise RESTful APIs following OpenAPI 3.1 and RFC 7807 standards.

Using ONLY the Glossary, Actors, Features, and Database Entities provided:
1. Deterministic IDs: Assign IDs strictly matching pattern ^EP-\\d{2,4}$ (e.g. 'EP-01', 'EP-02').
2. RESTful URIs: Resource paths must strictly match pattern ^/api/v\\d+/[a-z0-9_/\\-{}]*$ (e.g. '/api/v1/orders', '/api/v1/orders/{order_id}').
3. Bidirectional Traceability: EVERY endpoint's upstream_ids MUST include at least one valid FEAT-*.id AND at least one valid TBL-*.id. Every feature and table must be properly exposed or supported.
4. Least Privilege RBAC: Declare allowed_actor_ids with at least one valid ACT-*.id matching who has authorization to invoke the route.
5. Idempotency: Set is_idempotent=True on all GET, PUT, and DELETE routes, as well as on state-transition POST endpoints.
6. RFC 7807 Error Responses: Declare standard HTTP error_codes applicable to the operation (e.g. [400, 401, 403, 404, 409]).
7. Schemas: Provide request_dto_schema (when request body is expected) and response_dto_schema in valid JSON Schema format.
"""


def _mock_api_architect(payload: Dict[str, Any]) -> APIArchitectOutput:
    """Deterministic mock builder for API Architect adhering to StrictContractModel."""
    stale_eps: Set[str] = set(payload.get("stale_endpoints") or [])
    feedback: Optional[str] = payload.get("human_feedback_notes")

    raw_actors: List[Dict[str, Any]] = payload.get("actors") or []
    raw_feats: List[Dict[str, Any]] = payload.get("features") or []
    raw_tables: List[Dict[str, Any]] = payload.get("database_entities") or []

    actor_ids = [a["id"] for a in raw_actors if isinstance(a, dict) and "id" in a] or ["ACT-01", "ACT-02"]
    feat_ids = [f["id"] for f in raw_feats if isinstance(f, dict) and "id" in f] or ["FEAT-01", "FEAT-02"]
    table_ids = [t["id"] for t in raw_tables if isinstance(t, dict) and "id" in t] or ["TBL-01", "TBL-02"]

    f1 = feat_ids[0]
    f2 = feat_ids[1] if len(feat_ids) > 1 else feat_ids[0]
    t1 = table_ids[0]
    t2 = table_ids[1] if len(table_ids) > 1 else table_ids[0]

    existing_raw = payload.get("existing_endpoints") or []
    if existing_raw:
        endpoints = [EndpointSpec.model_validate(ep) for ep in existing_raw]
    else:
        endpoints = [
            EndpointSpec(
                id="EP-01",
                upstream_ids=[f1, t1],
                http_method=HTTPMethod.POST,
                path="/api/v1/orders",
                summary="Create and place a new customer order",
                allowed_actor_ids=[actor_ids[1]] if len(actor_ids) > 1 else [actor_ids[0]],
                is_idempotent=True,
                request_dto_schema={
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string"},
                        "items": {"type": "array"},
                    },
                    "required": ["customer_id", "items"],
                },
                response_dto_schema={
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "status": {"type": "string"},
                    },
                    "required": ["order_id", "status"],
                },
                error_codes=[400, 401, 403, 404, 409],
            ),
            EndpointSpec(
                id="EP-02",
                upstream_ids=[f1, t1],
                http_method=HTTPMethod.GET,
                path="/api/v1/orders/{order_id}",
                summary="Retrieve order details by order_id",
                allowed_actor_ids=actor_ids,
                is_idempotent=True,
                request_dto_schema=None,
                response_dto_schema={
                    "type": "object",
                    "properties": {
                        "order": {"type": "object"},
                    },
                    "required": ["order"],
                },
                error_codes=[400, 401, 403, 404],
            ),
            EndpointSpec(
                id="EP-03",
                upstream_ids=[f2, t2],
                http_method=HTTPMethod.GET,
                path="/api/v1/order-items",
                summary="List all order items for administration and auditing",
                allowed_actor_ids=[actor_ids[0]],
                is_idempotent=True,
                request_dto_schema=None,
                response_dto_schema={
                    "type": "object",
                    "properties": {
                        "items": {"type": "array"},
                    },
                    "required": ["items"],
                },
                error_codes=[400, 401, 403, 404],
            ),
            EndpointSpec(
                id="EP-04",
                upstream_ids=[f2, t2],
                http_method=HTTPMethod.PUT,
                path="/api/v1/order-items/{item_id}",
                summary="Update order item quantity or parameters",
                allowed_actor_ids=[actor_ids[0]],
                is_idempotent=True,
                request_dto_schema={
                    "type": "object",
                    "properties": {
                        "quantity": {"type": "integer"},
                    },
                    "required": ["quantity"],
                },
                response_dto_schema={
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string"},
                        "status": {"type": "string"},
                    },
                    "required": ["item_id", "status"],
                },
                error_codes=[400, 401, 403, 404, 409],
            ),
        ]

    # Reflect human feedback on stale endpoints when revising
    if feedback and stale_eps:
        revised: List[EndpointSpec] = []
        for ep in endpoints:
            if ep.id in stale_eps:
                rep = ep.model_copy(deep=True)
                rep.summary += f" [Revised: {feedback}]"
                revised.append(rep)
            else:
                revised.append(ep)
        endpoints = revised

    return APIArchitectOutput(endpoints=endpoints)


def run_api_architect(
    state: ProjectBlueprintState,
    blast_radius: Optional[Dict[str, Set[str]]] = None,
    retry_defects: Optional[List[ValidationDefect]] = None,
    settings: Optional[EngineSettings] = None,
) -> ProjectBlueprintState:
    """Execute Agent 4: API Architect with strict read contract and selective merging."""
    stale_eps = blast_radius.get("stale_endpoints") if blast_radius else None

    # Strict read contract: only extract glossary, actors, features, database_entities,
    # existing endpoints if revising, stale_endpoints, human_feedback_notes, and retry defects targeted at APIArchitect.
    # Never read requirements directly.
    relevant_defects = [
        d for d in (retry_defects or []) if d.target_agent == "APIArchitect"
    ]

    user_payload: Dict[str, Any] = {
        "glossary": [g.model_dump() for g in state.glossary],
        "actors": [a.model_dump() for a in state.actors],
        "features": [f.model_dump() for f in state.features],
        "database_entities": [t.model_dump() for t in state.database_entities],
        "human_feedback_notes": state.human_feedback_notes,
        "stale_endpoints": list(stale_eps) if stale_eps else [],
        "retry_defects": [d.model_dump() for d in relevant_defects],
    }

    if stale_eps and state.endpoints:
        user_payload["existing_endpoints"] = [
            ep.model_dump() for ep in state.endpoints
        ]

    output: APIArchitectOutput = invoke_structured_agent(
        schema_cls=APIArchitectOutput,
        system_prompt=API_SYSTEM_PROMPT,
        user_payload=user_payload,
        mock_builder=_mock_api_architect,
        settings=settings,
    )

    new_state = state.model_copy(deep=True)

    if new_state.endpoints and stale_eps:
        new_state.endpoints = DAGChangePropagator.merge_regenerated_slice(
            existing_items=new_state.endpoints,
            new_items=output.endpoints,
            stale_ids=stale_eps,
        )
    else:
        new_state.endpoints = output.endpoints

    return new_state

