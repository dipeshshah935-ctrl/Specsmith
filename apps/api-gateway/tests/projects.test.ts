import { describe, it, expect, vi, beforeEach, afterEach, beforeAll, afterAll } from "vitest";
import request from "supertest";
import { app } from "../src/server.js";
import { ProjectRecord } from "../src/models/ProjectRecord.js";
import { connectDatabase, disconnectDatabase } from "../src/config/db.js";

describe("API Gateway - Projects Endpoints & RFC 7807 Contracts", () => {
  const inMemoryDb = new Map<string, any>();

  beforeAll(async () => {
    if (process.env.MONGODB_TEST_URI) {
      await connectDatabase(process.env.MONGODB_TEST_URI);
    }
  });

  afterAll(async () => {
    if (process.env.MONGODB_TEST_URI) {
      await disconnectDatabase();
    }
  });

  beforeEach(() => {
    vi.restoreAllMocks();
    inMemoryDb.clear();

    if (!process.env.MONGODB_TEST_URI) {
      // Stub ProjectRecord methods with in-memory map
      vi.spyOn(ProjectRecord, "create").mockImplementation(async (doc: any) => {
        const record = {
          ...doc,
          save: vi.fn().mockImplementation(async function (this: any) {
            inMemoryDb.set(this.projectId, this);
            return this;
          }),
        };
        inMemoryDb.set(record.projectId, record);
        return record as any;
      });

      vi.spyOn(ProjectRecord, "find").mockImplementation(() => {
        return {
          sort: vi.fn().mockImplementation(async () => Array.from(inMemoryDb.values())),
        } as any;
      });

      vi.spyOn(ProjectRecord, "findOne").mockImplementation(((query: any) => {
        const id = query?.projectId;
        const item = inMemoryDb.get(id);
        if (!item) return Promise.resolve(null);
        return Promise.resolve({
          ...item,
          save: vi.fn().mockImplementation(async function (this: any) {
            inMemoryDb.set(id, this);
            return this;
          }),
        });
      }) as any);

      vi.spyOn(ProjectRecord, "findOneAndUpdate").mockImplementation(((query: any, update: any) => {
        const id = query?.projectId;
        const existing = inMemoryDb.get(id) || {};
        const updated = { ...existing, ...update };
        inMemoryDb.set(id, updated);
        return Promise.resolve(updated);
      }) as any);
    }
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
      inMemoryDb.set("proj-1", {
        projectId: "proj-1",
        title: "Project 1",
        currentPhase: "DISCOVERY",
      });
      inMemoryDb.set("proj-2", {
        projectId: "proj-2",
        title: "Project 2",
        currentPhase: "COMPLETED",
      });

      const res = await request(app).get("/api/projects");
      expect(res.status).toBe(200);
      expect(res.body).toHaveLength(2);
      expect(res.body[0].projectId).toBe("proj-1");
    });
  });

  describe("POST /api/projects", () => {
    it("creates a new project and triggers startOrchestrator with user_initial_prompt", async () => {
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

      const res = await request(app)
        .post("/api/projects")
        .send({
          title: "E-Commerce Architecture",
          user_initial_prompt: "Build an e-commerce platform",
        });

      expect(res.status).toBe(201);
      expect(res.body.projectId).toBe("test-uuid-1");
      expect(res.body.title).toBe("E-Commerce Architecture");
      expect(res.body.activeCheckpoint).toBe("GATE_1_REVIEW");
      expect(inMemoryDb.has("test-uuid-1")).toBe(true);
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

    it("returns RFC 7807 error when python engine returns !res.ok", async () => {
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
          user_initial_prompt: "Some prompt",
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
      inMemoryDb.set("proj-123", {
        projectId: "proj-123",
        title: "Auth Service",
        currentPhase: "ARCHITECTURE",
        currentVersion: 1,
      });

      const res = await request(app).get("/api/projects/proj-123");
      expect(res.status).toBe(200);
      expect(res.body.projectId).toBe("proj-123");
      expect(res.body.title).toBe("Auth Service");
    });

    it("returns RFC 7807 404 Not Found for non-existent project", async () => {
      const res = await request(app).get("/api/projects/unknown-proj");
      expect(res.status).toBe(404);
      expect(res.body.type).toBe("about:blank");
      expect(res.body.title).toBe("Not Found");
      expect(res.body.status).toBe(404);
      expect(res.body.detail).toContain("unknown-proj");
    });
  });

  describe("POST /api/projects/:id/review", () => {
    it("submits an APPROVE review action and updates project in MongoDB", async () => {
      inMemoryDb.set("proj-123", {
        projectId: "proj-123",
        title: "Auth Service",
        currentPhase: "DISCOVERY",
        currentVersion: 1,
        activeCheckpoint: "GATE_1_REVIEW",
        latestState: {},
        versions: [],
      });

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
      const updated = inMemoryDb.get("proj-123");
      expect(updated.currentPhase).toBe("ARCHITECTURE");
      expect(updated.activeCheckpoint).toBe("GATE_2_REVIEW");
    });

    it("returns RFC 7807 400 Bad Request if action is REVISE with empty modified_ids", async () => {
      inMemoryDb.set("proj-123", {
        projectId: "proj-123",
        title: "Auth Service",
      });

      const res = await request(app)
        .post("/api/projects/proj-123/review")
        .send({ action: "REVISE", modified_ids: [] });

      expect(res.status).toBe(400);
      expect(res.body.type).toBe("about:blank");
      expect(res.body.title).toBe("Validation Error");
      expect(res.body.detail).toContain("modified_ids must not be empty when action is REVISE");
    });

    it("returns RFC 7807 404 if project does not exist", async () => {
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
      inMemoryDb.set("proj-123", {
        projectId: "proj-123",
        versions: [
          { version: 1, blueprint: { version: 1 } },
          { version: 2, blueprint: { version: 2 } },
        ],
      });

      const res = await request(app).get("/api/projects/proj-123/versions");
      expect(res.status).toBe(200);
      expect(res.body).toHaveLength(2);
      expect(res.body[0].version).toBe(1);
      expect(res.body[1].version).toBe(2);
    });

    it("returns RFC 7807 404 if project does not exist", async () => {
      const res = await request(app).get("/api/projects/missing-proj/versions");
      expect(res.status).toBe(404);
      expect(res.body.type).toBe("about:blank");
      expect(res.body.title).toBe("Not Found");
    });
  });
});
