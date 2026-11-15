from datetime import datetime
import json
import pytest

from app.schemas import (
    Actor,
    ColumnDefinition,
    DatabaseEntity,
    DefectSeverity,
    EndpointSpec,
    EntityRelationship,
    Feature,
    GlossaryTerm,
    Priority,
    ProjectBlueprintState,
    ProjectPhase,
    Requirement,
    StateTransition,
    ValidationDefect,
    ValidationReport,
    ValidationStatus,
)
from app.linter import DeterministicLinter
from app.propagator import DAGChangePropagator


# =====================================================================
# FIXTURES
# =====================================================================

@pytest.fixture
def sample_actors():
    return [
        Actor(
            id="ACT-01",
            name="Admin",
            description="System administrator with full privileges",
            permissions_summary=["manage_users", "manage_billing"],
        ),
        Actor(
            id="ACT-02",
            name="Customer",
            description="End-user purchasing services",
            permissions_summary=["view_catalog", "create_order"],
        ),
    ]


@pytest.fixture
def sample_requirements():
    return [
        Requirement(
            id="REQ-01",
            actor_id="ACT-02",
            title="Place Order",
            description="Customer can submit an order for selected items.",
            priority=Priority.MUST_HAVE,
            acceptance_criteria=["Order is persisted with status PENDING", "Confirmation email sent"],
        ),
        Requirement(
            id="REQ-02",
            actor_id="ACT-01",
            title="Cancel Order",
            description="Admin can cancel any pending order.",
            priority=Priority.SHOULD_HAVE,
            acceptance_criteria=["Order status transitions to CANCELLED", "Audit log recorded"],
        ),
    ]


@pytest.fixture
def sample_features():
    return [
        Feature(
            id="FEAT-01",
            upstream_ids=["REQ-01"],
            module_name="OrderManagement",
            name="Order Checkout",
            description="Checkout flow converting cart items into an order.",
            happy_path=["Select payment method", "Submit order", "Receive receipt"],
            edge_cases=["Insufficient inventory error", "Payment gateway timeout"],
            state_machine=[
                StateTransition(from_state="DRAFT", to_state="PENDING", trigger_action="SUBMIT"),
                StateTransition(from_state="PENDING", to_state="PAID", trigger_action="PAY"),
            ],
        ),
        Feature(
            id="FEAT-02",
            upstream_ids=["REQ-02"],
            module_name="OrderManagement",
            name="Order Cancellation",
            description="Cancellation flow for administrative oversight.",
            happy_path=["Select order", "Provide reason", "Confirm cancellation"],
            edge_cases=["Cannot cancel already shipped order"],
            state_machine=[
                StateTransition(from_state="PENDING", to_state="CANCELLED", trigger_action="CANCEL"),
            ],
        ),
    ]


@pytest.fixture
def sample_database_entities():
    return [
        DatabaseEntity(
            id="TBL-01",
            upstream_ids=["FEAT-01", "FEAT-02"],
            table_name="orders",
            columns=[
                ColumnDefinition(name="id", data_type="UUID", is_primary_key=True),
                ColumnDefinition(name="customer_id", data_type="UUID", is_pii=True),
                ColumnDefinition(name="status", data_type="VARCHAR(32)"),
                ColumnDefinition(name="created_at", data_type="TIMESTAMPTZ"),
            ],
            relationships=[],
            indexes=["id", "customer_id", "status"],
        ),
        DatabaseEntity(
            id="TBL-02",
            upstream_ids=["FEAT-01"],
            table_name="order_items",
            columns=[
                ColumnDefinition(name="id", data_type="UUID", is_primary_key=True),
                ColumnDefinition(name="order_id", data_type="UUID"),
                ColumnDefinition(name="item_id", data_type="UUID"),
                ColumnDefinition(name="quantity", data_type="INT"),
            ],
            relationships=[
                EntityRelationship(
                    foreign_key_column="order_id",
                    references_entity="orders",
                    references_column="id",
                    on_delete="CASCADE",
                ),
            ],
            indexes=["id", "order_id"],
        ),
    ]


