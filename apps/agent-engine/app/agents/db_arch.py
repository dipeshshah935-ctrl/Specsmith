from typing import Any, Dict, List, Optional, Set
from app.agents.base import invoke_structured_agent
from app.config import EngineSettings
from app.propagator import DAGChangePropagator
from app.schemas import (
    ColumnDefinition,
    DatabaseArchitectOutput,
    DatabaseEntity,
    EntityRelationship,
    OnDeleteAction,
    ProjectBlueprintState,
    ValidationDefect,
)

DATABASE_SYSTEM_PROMPT = """You are a Principal Database Architect designing relational database schemas in Third Normal Form (3NF).

Using ONLY the Glossary and Features provided:
1. Deterministic IDs: Assign IDs strictly matching pattern ^TBL-\\d{2,4}$ (e.g. 'TBL-01', 'TBL-02').
2. Naming Conventions: Use snake_case plural table names matching ^[a-z][a-z0-9_]*$ (e.g. 'orders', 'order_items', 'workspaces').
3. Primary Keys: Every table must have at least one column marked with is_primary_key=True.
4. Bidirectional Traceability: Link every table's upstream_ids to at least one valid FEAT-*.id. Every feature must be supported.
5. Explicit Foreign Keys: For relational integrity, define foreign keys with on_delete ('RESTRICT', 'CASCADE', or 'SET NULL').
   The foreign_key_column MUST exist in the table's own columns and MUST be included in the table's indexes list.
6. Privacy by Design: Mark sensitive or personally identifiable data columns with is_pii=True.
7. Indexing Strategy: Declare single or composite indexes in the indexes list for primary keys, foreign keys, and frequently queried columns.
"""


def _mock_database_architect(payload: Dict[str, Any]) -> DatabaseArchitectOutput:
    """Deterministic mock builder for Database Architect adhering to StrictContractModel."""
    stale_tbls: Set[str] = set(payload.get("stale_tables") or [])
    feedback: Optional[str] = payload.get("human_feedback_notes")
    raw_feats: List[Dict[str, Any]] = payload.get("features") or []

    feat_ids = [f["id"] for f in raw_feats if isinstance(f, dict) and "id" in f]
    feat1_upstreams = [feat_ids[0]] if feat_ids else ["FEAT-01"]
    feat2_upstreams = feat_ids[1:] if len(feat_ids) > 1 else feat1_upstreams

    existing_raw = payload.get("existing_database_entities") or []
    if existing_raw:
        tables = [DatabaseEntity.model_validate(t) for t in existing_raw]
    else:
        tables = [
            DatabaseEntity(
                id="TBL-01",
                upstream_ids=feat1_upstreams,
                table_name="orders",
                columns=[
                    ColumnDefinition(
                        name="id",
                        data_type="UUID",
                        is_primary_key=True,
                        is_nullable=False,
                        is_unique=True,
                        is_pii=False,
                    ),
                    ColumnDefinition(
                        name="customer_id",
                        data_type="UUID",
                        is_primary_key=False,
                        is_nullable=False,
                        is_unique=False,
                        is_pii=True,
                    ),
                    ColumnDefinition(
                        name="status",
                        data_type="VARCHAR(50)",
                        is_primary_key=False,
                        is_nullable=False,
                        is_unique=False,
                        is_pii=False,
                    ),
                    ColumnDefinition(
                        name="created_at",
                        data_type="TIMESTAMPTZ",
                        is_primary_key=False,
                        is_nullable=False,
                        is_unique=False,
                        is_pii=False,
                    ),
                ],
                relationships=[],
                indexes=["id", "customer_id", "status"],
            ),
            DatabaseEntity(
                id="TBL-02",
                upstream_ids=feat2_upstreams,
                table_name="order_items",
                columns=[
                    ColumnDefinition(
                        name="id",
                        data_type="UUID",
                        is_primary_key=True,
                        is_nullable=False,
                        is_unique=True,
                        is_pii=False,
                    ),
                    ColumnDefinition(
                        name="order_id",
                        data_type="UUID",
                        is_primary_key=False,
                        is_nullable=False,
                        is_unique=False,
                        is_pii=False,
                    ),
                    ColumnDefinition(
                        name="product_name",
                        data_type="VARCHAR(255)",
                        is_primary_key=False,
                        is_nullable=False,
                        is_unique=False,
                        is_pii=False,
                    ),
                    ColumnDefinition(
                        name="quantity",
                        data_type="INTEGER",
                        is_primary_key=False,
                        is_nullable=False,
                        is_unique=False,
                        is_pii=False,
                    ),
                    ColumnDefinition(
                        name="unit_price",
                        data_type="NUMERIC(10,2)",
                        is_primary_key=False,
                        is_nullable=False,
                        is_unique=False,
                        is_pii=False,
                    ),
                ],
                relationships=[
                    EntityRelationship(
                        foreign_key_column="order_id",
                        references_entity="orders",
                        references_column="id",
                        on_delete=OnDeleteAction.CASCADE,
                    )
                ],
                indexes=["id", "order_id"],
            ),
        ]

    # Reflect human feedback on stale tables when revising
    if feedback and stale_tbls:
        revised: List[DatabaseEntity] = []
        for tbl in tables:
            if tbl.id in stale_tbls:
                rt = tbl.model_copy(deep=True)
                rt.columns.append(
                    ColumnDefinition(
                        name="revised_notes",
                        data_type="TEXT",
                        is_primary_key=False,
                        is_nullable=True,
                        is_unique=False,
                        is_pii=False,
                    )
                )
                rt.indexes.append("revised_notes")
                revised.append(rt)
            else:
                revised.append(tbl)
        tables = revised

    return DatabaseArchitectOutput(database_entities=tables)


def run_database_architect(
    state: ProjectBlueprintState,
    blast_radius: Optional[Dict[str, Set[str]]] = None,
    retry_defects: Optional[List[ValidationDefect]] = None,
    settings: Optional[EngineSettings] = None,
) -> ProjectBlueprintState:
    """Execute Agent 3: Database Architect with strict read contract and selective merging."""
    stale_tbls = blast_radius.get("stale_tables") if blast_radius else None

    # Strict read contract: only extract glossary, features, existing entities if revising,
    # stale_tables, human_feedback_notes, and retry defects targeted at DatabaseArchitect.
    # Never read endpoints.
    relevant_defects = [
        d for d in (retry_defects or []) if d.target_agent == "DatabaseArchitect"
    ]

    user_payload: Dict[str, Any] = {
        "glossary": [g.model_dump() for g in state.glossary],
        "features": [f.model_dump() for f in state.features],
        "human_feedback_notes": state.human_feedback_notes,
        "stale_tables": list(stale_tbls) if stale_tbls else [],
        "retry_defects": [d.model_dump() for d in relevant_defects],
    }

    if stale_tbls and state.database_entities:
        user_payload["existing_database_entities"] = [
            t.model_dump() for t in state.database_entities
        ]

    output: DatabaseArchitectOutput = invoke_structured_agent(
        schema_cls=DatabaseArchitectOutput,
        system_prompt=DATABASE_SYSTEM_PROMPT,
        user_payload=user_payload,
        mock_builder=_mock_database_architect,
        settings=settings,
    )

    new_state = state.model_copy(deep=True)

    if new_state.database_entities and stale_tbls:
        new_state.database_entities = DAGChangePropagator.merge_regenerated_slice(
            existing_items=new_state.database_entities,
            new_items=output.database_entities,
            stale_ids=stale_tbls,
        )
    else:
        new_state.database_entities = output.database_entities

    return new_state
