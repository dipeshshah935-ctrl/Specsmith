from typing import Dict, List, Set, Tuple, TypeVar
from app.schemas import ProjectBlueprintState

T = TypeVar("T")


class DAGChangePropagator:
    """Computes downstream impact across REQ -> FEAT -> TBL -> EP when human edits occur."""

    @staticmethod
    def compute_blast_radius(
        state: ProjectBlueprintState,
        modified_ids: Set[str],
    ) -> Dict[str, Set[str]]:
        """Calculate the blast radius of modified items across all architectural layers.

        Traces dependencies through:
        ACT -> REQ -> FEAT -> TBL -> EP (plus transitive foreign-key table dependencies)
        """
        stale_requirements: Set[str] = set()
        stale_features: Set[str] = set()
        stale_tables: Set[str] = set()
        stale_endpoints: Set[str] = set()

        # Layer 1: Requirements triggered by modified Actor IDs or directly modified REQ IDs
        for req in state.requirements:
            if req.id in modified_ids or req.actor_id in modified_ids:
                stale_requirements.add(req.id)

        # Layer 2: Features affected by modified feature IDs or upstream stale requirements
        req_triggers = modified_ids.union(stale_requirements)
        for feat in state.features:
            if feat.id in modified_ids or any(uid in req_triggers for uid in feat.upstream_ids):
                stale_features.add(feat.id)

        # Layer 3: Database entities directly modified or upstreamed by stale features
        l2_triggers = modified_ids.union(stale_features)
        for tbl in state.database_entities:
            if tbl.id in modified_ids or any(uid in l2_triggers for uid in tbl.upstream_ids):
                stale_tables.add(tbl.id)

        # Transitive foreign-key table dependencies:
        # If Table B has a foreign key referencing Table A and Table A is stale, Table B is also stale
        changed = True
        while changed:
            changed = False
            stale_table_names = {
                tbl.table_name for tbl in state.database_entities if tbl.id in stale_tables
            }
            for tbl in state.database_entities:
                if tbl.id not in stale_tables:
                    has_fk_to_stale = any(
                        rel.references_entity in stale_table_names
                        for rel in tbl.relationships
                    )
                    if has_fk_to_stale:
                        stale_tables.add(tbl.id)
                        changed = True

        # Layer 4: Endpoints affected by modified endpoints, stale features/tables, or modified actors
        l3_triggers = l2_triggers.union(stale_tables)
        for ep in state.endpoints:
            endpoint_affected = (
                ep.id in modified_ids
                or any(uid in l3_triggers for uid in ep.upstream_ids)
                or any(act_id in modified_ids for act_id in ep.allowed_actor_ids)
            )
            if endpoint_affected:
                stale_endpoints.add(ep.id)

        return {
            "stale_requirements": stale_requirements,
            "stale_features": stale_features,
            "stale_tables": stale_tables,
            "stale_endpoints": stale_endpoints,
        }

    @staticmethod
    def merge_regenerated_slice(
        existing_items: List[T],
        new_items: List[T],
        stale_ids: Set[str],
    ) -> List[T]:
        """Preserve untouched items while merging regenerated stale items sorted by ID.

        - Preserves items in existing_items whose .id is not in stale_ids.
        - Replaces items in stale_ids with their updated versions from new_items.
        - Appends any brand-new items from new_items.
        - Returns the combined list sorted deterministically by .id.
        """
        merged_map: Dict[str, T] = {}

        # 1. Keep untouched existing items
        for item in existing_items:
            item_id = getattr(item, "id", None)
            if item_id and item_id not in stale_ids:
                merged_map[item_id] = item

        # 2. Add / overwrite with new items (stale replacements or newly introduced items)
        for item in new_items:
            item_id = getattr(item, "id", None)
            if item_id:
                merged_map[item_id] = item

        # 3. Return sorted deterministically by .id
        return sorted(merged_map.values(), key=lambda x: getattr(x, "id", ""))

    @staticmethod
    def create_next_version_snapshot(
        current_state: ProjectBlueprintState,
        modified_ids: Set[str],
        human_notes: str = "",
    ) -> Tuple[ProjectBlueprintState, Dict[str, Set[str]]]:
        """Clone the current state to a new immutable version and compute its blast radius."""
        blast = DAGChangePropagator.compute_blast_radius(current_state, modified_ids)
        next_state = current_state.model_copy(deep=True)
        next_state.version += 1
        next_state.human_approved = False
        next_state.human_feedback_notes = human_notes
        return next_state, blast
