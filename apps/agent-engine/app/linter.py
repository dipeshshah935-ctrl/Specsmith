from typing import List, Set
from app.schemas import (
    DefectSeverity,
    Priority,
    ProjectBlueprintState,
    ValidationDefect,
    ValidationReport,
    ValidationStatus,
)


class DeterministicLinter:
    """Tier 1 zero-token static verifier for graph integrity and referential rules."""

    @staticmethod
    def calculate_traceability_coverage(
        state: ProjectBlueprintState, gate_name: str = "GATE_1"
    ) -> float:
        """Calculate forward traceability coverage percentage for requirements."""
        if not state.requirements:
            return 100.0

        if gate_name == "GATE_1":
            covered_req_ids: Set[str] = set()
            for feat in state.features:
                covered_req_ids.update(feat.upstream_ids)
            covered = sum(1 for r in state.requirements if r.id in covered_req_ids)
            return round((covered / len(state.requirements)) * 100.0, 2)

        # GATE_2: Full forward traceability (REQ -> FEAT -> TBL or EP)
        feat_with_db: Set[str] = {
            uid for tbl in state.database_entities for uid in tbl.upstream_ids
        }
        feat_with_ep: Set[str] = {
            uid for ep in state.endpoints for uid in ep.upstream_ids
        }
        implemented_features = feat_with_db.union(feat_with_ep)

        fully_traced_reqs: Set[str] = {
            uid
            for feat in state.features
            if feat.id in implemented_features
            for uid in feat.upstream_ids
        }
        covered = sum(1 for r in state.requirements if r.id in fully_traced_reqs)
        return round((covered / len(state.requirements)) * 100.0, 2)

    @staticmethod
    def build_report(
        gate_name: str,
        defects: List[ValidationDefect],
        coverage_percent: float,
    ) -> ValidationReport:
        """Construct a ValidationReport with the appropriate status based on defects."""
        has_blocking = any(d.severity == DefectSeverity.BLOCKING for d in defects)
        has_warning = any(d.severity == DefectSeverity.WARNING for d in defects)

        if has_blocking:
            status = ValidationStatus.FAILED
        elif has_warning:
            status = ValidationStatus.WARNINGS
        else:
            status = ValidationStatus.PASSED

        return ValidationReport(
            gate_name=gate_name,
            status=status,
            defects=defects,
            traceability_coverage_percent=coverage_percent,
        )

    @staticmethod
    def lint_gate_1(state: ProjectBlueprintState) -> List[ValidationDefect]:
        """Perform Tier 1 static checks on Layer 1 (Requirements) and Layer 2 (Features)."""
        defects: List[ValidationDefect] = []
        req_ids: Set[str] = {r.id for r in state.requirements}
        actor_ids: Set[str] = {a.id for a in state.actors}
        covered_reqs: Set[str] = set()

        # 1. Requirement checks
        for req in state.requirements:
            if req.actor_id not in actor_ids:
                defects.append(
                    ValidationDefect(
                        rule_code="ERR_DANGLING_ACTOR",
                        severity=DefectSeverity.BLOCKING,
                        target_agent="RequirementAnalyst",
                        target_item_id=req.id,
                        message=f"Requirement {req.id} references unknown actor '{req.actor_id}'.",
                        suggested_fix="Assign a valid Actor.id from state.actors.",
                    )
                )

            if len(req.acceptance_criteria) == 0:
                defects.append(
                    ValidationDefect(
                        rule_code="ERR_EMPTY_ACCEPTANCE",
                        severity=DefectSeverity.BLOCKING,
                        target_agent="RequirementAnalyst",
                        target_item_id=req.id,
                        message=f"Requirement {req.id} has no acceptance criteria.",
                        suggested_fix="Add at least one measurable acceptance criterion.",
                    )
                )

        # 2. Feature checks
        for feat in state.features:
            if not feat.upstream_ids:
                defects.append(
                    ValidationDefect(
                        rule_code="ERR_UNLINKED_FEATURE",
                        severity=DefectSeverity.BLOCKING,
                        target_agent="ProductArchitect",
                        target_item_id=feat.id,
                        message=f"Feature {feat.id} has no upstream requirement links.",
                        suggested_fix="Populate upstream_ids with valid REQ-* IDs.",
                    )
                )

            for up_id in feat.upstream_ids:
                if up_id not in req_ids:
                    defects.append(
                        ValidationDefect(
                            rule_code="ERR_INVALID_UPSTREAM_REQ",
                            severity=DefectSeverity.BLOCKING,
                            target_agent="ProductArchitect",
                            target_item_id=feat.id,
                            message=f"Feature {feat.id} references non-existent requirement '{up_id}'.",
                            suggested_fix="Reference only declared REQ-* IDs.",
                        )
                    )
                else:
                    covered_reqs.add(up_id)

            if len(feat.edge_cases) == 0:
                defects.append(
                    ValidationDefect(
                        rule_code="ERR_MISSING_EDGE_CASES",
                        severity=DefectSeverity.WARNING,
                        target_agent="ProductArchitect",
                        target_item_id=feat.id,
                        message=f"Feature {feat.id} does not document any edge cases.",
                        suggested_fix="Document boundary and failure conditions in edge_cases.",
                    )
                )

        # 3. Orphan requirement checks
        for req in state.requirements:
            if req.id not in covered_reqs:
                sev = (
                    DefectSeverity.BLOCKING
                    if req.priority == Priority.MUST_HAVE
                    else DefectSeverity.WARNING
                )
                defects.append(
                    ValidationDefect(
                        rule_code="ERR_ORPHAN_REQUIREMENT",
                        severity=sev,
                        target_agent="ProductArchitect",
                        target_item_id=req.id,
                        message=f"Requirement {req.id} ('{req.title}') is not covered by any feature.",
                        suggested_fix="Add or update a Feature with this REQ ID in upstream_ids.",
                    )
                )

        return defects

    @staticmethod
    def lint_gate_2(state: ProjectBlueprintState) -> List[ValidationDefect]:
        """Perform Tier 1 static checks on Layer 3 (Database) and Layer 4 (API)."""
        defects: List[ValidationDefect] = []
        feat_ids: Set[str] = {f.id for f in state.features}
        actor_ids: Set[str] = {a.id for a in state.actors}
        table_map = {t.table_name: t for t in state.database_entities}
        table_ids: Set[str] = {t.id for t in state.database_entities}
        covered_features: Set[str] = set()

        # 1. Database Entity checks
        for tbl in state.database_entities:
            # Primary key check
            has_pk = any(col.is_primary_key for col in tbl.columns)
            if not has_pk:
                defects.append(
                    ValidationDefect(
                        rule_code="ERR_MISSING_PRIMARY_KEY",
                        severity=DefectSeverity.BLOCKING,
                        target_agent="DatabaseArchitect",
                        target_item_id=tbl.id,
                        message=f"Table '{tbl.table_name}' ({tbl.id}) has no column marked with is_primary_key=True.",
                        suggested_fix="Mark at least one column as is_primary_key=True.",
                    )
                )

            # Upstream feature check
            for up_id in tbl.upstream_ids:
                if up_id not in feat_ids:
                    defects.append(
                        ValidationDefect(
                            rule_code="ERR_INVALID_UPSTREAM_FEATURE",
                            severity=DefectSeverity.BLOCKING,
                            target_agent="DatabaseArchitect",
                            target_item_id=tbl.id,
                            message=f"Table '{tbl.table_name}' links to unknown feature '{up_id}'.",
                            suggested_fix="Link upstream_ids to valid FEAT-* IDs.",
                        )
                    )
                else:
                    covered_features.add(up_id)

            # Foreign key relationships
            for rel in tbl.relationships:
                if rel.references_entity not in table_map:
                    defects.append(
                        ValidationDefect(
                            rule_code="ERR_DANGLING_FOREIGN_KEY",
                            severity=DefectSeverity.BLOCKING,
                            target_agent="DatabaseArchitect",
                            target_item_id=tbl.id,
                            message=f"Table '{tbl.table_name}' references missing table '{rel.references_entity}'.",
                            suggested_fix="Create the target table or fix references_entity name.",
                        )
                    )
                else:
                    target_cols = {c.name for c in table_map[rel.references_entity].columns}
                    if rel.references_column not in target_cols:
                        defects.append(
                            ValidationDefect(
                                rule_code="ERR_DANGLING_FK_COLUMN",
                                severity=DefectSeverity.BLOCKING,
                                target_agent="DatabaseArchitect",
                                target_item_id=tbl.id,
                                message=(
                                    f"FK '{rel.foreign_key_column}' in '{tbl.table_name}' targets missing "
                                    f"column '{rel.references_column}' on '{rel.references_entity}'."
                                ),
                                suggested_fix="Ensure target column exists on referenced table.",
                            )
                        )

                # Unindexed foreign key check
                fk_col = rel.foreign_key_column
                is_indexed = any(fk_col in idx for idx in tbl.indexes)
                if not is_indexed:
                    defects.append(
                        ValidationDefect(
                            rule_code="ERR_UNINDEXED_FOREIGN_KEY",
                            severity=DefectSeverity.WARNING,
                            target_agent="DatabaseArchitect",
                            target_item_id=tbl.id,
                            message=(
                                f"Foreign key column '{fk_col}' in '{tbl.table_name}' is not indexed."
                            ),
                            suggested_fix=f"Add '{fk_col}' to indexes list of table '{tbl.table_name}'.",
                        )
                    )

        # 2. Endpoint checks
        valid_ep_upstreams = feat_ids.union(table_ids)
        for ep in state.endpoints:
            # Actor permissions check
            for act_id in ep.allowed_actor_ids:
                if act_id not in actor_ids:
                    defects.append(
                        ValidationDefect(
                            rule_code="ERR_UNKNOWN_ACTOR_PERMISSION",
                            severity=DefectSeverity.BLOCKING,
                            target_agent="APIArchitect",
                            target_item_id=ep.id,
                            message=f"Endpoint '{ep.http_method} {ep.path}' permits unknown actor '{act_id}'.",
                            suggested_fix="Use valid ACT-* IDs from state.actors.",
                        )
                    )

            # Upstream links check
            if not ep.upstream_ids:
                defects.append(
                    ValidationDefect(
                        rule_code="ERR_ORPHAN_ENDPOINT",
                        severity=DefectSeverity.BLOCKING,
                        target_agent="APIArchitect",
                        target_item_id=ep.id,
                        message=f"Endpoint '{ep.id}' has no upstream links.",
                        suggested_fix="Link endpoint upstream_ids to valid FEAT-* or TBL-* IDs.",
                    )
                )
            else:
                for up_id in ep.upstream_ids:
                    if up_id not in valid_ep_upstreams:
                        defects.append(
                            ValidationDefect(
                                rule_code="ERR_ORPHAN_ENDPOINT",
                                severity=DefectSeverity.BLOCKING,
                                target_agent="APIArchitect",
                                target_item_id=ep.id,
                                message=f"Endpoint '{ep.id}' references unknown upstream ID '{up_id}'.",
                                suggested_fix="Link endpoint upstream_ids to valid FEAT-* or TBL-* IDs.",
                            )
                        )
                    elif up_id in feat_ids:
                        covered_features.add(up_id)

        # 3. Feature data coverage check
        for feat in state.features:
            if feat.id not in covered_features:
                defects.append(
                    ValidationDefect(
                        rule_code="ERR_ORPHAN_FEATURE_DATA",
                        severity=DefectSeverity.WARNING,
                        target_agent="DatabaseArchitect",
                        target_item_id=feat.id,
                        message=f"Feature {feat.id} ('{feat.name}') is not referenced by any database entity or endpoint.",
                        suggested_fix="Ensure this feature is supported by database entities or API endpoints.",
                    )
                )

        return defects

