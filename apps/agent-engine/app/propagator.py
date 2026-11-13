from typing import Dict, Set, Tuple
from app.schemas import ProjectBlueprintState


class DAGChangePropagator:
    """Computes downstream impact across REQ -> FEAT -> TBL -> EP when human edits occur."""

    @staticmethod
    def compute_blast_radius(
        state: ProjectBlueprintState,
        modified_ids: Set[str],
    ) -> Dict[str, Set[str]]:
        """Calculate the blast radius of modified items across all architectural layers.

        Traces dependencies through:
        ACT -> REQ -> FEAT -> TBL -> EP
        """
        stale_features: Set[str] = set()
        stale_tables: Set[str] = set()
        stale_endpoints: Set[str] = set()

        # Expand triggers to requirements if any Actor was modified
        req_triggers = set(modified_ids)
        for req in state.requirements:
            if req.actor_id in modified_ids:
                req_triggers.add(req.id)

        # Layer 2: Features affected by modified features or upstream requirements/actors
        for feat in state.features:
            if feat.id in modified_ids or any(uid in req_triggers for uid in feat.upstream_ids):
                stale_features.add(feat.id)

        # Layer 3: Database Entities affected by modified tables or upstream features
        l2_triggers = modified_ids.union(stale_features)
        for tbl in state.database_entities:
            if tbl.id in modified_ids or any(uid in l2_triggers for uid in tbl.upstream_ids):
                stale_tables.add(tbl.id)

        # Layer 4: Endpoints affected by modified endpoints, tables, or features
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
        human_notes: str = "",
    ) -> Tuple[ProjectBlueprintState, Dict[str, Set[str]]]:
        """Clone the current state to a new immutable version and compute its blast radius."""
        blast = DAGChangePropagator.compute_blast_radius(current_state, modified_ids)
        next_state = current_state.model_copy(deep=True)
        next_state.version += 1
        next_state.human_approved = False
        next_state.human_feedback_notes = human_notes
        return next_state, blast

