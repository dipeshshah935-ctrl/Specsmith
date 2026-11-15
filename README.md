# Blueprint Engine: 5-Agent + Orchestrator Technical Architecture Platform

A production-grade, software-engineering-first multi-agent system that transforms raw product ideas into verified, traceable, versioned technical blueprints (Requirements, Domain-Driven Product Specs, 3NF Database Schemas, and OpenAPI 3.1 REST Contracts).

Built on a **Polyglot MERN + Python AI Stack**:

* **AI Orchestration & Agent Engine (`apps/agent-engine`):** Python 3.12, FastAPI, LangGraph, Pydantic v2

* **API Gateway & Persistence Layer (`apps/api-gateway`):** Node.js, Express, TypeScript, MongoDB (Mongoose + LangGraph `MongoDBSaver`)

* **Interactive Blueprint Studio (`apps/web`):** React 18, Vite, TypeScript, Tailwind CSS, React Flow (`@xyflow/react`)

## 1. Architectural Philosophy & Why "5 Agents + 1 Orchestrator"

### 1.1 Why 5 Domain Agents + 1 Central Orchestrator?

In multi-agent system design, splitting responsibilities across 8 to 12 micro-agents (such as separate agents for Security, Business Rules, Impact Analysis, Compliance, and Naming) introduces severe engineering liabilities:

* **Context-Handoff Latency & Token Bloat:** Every agent boundary requires serializing and re-reading project context.

* **Prompt Drift & Naming Contradictions:** More agents increase the probability that one agent invents terminology or rules that conflict with another.

* **State-Synchronization Complexity:** Resolving circular disagreements across 10 agents makes rollback routing non-deterministic.

**Our Architectural Decision:** Keep the system strictly at **5 Domain Agents + 1 Orchestrator**. Each of the 5 agents maps 1-to-1 to a canonical layer of the software engineering lifecycle, while cross-cutting concerns (**security, business rules, privacy/PII, non-functional limits, and impact analysis**) are embedded directly inside the domain agents where those decisions naturally live. If any single agent's responsibility grows too large in the future, it can be sub-divided behind its existing state contract without changing the Orchestrator.

### 1.2 Hub-and-Spoke Coordination vs. Linear Prompt Chains

Agents never talk directly to one another in an unstructured chat thread. Instead:

1. **The Orchestrator is the Hub:** It owns the canonical `ProjectBlueprintState`, version history (`v1`, `v2`, `v3`), execution routing, retry circuit breakers, human-in-the-loop checkpoints, and change propagation.

2. **The 5 Agents are Pure Functional Spokes:** Each agent receives only a minimal, read-only slice of the current state (`Read Contract`) and outputs a strictly typed Pydantic v2 payload (`Write Contract`).

### 1.3 End-to-End Execution Topology

| Stage | Component | Action Performed | Routing Outcome | 
| ----- | ----- | ----- | ----- | 
| **Stage 1** | **User Input** | Submits initial product idea and constraints via React UI. | Initializes `ProjectBlueprintState` (`v1`, `DISCOVERY`). | 
| **Stage 2** | **1. Requirement Analyst** | Establishes the Ubiquitous Language `glossary`, identifies `actors` (`ACT-*`), and writes atomic, testable `requirements` (`REQ-*`). | Advances to **Product Architect**. | 
| **Stage 3** | **2. Product Architect** | Organizes DDD Bounded Context modules, creates `features` (`FEAT-*` linked to `REQ-*`), maps happy/edge paths, and defines Finite State Machines (`state_machine`). | Advances to **Validation Gate 1**. | 
| **Stage 4** | **5. Validation Agent (Gate 1)** | Runs Tier 1 Python Static Linter (actor links, 100% `REQ` coverage) followed by Tier 2 LLM Semantic Critic (FSM completeness, edge cases). | If `FAILED` and `retries < 2`: routes back to **Requirement Analyst** or **Product Architect**. Otherwise advances to **Human Checkpoint 1**. | 
| **Stage 5** | **Human Checkpoint 1** | Pauses graph (`interrupt()`). Human inspects Discovery specs in React UI and either **Approves** or edits specific `ACT-*`/`REQ-*`/`FEAT-*` IDs. | On **Approve**: advances to **Database Architect**. On **Edit**: increments version (`v2`), computes DAG blast radius, and re-runs affected Discovery agent. | 
| **Stage 6** | **3. Database Architect** | Designs 3NF relational `database_entities` (`TBL-*` linked to `FEAT-*`), columns, foreign keys (`on_delete`), PII flags, and query indexes. | Advances to **API Architect**. | 
| **Stage 7** | **4. API Architect** | Designs REST `endpoints` (`EP-*` linked to `FEAT-*` and `TBL-*`), HTTP methods, DTO JSON schemas, RBAC permissions (`allowed_actor_ids`), idempotency flags, and RFC 7807 error codes. | Advances to **Validation Gate 2**. | 
| **Stage 8** | **5. Validation Agent (Gate 2)** | Runs Tier 1 Python Static Linter (foreign key targets, unindexed FKs, actor RBAC links, orphan endpoints) + Tier 2 LLM Critic (CRUD completeness, FSM transition endpoints, PII exposure). | If `FAILED` and `retries < 2`: routes back to **Database Architect** or **API Architect**. Otherwise advances to **Human Checkpoint 2**. | 
| **Stage 9** | **Human Checkpoint 2** | Pauses graph (`interrupt()`). Human inspects the complete blueprint, DAG traceability graph, and version diffs. | On **Approve**: marks `COMPLETED`. On **Edit** (at any layer `REQ`, `FEAT`, `TBL`, or `EP`): computes downstream blast radius and routes back to the earliest modified layer while preserving untouched items. | 