@pytest.fixture
def sample_endpoints():
    return [
        EndpointSpec(
            id="EP-01",
            upstream_ids=["FEAT-01", "TBL-01"],
            http_method="POST",
            path="/api/v1/orders",
            summary="Create a new order",
            allowed_actor_ids=["ACT-02"],
            is_idempotent=True,
            request_dto_schema={"type": "object", "properties": {"items": {"type": "array"}}},
            response_dto_schema={"type": "object", "properties": {"order_id": {"type": "string"}}},
            error_codes=[400, 401, 403, 409, 500],
        ),
        EndpointSpec(
            id="EP-02",
            upstream_ids=["FEAT-02", "TBL-01"],
            http_method="POST",
            path="/api/v1/orders/{order_id}/cancel",
            summary="Cancel an existing order",
            allowed_actor_ids=["ACT-01"],
            is_idempotent=True,
            request_dto_schema=None,
            response_dto_schema={"type": "object", "properties": {"status": {"type": "string"}}},
            error_codes=[400, 401, 403, 404, 409],
        ),
    ]


@pytest.fixture
def clean_blueprint_state(
    sample_actors, sample_requirements, sample_features, sample_database_entities, sample_endpoints
):
    return ProjectBlueprintState(
        project_id="proj-test-101",
        version=1,
        current_phase=ProjectPhase.DISCOVERY,
        user_initial_prompt="Build an e-commerce order management system",
        glossary=[
            GlossaryTerm(term="Order", definition="A commercial transaction between customer and merchant"),
            GlossaryTerm(term="Customer", definition="An end user purchasing goods"),
        ],
        actors=sample_actors,
        requirements=sample_requirements,
        features=sample_features,
        database_entities=sample_database_entities,
        endpoints=sample_endpoints,
    )


# =====================================================================
# 1. SCHEMAS TESTS: SERIALIZATION & ROUNDTRIP
# =====================================================================

class TestSchemas:
    def test_blueprint_state_defaults(self):
        state = ProjectBlueprintState(
            project_id="proj-default",
            user_initial_prompt="Build something",
        )
        assert state.version == 1
        assert state.current_phase == ProjectPhase.DISCOVERY
        assert state.human_approved is False
        assert state.human_feedback_notes is None
        assert state.glossary == []
        assert state.actors == []
        assert state.requirements == []
        assert state.features == []
        assert state.database_entities == []
        assert state.endpoints == []
        assert state.validation_reports == []
        assert isinstance(state.created_at, datetime)

    def test_json_roundtrip(self, clean_blueprint_state):
        raw_json = clean_blueprint_state.model_dump_json()
        assert isinstance(raw_json, str)
        parsed = json.loads(raw_json)
        assert parsed["project_id"] == "proj-test-101"
        assert len(parsed["actors"]) == 2
        assert len(parsed["requirements"]) == 2
        assert len(parsed["features"]) == 2
        assert len(parsed["database_entities"]) == 2
        assert len(parsed["endpoints"]) == 2

        restored = ProjectBlueprintState.model_validate_json(raw_json)
        assert restored.project_id == clean_blueprint_state.project_id
        assert restored.version == clean_blueprint_state.version
        assert restored.requirements[0].id == "REQ-01"
        assert restored.database_entities[1].relationships[0].references_entity == "orders"


# =====================================================================
# 2. DETERMINISTIC LINTER: GATE 1 TESTS
# =====================================================================

