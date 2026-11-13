# Antigravity Atomic Micro-Task Execution Playbook (`ANTIGRAVITY_PLAYBOOK.md`)

This playbook breaks the **6 Vertical Slices** into **24 Atomic, Single-Responsibility Micro-Tasks**. 
Never ask Antigravity to implement an entire slice at once. Feed it **one Micro-Task prompt at a time**, inspect the generated file against the **Corner-Case Checklist**, run the **Verification Command**, and only proceed when it passes 100%.

---

## SLICE 1: Core Data Contracts, Deterministic Linter & DAG Propagator

### Micro-Task 1.1: Python Workspace & Dependency Lock (`pyproject.toml` + `app/config.py`)
* **Target Files:**
  * `apps/agent-engine/pyproject.toml`
  * `apps/agent-engine/app/__init__.py`
  * `apps/agent-engine/app/config.py`
* **Exact Implementation Rules:**
  1. In `pyproject.toml`, declare Python `>=3.11` and pin exact minimum versions: `pydantic>=2.7.0`, `pydantic-settings>=2.2.0`, `fastapi>=0.111.0`, `uvicorn[standard]>=0.30.0`, `langgraph>=0.2.0`, `langchain-core>=0.2.0`, `langchain-google-genai>=1.0.0`, `pymongo>=4.7.0`, `httpx>=0.27.0`, `pytest>=8.2.0`, `pytest-asyncio>=0.23.0`.
  2. Configure `[tool.pytest.ini_options]` with `pythonpath = ["."]` and `asyncio_mode = "auto"` so imports like `from app.schemas import ...` never fail with `ModuleNotFoundError`.
  3. In `app/config.py`, implement `EngineSettings(BaseSettings)` using `pydantic_settings`:
     * `USE_MOCK_LLM: bool = True`
     * `GEMINI_API_KEY: Optional[str] = None`
     * `GEMINI_MODEL: str = "gemini-2.5-flash"`
     * `MONGODB_URI: Optional[str] = None`
     * `MONGODB_DB_NAME: str = "blueprint_engine"`
     * `MAX_AUTO_RETRIES: int = 2`
     * Add a `@model_validator(mode="after")` that raises a `ValueError("GEMINI_API_KEY is required when USE_MOCK_LLM=False")` if `not self.USE_MOCK_LLM and not self.GEMINI_API_KEY`.
  4. **Anti-Shortcut Guardrail:** Do NOT initialize any network connections, database clients, or LLM clients at import time in `config.py` or `__init__.py` (zero import side-effects).
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 1.1: Create apps/agent-engine/pyproject.toml, apps/agent-engine/app/__init__.py, and apps/agent-engine/app/config.py. In pyproject.toml, set pythonpath = ["."] and asyncio_mode = "auto" under [tool.pytest.ini_options]. In app/config.py, implement EngineSettings(BaseSettings) with USE_MOCK_LLM (default True), GEMINI_API_KEY, GEMINI_MODEL, MONGODB_URI, MONGODB_DB_NAME, and MAX_AUTO_RETRIES=2, plus a model_validator that raises ValueError if USE_MOCK_LLM is False and GEMINI_API_KEY is missing. Ensure zero import-time side effects.
  ```
* **Verification Command:**
  ```powershell
  cd apps/agent-engine
  python -c "from app.config import EngineSettings; s = EngineSettings(); assert s.USE_MOCK_LLM is True; print('Micro-Task 1.1 OK')"
  ```

---

### Micro-Task 1.2: Canonical Pydantic v2 Schemas & Field-Level Regex Validators (`app/schemas.py`)
* **Target File:** `apps/agent-engine/app/schemas.py`
* **Exact Implementation Rules:**
  1. Define all Enums (`ProjectPhase`, `Priority`, `ValidationStatus`, `DefectSeverity`, `HTTPMethod`, `OnDeleteAction`).
  2. Enforce **Strict Regex Patterns** on IDs using `Field(pattern=...)`:
     * `Actor.id`: `pattern=r"^ACT-\d{2,4}$"` (e.g., `ACT-01`, rejects `actor1` or `REQ-01`).
     * `Requirement.id`: `pattern=r"^REQ-\d{2,4}$"` and `Requirement.actor_id`: `pattern=r"^ACT-\d{2,4}$"`.
     * `Feature.id`: `pattern=r"^FEAT-\d{2,4}$"`.
     * `DatabaseEntity.id`: `pattern=r"^TBL-\d{2,4}$"` and `DatabaseEntity.table_name`: `pattern=r"^[a-z][a-z0-9_]*$"` (strict snake_case).
     * `EndpointSpec.id`: `pattern=r"^EP-\d{2,4}$"` and `EndpointSpec.path`: `pattern=r"^/api/v\d+/[a-z0-9_/\-{}+]*$"`.
  3. Enforce **Non-Empty String & List Constraints**:
     * Use ` ConfigDict(str_strip_whitespace=True, extra="forbid")` on a base class `StrictContractModel(BaseModel)` inherited by every schema so extra/hallucinated LLM fields are immediately rejected!
     * `GlossaryTerm.term` and `definition`: `min_length=2`.
     * `Requirement.acceptance_criteria`: `min_length=1` (at least one criterion required at schema level).
     * `Feature.happy_path`: `min_length=1`.
     * `DatabaseEntity.columns`: `min_length=1`.
  4. Define the 5 Agent Output wrapper models (`RequirementAnalystOutput`, `ProductArchitectOutput`, `DatabaseArchitectOutput`, `APIArchitectOutput`, `ValidationCriticOutput`) and the root `ProjectBlueprintState`.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 1.2: Implement apps/agent-engine/app/schemas.py. Create a base class StrictContractModel(BaseModel) with model_config = ConfigDict(str_strip_whitespace=True, extra="forbid"). Implement all models from docs/ARCHITECTURE_SPEC.md inheriting from StrictContractModel. Add strict regex patterns on IDs: Actor.id (^ACT-\d{2,4}$), Requirement.id (^REQ-\d{2,4}$), Feature.id (^FEAT-\d{2,4}$), DatabaseEntity.id (^TBL-\d{2,4}$), DatabaseEntity.table_name (^[a-z][a-z0-9_]*$), EndpointSpec.id (^EP-\d{2,4}$), and EndpointSpec.path (^/api/v\d+/[a-z0-9_/\-{}]*$). Enforce min_length=1 on Requirement.acceptance_criteria, Feature.happy_path, and DatabaseEntity.columns.
  ```