## 2. Dual-Layer Software Engineering (SE) Principles

Every part of this platform enforces formal Software Engineering principles at two distinct levels: **System-Level** (how the runtime is engineered) and **Artifact-Level** (what standards the agents enforce on the generated blueprint).

### 2.1 System-Level SE Principles (Platform Engineering)

1. **Design by Contract (DbC):**

   * **Pre-conditions:** Validated input slices extracted from `ProjectBlueprintState`.

   * **Post-conditions:** Enforced via LLM Structured Outputs (`with_structured_output(PydanticModel)`). Malformed JSON or type violations fail at parser level before reaching state storage.

   * **Invariants:** Global graph rules verified deterministically on every state transition.

2. **Event Sourcing & Immutable State Versioning (`v1`, `v2`, `v3...`):**

   * Approved or checkpointed states are never mutated in place.

   * Any human revision deep-clones the state into `version = N + 1` via `DAGChangePropagator.create_next_version_snapshot()`, enabling instant rollback and visual diffing in the React UI.

3. **Hybrid Two-Tier Validation (Static Linter + Semantic Critic):**

   * **Tier 1 (`DeterministicLinter`):** Pure Python set-theory and graph assertions executing in under 5 milliseconds at zero token cost. Catches dangling IDs, missing foreign key targets, unindexed FKs, and uncovered `MUST_HAVE` requirements. If Tier 1 finds any `BLOCKING` defect, Tier 2 is skipped to save tokens and latency.

   * **Tier 2 (`ValidationAgent` LLM Critic):** Runs only after Tier 1 passes. Evaluates semantic qualities that require domain reasoning (unreachable state transitions, missing failure recovery flows, CRUD deadlocks, PII leakage).

4. **Directed Acyclic Graph (DAG) Traceability & Selective Blast-Radius Propagation:**

   * Every item carries a deterministic prefix ID (`ACT-01`, `REQ-01`, `FEAT-01`, `TBL-01`, `EP-01`) and an `upstream_ids: List[str]` pointer array.

   * When a user edits `REQ-02` at a checkpoint, the Orchestrator runs a Breadth-First Search (BFS) over the DAG to mark only the dependent `FEAT-*`, `TBL-*`, and `EP-*` nodes as `stale`. Agents regenerate only the stale slice while keeping untouched modules intact.

5. **Bounded Auto-Retry Circuit Breakers:**

   * Both Gate 1 and Gate 2 enforce `MAX_AUTO_RETRIES = 2`. If agents cannot resolve a blocking validation defect within 2 automated self-correction loops, the Orchestrator halts the loop and escalates the exact defect list to the Human Checkpoint.

### 2.2 Artifact-Level SE Principles (Blueprint Quality Standards)

