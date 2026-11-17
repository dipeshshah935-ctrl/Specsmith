import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import request from "supertest";
import { app } from "../src/server.js";
import { ProjectRecord } from "../src/models/ProjectRecord.js";

describe("API Gateway - Projects Endpoints & RFC 7807 Contracts", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("GET /health", () => {
    it("returns gateway health status", async () => {
      vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "ok", mock_llm: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );

      const res = await request(app).get("/health");
      expect(res.status).toBe(200);
      expect(res.body).toEqual({
        status: "ok",
        gateway: true,
        python_engine: "ok",
      });
    });

    it("handles unreachable python engine gracefully in health check", async () => {
      vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new Error("Connection refused"));

      const res = await request(app).get("/health");
      expect(res.status).toBe(200);
      expect(res.body).toEqual({
        status: "ok",
        gateway: true,
        python_engine: "unreachable",
      });
    });
  });

  describe("GET /api/projects", () => {
    it("returns a list of projects sorted by updatedAt descending", async () => {
      const mockProjects = [
        { projectId: "proj-1", title: "Project 1", currentPhase: "DISCOVERY" },
        { projectId: "proj-2", title: "Project 2", currentPhase: "COMPLETED" },
      ];

      vi.spyOn(ProjectRecord, "find").mockReturnValue({
        sort: vi.fn().mockResolvedValue(mockProjects),
      } as any);

      const res = await request(app).get("/api/projects");
      expect(res.status).toBe(200);
      expect(res.body).toHaveLength(2);
      expect(res.body[0].projectId).toBe("proj-1");
    });
  });

  describe("POST /api/projects", () => {
    it("creates a new project and triggers python engine start", async () => {
      const pythonResponse = {
        project_id: "test-uuid-1",
        active_checkpoint: "GATE_1_REVIEW",
        state: { current_phase: "DISCOVERY", version: 1 },
        versions: [{ version: 1, blueprint: { version: 1 } }],
      };

      vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
        new Response(JSON.stringify(pythonResponse), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );

      const createdDoc = {
        projectId: "test-uuid-1",
        title: "E-Commerce Architecture",
        userInitialPrompt: "Build an e-commerce platform",
        currentPhase: "DISCOVERY",
        currentVersion: 1,
        activeCheckpoint: "GATE_1_REVIEW",
        latestState: pythonResponse.state,
        versions: pythonResponse.versions,
      };

      vi.spyOn(ProjectRecord, "create").mockResolvedValueOnce(createdDoc as any);

      const res = await request(app)
        .post("/api/projects")
        .send({
          title: "E-Commerce Architecture",
          prompt: "Build an e-commerce platform",
        });

      expect(res.status).toBe(201);
      expect(res.body.projectId).toBe("test-uuid-1");
      expect(res.body.activeCheckpoint).toBe("GATE_1_REVIEW");
    });

    it("returns RFC 7807 400 Bad Request on invalid input body", async () => {
      const res = await request(app)
        .post("/api/projects")
        .send({ title: "" });

      expect(res.status).toBe(400);
      expect(res.body.type).toBe("about:blank");
      expect(res.body.title).toBe("Validation Error");
      expect(res.body.status).toBe(400);
      expect(res.body.detail).toBeDefined();
    });

    it("returns RFC 7807 error when python engine fails", async () => {
      vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            type: "about:blank",
            title: "Conflict",
            status: 409,
            detail: "Project ID already exists",
          }),
          {
            status: 409,
            statusText: "Conflict",
            headers: { "Content-Type": "application/problem+json" },
          }
        )
      );

      const res = await request(app)
        .post("/api/projects")
        .send({
          title: "Duplicate Project",
          prompt: "Some prompt",
        });

      expect(res.status).toBe(409);
      expect(res.body.type).toBe("about:blank");
      expect(res.body.title).toBe("Conflict");
      expect(res.body.status).toBe(409);
      expect(res.body.detail).toContain("Project ID already exists");
    });
  });

  describe("GET /api/projects/:id", () => {
    it("returns project details for an existing project", async () => {
      const mockProject = {
        projectId: "proj-123",
        title: "Auth Service",
        currentPhase: "ARCHITECTURE",
        currentVersion: 1,
      };

      vi.spyOn(ProjectRecord, "findOne").mockResolvedValueOnce(mockProject as any);

      const res = await request(app).get("/api/projects/proj-123");
      expect(res.status).toBe(200);
      expect(res.body.projectId).toBe("proj-123");
      expect(res.body.title).toBe("Auth Service");
    });

    it("returns RFC 7807 404 Not Found for non-existent project", async () => {
      vi.spyOn(ProjectRecord, "findOne").mockResolvedValueOnce(null);

      const res = await request(app).get("/api/projects/unknown-proj");
      expect(res.status).toBe(404);
      expect(res.body.type).toBe("about:blank");
      expect(res.body.title).toBe("Not Found");
      expect(res.body.status).toBe(404);
      expect(res.body.detail).toContain("unknown-proj");
    });
  });

  describe("POST /api/projects/:id/review", () => {
    it("submits an APPROVE review action and updates project", async () => {
      const mockProjectDoc = {
        projectId: "proj-123",
        title: "Auth Service",
        currentPhase: "DISCOVERY",
        currentVersion: 1,
        activeCheckpoint: "GATE_1_REVIEW",
        latestState: {},
        versions: [],
        save: vi.fn().mockResolvedValue(true),
      };

      vi.spyOn(ProjectRecord, "findOne").mockResolvedValueOnce(mockProjectDoc as any);

      const pythonResumeResponse = {
        project_id: "proj-123",
        active_checkpoint: "GATE_2_REVIEW",
        state: { current_phase: "ARCHITECTURE", version: 1 },
        versions: [{ version: 1 }],
      };

      vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
        new Response(JSON.stringify(pythonResumeResponse), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );

      const res = await request(app)
        .post("/api/projects/proj-123/review")
        .send({ action: "APPROVE" });

      expect(res.status).toBe(200);
      expect(mockProjectDoc.save).toHaveBeenCalled();
      expect(mockProjectDoc.currentPhase).toBe("ARCHITECTURE");
      expect(mockProjectDoc.activeCheckpoint).toBe("GATE_2_REVIEW");
    });

    it("returns RFC 7807 400 Bad Request if action is REVISE with empty modified_ids", async () => {
      const mockProjectDoc = {
        projectId: "proj-123",
        save: vi.fn(),
      };
      vi.spyOn(ProjectRecord, "findOne").mockResolvedValueOnce(mockProjectDoc as any);

      const res = await request(app)
        .post("/api/projects/proj-123/review")
        .send({ action: "REVISE", modified_ids: [] });

      expect(res.status).toBe(400);
      expect(res.body.type).toBe("about:blank");
      expect(res.body.title).toBe("Validation Error");
      expect(res.body.detail).toContain("modified_ids must not be empty when action is REVISE");
    });

    it("returns RFC 7807 404 if project does not exist", async () => {
      vi.spyOn(ProjectRecord, "findOne").mockResolvedValueOnce(null);

      const res = await request(app)
        .post("/api/projects/missing-proj/review")
        .send({ action: "APPROVE" });

      expect(res.status).toBe(404);
      expect(res.body.type).toBe("about:blank");
      expect(res.body.title).toBe("Not Found");
      expect(res.body.status).toBe(404);
    });
  });

  describe("GET /api/projects/:id/versions", () => {
    it("returns the version history for a project", async () => {
      const mockVersions = [
        { version: 1, blueprint: { version: 1 } },
        { version: 2, blueprint: { version: 2 } },
      ];

      vi.spyOn(ProjectRecord, "findOne").mockResolvedValueOnce({
        projectId: "proj-123",
        versions: mockVersions,
      } as any);

      const res = await request(app).get("/api/projects/proj-123/versions");
      expect(res.status).toBe(200);
      expect(res.body).toHaveLength(2);
      expect(res.body[0].version).toBe(1);
      expect(res.body[1].version).toBe(2);
    });

    it("returns RFC 7807 404 if project does not exist", async () => {
      vi.spyOn(ProjectRecord, "findOne").mockResolvedValueOnce(null);

      const res = await request(app).get("/api/projects/missing-proj/versions");
      expect(res.status).toBe(404);
      expect(res.body.type).toBe("about:blank");
      expect(res.body.title).toBe("Not Found");
    });
  });
});