* **Verification Command:**
  ```powershell
  python -c "from app.schemas import Actor, StrictContractModel; import pydantic; a = Actor(id='ACT-01', name='Admin', description='Sys admin', permissions_summary=['all']); print('Micro-Task 1.2 OK')"
  ```

---

### Micro-Task 1.3: Tier 1 Deterministic Static Linter — Gate 1 (`app/linter.py` Part 1)
* **Target File:** `apps/agent-engine/app/linter.py`
* **Exact Implementation Rules for `DeterministicLinter.lint_gate_1(state: ProjectBlueprintState)`:**
  Implement these **7 exact deterministic checks** in order:
  1. `ERR_DUPLICATE_ID` (`BLOCKING`): Check if any duplicate IDs exist within `state.actors`, `state.requirements`, or `state.features`.
  2. `ERR_EMPTY_GLOSSARY` (`WARNING`): Check if `len(state.glossary) == 0`.
  3. `ERR_DANGLING_ACTOR` (`BLOCKING`, `target_agent="RequirementAnalyst"`): For each `req` in `state.requirements`, verify `req.actor_id` exists in `{a.id for a in state.actors}`.
  4. `ERR_UNLINKED_FEATURE` (`BLOCKING`, `target_agent="ProductArchitect"`): For each `feat` in `state.features`, verify `len(feat.upstream_ids) > 0`.
  5. `ERR_INVALID_UPSTREAM_REQ` (`BLOCKING`, `target_agent="ProductArchitect"`): Verify every ID in `feat.upstream_ids` exists in `{r.id for r in state.requirements}`.
  6. `ERR_ORPHAN_REQUIREMENT` (`BLOCKING` if `req.priority == Priority.MUST_HAVE` else `WARNING`, `target_agent="ProductArchitect"`): Verify every `req.id` is referenced in at least one `feat.upstream_ids`.
  7. `ERR_FSM_INVALID_TRANSITION` (`BLOCKING`, `target_agent="ProductArchitect"`): If `feat.state_machine` is not `None` and non-empty, verify that no transition has `from_state == to_state` (self-loop without state change) and that at least 1 transition exists.
  8. Also implement `calculate_gate_1_coverage(state: ProjectBlueprintState) -> float`: returns `(covered_req_count / total_req_count) * 100.0` rounded to 2 decimals (returns `0.0` if `total_req_count == 0`).
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 1.3: Create apps/agent-engine/app/linter.py and implement DeterministicLinter.lint_gate_1(state) and calculate_gate_1_coverage(state). Include all 7 checks: ERR_DUPLICATE_ID, ERR_EMPTY_GLOSSARY, ERR_DANGLING_ACTOR, ERR_UNLINKED_FEATURE, ERR_INVALID_UPSTREAM_REQ, ERR_ORPHAN_REQUIREMENT (BLOCKING for MUST_HAVE, WARNING otherwise), and ERR_FSM_INVALID_TRANSITION (flagging identical from_state == to_state).
  ```
* **Verification Command:**
  ```powershell
  python -c "from app.linter import DeterministicLinter; print('Micro-Task 1.3 OK')"
  ```

---

### Micro-Task 1.4: Tier 1 Deterministic Static Linter — Gate 2 (`app/linter.py` Part 2)
* **Target File:** `apps/agent-engine/app/linter.py`
* **Exact Implementation Rules for `DeterministicLinter.lint_gate_2(state: ProjectBlueprintState)`:**
  Implement these **9 exact deterministic checks** in order:
  1. `ERR_DUPLICATE_TABLE_OR_ENDPOINT` (`BLOCKING`): Verify no duplicate `DatabaseEntity.id`, `DatabaseEntity.table_name`, `EndpointSpec.id`, or duplicate `(ep.http_method, ep.path)` pairs exist.
  2. `ERR_MISSING_PRIMARY_KEY` (`BLOCKING`, `target_agent="DatabaseArchitect"`): Every `DatabaseEntity` must have at least one column with `is_primary_key == True`.
  3. `ERR_INVALID_UPSTREAM_FEATURE` (`BLOCKING`, `target_agent="DatabaseArchitect"`): Every `DatabaseEntity.upstream_ids` must be non-empty and reference valid `FEAT-*` IDs.
  4. `ERR_INVALID_FK_SOURCE_COLUMN` (`BLOCKING`, `target_agent="DatabaseArchitect"`): For every relationship `rel` in `tbl.relationships`, `rel.foreign_key_column` must exist in `{c.name for c in tbl.columns}`.
  5. `ERR_DANGLING_FOREIGN_KEY` (`BLOCKING`, `target_agent="DatabaseArchitect"`): `rel.references_entity` must exist in `{t.table_name for t in state.database_entities}`.
  6. `ERR_DANGLING_FK_COLUMN` (`BLOCKING`, `target_agent="DatabaseArchitect"`): `rel.references_column` must exist in the target table's columns.
  7. `ERR_UNINDEXED_FOREIGN_KEY` (`WARNING`, `target_agent="DatabaseArchitect"`): `rel.foreign_key_column` must appear as a substring in at least one entry of `tbl.indexes`.
  8. `ERR_UNKNOWN_ACTOR_PERMISSION` (`BLOCKING`, `target_agent="APIArchitect"`): Every `ep.allowed_actor_ids` must be non-empty and reference valid `ACT-*` IDs.
  9. `ERR_ORPHAN_ENDPOINT` (`BLOCKING`, `target_agent="APIArchitect"`): Every `ep.upstream_ids` must reference at least one valid `FEAT-*` ID and at least one valid `TBL-*` ID.
  10. Implement `calculate_gate_2_coverage(state: ProjectBlueprintState) -> float`: percentage of `Feature.id`s covered by at least one `DatabaseEntity` AND at least one `EndpointSpec`.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 1.4: Add DeterministicLinter.lint_gate_2(state) and calculate_gate_2_coverage(state) to apps/agent-engine/app/linter.py. Implement all 9 checks: ERR_DUPLICATE_TABLE_OR_ENDPOINT, ERR_MISSING_PRIMARY_KEY, ERR_INVALID_UPSTREAM_FEATURE, ERR_INVALID_FK_SOURCE_COLUMN, ERR_DANGLING_FOREIGN_KEY, ERR_DANGLING_FK_COLUMN, ERR_UNINDEXED_FOREIGN_KEY, ERR_UNKNOWN_ACTOR_PERMISSION, and ERR_ORPHAN_ENDPOINT (requiring each endpoint to link to >=1 valid FEAT-* and >=1 valid TBL-*).
  ```