| Agent | Core SE Frameworks Enforced | Embedded Secondary Concerns | Concrete Engineering Guardrails | 
| ----- | ----- | ----- | ----- | 
| **1. Requirement Analyst** | • **IEEE 830 / ISO 29148** (Atomic, unambiguous, verifiable requirements)  • **INVEST** Criteria  • **DDD Ubiquitous Language** | • High-level compliance & privacy boundaries  • Actor role hierarchy  • Non-functional SLAs (latency, availability, RPO/RTO) | • Initializes the canonical `glossary` so downstream agents never drift on naming (`Workspace` vs `Tenant`).  • Rejects vague adjectives ("fast", "scalable")—requires quantifiable `acceptance_criteria` (e.g., `p95 < 200ms`). | 
| **2. Product Architect** | • **Domain-Driven Design (DDD)** Bounded Contexts  • **High Cohesion / Loose Coupling**  • **Finite State Machines (FSM)** | • Functional business rules & invariants  • Lifecycle state transitions & guard conditions  • Role-to-feature access matrix | • Groups features into explicit DDD `module_name` contexts.  • Requires every stateful entity (`Order`, `Subscription`, `Ticket`) to declare a `state_machine` with initial, intermediate, and terminal states.  • Requires both `happy_path` and explicit `edge_cases`. | 
| **3. Database Architect** | • **Third Normal Form (3NF)**  • **ACID & Referential Integrity**  • **Query-Driven Indexing**  • **Privacy by Design** | • Data-level integrity constraints  • Foreign key cascade/restrict policies  • PII classification (`is_pii`)  • Soft-delete & audit timestamp strategy | • Prohibits orphan tables and circular foreign keys.  • Requires explicit `on_delete` (`RESTRICT`, `CASCADE`, `SET NULL`) on every relationship.  • Requires every FK, unique constraint, and state enum column to appear in `indexes`. | 
| **4. API Architect** | • **RESTful Uniform Interface (OpenAPI 3.1)**  • **Idempotency Standards**  • **Least Privilege RBAC**  • **RFC 7807 Problem Details** | • Route-level authorization (`allowed_actor_ids`)  • Rate-limiting & pagination contracts  • Request/Response DTO validation schemas | • Uses plural kebab/snake-case resource nouns in paths (no verbs in URLs).  • Enforces `is_idempotent = True` on `GET`, `PUT`, `DELETE`, and financial/state-transition `POST` routes.  • Ensures every FSM transition has a corresponding endpoint. | 
| **5. Validation Agent** | • **Bidirectional Requirements Traceability Matrix (RTM)**  • **Failure Mode & Effects Analysis (FMEA)**  • **Static Contract Verification** | • Cross-layer consistency auditing  • Dead-feature / gold-plating detection  • Blast-radius impact verification | • **Forward Traceability:** 100% of `MUST_HAVE` `REQ-*` IDs must map to $\ge 1$ `FEAT-*` $\rightarrow$ `TBL-*` $\rightarrow$ `EP-*`.  • **Backward Traceability:** Zero orphan features, tables, or endpoints without valid upstream parents. | 

## 3. Monorepo Directory Architecture

```
blueprint-engine/
├── README.md                                # Master project overview & architecture specification
├── docker-compose.yml                       # Local MongoDB + FastAPI + Express + React
├── .env.example                             # Environment variables template
├── apps/
│   ├── agent-engine/                        # PYTHON 3.12 SERVICE (Port 8000)
│   │   ├── pyproject.toml                   # FastAPI, LangGraph, Pydantic v2, Motor/PyMongo, Pytest
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── config.py                    # Env config (USE_MOCK_LLM, MONGODB_URI, GEMINI_API_KEY)
│   │   │   ├── schemas.py                   # Canonical Pydantic v2 ProjectBlueprintState & Agent I/O
│   │   │   ├── linter.py                    # Tier 1 DeterministicLinter (Gate 1 & Gate 2 static checks)
│   │   │   ├── propagator.py                # DAGChangePropagator (BFS blast-radius & version cloning)
│   │   │   ├── orchestrator.py              # LangGraph StateGraph, conditional edges, interrupt() nodes
│   │   │   ├── main.py                      # FastAPI server (/orchestrator/start, /resume, /events, /state)
│   │   │   └── agents/
│   │   │       ├── __init__.py
│   │   │       ├── base.py                  # LLM factory + USE_MOCK_LLM deterministic fixture support
│   │   │       ├── req_analyst.py           # Agent 1: Requirement Analyst
│   │   │       ├── product_arch.py          # Agent 2: Product Architect
│   │   │       ├── db_arch.py               # Agent 3: Database Architect
│   │   │       ├── api_arch.py              # Agent 4: API Architect
│   │   │       └── validator_critic.py      # Agent 5: Tier 2 Semantic Critic (Gate 1 & Gate 2 modes)
│   │   └── tests/
│   │       ├── test_core_logic.py           # Unit tests for schemas, DeterministicLinter, DAGPropagator
│   │       ├── test_agents.py               # Unit tests for all 5 agents (mock + contract validation)
│   │       └── test_orchestrator_flow.py    # End-to-end state machine, retry loop, and checkpoint tests
│   │
│   ├── api-gateway/                         # NODE.JS + EXPRESS SERVICE (Port 4000)
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   └── src/
│   │       ├── server.ts                    # Express app setup, CORS, RFC 7807 error middleware
│   │       ├── config/db.ts                 # Mongoose connection to shared MongoDB cluster
│   │       ├── models/ProjectSnapshot.ts    # Mongoose schema storing immutable v1, v2, v3 snapshots
│   │       ├── services/pythonBridge.ts     # Typed HTTP + SSE client talking to FastAPI (Port 8000)
│   │       └── routes/projects.ts           # REST & SSE endpoints for React UI
│   │
│   └── web/                                 # REACT + VITE FRONTEND (Port 5173)
│       ├── package.json
│       ├── tsconfig.json
│       ├── vite.config.ts
│       └── src/
│           ├── types/blueprint.ts           # TypeScript interfaces mirroring ProjectBlueprintState
│           ├── api/projectsApi.ts           # API client + EventSource SSE hook
│           ├── pages/ProjectWorkspace.tsx   # Main studio view with phase stepper & tabs
│           └── components/
│               ├── PhaseStepper.tsx         # Live pipeline progress & active agent indicator
│               ├── ArtifactTabs.tsx         # Structured cards for Glossary, Actors, Reqs, Features, DB, API
│               ├── ValidationBanner.tsx     # Gate 1 / Gate 2 RTM coverage bar & defect list
│               ├── CheckpointDrawer.tsx     # Human Approve button + selective ID multi-select & notes
│               ├── TraceabilityGraph.tsx    # @xyflow/react interactive 4-column DAG with blast-radius glow
│               └── VersionDiffModal.tsx     # Side-by-side comparison of v1 vs v2 snapshots

```

