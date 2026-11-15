import pytest
from pydantic import ValidationError
from typing import Set

from app.config import EngineSettings
from app.schemas import (
    DefectSeverity,
    ProjectBlueprintState,
    ValidationStatus,
)
from app.propagator import DAGChangePropagator
from app.agents.req_analyst import run_requirement_analyst
from app.agents.product_arch import run_product_architect
from app.agents.db_arch import run_database_architect
from app.agents.api_arch import run_api_architect
from app.agents.validator_critic import run_validation_gate


class TestEngineSettings:
    def test_settings_rejects_missing_api_key_when_mock_disabled(self):
        """EngineSettings(USE_MOCK_LLM=False, GEMINI_API_KEY=None) must raise ValueError/ValidationError."""
        with pytest.raises((ValueError, ValidationError)):
            EngineSettings(USE_MOCK_LLM=False, GEMINI_API_KEY=None)


class TestAgentPipelines:
    def test_discovery_pipeline_passes_gate_1(self):
        """Verify Discovery pipeline: run_requirement_analyst -> run_product_architect -> run_validation_gate GATE_1."""
        state = ProjectBlueprintState(
            project_id="proj-discovery-01",
            user_initial_prompt="Build a cloud-based project management SaaS platform.",
        )
        state = run_requirement_analyst(state)
        assert len(state.glossary) >= 2
        assert len(state.actors) >= 2
        assert len(state.requirements) >= 2

        state = run_product_architect(state)
        assert len(state.features) >= 2

        state = run_validation_gate(state, gate_name="GATE_1")
        assert len(state.validation_reports) == 1
        report = state.validation_reports[0]
        assert report.gate_name == "GATE_1"
        assert report.status == ValidationStatus.PASSED
        assert report.traceability_coverage_percent == 100.0
        assert len([d for d in report.defects if d.severity == DefectSeverity.BLOCKING]) == 0

    def test_architecture_pipeline_passes_gate_2(self):
        """Verify Architecture pipeline: run_database_architect -> run_api_architect -> run_validation_gate GATE_2."""
        state = ProjectBlueprintState(
            project_id="proj-arch-01",
            user_initial_prompt="Build an enterprise e-commerce checkout platform.",
        )
        state = run_requirement_analyst(state)
        state = run_product_architect(state)
        state = run_database_architect(state)
        assert len(state.database_entities) >= 2

        state = run_api_architect(state)
        assert len(state.endpoints) >= 4

        state = run_validation_gate(state, gate_name="GATE_2")
        assert len(state.validation_reports) == 1
        report = state.validation_reports[0]
        assert report.gate_name == "GATE_2"
        assert report.status == ValidationStatus.PASSED
        assert report.traceability_coverage_percent == 100.0
        assert len([d for d in report.defects if d.severity == DefectSeverity.BLOCKING]) == 0


class TestValidationCriticShortCircuit:
    def test_gate_1_short_circuits_on_blocking_static_defect(self, monkeypatch):
        """Verify Gate 1 short-circuits and never calls Tier 2 LLM when a static BLOCKING defect exists."""
        state = ProjectBlueprintState(
            project_id="proj-sc-01",
            user_initial_prompt="Build a billing system.",
        )
        state = run_requirement_analyst(state)
        state = run_product_architect(state)

        # Inject a blocking defect: invalid actor reference on REQ-01
        state.requirements[0].actor_id = "ACT-99"

        def _raise_on_tier_2(*args, **kwargs):
            raise AssertionError("Tier 2 LLM critic should NOT be called when blocking defects exist!")

        import app.agents.validator_critic as vc_module
        monkeypatch.setattr(vc_module, "invoke_structured_agent", _raise_on_tier_2)

        state = run_validation_gate(state, gate_name="GATE_1")
        assert len(state.validation_reports) == 1
        report = state.validation_reports[0]
        assert report.status == ValidationStatus.FAILED
        blocking_defects = [d for d in report.defects if d.severity == DefectSeverity.BLOCKING]
        assert len(blocking_defects) > 0
        assert any(d.rule_code == "ERR_DANGLING_ACTOR" for d in blocking_defects)

    def test_gate_2_short_circuits_on_blocking_static_defect(self, monkeypatch):
        """Verify Gate 2 short-circuits and never calls Tier 2 LLM when a static BLOCKING defect exists."""
        state = ProjectBlueprintState(
            project_id="proj-sc-02",
            user_initial_prompt="Build an inventory system.",
        )
        state = run_requirement_analyst(state)
        state = run_product_architect(state)
        state = run_database_architect(state)
        state = run_api_architect(state)

        # Inject a blocking defect: remove primary key from TBL-01
        for col in state.database_entities[0].columns:
            col.is_primary_key = False

        def _raise_on_tier_2(*args, **kwargs):
            raise AssertionError("Tier 2 LLM critic should NOT be called when blocking defects exist!")

        import app.agents.validator_critic as vc_module
        monkeypatch.setattr(vc_module, "invoke_structured_agent", _raise_on_tier_2)

        state = run_validation_gate(state, gate_name="GATE_2")
        assert len(state.validation_reports) == 1
        report = state.validation_reports[0]
        assert report.status == ValidationStatus.FAILED
        blocking_defects = [d for d in report.defects if d.severity == DefectSeverity.BLOCKING]
        assert any(d.rule_code == "ERR_MISSING_PRIMARY_KEY" for d in blocking_defects)