* **Verification Command:**
  ```powershell
  python -c "from app.linter import DeterministicLinter; assert hasattr(DeterministicLinter, 'lint_gate_2'); print('Micro-Task 1.4 OK')"
  ```

---

### Micro-Task 1.5: DAG Blast-Radius Propagator & Selective Merge Utility (`app/propagator.py`)
* **Target File:** `apps/agent-engine/app/propagator.py`
* **Exact Implementation Rules:**
  1. `compute_blast_radius(state: ProjectBlueprintState, modified_ids: Set[str]) -> Dict[str, Set[str]]`:
     * If an `ACT-xx` is in `modified_ids`, automatically find all `REQ-xx` where `req.actor_id == act_id` and add them to `stale_requirements`.
     * Any `REQ-xx` directly in `modified_ids` is added to `stale_requirements`.
     * Any `FEAT-xx` in `modified_ids` OR whose `upstream_ids` intersects `stale_requirements` is added to `stale_features`.
     * Any `TBL-xx` in `modified_ids` OR whose `upstream_ids` intersects `stale_features` (OR which has a foreign key pointing to a table in `stale_tables` — transitive table dependency!) is added to `stale_tables`.
     * Any `EP-xx` in `modified_ids` OR whose `upstream_ids` intersects `stale_features` $\cup$ `stale_tables` OR whose `allowed_actor_ids` intersects `modified_ids` is added to `stale_endpoints`.
     * Return `{"stale_requirements": ..., "stale_features": ..., "stale_tables": ..., "stale_endpoints": ...}`.
  2. `merge_regenerated_slice(existing_items: List[T], new_items: List[T], stale_ids: Set[str]) -> List[T]`:
     * Preserves any item in `existing_items` whose `.id` is NOT in `stale_ids` (unless overwritten by a matching `.id` in `new_items`), replaces items in `stale_ids` with their updated versions from `new_items`, and appends any brand-new IDs from `new_items`, sorted deterministically by `.id`.
  3. `create_next_version_snapshot(current_state: ProjectBlueprintState, modified_ids: Set[str], human_notes: str)`:
     * Deep-copies `current_state`, increments `version` by 1, sets `human_approved = False`, stores `human_feedback_notes = human_notes`, and returns `(next_state, blast_radius)`.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 1.5: Implement apps/agent-engine/app/propagator.py with DAGChangePropagator. Include compute_blast_radius (handling ACT->REQ->FEAT->TBL->EP plus transitive foreign-key table dependencies), merge_regenerated_slice(existing_items, new_items, stale_ids) to preserve untouched items while merging regenerated stale items sorted by ID, and create_next_version_snapshot.
  ```
* **Verification Command:**
  ```powershell
  python -c "from app.propagator import DAGChangePropagator; print('Micro-Task 1.5 OK')"
  ```

---

### Micro-Task 1.6: Slice 1 Exhaustive Unit Test Suite (`tests/test_core_logic.py`)
* **Target File:** `apps/agent-engine/tests/test_core_logic.py`
* **Exact Implementation Rules:**
  Write **12 unit tests** covering every positive and negative corner case:
  1. `test_schema_rejects_invalid_id_prefixes` (e.g., `REQ-1` or `BAD-01` raises `ValidationError`).
  2. `test_schema_rejects_extra_fields` (`extra="forbid"` rejects hallucinated keys).
  3. `test_gate_1_passes_clean_blueprint` (returns 0 blocking defects and `100.0%` coverage).
  4. `test_gate_1_catches_dangling_actor_and_orphan_must_have_req`.
  5. `test_gate_1_catches_invalid_upstream_req_and_self_loop_fsm`.
  6. `test_gate_2_passes_clean_architecture`.
  7. `test_gate_2_catches_missing_pk_and_dangling_fk_table_and_column`.
  8. `test_gate_2_warns_on_unindexed_foreign_key`.
  9. `test_gate_2_catches_orphan_endpoint_and_unknown_actor_permission`.
  10. `test_dag_blast_radius_isolates_modified_branch` (modifying `REQ-01` marks `FEAT-01`, `TBL-01`, `EP-01` stale, while leaving `REQ-02`, `FEAT-02`, `TBL-02`, `EP-02` completely untouched).
  11. `test_dag_blast_radius_transitive_fk_propagation` (if `TBL-02` has a FK to `TBL-01` and `TBL-01` is modified, `TBL-02` is also marked stale).
  12. `test_merge_regenerated_slice_preserves_untouched_items`.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 1.6: Create apps/agent-engine/tests/test_core_logic.py implementing all 12 unit tests specified in ANTIGRAVITY_PLAYBOOK.md for schemas, Gate 1 linter, Gate 2 linter, transitive DAG blast-radius calculation, and selective slice merging. Run pytest tests/test_core_logic.py -v and fix any defects until all 12 pass.
  ```
* **Verification Command:**
  ```powershell
  pytest tests/test_core_logic.py -v
  ```

---

## SLICE 2: The 5 Domain Agents with Dual-Mode Execution & Selective Regeneration