## 4. Canonical Data Contract Specification (`apps/agent-engine/app/schemas.py`)

Every service in the monorepo adheres to `ProjectBlueprintState`. Below is the complete field-level specification:

### 4.1 Enums & Status Codes

* **`ProjectPhase`:** `DISCOVERY` | `GATE_1_REVIEW` | `ARCHITECTURE` | `GATE_2_REVIEW` | `COMPLETED`

* **`Priority`:** `MUST_HAVE` | `SHOULD_HAVE` | `COULD_HAVE`

* **`ValidationStatus`:** `PASSED` | `FAILED` | `WARNINGS`

* **`DefectSeverity`:** `BLOCKING` (halts progression, triggers retry or human escalation) | `WARNING` (advisory)

### 4.2 Entity Schemas & Traceability Rules

| Model Name | ID Format | Upstream Link Field | Key Fields & Engineering Constraints | 
| ----- | ----- | ----- | ----- | 
| **`GlossaryTerm`** | N/A (`term`) | None (Root Layer) | `term: str`, `definition: str`. Enforces Ubiquitous Language across all layers. | 
| **`Actor`** | `ACT-01` | None (Root Layer) | `id`, `name`, `description`, `permissions_summary: List[str]`. | 
| **`Requirement`** | `REQ-01` | `actor_id: str` | `id`, `actor_id` (must exist in `actors`), `title`, `description`, `priority`, `acceptance_criteria: List[str]`. | 
| **`StateTransition`** | Embedded | N/A | `from_state: str`, `to_state: str`, `trigger_action: str`, `guard_condition: Optional[str]`. | 
| **`Feature`** | `FEAT-01` | `upstream_ids: List[str]` (`REQ-*`) | `id`, `upstream_ids` ($\ge 1$ valid `REQ-*`), `module_name` (DDD Bounded Context), `name`, `description`, `happy_path: List[str]`, `edge_cases: List[str]`, `state_machine: Optional[List[StateTransition]]`. | 
| **`ColumnDefinition`** | Embedded | N/A | `name`, `data_type`, `is_primary_key: bool`, `is_nullable: bool`, `is_unique: bool`, `is_pii: bool`. | 
| **`EntityRelationship`** | Embedded | N/A | `foreign_key_column`, `references_entity` (must match a valid `table_name`), `references_column`, `on_delete` (`RESTRICT`, `CASCADE`, `SET NULL`). | 
| **`DatabaseEntity`** | `TBL-01` | `upstream_ids: List[str]` (`FEAT-*`) | `id`, `upstream_ids` ($\ge 1$ valid `FEAT-*`), `table_name` (snake_case plural), `columns: List[ColumnDefinition]`, `relationships: List[EntityRelationship]`, `indexes: List[str]`. | 
| **`EndpointSpec`** | `EP-01` | `upstream_ids: List[str]` (`FEAT-*`, `TBL-*`) | `id`, `upstream_ids`, `http_method`, `path` (REST resource URI), `summary`, `allowed_actor_ids: List[str]` (valid `ACT-*`), `is_idempotent: bool`, `request_dto_schema: Optional[dict]`, `response_dto_schema: dict`, `error_codes: List[int]`. | 
| **`ValidationDefect`** | N/A | `target_item_id: Optional[str]` | `rule_code`, `severity`, `target_agent`, `target_item_id`, `message`, `suggested_fix`. | 
| **`ValidationReport`** | N/A | N/A | `gate_name` (`GATE_1` or `GATE_2`), `status`, `defects: List[ValidationDefect]`, `traceability_coverage_percent: float`. | 

### 4.3 Root State & LangGraph Wrapper State

While `ProjectBlueprintState` is the persisted domain document, the LangGraph `StateGraph` operates on an orchestration dictionary `OrchestratorGraphState`:

