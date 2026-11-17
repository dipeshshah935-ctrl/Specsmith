import pytest
from fastapi.testclient import TestClient

import app.orchestrator as orch_module
from app.main import app, get_graph


@pytest.fixture
def client():
    """TestClient fixture with mock LLM enabled."""
    return TestClient(app)


class TestOrchestratorFlow:
    def test_full_happy_path_start_to_completion(self, client):
        """Test full happy path: Start -> Checkpoint 1 (APPROVE) -> Checkpoint 2 (APPROVE) -> COMPLETED."""
        # 1. Start project -> advances to Checkpoint 1
        start_payload = {
            "user_initial_prompt": "Build an enterprise cloud project management platform."
        }
        res_start = client.post("/orchestrator/start", json=start_payload)
        assert res_start.status_code == 201, res_start.text
        start_data = res_start.json()
        pid = start_data["project_id"]
        assert start_data["active_checkpoint"] == "GATE_1_REVIEW"
        assert start_data["state"]["version"] == 1
        assert len(start_data["state"]["requirements"]) >= 2
        assert len(start_data["state"]["features"]) >= 2
        assert len(start_data["state"]["database_entities"]) == 0
        assert len(start_data["state"]["endpoints"]) == 0

        # 2. Approve Checkpoint 1 -> advances through Architecture to Checkpoint 2
        res_cp2 = client.post(
            f"/orchestrator/{pid}/resume",
            json={"action": "APPROVE"},
        )
        assert res_cp2.status_code == 200, res_cp2.text
        cp2_data = res_cp2.json()
        assert cp2_data["active_checkpoint"] == "GATE_2_REVIEW"
        assert cp2_data["state"]["current_phase"] == "GATE_2_REVIEW"
        assert len(cp2_data["state"]["database_entities"]) >= 2
        assert len(cp2_data["state"]["endpoints"]) >= 4

        # 3. Approve Checkpoint 2 -> completes the workflow
        res_done = client.post(
            f"/orchestrator/{pid}/resume",
            json={"action": "APPROVE"},
        )
        assert res_done.status_code == 200, res_done.text
        done_data = res_done.json()
        assert done_data["active_checkpoint"] is None
        assert done_data["state"]["current_phase"] == "COMPLETED"
        assert done_data["state"]["human_approved"] is True

        # 4. Verify state and versions endpoints
        res_state = client.get(f"/orchestrator/{pid}/state")
        assert res_state.status_code == 200
        assert res_state.json()["state"]["current_phase"] == "COMPLETED"

        res_versions = client.get(f"/orchestrator/{pid}/versions")
        assert res_versions.status_code == 200
        assert len(res_versions.json()) >= 1

    def test_checkpoint_2_cross_phase_revision_to_req_analyst(self, client):
        """Run to GATE_2_REVIEW (v1) -> REVISE REQ-01 -> increments to v2, loops back to GATE_1_REVIEW,

        reflects feedback on REQ-01 while REQ-02 is preserved, and /versions returns both v1 and v2.
        """
        # 1. Advance to Checkpoint 2 (v1)
        res_start = client.post(
            "/orchestrator/start",
            json={"user_initial_prompt": "Build a zero-trust identity and access management system."},
        )
        pid = res_start.json()["project_id"]

        res_cp2 = client.post(f"/orchestrator/{pid}/resume", json={"action": "APPROVE"})
        assert res_cp2.json()["active_checkpoint"] == "GATE_2_REVIEW"
        assert res_cp2.json()["state"]["version"] == 1

        # 2. Request revision on REQ-01 at Checkpoint 2
        feedback = "Require hardware MFA token verification"
        res_rev = client.post(
            f"/orchestrator/{pid}/resume",
            json={
                "action": "REVISE",
                "modified_ids": ["REQ-01"],
                "feedback_notes": feedback,
            },
        )
        assert res_rev.status_code == 200, res_rev.text
        rev_data = res_rev.json()

        # 3. Verify version incremented to 2 and graph routed back to Discovery Checkpoint 1
        assert rev_data["active_checkpoint"] == "GATE_1_REVIEW"
        assert rev_data["state"]["version"] == 2

        reqs = rev_data["state"]["requirements"]
        req01 = next(r for r in reqs if r["id"] == "REQ-01")
        req02 = next(r for r in reqs if r["id"] == "REQ-02")
        assert f"[Revised: {feedback}]" in req01["description"]
        assert f"[Revised: {feedback}]" not in req02["description"]

        # 4. Verify /versions returns both v1 and v2 snapshots
        res_versions = client.get(f"/orchestrator/{pid}/versions")
        assert res_versions.status_code == 200
        versions = res_versions.json()
        assert len(versions) == 2
        assert versions[0]["version"] == 1
        assert versions[1]["version"] == 2

    def test_auto_retry_circuit_breaker_halts_at_max_2(self, client, monkeypatch):
        """Monkeypatch product_architect to produce an orphan requirement defect,

        verify gate_1_retries halts at MAX_AUTO_RETRIES == 2 and escalates to GATE_1_REVIEW without infinite looping.
        """
        orig_prod = orch_module.run_product_architect

        def failing_product_architect(state, *args, **kwargs):
            # Produce state with empty features, leaving MUST_HAVE REQ-01 orphaned
            s = orig_prod(state, *args, **kwargs)
            s.features = []
            return s

        monkeypatch.setattr(orch_module, "run_product_architect", failing_product_architect)

        res = client.post(
            "/orchestrator/start",
            json={"user_initial_prompt": "Build an e-commerce platform with automated refunds."},
        )
        assert res.status_code == 201, res.text
        data = res.json()
        pid = data["project_id"]

        # Verify it halted and escalated to human checkpoint 1
        assert data["active_checkpoint"] == "GATE_1_REVIEW"

        # Verify graph state retries counter stopped at MAX_AUTO_RETRIES == 2
        config = {"configurable": {"thread_id": pid}}
        graph_state = get_graph().get_state(config)
        assert graph_state.values.get("gate_1_retries") == 2

    def test_rfc7807_error_contracts(self, client):
        """Verify RFC 7807 problem details error responses: 400 Bad Request, 404 Not Found, 409 Conflict."""
        # 1. 404 on unknown project_id
        res_404 = client.get("/orchestrator/unknown-non-existent-id/state")
        assert res_404.status_code == 404
        err_404 = res_404.json()
        assert err_404["type"] == "about:blank"
        assert err_404["status"] == 404
        assert "not found" in err_404["detail"].lower()

        # 2. 400 on REVISE with empty modified_ids
        res_start = client.post(
            "/orchestrator/start",
            json={"user_initial_prompt": "Build an analytics dashboard."},
        )
        pid = res_start.json()["project_id"]

        res_400 = client.post(
            f"/orchestrator/{pid}/resume",
            json={"action": "REVISE", "modified_ids": []},
        )
        assert res_400.status_code == 400
        err_400 = res_400.json()
        assert err_400["type"] == "about:blank"
        assert err_400["status"] == 400
        assert "modified_ids cannot be empty" in err_400["detail"]

        # 3. 409 Conflict when attempting to resume an already COMPLETED project
        client.post(f"/orchestrator/{pid}/resume", json={"action": "APPROVE"})
        client.post(f"/orchestrator/{pid}/resume", json={"action": "APPROVE"})

        res_409 = client.post(
            f"/orchestrator/{pid}/resume",
            json={"action": "APPROVE"},
        )
        assert res_409.status_code == 409
        err_409 = res_409.json()
        assert err_409["type"] == "about:blank"
        assert err_409["status"] == 409
        assert "already COMPLETED" in err_409["detail"]