### Micro-Task 2.1: Structured-Output LLM Factory & Deterministic Fixture Registry (`app/agents/base.py`)
* **Target File:** `apps/agent-engine/app/agents/base.py`
* **Exact Implementation Rules:**
  1. Create `invoke_structured_agent(schema_cls: Type[T], system_prompt: str, user_payload: dict, mock_builder: Callable[[dict], T]) -> T`.
  2. Read `settings = EngineSettings()` inside the function (never at module import level).
  3. If `settings.USE_MOCK_LLM` is `True`, call `result = mock_builder(user_payload)` and validate it through `schema_cls.model_validate(result.model_dump())` so mock mode exercises the exact same Pydantic validation path as live LLM calls!
  4. If `settings.USE_MOCK_LLM` is `False`, instantiate `ChatGoogleGenerativeAI(model=settings.GEMINI_MODEL, google_api_key=settings.GEMINI_API_KEY, temperature=0.1)` with `.with_structured_output(schema_cls)` and invoke it with `[SystemMessage(content=system_prompt), HumanMessage(content=json.dumps(user_payload, indent=2))]`.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 2.1: Create apps/agent-engine/app/__init__.py, apps/agent-engine/app/agents/__init__.py, and apps/agent-engine/app/agents/base.py. Implement invoke_structured_agent(schema_cls, system_prompt, user_payload, mock_builder) supporting both USE_MOCK_LLM=True (with full Pydantic model_validate enforcement) and live ChatGoogleGenerativeAI structured output calls.
  ```
* **Verification Command:**
  ```powershell
  python -c "from app.agents.base import invoke_structured_agent; print('Micro-Task 2.1 OK')"
  ```

---

### Micro-Task 2.2: Agent 1 — Requirement Analyst (`app/agents/req_analyst.py`)
* **Target File:** `apps/agent-engine/app/agents/req_analyst.py`
* **Exact Implementation Rules:**
  1. **Read Contract Isolation:** The function `run_requirement_analyst(state: ProjectBlueprintState, blast_radius: Optional[Dict[str, Set[str]]] = None, retry_defects: Optional[List[ValidationDefect]] = None) -> ProjectBlueprintState` may ONLY extract `user_initial_prompt`, `human_feedback_notes`, `glossary`, `actors`, `requirements`, plus `stale_requirements` and `retry_defects`. It must NEVER read `features`, `database_entities`, or `endpoints`.
  2. **Selective Update Mode:** If `blast_radius` has `stale_requirements` (and `state.requirements` is non-empty), use `DAGChangePropagator.merge_regenerated_slice` so untouched `REQ-*` items keep their exact IDs and text, while only the stale `REQ-*` items are updated with the human feedback notes.
  3. **Deterministic Mock Builder:** When `USE_MOCK_LLM=True`, generate 3 glossary terms (`Workspace`, `Project`, `Member`), 2 actors (`ACT-01` Admin, `ACT-02` Member), and 2 testable requirements (`REQ-01`, `REQ-02`). If `human_feedback_notes` is present during a revision of `REQ-01`, append the feedback note into `REQ-01.description` and `acceptance_criteria` so tests can verify revision propagation deterministically.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 2.2: Implement apps/agent-engine/app/agents/req_analyst.py with run_requirement_analyst(state, blast_radius, retry_defects). Enforce strict Read Contract isolation, IEEE 830 system prompt instructions, selective slice merging via DAGChangePropagator.merge_regenerated_slice when stale_requirements is provided, and a deterministic mock_builder that reflects human_feedback_notes on revised requirements.
  ```
* **Verification Command:**
  ```powershell
  python -c "from app.agents.req_analyst import run_requirement_analyst; from app.schemas import ProjectBlueprintState; s = ProjectBlueprintState(project_id='p1', user_initial_prompt='Build a SaaS task manager'); s2 = run_requirement_analyst(s); assert len(s2.requirements) >= 2; print('Micro-Task 2.2 OK')"
  ```

---

### Micro-Task 2.3: Agent 2 — Product Architect (`app/agents/product_arch.py`)
* **Target File:** `apps/agent-engine/app/agents/product_arch.py`
* **Exact Implementation Rules:**
  1. **Read Contract Isolation:** Only read `glossary`, `actors`, `requirements`, existing `features` (for selective merge), `stale_features`, `human_feedback_notes`, and `retry_defects` targeted at `ProductArchitect`.
  2. **DDD & FSM Enforcement:** Ensure the mock builder and LLM prompt create features mapped 1-to-1 or many-to-many covering 100% of `state.requirements`, with valid `state_machine` transitions (`CREATED -> ACTIVE -> ARCHIVED`) and non-empty `happy_path` and `edge_cases`.
  3. **Selective Update Mode:** When `stale_features` is non-empty, regenerate only the features in `stale_features` (plus any new features required by newly added `REQ-*` IDs) and merge via `merge_regenerated_slice`.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 2.3: Implement apps/agent-engine/app/agents/product_arch.py with run_product_architect(state, blast_radius, retry_defects). Enforce Read Contract isolation (glossary, actors, requirements, features), DDD bounded contexts, finite state machines, selective slice merging on stale_features, and 100% upstream REQ-* coverage in mock mode.
  ```
* **Verification Command:**
  ```powershell
  python -c "from app.agents.req_analyst import run_requirement_analyst; from app.agents.product_arch import run_product_architect; from app.linter import DeterministicLinter; from app.schemas import ProjectBlueprintState; s = run_product_architect(run_requirement_analyst(ProjectBlueprintState(project_id='p1', user_initial_prompt='Task app'))); assert len(DeterministicLinter.lint_gate_1(s)) == 0; print('Micro-Task 2.3 OK')"
  ```

---

### Micro-Task 2.4: Agent 3 — Database Architect (`app/agents/db_arch.py`)
* **Target File:** `apps/agent-engine/app/agents/db_arch.py`
* **Exact Implementation Rules:**
  1. **Read Contract Isolation:** Only read `glossary`, `features`, existing `database_entities`, `stale_tables`, `human_feedback_notes`, and `retry_defects` targeted at `DatabaseArchitect`.
  2. **3NF, FK & Index Integrity:** Every generated table must have a primary key (`id UUID`), snake_case name, valid `upstream_ids` pointing to `state.features`, valid foreign keys pointing to existing `table_name`s, `is_pii=True` on sensitive columns (like `email`), and indexes covering every foreign key column so Gate 2 produces zero warnings or errors.
  3. **Selective Update Mode:** When `stale_tables` is provided, regenerate only the impacted tables and merge via `merge_regenerated_slice`.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 2.4: Implement apps/agent-engine/app/agents/db_arch.py with run_database_architect(state, blast_radius, retry_defects). Enforce 3NF schema rules, primary keys, indexed foreign keys, PII flags, and selective slice merging on stale_tables.
  ```
