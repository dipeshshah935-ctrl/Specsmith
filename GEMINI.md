# Antigravity Workspace Rules — Multi-Agent Blueprint Engine (`GEMINI.md`)

You are working inside a polyglot monorepo (`blueprint-engine/`) consisting of:
- `apps/agent-engine/`: Python 3.12 + FastAPI + LangGraph + Pydantic v2
- `apps/api-gateway/`: Node.js + Express + TypeScript + Mongoose
- `apps/web/`: React + Vite + TypeScript + Tailwind CSS + `@xyflow/react`
- `docs/ARCHITECTURE_SPEC.md`: The canonical specification for all schemas, agent contracts, validation rules, and state machine transitions.

Always read `docs/ARCHITECTURE_SPEC.md` before creating or modifying any file.

## 1. Strict Architectural Invariants

1. **5 Domain Agents + 1 Orchestrator Only:**
   - Do not create separate micro-agents for security, business rules, or impact analysis.
   - Keep those concerns embedded in the 5 domain agents: `RequirementAnalyst`, `ProductArchitect`, `DatabaseArchitect`, `APIArchitect`, and `ValidationAgent`.
2. **Canonical Data Contract (`app/schemas.py`):**
   - `ProjectBlueprintState` is the single source of truth across Python, MongoDB, Express, and React.
   - Never pass unstructured markdown between agents. Every agent must return its designated Pydantic v2 output model (`RequirementAnalystOutput`, `ProductArchitectOutput`, `DatabaseArchitectOutput`, `APIArchitectOutput`, `ValidationReport`).
3. **Read/Write Slice Isolation:**
   - Each agent node may only read its designated input fields from `ProjectBlueprintState` to prevent context bloat and prompt drift.
4. **Mandatory Bidirectional Traceability (`upstream_ids`):**
   - Every `Feature` must reference valid `REQ-*` IDs in `upstream_ids`.
   - Every `DatabaseEntity` must reference valid `FEAT-*` IDs in `upstream_ids`.
   - Every `EndpointSpec` must reference valid `FEAT-*` and `TBL-*` IDs in `upstream_ids`.
5. **Immutable Version Snapshots & Selective Rollback:**
   - Never overwrite an approved or checkpointed state version in place.
   - When handling human edits at `human_checkpoint_1` or `human_checkpoint_2`, always call `DAGChangePropagator.create_next_version_snapshot()` to increment `version` (`v1` -> `v2`) and compute the `blast_radius` (`stale_features`, `stale_tables`, `stale_endpoints`).
   - Downstream agents must preserve untouched items and regenerate only the IDs flagged in `blast_radius` (plus any newly added requirements/features).
6. **Hybrid Validation Gates (Tier 1 Static Linter -> Tier 2 LLM Critic):**
   - In both `validation_gate_1` and `validation_gate_2`, execute `DeterministicLinter` first.
   - If `DeterministicLinter` returns any `DefectSeverity.BLOCKING` defects, short-circuit and return the failed `ValidationReport` immediately without spending LLM tokens on the semantic critic.
   - Enforce `MAX_AUTO_RETRIES = 2` on conditional edges after Gate 1 and Gate 2. When retries reach 2, escalate directly to the human checkpoint node.

## 2. Coding & Testing Standards

1. **Vertical-Slice Execution:**
   - Implement only the slice requested in the current prompt. Do not scaffold unrequested frontend or gateway files while working on Python core slices.
2. **Deterministic Mock Mode (`USE_MOCK_LLM`):**
   - Every LLM-backed agent in `apps/agent-engine/app/agents/` must support `USE_MOCK_LLM=true` via environment variables, returning valid, deterministic Pydantic fixtures so unit and integration tests run offline in milliseconds.
3. **Test-First Verification:**
   - Every Python module in `apps/agent-engine/app/` must be verified with `pytest` before marking a task complete.
   - Every TypeScript change in `apps/api-gateway/` or `apps/web/` must pass `tsc --noEmit` and its test/build script before completion.
4. **Error Contract Standardization:**
   - FastAPI and Express endpoints must return structured JSON error responses following RFC 7807 (`type`, `title`, `status`, `detail`).