```
from typing import TypedDict, Optional, Dict, Set
from app.schemas import ProjectBlueprintState

class OrchestratorGraphState(TypedDict):
    blueprint: ProjectBlueprintState
    gate_1_retries: int
    gate_2_retries: int
    blast_radius: Optional[Dict[str, Set[str]]]

```

## 5. Complete Hybrid Validation Rulebook (`apps/agent-engine/app/linter.py`)

The Validation Agent never relies on guesswork. It executes the deterministic rulebook below first, then runs the LLM semantic critic only if zero `BLOCKING` static defects exist.

### 5.1 Gate 1 Validation Rules (Post-Product Architect)

| Rule Code | Tier | Severity | Target Agent | Verification Logic | 
| ----- | ----- | ----- | ----- | ----- | 
| `ERR_DANGLING_ACTOR` | Tier 1 (Static) | `BLOCKING` | `RequirementAnalyst` | `req.actor_id` is not present in `{a.id for a in state.actors}`. | 
| `ERR_EMPTY_ACCEPTANCE` | Tier 1 (Static) | `BLOCKING` | `RequirementAnalyst` | `len(req.acceptance_criteria) == 0`. Every IEEE 830 requirement must be testable. | 
| `ERR_UNLINKED_FEATURE` | Tier 1 (Static) | `BLOCKING` | `ProductArchitect` | `len(feat.upstream_ids) == 0`. Prevents gold-plated features with no parent requirement. | 
| `ERR_INVALID_UPSTREAM_REQ` | Tier 1 (Static) | `BLOCKING` | `ProductArchitect` | Any ID in `feat.upstream_ids` does not exist in `{r.id for r in state.requirements}`. | 
| `ERR_ORPHAN_REQUIREMENT` | Tier 1 (Static) | `BLOCKING` (if `MUST_HAVE`) / `WARNING` | `ProductArchitect` | A `Requirement.id` is not referenced by any `Feature.upstream_ids`. | 
| `ERR_MISSING_EDGE_CASES` | Tier 1 (Static) | `WARNING` | `ProductArchitect` | `len(feat.edge_cases) == 0`. Every feature must document failure/boundary paths. | 
| `SEM_FSM_DEADLOCK` | Tier 2 (LLM) | `BLOCKING` | `ProductArchitect` | A stateful feature's `state_machine` lacks an initial state, terminal state, or has unreachable states. | 
| `SEM_ACTOR_ROLE_CONFLICT` | Tier 2 (LLM) | `BLOCKING` | `ProductArchitect` | A feature grants capabilities that contradict the actor's `permissions_summary` or business goal. | 

### 5.2 Gate 2 Validation Rules (Post-API Architect)

| Rule Code | Tier | Severity | Target Agent | Verification Logic | 
| ----- | ----- | ----- | ----- | ----- | 
| `ERR_MISSING_PRIMARY_KEY` | Tier 1 (Static) | `BLOCKING` | `DatabaseArchitect` | A `DatabaseEntity` has no column with `is_primary_key == True`. | 
| `ERR_INVALID_UPSTREAM_FEATURE` | Tier 1 (Static) | `BLOCKING` | `DatabaseArchitect` | Any ID in `tbl.upstream_ids` is not in `{f.id for f in state.features}`. | 
| `ERR_DANGLING_FOREIGN_KEY` | Tier 1 (Static) | `BLOCKING` | `DatabaseArchitect` | `rel.references_entity` does not match any `table_name` in `state.database_entities`. | 
| `ERR_DANGLING_FK_COLUMN` | Tier 1 (Static) | `BLOCKING` | `DatabaseArchitect` | `rel.references_column` does not exist on the target `DatabaseEntity`. | 
| `ERR_UNINDEXED_FOREIGN_KEY` | Tier 1 (Static) | `WARNING` | `DatabaseArchitect` | `rel.foreign_key_column` is not mentioned in `tbl.indexes`. | 
| `ERR_ORPHAN_FEATURE_DATA` | Tier 1 (Static) | `WARNING` | `DatabaseArchitect` | A `Feature.id` is not referenced by any `DatabaseEntity.upstream_ids` or `EndpointSpec.upstream_ids`. | 
| `ERR_UNKNOWN_ACTOR_PERMISSION` | Tier 1 (Static) | `BLOCKING` | `APIArchitect` | Any ID in `ep.allowed_actor_ids` is not in `{a.id for a in state.actors}`. | 
| `ERR_ORPHAN_ENDPOINT` | Tier 1 (Static) | `BLOCKING` | `APIArchitect` | `ep.upstream_ids` is empty or contains an ID not in `features` $\cup$ `database_entities`. | 
| `SEM_MISSING_FSM_ENDPOINT` | Tier 2 (LLM) | `BLOCKING` | `APIArchitect` | A `StateTransition` defined on a `Feature` has no corresponding mutating REST endpoint (`POST`/`PATCH`/`PUT`). | 
| `SEM_CRUD_DEAD_TABLE` | Tier 2 (LLM) | `BLOCKING` | `APIArchitect` | A `DatabaseEntity` is read via `GET` endpoints but has no creation/ingestion mechanism or seed policy. | 
| `SEM_PII_EXPOSURE` | Tier 2 (LLM) | `BLOCKING` | `APIArchitect` | A table containing `is_pii=True` columns is exposed on public/unauthenticated endpoints without masking. | 