* **Verification Command:**
  ```powershell
  python -c "from app.agents.db_arch import run_database_architect; print('Micro-Task 2.4 OK')"
  ```

---

### Micro-Task 2.5: Agent 4 — API Architect (`app/agents/api_arch.py`)
* **Target File:** `apps/agent-engine/app/agents/api_arch.py`
* **Exact Implementation Rules:**
  1. **Read Contract Isolation:** Only read `glossary`, `actors`, `features`, `database_entities`, existing `endpoints`, `stale_endpoints`, `human_feedback_notes`, and `retry_defects` targeted at `APIArchitect`.
  2. **OpenAPI 3.1, RBAC & FSM Endpoint Coverage:** Every generated `EndpointSpec` must link its `upstream_ids` to at least one valid `FEAT-*` ID and at least one valid `TBL-*` ID, assign valid `ACT-*` IDs in `allowed_actor_ids`, set `is_idempotent=True` on `GET`/`PUT`/`DELETE` and state-transition routes, and include RFC 7807 error codes `[400, 401, 403, 404, 409]`.
  3. **Selective Update Mode:** Merge regenerated endpoints via `merge_regenerated_slice` when `stale_endpoints` is present.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 2.5: Implement apps/agent-engine/app/agents/api_arch.py with run_api_architect(state, blast_radius, retry_defects). Enforce RESTful URI rules, RBAC actor references, idempotency flags, RFC 7807 error codes, and selective slice merging on stale_endpoints.
  ```
* **Verification Command:**
  ```powershell
  python -c "from app.agents.api_arch import run_api_architect; print('Micro-Task 2.5 OK')"
  ```

---

### Micro-Task 2.6: Agent 5 — Hybrid Validation Gate Runner & Slice 2 Test Suite (`app/agents/validator_critic.py` + `tests/test_agents.py`)
* **Target Files:**
  * `apps/agent-engine/app/agents/validator_critic.py`
  * `apps/agent-engine/tests/test_agents.py`
* **Exact Implementation Rules:**
  1. Implement `run_validation_gate(state: ProjectBlueprintState, gate_name: Literal["GATE_1", "GATE_2"]) -> ProjectBlueprintState`.
  2. **Step A (Tier 1 Static Linter Short-Circuit):** Call `DeterministicLinter.lint_gate_1(state)` or `lint_gate_2(state)`. If ANY defect has `severity == DefectSeverity.BLOCKING`, append a `ValidationReport(gate_name=gate_name, status=ValidationStatus.FAILED, defects=static_defects, traceability_coverage_percent=coverage)` to `state.validation_reports` and return immediately **without** calling the Tier 2 LLM Critic!
  3. **Step B (Tier 2 LLM Semantic Critic):** If Tier 1 has zero `BLOCKING` defects, call `invoke_structured_agent` with the Gate 1 or Gate 2 semantic critic prompt. Merge static warnings + semantic defects, compute final status (`FAILED`, `WARNINGS`, or `PASSED`), append the `ValidationReport` to `state.validation_reports`, and return `state`.
  4. In `tests/test_agents.py`, write **6 tests** verifying:
     * Full Discovery pipeline (`req_analyst -> product_arch -> Gate 1`) passes with `100%` coverage.
     * Full Architecture pipeline (`db_arch -> api_arch -> Gate 2`) passes with `100%` coverage.
     * Tier 1 short-circuit: when a dangling FK is injected, `run_validation_gate` fails immediately without invoking Tier 2.
     * Selective regeneration on `REQ-01` updates `REQ-01` and `FEAT-01` while keeping `REQ-02` and `FEAT-02` intact.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 2.6: Implement apps/agent-engine/app/agents/validator_critic.py with run_validation_gate(state, gate_name) enforcing the Tier 1 static linter short-circuit before Tier 2 semantic critic evaluation. Then create apps/agent-engine/tests/test_agents.py covering all 5 agents, Tier 1 short-circuiting, and selective blast-radius regeneration. Run pytest tests/test_agents.py -v.
  ```
* **Verification Command:**
  ```powershell
  pytest tests/test_agents.py -v
  ```

---

## SLICE 3: LangGraph Orchestrator State Machine, Checkpoints & FastAPI Server