class TestSelectiveRegeneration:
    def test_selective_regeneration_across_all_4_agents(self):
        """Modify REQ-01 via create_next_version_snapshot, re-run all 4 agents with blast_radius,

        and verify REQ-01/FEAT-01/TBL-01/EP-01 reflect the revision while REQ-02 and FEAT-02 are preserved.
        """
        # 1. Initial generation of complete blueprint (v1)
        v1_state = ProjectBlueprintState(
            project_id="proj-selective-01",
            user_initial_prompt="Build a SaaS platform.",
        )
        v1_state = run_requirement_analyst(v1_state)
        v1_state = run_product_architect(v1_state)
        v1_state = run_database_architect(v1_state)
        v1_state = run_api_architect(v1_state)

        req02_original_desc = next(r.description for r in v1_state.requirements if r.id == "REQ-02")
        feat02_original_desc = next(f.description for f in v1_state.features if f.id == "FEAT-02")

        # 2. Create version snapshot (v2) modifying REQ-01
        modified_ids: Set[str] = {"REQ-01"}
        human_notes = "Add express checkout and fraud verification"
        v2_state, blast = DAGChangePropagator.create_next_version_snapshot(
            v1_state, modified_ids=modified_ids, human_notes=human_notes
        )

        assert v2_state.version == 2
        assert "REQ-01" in blast["stale_requirements"]
        assert "FEAT-01" in blast["stale_features"]
        assert "TBL-01" in blast["stale_tables"]
        assert len(blast["stale_endpoints"]) > 0

        # 3. Re-run all 4 domain agents with selective blast radius
        v2_state = run_requirement_analyst(v2_state, blast_radius=blast)
        v2_state = run_product_architect(v2_state, blast_radius=blast)
        v2_state = run_database_architect(v2_state, blast_radius=blast)
        v2_state = run_api_architect(v2_state, blast_radius=blast)

        # 4. Verify REQ-01 was revised, REQ-02 was preserved untouched
        req01 = next(r for r in v2_state.requirements if r.id == "REQ-01")
        req02 = next(r for r in v2_state.requirements if r.id == "REQ-02")
        assert f"[Revised: {human_notes}]" in req01.description
        assert req02.description == req02_original_desc

        # 5. Verify FEAT-01 was revised, FEAT-02 was preserved untouched
        feat01 = next(f for f in v2_state.features if f.id == "FEAT-01")
        feat02 = next(f for f in v2_state.features if f.id == "FEAT-02")
        assert f"[Revised: {human_notes}]" in feat01.description
        assert feat02.description == feat02_original_desc

        # 6. Verify TBL-01 reflects revision (has revised_notes column)
        tbl01 = next(t for t in v2_state.database_entities if t.id == "TBL-01")
        assert any(c.name == "revised_notes" for c in tbl01.columns)

        # 7. Verify stale endpoints reflect revision
        revised_eps = [e for e in v2_state.endpoints if f"[Revised: {human_notes}]" in e.summary]
        assert len(revised_eps) > 0
        assert any(e.id == "EP-01" for e in revised_eps)