## 6. Selective Change Propagation & Cross-Phase Rollback Mechanics

When a human reviewer pauses at **Checkpoint 1** or **Checkpoint 2** and requests changes to specific items (for example, editing `REQ-02` and `TBL-03`), the system executes a deterministic 4-step propagation protocol:

1. **Snapshot Cloning (`version = N + 1`):**
   `DAGChangePropagator.create_next_version_snapshot()` deep-copies the current `ProjectBlueprintState`, increments `version`, resets `human_approved = False`, and records `human_feedback_notes`.

2. **BFS Blast-Radius Calculation:**

   * Any `Feature` whose `id` is in `modified_ids` OR whose `upstream_ids` intersects `modified_ids` is added to `stale_features`.

   * Any `DatabaseEntity` whose `id` is in `modified_ids` OR whose `upstream_ids` intersects `modified_ids` $\cup$ `stale_features` is added to `stale_tables`.

   * Any `EndpointSpec` whose `id` is in `modified_ids` OR whose `upstream_ids` intersects `modified_ids` $\cup$ `stale_features` $\cup$ `stale_tables` is added to `stale_endpoints`.

3. **Selective Merge Inside Agent Nodes:**
   When an agent runs with a non-empty `blast_radius`, its node wrapper passes both the untouched items (to preserve their exact IDs and specs) and the stale IDs + `human_feedback_notes` (to regenerate or update only the impacted slice).

4. **Earliest-Layer Backward Routing:**

   * If any modified ID starts with `REQ-` or `ACT-`, the Orchestrator jumps back to `requirement_analyst`.

   * Else if any modified ID starts with `FEAT-`, it jumps to `product_architect`.

   * Else if any modified ID starts with `TBL-`, it jumps to `database_architect`.

   * Else it jumps to `api_architect`.

## 7. Cross-Service API Contract (MERN <-> Python FastAPI)

| Layer | Method & Path | Request Payload | Response / Stream Payload | Description | 
| ----- | ----- | ----- | ----- | ----- | 
| **FastAPI** | `POST /orchestrator/start` | `{ "project_id": "str", "user_initial_prompt": "str" }` | `ProjectBlueprintState` (paused at `GATE_1_REVIEW`) | Starts a new LangGraph thread (`thread_id = project_id`), runs Discovery + Gate 1, and pauses at `human_checkpoint_1`. | 
| **FastAPI** | `POST /orchestrator/{project_id}/resume` | `{ "action": "APPROVE" | "REVISE", "modified_ids": ["REQ-01"], "feedback_notes": "str" }` | `ProjectBlueprintState` (paused at next checkpoint or `COMPLETED`) | Passes `Command(resume=payload)` to the paused LangGraph thread and runs until the next interrupt or `END`. | 
| **FastAPI** | `GET /orchestrator/{project_id}/state` | Query: `?version=optional_int` | `ProjectBlueprintState` + `active_checkpoint` metadata | Returns current state or a specific historical version snapshot. | 
| **Express** | `POST /api/projects` | `{ "title": "str", "prompt": "str" }` | `{ "project_id": "str", "state": ProjectBlueprintState }` | Creates project record in MongoDB, calls FastAPI `/orchestrator/start`, saves `v1` snapshot. | 
| **Express** | `POST /api/projects/:id/review` | `{ "action": "APPROVE" | "REVISE", "modified_ids": [], "feedback_notes": "str" }` | `{ "project_id": "str", "state": ProjectBlueprintState }` | Calls FastAPI `/orchestrator/:id/resume`, archives new version snapshot in MongoDB `project_snapshots` collection. | 
| **Express** | `GET /api/projects/:id/versions` | None | `List[ProjectBlueprintState]` (`v1`, `v2`, ...) | Reads all immutable snapshots for side-by-side diffing in the React UI. | 

## 8. Step-by-Step Engineering Implementation Roadmap

To build this entire system with strict modularity and high reliability, the architecture is engineered across **6 Vertical Slices** in strict order. Each slice must pass its automated verification and test suite 100% before integrating downstream services.

### Slice 1: Python Core Data Contracts, Static Linter & DAG Propagator

* **Goal:** Establish the mathematical and schema foundation of the platform with zero LLM calls required.