### Micro-Task 3.1: LangGraph Cyclic State Machine, Retry Circuit Breakers & Interrupts (`app/orchestrator.py`)
* **Target File:** `apps/agent-engine/app/orchestrator.py`
* **Exact Implementation Rules:**
  1. Define `OrchestratorGraphState(TypedDict)`:
     * `blueprint: dict` (serialized `ProjectBlueprintState` via `.model_dump(mode="json")` so LangGraph checkpoint serialization to MemorySaver/MongoDBSaver never chokes on custom Pydantic types or `set` objects!)
     * `gate_1_retries: int`
     * `gate_2_retries: int`
     * `blast_radius: Optional[Dict[str, List[str]]]` (store lists of strings in graph state, convert to `Set[str]` inside nodes).
     * `version_history: List[dict]` (append every checkpointed `blueprint` snapshot so version history is always preserved inside the graph state).
  2. Implement `route_after_gate_1` and `route_after_gate_2` enforcing `MAX_AUTO_RETRIES = 2`:
     * Whenever a gate fails and routes backward to an agent node, increment `gate_1_retries` or `gate_2_retries` inside the gate node!
     * Once `retries >= 2` or `status != ValidationStatus.FAILED`, route to `human_checkpoint_1` or `human_checkpoint_2`.
  3. Implement `human_checkpoint_1_node` and `human_checkpoint_2_node` using `from langgraph.types import interrupt, Command`:
     * Before calling `interrupt(...)`, save the current `blueprint` into `version_history` (replacing any existing entry with the same `version` number or appending if new).
     * On `APPROVE` at Checkpoint 1: set `current_phase = ProjectPhase.ARCHITECTURE`, clear `blast_radius = None`, reset `gate_1_retries = 0`, and `goto="database_architect"`.
     * On `REVISE` at Checkpoint 1 or 2: call `DAGChangePropagator.create_next_version_snapshot`, store the new `blast_radius`, and jump to the earliest affected agent (`requirement_analyst`, `product_architect`, `database_architect`, or `api_architect`).
     * On `APPROVE` at Checkpoint 2: set `human_approved = True`, `current_phase = ProjectPhase.COMPLETED`, append final snapshot to `version_history`, and `goto=END`.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 3.1: Implement apps/agent-engine/app/orchestrator.py using LangGraph StateGraph, interrupt(), and Command. Store blueprint as a JSON-serializable dict via model_dump(mode="json") and blast_radius values as lists so checkpointers never fail on Pydantic/set serialization. Maintain version_history inside the state, increment retry counters on failed gates, enforce MAX_AUTO_RETRIES = 2, and support cross-phase rollback from Checkpoint 2 to any of the 4 domain agents based on modified_ids prefixes.
  ```
* **Verification Command:**
  ```powershell
  python -c "from app.orchestrator import build_orchestrator_graph; g = build_orchestrator_graph(); print('Micro-Task 3.1 OK')"
  ```

---

### Micro-Task 3.2: FastAPI Server, Thread Manager & RFC 7807 Error Contract (`app/main.py`)
* **Target File:** `apps/agent-engine/app/main.py`
* **Exact Implementation Rules:**
  1. Configure `CORSMiddleware` allowing `http://localhost:4000` and `http://localhost:5173`.
  2. Add an RFC 7807 Problem Details exception handler returning `{"type": "about:blank", "title": "...", "status": code, "detail": "..."}` on `400`, `404`, `409`, `422`, and `500`.
  3. Implement 5 exact endpoints:
     * `GET /health` $\rightarrow$ `{"status": "ok", "mock_llm": settings.USE_MOCK_LLM}`
     * `POST /orchestrator/start` (Body: `StartProjectRequest(project_id: Optional[str], user_initial_prompt: str)`) $\rightarrow$ invokes graph up to `human_checkpoint_1`, returns `{ "project_id": id, "active_checkpoint": "GATE_1_REVIEW", "state": blueprint, "versions": version_history }`.
     * `POST /orchestrator/{project_id}/resume` (Body: `ResumeProjectRequest(action: Literal["APPROVE", "REVISE"], modified_ids: List[str] = [], feedback_notes: Optional[str] = None)`) $\rightarrow$ validates that the project thread exists and is currently paused at an interrupt (returns `409 Conflict` if already `COMPLETED`, or `400 Bad Request` if `action == "REVISE"` and `len(modified_ids) == 0`), invokes `graph.invoke(Command(resume=...), config)`, and returns the updated envelope.
     * `GET /orchestrator/{project_id}/state` $\rightarrow$ returns current state and active interrupt checkpoint (or `404` if `project_id` not found).
     * `GET /orchestrator/{project_id}/versions` $\rightarrow$ returns `List[ProjectBlueprintState]` from `version_history`.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 3.2: Implement apps/agent-engine/app/main.py with FastAPI, CORSMiddleware, RFC 7807 error formatting, and the 5 endpoints (/health, POST /orchestrator/start, POST /orchestrator/{project_id}/resume, GET /orchestrator/{project_id}/state, GET /orchestrator/{project_id}/versions). Validate that action=="REVISE" requires non-empty modified_ids (400 error) and resuming a completed project returns 409 Conflict.
  ```
* **Verification Command:**
  ```powershell
  python -c "from app.main import app; print('Micro-Task 3.2 OK')"
  ```

---

### Micro-Task 3.3: End-to-End Orchestrator & FastAPI Integration Tests (`tests/test_orchestrator_flow.py`)
* **Target File:** `apps/agent-engine/tests/test_orchestrator_flow.py`
* **Exact Implementation Rules:**
  Use FastAPI's `TestClient(app)` to test the entire HTTP + LangGraph lifecycle:
  1. `test_full_happy_path_start_to_completion`: `POST /orchestrator/start` (assert pauses at `GATE_1_REVIEW`, `version == 1`) $\rightarrow$ `POST /resume` with `APPROVE` (assert pauses at `GATE_2_REVIEW`, DB tables & API endpoints populated) $\rightarrow$ `POST /resume` with `APPROVE` (assert `current_phase == "COMPLETED"`, `human_approved == True`).
  2. `test_checkpoint_2_cross_phase_revision_to_req_analyst`: Run to `GATE_2_REVIEW` (`v1`) $\rightarrow$ `POST /resume` with `action="REVISE"`, `modified_ids=["REQ-01"]`, `feedback_notes="Require hardware MFA"` $\rightarrow$ assert state increments to `version == 2`, loops back through `requirement_analyst` & `product_arch`, pauses at `GATE_1_REVIEW` with `"Require hardware MFA"` reflected in `REQ-01` while `REQ-02` is preserved, and `GET /versions` returns both `v1` and `v2`.
  3. `test_auto_retry_circuit_breaker_halts_at_max_2`: Force a blocking defect in Gate 1 and verify `gate_1_retries` stops at `MAX_AUTO_RETRIES == 2` and escalates to `human_checkpoint_1` instead of looping forever.
  4. `test_rfc7807_error_on_empty_revise_and_unknown_project`: Verify `400` on `REVISE` with `modified_ids=[]` and `404` on unknown `project_id`.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 3.3: Create apps/agent-engine/tests/test_orchestrator_flow.py with all 4 end-to-end integration tests using FastAPI TestClient (happy path, Checkpoint 2 cross-phase rollback v1->v2 preserving untouched slices, MAX_AUTO_RETRIES=2 circuit breaker, and RFC 7807 error cases). Run pytest apps/agent-engine/tests/ -v until every test in the suite passes.
  ```
* **Verification Command:**
  ```powershell
  pytest tests/ -v
  ```

---

## SLICE 4: Node.js + Express API Gateway & MongoDB Snapshot Store

### Micro-Task 4.1: TypeScript Express Scaffold & MongoDB / Memory Persistence (`apps/api-gateway`)
* **Target Files:**
  * `apps/api-gateway/package.json`
  * `apps/api-gateway/tsconfig.json`
  * `apps/api-gateway/src/config/db.ts`
  * `apps/api-gateway/src/models/ProjectRecord.ts`