class TestGate1Linter:
    def test_gate_1_clean_state(self, clean_blueprint_state):
        defects = DeterministicLinter.lint_gate_1(clean_blueprint_state)
        blocking = [d for d in defects if d.severity == DefectSeverity.BLOCKING]
        assert blocking == []
        report = DeterministicLinter.build_report(
            "GATE_1", defects, DeterministicLinter.calculate_traceability_coverage(clean_blueprint_state, "GATE_1")
        )
        assert report.status == ValidationStatus.PASSED
        assert report.traceability_coverage_percent == 100.0

    def test_catches_dangling_actor(self, clean_blueprint_state):
        clean_blueprint_state.requirements[0].actor_id = "ACT-UNKNOWN"
        defects = DeterministicLinter.lint_gate_1(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_DANGLING_ACTOR"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert err.target_item_id == "REQ-01"
        assert err.target_agent == "RequirementAnalyst"

    def test_catches_empty_acceptance(self, clean_blueprint_state):
        clean_blueprint_state.requirements[0].acceptance_criteria = []
        defects = DeterministicLinter.lint_gate_1(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_EMPTY_ACCEPTANCE"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert err.target_item_id == "REQ-01"
        assert err.target_agent == "RequirementAnalyst"

    def test_catches_unlinked_feature(self, clean_blueprint_state):
        clean_blueprint_state.features[0].upstream_ids = []
        defects = DeterministicLinter.lint_gate_1(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_UNLINKED_FEATURE"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert err.target_item_id == "FEAT-01"
        assert err.target_agent == "ProductArchitect"

    def test_catches_invalid_upstream_req(self, clean_blueprint_state):
        clean_blueprint_state.features[0].upstream_ids = ["REQ-999"]
        defects = DeterministicLinter.lint_gate_1(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_INVALID_UPSTREAM_REQ"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert err.target_item_id == "FEAT-01"
        assert err.target_agent == "ProductArchitect"

    def test_catches_orphan_requirement_must_have(self, clean_blueprint_state):
        # Remove FEAT-01 so REQ-01 (MUST_HAVE) is orphaned
        clean_blueprint_state.features = [clean_blueprint_state.features[1]]
        defects = DeterministicLinter.lint_gate_1(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_ORPHAN_REQUIREMENT" and d.target_item_id == "REQ-01"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert err.target_agent == "ProductArchitect"

    def test_catches_orphan_requirement_should_have_as_warning(self, clean_blueprint_state):
        # Remove FEAT-02 so REQ-02 (SHOULD_HAVE) is orphaned
        clean_blueprint_state.features = [clean_blueprint_state.features[0]]
        defects = DeterministicLinter.lint_gate_1(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_ORPHAN_REQUIREMENT" and d.target_item_id == "REQ-02"), None)
        assert err is not None
        assert err.severity == DefectSeverity.WARNING

    def test_catches_missing_edge_cases_as_warning(self, clean_blueprint_state):
        clean_blueprint_state.features[0].edge_cases = []
        defects = DeterministicLinter.lint_gate_1(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_MISSING_EDGE_CASES"), None)
        assert err is not None
        assert err.severity == DefectSeverity.WARNING
        assert err.target_item_id == "FEAT-01"

    def test_catches_duplicate_id_in_gate_1(self, clean_blueprint_state):
        clean_blueprint_state.actors.append(clean_blueprint_state.actors[0].model_copy())
        defects = DeterministicLinter.lint_gate_1(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_DUPLICATE_ID"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert err.target_item_id == "ACT-01"

    def test_catches_empty_glossary_as_warning(self, clean_blueprint_state):
        clean_blueprint_state.glossary = []
        defects = DeterministicLinter.lint_gate_1(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_EMPTY_GLOSSARY"), None)
        assert err is not None
        assert err.severity == DefectSeverity.WARNING
        assert err.target_agent == "RequirementAnalyst"

    def test_catches_fsm_self_loop_transition(self, clean_blueprint_state):
        clean_blueprint_state.features[0].state_machine = [
            StateTransition(from_state="PENDING", to_state="PENDING", trigger_action="RETRY")
        ]
        defects = DeterministicLinter.lint_gate_1(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_FSM_INVALID_TRANSITION"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert err.target_item_id == "FEAT-01"

    def test_catches_fsm_empty_transition_list(self, clean_blueprint_state):
        clean_blueprint_state.features[0].state_machine = []
        defects = DeterministicLinter.lint_gate_1(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_FSM_INVALID_TRANSITION"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert err.target_item_id == "FEAT-01"


# =====================================================================
# 3. DETERMINISTIC LINTER: GATE 2 TESTS
# =====================================================================

class TestGate2Linter:
    def test_gate_2_clean_state(self, clean_blueprint_state):
        defects = DeterministicLinter.lint_gate_2(clean_blueprint_state)
        blocking = [d for d in defects if d.severity == DefectSeverity.BLOCKING]
        assert blocking == []
        report = DeterministicLinter.build_report(
            "GATE_2", defects, DeterministicLinter.calculate_traceability_coverage(clean_blueprint_state, "GATE_2")
        )
        assert report.status == ValidationStatus.PASSED
        assert report.traceability_coverage_percent == 100.0

    def test_catches_missing_primary_key(self, clean_blueprint_state):
        # Strip PK from orders table
        for col in clean_blueprint_state.database_entities[0].columns:
            col.is_primary_key = False
        defects = DeterministicLinter.lint_gate_2(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_MISSING_PRIMARY_KEY"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert err.target_item_id == "TBL-01"
        assert err.target_agent == "DatabaseArchitect"

    def test_catches_invalid_upstream_feature_in_db(self, clean_blueprint_state):
        clean_blueprint_state.database_entities[0].upstream_ids = ["FEAT-DOES-NOT-EXIST"]
        defects = DeterministicLinter.lint_gate_2(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_INVALID_UPSTREAM_FEATURE"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert err.target_agent == "DatabaseArchitect"

    def test_catches_empty_upstream_ids_in_database_entity(self, clean_blueprint_state):
        clean_blueprint_state.database_entities[0].upstream_ids = []
        defects = DeterministicLinter.lint_gate_2(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_INVALID_UPSTREAM_FEATURE"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert err.target_agent == "DatabaseArchitect"

    def test_catches_empty_allowed_actor_ids_in_endpoint(self, clean_blueprint_state):
        clean_blueprint_state.endpoints[0].allowed_actor_ids = []
        defects = DeterministicLinter.lint_gate_2(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_UNKNOWN_ACTOR_PERMISSION"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert err.target_agent == "APIArchitect"

    def test_catches_dangling_foreign_key(self, clean_blueprint_state):
        clean_blueprint_state.database_entities[1].relationships[0].references_entity = "non_existent_table"
        defects = DeterministicLinter.lint_gate_2(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_DANGLING_FOREIGN_KEY"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert err.target_agent == "DatabaseArchitect"

    def test_catches_dangling_fk_column(self, clean_blueprint_state):
        clean_blueprint_state.database_entities[1].relationships[0].references_column = "ghost_column"
        defects = DeterministicLinter.lint_gate_2(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_DANGLING_FK_COLUMN"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert err.target_agent == "DatabaseArchitect"

    def test_catches_unindexed_foreign_key_as_warning(self, clean_blueprint_state):
        clean_blueprint_state.database_entities[1].indexes = ["id"]  # order_id missing from indexes
        defects = DeterministicLinter.lint_gate_2(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_UNINDEXED_FOREIGN_KEY"), None)
        assert err is not None
        assert err.severity == DefectSeverity.WARNING
        assert err.target_item_id == "TBL-02"

    def test_catches_unknown_actor_permission(self, clean_blueprint_state):
        clean_blueprint_state.endpoints[0].allowed_actor_ids = ["ACT-GHOST"]
        defects = DeterministicLinter.lint_gate_2(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_UNKNOWN_ACTOR_PERMISSION"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert err.target_agent == "APIArchitect"

    def test_catches_orphan_endpoint(self, clean_blueprint_state):
        clean_blueprint_state.endpoints[0].upstream_ids = ["TBL-INVALID"]
        defects = DeterministicLinter.lint_gate_2(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_ORPHAN_ENDPOINT"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert err.target_agent == "APIArchitect"

    def test_catches_orphan_endpoint_empty(self, clean_blueprint_state):
        clean_blueprint_state.endpoints[0].upstream_ids = []
        defects = DeterministicLinter.lint_gate_2(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_ORPHAN_ENDPOINT"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING

    def test_catches_orphan_feature_data(self, clean_blueprint_state):
        # Add a feature not referenced by any table or endpoint
        clean_blueprint_state.features.append(
            Feature(
                id="FEAT-03",
                upstream_ids=["REQ-01"],
                module_name="Analytics",
                name="Customer Metrics",
                description="Dashboard metrics",
                happy_path=["View dashboard"],
                edge_cases=["No data available"],
            )
        )
        defects = DeterministicLinter.lint_gate_2(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_ORPHAN_FEATURE_DATA" and d.target_item_id == "FEAT-03"), None)
        assert err is not None
        assert err.severity == DefectSeverity.WARNING

    def test_catches_duplicate_table_or_endpoint(self, clean_blueprint_state):
        # Duplicate table ID
        clean_blueprint_state.database_entities.append(clean_blueprint_state.database_entities[0].model_copy())
        defects = DeterministicLinter.lint_gate_2(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_DUPLICATE_TABLE_OR_ENDPOINT"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING

    def test_catches_invalid_fk_source_column(self, clean_blueprint_state):
        clean_blueprint_state.database_entities[1].relationships[0].foreign_key_column = "non_existent_col"
        defects = DeterministicLinter.lint_gate_2(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_INVALID_FK_SOURCE_COLUMN"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert err.target_item_id == "TBL-02"

    def test_catches_endpoint_missing_table_link(self, clean_blueprint_state):
        # Endpoint links only to FEAT-01, missing TBL link
        clean_blueprint_state.endpoints[0].upstream_ids = ["FEAT-01"]
        defects = DeterministicLinter.lint_gate_2(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_ORPHAN_ENDPOINT"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert "must reference at least one valid FEAT-* ID and at least one valid TBL-* ID" in err.message

    def test_catches_endpoint_missing_feature_link(self, clean_blueprint_state):
        # Endpoint links only to TBL-01, missing FEAT link
        clean_blueprint_state.endpoints[0].upstream_ids = ["TBL-01"]
        defects = DeterministicLinter.lint_gate_2(clean_blueprint_state)
        err = next((d for d in defects if d.rule_code == "ERR_ORPHAN_ENDPOINT"), None)
        assert err is not None
        assert err.severity == DefectSeverity.BLOCKING
        assert "must reference at least one valid FEAT-* ID and at least one valid TBL-* ID" in err.message


# =====================================================================
# 4. TRACEABILITY COVERAGE TESTS
# =====================================================================

class TestTraceabilityCoverage:
    def test_empty_requirements_returns_100(self):
        state = ProjectBlueprintState(project_id="p-empty", user_initial_prompt="empty")
        assert DeterministicLinter.calculate_traceability_coverage(state, "GATE_1") == 100.0
        assert DeterministicLinter.calculate_traceability_coverage(state, "GATE_2") == 100.0

    def test_partial_gate_1_coverage(self, clean_blueprint_state):
        # 1 of 2 requirements covered
        clean_blueprint_state.features = [clean_blueprint_state.features[0]]  # covers only REQ-01
        cov = DeterministicLinter.calculate_traceability_coverage(clean_blueprint_state, "GATE_1")
        assert cov == 50.0
        assert DeterministicLinter.calculate_gate_1_coverage(clean_blueprint_state) == 50.0

    def test_calculate_gate_2_coverage(self, clean_blueprint_state):
        cov = DeterministicLinter.calculate_gate_2_coverage(clean_blueprint_state)
        assert cov == 100.0
        # If FEAT-02 is not referenced by an endpoint
        clean_blueprint_state.endpoints = [clean_blueprint_state.endpoints[0]]  # only covers FEAT-01
        cov_partial = DeterministicLinter.calculate_gate_2_coverage(clean_blueprint_state)
        assert cov_partial == 50.0


# =====================================================================
# 5. DAG CHANGE PROPAGATOR TESTS
# =====================================================================

class TestDAGChangePropagator:
    def test_blast_radius_req01_modification(self, clean_blueprint_state):
        """Modifying REQ-01 should stale FEAT-01, TBL-01, TBL-02, and EP-01, but NOT FEAT-02 or EP-02."""
        # FEAT-01 links to REQ-01. FEAT-02 links only to REQ-02.
        # TBL-01 links to FEAT-01, FEAT-02. Since FEAT-01 is stale, TBL-01 is stale.
        # TBL-02 links to FEAT-01, so TBL-02 is stale.
        # EP-01 links to FEAT-01, TBL-01 -> stale.
        # EP-02 links to FEAT-02 and TBL-01. Because TBL-01 is stale (L3 trigger), EP-02 also becomes stale!
        blast = DAGChangePropagator.compute_blast_radius(clean_blueprint_state, {"REQ-01"})
        assert blast["stale_features"] == {"FEAT-01"}
        assert "FEAT-02" not in blast["stale_features"]
        assert "TBL-01" in blast["stale_tables"]
        assert "TBL-02" in blast["stale_tables"]
        assert "EP-01" in blast["stale_endpoints"]

    def test_blast_radius_isolated_branches(self):
        """Create completely isolated branches and verify non-overlapping blast radius."""
        state = ProjectBlueprintState(
            project_id="isolated",
            user_initial_prompt="prompt",
            actors=[Actor(id="ACT-01", name="A", description="d", permissions_summary=[])],
            requirements=[
                Requirement(id="REQ-01", actor_id="ACT-01", title="R1", description="d", priority=Priority.MUST_HAVE, acceptance_criteria=["c"]),
                Requirement(id="REQ-02", actor_id="ACT-01", title="R2", description="d", priority=Priority.MUST_HAVE, acceptance_criteria=["c"]),
            ],
            features=[
                Feature(id="FEAT-01", upstream_ids=["REQ-01"], module_name="M1", name="F1", description="d", happy_path=["h"], edge_cases=["e"]),
                Feature(id="FEAT-02", upstream_ids=["REQ-02"], module_name="M2", name="F2", description="d", happy_path=["h"], edge_cases=["e"]),
            ],
            database_entities=[
                DatabaseEntity(id="TBL-01", upstream_ids=["FEAT-01"], table_name="t1", columns=[ColumnDefinition(name="id", data_type="int", is_primary_key=True)]),
                DatabaseEntity(id="TBL-02", upstream_ids=["FEAT-02"], table_name="t2", columns=[ColumnDefinition(name="id", data_type="int", is_primary_key=True)]),
            ],
            endpoints=[
                EndpointSpec(id="EP-01", upstream_ids=["FEAT-01", "TBL-01"], http_method="GET", path="/api/v1/t1", summary="s", allowed_actor_ids=["ACT-01"], response_dto_schema={}),
                EndpointSpec(id="EP-02", upstream_ids=["FEAT-02", "TBL-02"], http_method="GET", path="/api/v1/t2", summary="s", allowed_actor_ids=["ACT-01"], response_dto_schema={}),
            ],
        )

        blast = DAGChangePropagator.compute_blast_radius(state, {"REQ-01"})
        assert blast["stale_features"] == {"FEAT-01"}
        assert blast["stale_tables"] == {"TBL-01"}
        assert blast["stale_endpoints"] == {"EP-01"}
        assert "FEAT-02" not in blast["stale_features"]
        assert "TBL-02" not in blast["stale_tables"]
        assert "EP-02" not in blast["stale_endpoints"]

    def test_blast_radius_actor_modification(self, clean_blueprint_state):
        # Modifying ACT-02 should cascade through REQ-01 to FEAT-01
        blast = DAGChangePropagator.compute_blast_radius(clean_blueprint_state, {"ACT-02"})
        assert "FEAT-01" in blast["stale_features"]
        assert "FEAT-02" not in blast["stale_features"]

    def test_create_next_version_snapshot(self, clean_blueprint_state):
        clean_blueprint_state.human_approved = True
        next_state, blast = DAGChangePropagator.create_next_version_snapshot(
            clean_blueprint_state,
            modified_ids={"REQ-02"},
            human_notes="Admin must also approve before cancellation.",
        )

        assert next_state.version == 2
        assert next_state.human_approved is False
        assert next_state.human_feedback_notes == "Admin must also approve before cancellation."
        assert blast["stale_features"] == {"FEAT-02"}

        # Verify deep copy isolation
        next_state.features[0].name = "Mutated in V2"
        assert clean_blueprint_state.features[0].name != "Mutated in V2"

    def test_dag_blast_radius_transitive_fk_propagation(self, clean_blueprint_state):
        """If TBL-01 is modified, TBL-02 which has a FK referencing TBL-01 should also become stale."""
        blast = DAGChangePropagator.compute_blast_radius(clean_blueprint_state, {"TBL-01"})
        assert "TBL-01" in blast["stale_tables"]
        assert "TBL-02" in blast["stale_tables"]  # Transitive FK dependency

    def test_merge_regenerated_slice_preserves_untouched_items(self, clean_blueprint_state):
        """merge_regenerated_slice should preserve untouched items, replace stale ones, and sort by ID."""
        existing = [
            Requirement(id="REQ-01", actor_id="ACT-01", title="R1", description="D1", priority=Priority.MUST_HAVE, acceptance_criteria=["AC1"]),
            Requirement(id="REQ-02", actor_id="ACT-01", title="R2", description="D2", priority=Priority.MUST_HAVE, acceptance_criteria=["AC2"]),
            Requirement(id="REQ-03", actor_id="ACT-01", title="R3", description="D3", priority=Priority.MUST_HAVE, acceptance_criteria=["AC3"]),
        ]
        stale_ids = {"REQ-02"}
        new_items = [
            Requirement(id="REQ-02", actor_id="ACT-01", title="R2-Updated", description="D2-Updated", priority=Priority.MUST_HAVE, acceptance_criteria=["AC2-New"]),
            Requirement(id="REQ-04", actor_id="ACT-01", title="R4-BrandNew", description="D4", priority=Priority.SHOULD_HAVE, acceptance_criteria=["AC4"]),
        ]

        merged = DAGChangePropagator.merge_regenerated_slice(existing, new_items, stale_ids)

        assert [r.id for r in merged] == ["REQ-01", "REQ-02", "REQ-03", "REQ-04"]
        assert merged[0].title == "R1"  # Untouched preserved
        assert merged[1].title == "R2-Updated"  # Stale updated
        assert merged[2].title == "R3"  # Untouched preserved
        assert merged[3].title == "R4-BrandNew"  # Brand-new appended