* **Files to Create:**

  1. `apps/agent-engine/pyproject.toml` (Dependencies: `fastapi`, `uvicorn`, `pydantic>=2.7`, `langgraph`, `langchain-core`, `langchain-google-genai`, `pymongo`, `pytest`, `httpx`)

  2. `apps/agent-engine/app/__init__.py`

  3. `apps/agent-engine/app/schemas.py` (Full Pydantic v2 models: `ProjectBlueprintState`, `Requirement`, `Feature`, `DatabaseEntity`, `EndpointSpec`)

  4. `apps/agent-engine/app/linter.py` (`DeterministicLinter.lint_gate_1` and `lint_gate_2` implementing all Tier 1 rules + `calculate_traceability_coverage`)

  5. `apps/agent-engine/app/propagator.py` (`DAGChangePropagator.compute_blast_radius` and `create_next_version_snapshot`)

  6. `apps/agent-engine/tests/test_core_logic.py`

* **Unit Tests Required in `test_core_logic.py`:**

  * Verify valid `ProjectBlueprintState` serialization and deserialization.

  * Verify `lint_gate_1` catches `ERR_DANGLING_ACTOR`, `ERR_INVALID_UPSTREAM_REQ`, and `ERR_ORPHAN_REQUIREMENT`.

  * Verify `lint_gate_2` catches `ERR_DANGLING_FOREIGN_KEY`, `ERR_DANGLING_FK_COLUMN`, `ERR_UNKNOWN_ACTOR_PERMISSION`, and `ERR_ORPHAN_ENDPOINT`.

  * Verify `DAGChangePropagator.compute_blast_radius` accurately marks only downstream `FEAT-*`, `TBL-*`, and `EP-*` items when a single `REQ-01` is modified, leaving `REQ-02` branches untouched.

* **Slice 1 Verification:**
  Run `pytest apps/agent-engine/tests/test_core_logic.py -v` and ensure 100% of tests pass.

### Slice 2: The 5 Domain Agents with Dual-Mode Execution (`USE_MOCK_LLM` + Live Structured Outputs)

* **Goal:** Implement all 5 domain agents with strict Read/Write slice isolation, embedded SE guardrails, and an offline deterministic mock mode for instant CI testing.

* **Files to Create:**

  1. `apps/agent-engine/app/config.py` (Settings loader reading `USE_MOCK_LLM`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `MONGODB_URI`)

  2. `apps/agent-engine/app/agents/__init__.py`

  3. `apps/agent-engine/app/agents/base.py` (Helper that binds Pydantic output schemas via `.with_structured_output()` when `USE_MOCK_LLM=false`, or returns realistic, traceable multi-item fixtures when `USE_MOCK_LLM=true`)

  4. `apps/agent-engine/app/agents/req_analyst.py` (`run_requirement_analyst(state, blast_radius)`)

  5. `apps/agent-engine/app/agents/product_arch.py` (`run_product_architect(state, blast_radius)`)

  6. `apps/agent-engine/app/agents/db_arch.py` (`run_database_architect(state, blast_radius)`)

  7. `apps/agent-engine/app/agents/api_arch.py` (`run_api_architect(state, blast_radius)`)

  8. `apps/agent-engine/app/agents/validator_critic.py` (`run_validation_gate(state, gate_name)` combining Tier 1 `DeterministicLinter` + Tier 2 LLM semantic critic)

  9. `apps/agent-engine/tests/test_agents.py`

* **Unit Tests Required in `test_agents.py`:**

  * Test each agent in `USE_MOCK_LLM=true` mode to confirm its output passes Pydantic validation and satisfies Tier 1 linter rules.

  * Test selective regeneration: pass a `blast_radius` containing `{"stale_features": {"FEAT-01"}}` to `run_product_architect` and verify that `FEAT-02` remains untouched while `FEAT-01` is updated.

* **Slice 2 Verification:**
  Run `pytest apps/agent-engine/tests/test_agents.py -v` and ensure 100% of agent tests pass.

### Slice 3: LangGraph Orchestrator State Machine, Checkpoints & FastAPI Endpoints

* **Goal:** Wire the cyclic LangGraph state machine with `MAX_AUTO_RETRIES = 2` circuit breakers, `interrupt()` human checkpoints, version history storage, and FastAPI endpoints.

* **Files to Create:**

  1. `apps/agent-engine/app/orchestrator.py` (`build_orchestrator_graph`, node wrappers, `route_after_gate_1`, `route_after_gate_2`, `human_checkpoint_1_node`, `human_checkpoint_2_node`)

  2. `apps/agent-engine/app/main.py` (FastAPI server with `/health`, `POST /orchestrator/start`, `POST /orchestrator/{project_id}/resume`, `GET /orchestrator/{project_id}/state`, `GET /orchestrator/{project_id}/versions`, plus RFC 7807 exception handlers)

  3. `apps/agent-engine/tests/test_orchestrator_flow.py`