* **Exact Implementation Rules:**
  1. In `package.json`, include dependencies: `express`, `cors`, `mongoose`, `zod`, `dotenv` and devDependencies: `typescript`, `@types/express`, `@types/cors`, `@types/node`, `tsx`, `vitest`, `supertest`, `@types/supertest`, `mongodb-memory-server`.
  2. In `src/config/db.ts`, implement `connectDatabase(uri?: string)` that connects Mongoose to `process.env.MONGODB_URI` if provided, or automatically starts `MongoMemoryServer.create()` in local/test development so `npm run dev` and `npm test` NEVER fail if local MongoDB isn't running!
  3. In `src/models/ProjectRecord.ts`, create a real Mongoose schema storing `projectId` (unique index), `title`, `currentPhase`, `currentVersion`, `activeCheckpoint`, `latestState` (Mixed), and `versions` (Array of immutable state snapshots indexed by `version`).
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 4.1: Scaffold apps/api-gateway with package.json, tsconfig.json, src/config/db.ts (using Mongoose with automatic mongodb-memory-server fallback when MONGODB_URI is unset), and src/models/ProjectRecord.ts storing project metadata, latestState, and the immutable versions array. Run npm install and npx tsc --noEmit.
  ```
* **Verification Command:**
  ```powershell
  cd ../api-gateway
  npm install
  npx tsc --noEmit
  ```

---

### Micro-Task 4.2: Python FastAPI Bridge, Express Routes & Supertest Suite (`src/routes/projects.ts`)
* **Target Files:**
  * `apps/api-gateway/src/services/pythonBridge.ts`
  * `apps/api-gateway/src/routes/projects.ts`
  * `apps/api-gateway/src/server.ts`
  * `apps/api-gateway/tests/projects.test.ts`
* **Exact Implementation Rules:**
  1. In `pythonBridge.ts`, implement typed `fetch` calls to `PYTHON_ENGINE_URL` (`default: http://127.0.0.1:8000`) for `startOrchestrator`, `resumeOrchestrator`, `getOrchestratorState`, and `getOrchestratorVersions`, forwarding RFC 7807 error payloads cleanly.
  2. In `routes/projects.ts`, validate request bodies with **Zod** and implement:
     * `GET /api/projects` (list all saved projects sorted by `updatedAt` desc)
     * `POST /api/projects` (calls `startOrchestrator`, upserts `ProjectRecord` in Mongoose, returns `201`)
     * `GET /api/projects/:id` (returns project record + latest state)
     * `POST /api/projects/:id/review` (validates `{ action, modified_ids, feedback_notes }`, calls `resumeOrchestrator`, updates Mongoose `latestState` and `versions` array, returns `200`)
     * `GET /api/projects/:id/versions` (returns all stored version snapshots for diffing)
  3. Write `tests/projects.test.ts` using `vitest` + `supertest` + `mongodb-memory-server` to test all 5 routes and RFC 7807 validation errors.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 4.2: Implement src/services/pythonBridge.ts, src/routes/projects.ts (with Zod validation and Mongoose persistence), src/server.ts (exporting app without calling app.listen when imported by tests), and tests/projects.test.ts using Vitest, Supertest, and mongodb-memory-server. Run npx tsc --noEmit and npm test.
  ```
* **Verification Command:**
  ```powershell
  npx tsc --noEmit && npm test
  ```

---

## SLICE 5: React Blueprint Studio, Artifact Cards & Checkpoint Drawer

### Micro-Task 5.1: React + Vite + Tailwind Scaffold, Strict TypeScript Mirror & API Client (`apps/web`)
* **Target Files:**
  * `apps/web/package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`
  * `apps/web/src/types/blueprint.ts`
  * `apps/web/src/api/projectsApi.ts`
* **Exact Implementation Rules:**
  1. Include dependencies: `react`, `react-dom`, `lucide-react`, `@xyflow/react`, `clsx`, `tailwind-merge` and Tailwind CSS setup.
  2. In `src/types/blueprint.ts`, define exact TypeScript interfaces matching every field of `ProjectBlueprintState`, `ValidationReport`, `ValidationDefect`, and the API Gateway response envelopes.
  3. In `src/api/projectsApi.ts`, implement live `fetch` functions hitting `/api/projects` (proxied in `vite.config.ts` to `http://127.0.0.1:4000`). **Zero hardcoded mock fallbacks in the frontend API client**—errors must surface cleanly in the UI banner.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 5.1: Scaffold apps/web with React 18, Vite, TypeScript, Tailwind CSS, lucide-react, and @xyflow/react. Configure Vite proxy for /api -> http://127.0.0.1:4000. Create src/types/blueprint.ts mirroring ProjectBlueprintState and src/api/projectsApi.ts with real HTTP calls and zero fake frontend mock fallbacks. Verify with npm install and npx tsc --noEmit.
  ```
* **Verification Command:**
  ```powershell
  cd ../web
  npm install
  npx tsc --noEmit
  ```

---

### Micro-Task 5.2: Phase Stepper, Validation Defect Banner & 5-Layer Artifact Inspector (`ArtifactTabs.tsx`)
* **Target Files:**
  * `apps/web/src/components/PhaseStepper.tsx`
  * `apps/web/src/components/ValidationBanner.tsx`
  * `apps/web/src/components/ArtifactTabs.tsx`
* **Exact Implementation Rules:**
  1. `PhaseStepper.tsx`: Renders the 5 phases (`DISCOVERY`, `GATE_1_REVIEW`, `ARCHITECTURE`, `GATE_2_REVIEW`, `COMPLETED`), current version badge (`v1`, `v2`), and active checkpoint status pill.
  2. `ValidationBanner.tsx`: Renders the Gate 1 / Gate 2 `traceability_coverage_percent` progress bar and expandable cards for every `ValidationDefect` (`BLOCKING` in red, `WARNING` in amber) showing `rule_code`, `target_agent`, `target_item_id`, `message`, and `suggested_fix`.
  3. `ArtifactTabs.tsx`: Renders 5 interactive tabs:
     * **Glossary & Actors (`ACT-*`)**: Shows ubiquitous language definitions and actor permission tags.
     * **Requirements (`REQ-*`)**: Shows priority badge (`MUST_HAVE`), linked `actor_id`, description, and numbered `acceptance_criteria`.
     * **Product Features (`FEAT-*`)**: Shows DDD `module_name`, linked `upstream_ids` (`REQ-*`), `happy_path`, `edge_cases`, and visual `state_machine` transition badges (`from_state -> to_state`).
     * **Database Schema (`TBL-*`)**: Shows 3NF tables, columns with `PK`, `UNIQUE`, `PII` badges, foreign key relationships with `on_delete` rules, and `indexes`.
     * **API Contracts (`EP-*`)**: Shows HTTP method badge (`GET`, `POST`, `PATCH`, `DELETE`), URI path, `IDEMPOTENT` badge, permitted `ACT-*` roles, RFC 7807 error status chips, and expandable JSON request/response DTO schemas.
     * Every card (`ACT-*`, `REQ-*`, `FEAT-*`, `TBL-*`, `EP-*`) must have a **"Select for Revision" checkbox** that toggles its ID in the parent `selectedModifiedIds` state!
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 5.2: Implement src/components/PhaseStepper.tsx, src/components/ValidationBanner.tsx, and src/components/ArtifactTabs.tsx in apps/web. Ensure every ACT-*, REQ-*, FEAT-*, TBL-*, and EP-* card renders all software engineering metadata (DDD module, FSM transitions, PII flags, FK rules, idempotency, RFC 7807 codes) and includes a checkbox to toggle its ID in selectedModifiedIds for selective checkpoint revisions. Run npx tsc --noEmit.
  ```
