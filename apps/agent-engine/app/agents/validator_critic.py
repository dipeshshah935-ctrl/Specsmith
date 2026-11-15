from typing import Any, Dict, List, Literal, Optional
from app.agents.base import invoke_structured_agent
from app.config import EngineSettings
from app.linter import DeterministicLinter
from app.schemas import (
    DefectSeverity,
    ProjectBlueprintState,
    ValidationCriticOutput,
    ValidationDefect,
    ValidationReport,
)

GATE_1_CRITIC_PROMPT = """You are a Principal Software QA & Requirements Architect acting as the Tier 2 Semantic Critic for Validation Gate 1.

Review the provided Requirements, Actors, and Features for semantic consistency, feasibility, edge cases, and IEEE 830 compliance:
1. Ensure all business rules and user flows are unambiguous, non-contradictory, and measurable.
2. Identify any missing edge cases, security implications, or failure scenarios not accounted for in feature happy_paths and edge_cases.
3. Verify that all features adequately solve the intended requirements without unnecessary complexity.
4. If semantic defects or quality issues are found, return a list of ValidationDefect items with rule_code, severity (BLOCKING or WARNING), target_agent, target_item_id, message, and suggested_fix.
If the specifications are solid, return an empty defects list.
"""

GATE_2_CRITIC_PROMPT = """You are a Principal Systems & Cloud Security Architect acting as the Tier 2 Semantic Critic for Validation Gate 2.

Review the provided Database Entities and OpenAPI Endpoints against the Features:
1. Evaluate 3NF relational integrity, foreign key consistency, and appropriate column indexing.
2. Ensure RESTful resource modeling, proper HTTP method semantics, idempotency on state-mutating operations, and standard RFC 7807 error responses.
3. Validate Least Privilege Role-Based Access Control (RBAC) ensuring appropriate actor authorization on every endpoint.
4. Verify Privacy by Design, ensuring all PII is explicitly flagged on sensitive data columns.
5. If architectural defects or security vulnerabilities are found, return a list of ValidationDefect items with rule_code, severity (BLOCKING or WARNING), target_agent, target_item_id, message, and suggested_fix.
If the specifications are solid, return an empty defects list.
"""


def _mock_validation_critic(payload: Dict[str, Any]) -> ValidationCriticOutput:
    """Deterministic mock critic returning empty defects by default or injected defects."""
    injected = payload.get("inject_critic_defects") or []
    if injected:
        defects = [ValidationDefect.model_validate(d) for d in injected]
        return ValidationCriticOutput(defects=defects)
    return ValidationCriticOutput(defects=[])


def run_validation_gate(
    state: ProjectBlueprintState,
    gate_name: Literal["GATE_1", "GATE_2"],
    settings: Optional[EngineSettings] = None,
) -> ProjectBlueprintState:
    """Execute Hybrid Validation Gate: Tier 1 Static Linter -> Tier 2 Semantic LLM Critic.

    Applies the strict short-circuit rule: if Tier 1 yields any BLOCKING defects,
    the gate terminates immediately and returns a FAILED ValidationReport without
    invoking the LLM critic.
    """
    # 1. Tier 1 Static Linter First
    if gate_name == "GATE_1":
        static_defects: List[ValidationDefect] = DeterministicLinter.lint_gate_1(state)
        coverage: float = DeterministicLinter.calculate_gate_1_coverage(state)
    else:
        static_defects: List[ValidationDefect] = DeterministicLinter.lint_gate_2(state)
        coverage: float = DeterministicLinter.calculate_gate_2_coverage(state)

    # 2. SHORT-CIRCUIT RULE:
    # If any static defect is BLOCKING, terminate immediately without spending LLM tokens.
    has_blocking = any(d.severity == DefectSeverity.BLOCKING for d in static_defects)
    if has_blocking:
        report: ValidationReport = DeterministicLinter.build_report(
            gate_name=gate_name,
            defects=static_defects,
            coverage_percent=coverage,
        )
        new_state = state.model_copy(deep=True)
        new_state.validation_reports.append(report)
        return new_state

    # 3. Tier 2 Semantic Critic: Only executed when zero BLOCKING static defects exist.
    if gate_name == "GATE_1":
        system_prompt = GATE_1_CRITIC_PROMPT
        user_payload: Dict[str, Any] = {
            "gate_name": gate_name,
            "glossary": [g.model_dump() for g in state.glossary],
            "actors": [a.model_dump() for a in state.actors],
            "requirements": [r.model_dump() for r in state.requirements],
            "features": [f.model_dump() for f in state.features],
            "static_warnings": [
                d.model_dump()
                for d in static_defects
                if d.severity == DefectSeverity.WARNING
            ],
            "human_feedback_notes": state.human_feedback_notes,
        }
    else:
        system_prompt = GATE_2_CRITIC_PROMPT
        user_payload = {
            "gate_name": gate_name,
            "glossary": [g.model_dump() for g in state.glossary],
            "actors": [a.model_dump() for a in state.actors],
            "features": [f.model_dump() for f in state.features],
            "database_entities": [t.model_dump() for t in state.database_entities],
            "endpoints": [ep.model_dump() for ep in state.endpoints],
            "static_warnings": [
                d.model_dump()
                for d in static_defects
                if d.severity == DefectSeverity.WARNING
            ],
            "human_feedback_notes": state.human_feedback_notes,
        }

    critic_output: ValidationCriticOutput = invoke_structured_agent(
        schema_cls=ValidationCriticOutput,
        system_prompt=system_prompt,
        user_payload=user_payload,
        mock_builder=_mock_validation_critic,
        settings=settings,
    )

    all_defects: List[ValidationDefect] = static_defects + critic_output.defects
    report = DeterministicLinter.build_report(
        gate_name=gate_name,
        defects=all_defects,
        coverage_percent=coverage,
    )

    new_state = state.model_copy(deep=True)
    new_state.validation_reports.append(report)
    return new_state