* **Integration Tests Required in `test_orchestrator_flow.py`:**

  * **Flow 1 (Happy Path):** Start project $\rightarrow$ pause at `GATE_1_REVIEW` $\rightarrow$ resume with `APPROVE` $\rightarrow$ pause at `GATE_2_REVIEW` $\rightarrow$ resume with `APPROVE` $\rightarrow$ verify `current_phase == COMPLETED` and `human_approved == True`.

  * **Flow 2 (Selective Revision & Rollback at Checkpoint 2):** Pause at `GATE_2_REVIEW` (`v1`) $\rightarrow$ resume with `action="REVISE"`, `modified_ids=["REQ-01"]`, `feedback_notes="Add 2FA requirement"` $\rightarrow$ verify version increments to `v2`, graph routes back to `requirement_analyst`, and pauses at `GATE_1_REVIEW` with updated state.

  * **Flow 3 (Auto-Retry Circuit Breaker):** Inject a deliberate blocking defect in mock mode and verify the conditional edge retries at most `MAX_AUTO_RETRIES = 2` times before escalating to the human checkpoint.

* **Slice 3 Verification:**
  Run `pytest apps/agent-engine/tests/test_orchestrator_flow.py -v` and verify end-to-end state machine workflows.

### Slice 4: Node.js + Express API Gateway & MongoDB Snapshot Persistence

* **Goal:** Build the TypeScript Express backend that manages projects, persists immutable version snapshots (`v1`, `v2`, `v3`) in MongoDB (or an in-memory fallback when running local tests without Docker), and proxies orchestration commands to FastAPI.

* **Files to Create:**

  1. `apps/api-gateway/package.json` & `tsconfig.json`

  2. `apps/api-gateway/src/config/db.ts`

  3. `apps/api-gateway/src/models/ProjectSnapshot.ts`

  4. `apps/api-gateway/src/services/pythonBridge.ts`

  5. `apps/api-gateway/src/routes/projects.ts`

  6. `apps/api-gateway/src/server.ts`

  7. `apps/api-gateway/tests/projects.test.ts`

* **Slice 4 Verification:**
  Run `npm test` and `npx tsc --noEmit` inside `apps/api-gateway/` to verify TypeScript typing and Gateway integration.

### Slice 5: React Blueprint Studio, Artifact Cards & Human Checkpoint Drawer

* **Goal:** Build the interactive React frontend for submitting ideas, inspecting the 5 architectural layers, reviewing validation defects, and approving or requesting selective revisions at Gate 1 and Gate 2.

* **Files to Create:**

  1. `apps/web/package.json`, `tsconfig.json`, `vite.config.ts`, `tailwind.config.js`

  2. `apps/web/src/types/blueprint.ts` (Exact TypeScript mirror of `ProjectBlueprintState`)

  3. `apps/web/src/api/projectsApi.ts`

  4. `apps/web/src/components/PhaseStepper.tsx`

  5. `apps/web/src/components/ArtifactTabs.tsx` (Dedicated views for Glossary & Actors, IEEE 830 Requirements, DDD Features + State Machine badges, 3NF Database Tables with PII/FK badges, and OpenAPI Endpoints with RBAC/Idempotency badges)

  6. `apps/web/src/components/ValidationBanner.tsx` (Displays RTM coverage percentage and `BLOCKING` vs `WARNING` defects)

  7. `apps/web/src/components/CheckpointDrawer.tsx` (Lets the user click any `ACT-*`, `REQ-*`, `FEAT-*`, `TBL-*`, or `EP-*` card to add it to `modified_ids`, type revision instructions, and trigger a selective rollback or click **Approve Checkpoint**)

  8. `apps/web/src/pages/ProjectWorkspace.tsx`

* **Slice 5 Verification:**
  Run `npm run build` in `apps/web/` to verify clean frontend compilation.

### Slice 6: Interactive DAG Traceability Graph (`@xyflow/react`) & Version Diff Modal

* **Goal:** Add visual software engineering observability—an interactive 4-column Directed Acyclic Graph (`REQ -> FEAT -> TBL -> EP`) with live blast-radius highlighting and a side-by-side version comparison modal (`v1` vs `v2`).

* **Files to Create:**

  1. `apps/web/src/components/TraceabilityGraph.tsx` (Uses `@xyflow/react` to render nodes across 4 columns connected by `upstream_ids`; hovering or selecting any node highlights all downstream dependent nodes in amber to preview the exact blast radius before submitting a revision)

  2. `apps/web/src/components/VersionDiffModal.tsx` (Compares any two versions `vA` and `vB`, highlighting added, modified, and preserved item IDs across layers)

  3. `docker-compose.yml` & `.env.example` at the monorepo root so the entire 4-container stack (`mongodb`, `agent-engine`, `api-gateway`, `web`) launches with a single `docker compose up --build`.

* **Slice 6 Verification:**
  Launch the complete platform with `docker compose up --build` and verify end-to-end system operation.