* **Verification Command:**
  ```powershell
  npx tsc --noEmit
  ```

---

### Micro-Task 5.3: Human-in-the-Loop Checkpoint Review Bar (`CheckpointDrawer.tsx`)
* **Target File:** `apps/web/src/components/CheckpointDrawer.tsx`
* **Exact Implementation Rules:**
  1. Renders whenever `current_phase` is `GATE_1_REVIEW` or `GATE_2_REVIEW`.
  2. Shows all currently selected item IDs (`selectedModifiedIds`) as removable pills, plus a live preview count of how many downstream items will be regenerated (`blastRadiusPreviewIds`).
  3. Provides two primary actions:
     * **Approve Checkpoint & Continue (`action: "APPROVE"`)**: Advances Gate 1 to Architecture Phase, or finalizes Gate 2 to `COMPLETED`.
     * **Submit Selective Revision (`action: "REVISE"`)**: Requires at least 1 selected ID (`REQ-*`, `FEAT-*`, `TBL-*`, or `EP-*`) and non-empty `feedback_notes`, then triggers the selective DAG rollback to `vN+1`.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 5.3: Implement src/components/CheckpointDrawer.tsx allowing the human reviewer at GATE_1_REVIEW or GATE_2_REVIEW to either Approve the checkpoint or submit a Selective Revision with selectedModifiedIds, blast-radius impact count, and feedback_notes. Run npx tsc --noEmit.
  ```
* **Verification Command:**
  ```powershell
  npx tsc --noEmit
  ```

---

## SLICE 6: Interactive DAG Traceability Graph (`@xyflow/react`) & Version Diff Studio

### Micro-Task 6.1: 4-Column Interactive DAG & Live Blast-Radius Highlighter (`TraceabilityGraph.tsx`)
* **Target File:** `apps/web/src/components/TraceabilityGraph.tsx`
* **Exact Implementation Rules:**
  1. Uses `@xyflow/react` (`ReactFlow`, `Background`, `Controls`, `MarkerType`) to layout nodes in **4 deterministic vertical columns** (`x = 40` for `REQ-*`, `x = 340` for `FEAT-*`, `x = 640` for `TBL-*`, `x = 940` for `EP-*`).
  2. Creates directed edges from every item's `upstream_ids` to the item itself.
  3. Implements a client-side `computeClientBlastRadius(blueprint, selectedAndHoveredIds)` mirror of `DAGChangePropagator`:
     * When the user hovers over or selects any node (e.g., `REQ-01`), that node highlights in **blue/indigo**, and every downstream `FEAT-*`, `TBL-*`, and `EP-*` node in its blast radius highlights in **amber/orange** with animated edges!
     * Clicking a node in the graph also toggles it in `selectedModifiedIds` for revision.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 6.1: Implement src/components/TraceabilityGraph.tsx using @xyflow/react. Position REQ-*, FEAT-*, TBL-*, and EP-* nodes in 4 vertical columns connected by upstream_ids edges. Compute downstream blast radius on node hover/selection so impacted downstream nodes and edges glow in amber, and allow clicking any node to toggle its selection for checkpoint revision. Run npx tsc --noEmit.
  ```
* **Verification Command:**
  ```powershell
  npx tsc --noEmit
  ```

---

### Micro-Task 6.2: Side-by-Side Immutable Version Diff Viewer & Main Studio (`VersionDiffModal.tsx` + `ProjectWorkspace.tsx`)
* **Target Files:**
  * `apps/web/src/components/VersionDiffModal.tsx`
  * `apps/web/src/pages/ProjectWorkspace.tsx`
  * `apps/web/src/App.tsx`
* **Exact Implementation Rules:**
  1. `VersionDiffModal.tsx`: Lets the user pick any two snapshots from `versions` (e.g., `v1` vs `v2`) and compares every `REQ-*`, `FEAT-*`, `TBL-*`, and `EP-*` item by ID—badging items as **Added (Green)**, **Modified (Amber, showing before/after JSON or text diff)**, or **Preserved/Untouched (Slate)** to prove that selective DAG regeneration kept untouched modules intact.
  2. `ProjectWorkspace.tsx`: Integrates project creation sidebar, `PhaseStepper`, `ValidationBanner`, a view switcher between **Structured Artifact Tabs** and **Interactive Traceability DAG**, `VersionDiffModal`, and `CheckpointDrawer`.
  3. Run `npm run build` to verify the entire frontend compiles cleanly into production bundles.
* **Copy-Paste Prompt for Antigravity:**
  ```text
  Execute Micro-Task 6.2: Implement src/components/VersionDiffModal.tsx (comparing v1 vs v2 snapshots and badging each ID as Added, Modified, or Preserved), src/pages/ProjectWorkspace.tsx, and src/App.tsx. Run npm run build in apps/web and fix any TypeScript or bundler errors.
  ```
* **Verification Command:**
  ```powershell
  npm run build
  ```
