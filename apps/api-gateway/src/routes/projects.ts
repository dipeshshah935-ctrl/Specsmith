import { Router, Request, Response, NextFunction } from "express";
import { z } from "zod";
import { ProjectRecord } from "../models/ProjectRecord.js";
import { pythonBridge, GatewayHttpError } from "../services/pythonBridge.js";

export const projectsRouter = Router();

const createProjectSchema = z
  .object({
    title: z.string().trim().min(1, "Title is required"),
    prompt: z.string().trim().min(1, "Prompt is required").optional(),
    userInitialPrompt: z.string().trim().min(1, "User initial prompt is required").optional(),
    projectId: z.string().trim().min(1).optional(),
  })
  .refine((data) => Boolean(data.prompt || data.userInitialPrompt), {
    message: "Either prompt or userInitialPrompt must be provided",
    path: ["prompt"],
  });

const reviewProjectSchema = z
  .object({
    action: z.enum(["APPROVE", "REVISE"]),
    modified_ids: z.array(z.string()).default([]),
    feedback_notes: z.string().optional(),
    force_approve: z.boolean().default(false),
  })
  .refine(
    (data) => {
      if (data.action === "REVISE") {
        return data.modified_ids.length > 0;
      }
      return true;
    },
    {
      message: "modified_ids must not be empty when action is REVISE",
      path: ["modified_ids"],
    }
  );

// GET /api/projects - list all projects
projectsRouter.get("/", async (_req: Request, res: Response, next: NextFunction) => {
  try {
    const projects = await ProjectRecord.find().sort({ updatedAt: -1 });
    res.json(projects);
  } catch (error) {
    next(error);
  }
});

// POST /api/projects - initialize project with Python engine
projectsRouter.post("/", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const parsed = createProjectSchema.safeParse(req.body);
    if (!parsed.success) {
      return res.status(400).json({
        type: "about:blank",
        title: "Validation Error",
        status: 400,
        detail: parsed.error.issues.map((i) => i.message).join(", "),
      });
    }

    const { title, projectId } = parsed.data;
    const prompt = (parsed.data.prompt || parsed.data.userInitialPrompt) as string;

    const pythonResult = await pythonBridge.startProject(prompt, projectId);

    const project = await ProjectRecord.create({
      projectId: pythonResult.project_id,
      title,
      userInitialPrompt: prompt,
      currentPhase: pythonResult.state?.current_phase ?? "DISCOVERY",
      currentVersion: pythonResult.state?.version ?? 1,
      activeCheckpoint: pythonResult.active_checkpoint,
      latestState: pythonResult.state,
      versions: pythonResult.versions ?? [],
    });

    return res.status(201).json(project);
  } catch (error) {
    next(error);
  }
});

// GET /api/projects/:id - get single project
projectsRouter.get("/:id", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const project = await ProjectRecord.findOne({ projectId: req.params.id });
    if (!project) {
      return res.status(404).json({
        type: "about:blank",
        title: "Not Found",
        status: 404,
        detail: `Project with ID '${req.params.id}' was not found`,
      });
    }
    return res.json(project);
  } catch (error) {
    next(error);
  }
});

// POST /api/projects/:id/review - submit review action to Python engine
projectsRouter.post("/:id/review", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const project = await ProjectRecord.findOne({ projectId: req.params.id });
    if (!project) {
      return res.status(404).json({
        type: "about:blank",
        title: "Not Found",
        status: 404,
        detail: `Project with ID '${req.params.id}' was not found`,
      });
    }

    const parsed = reviewProjectSchema.safeParse(req.body);
    if (!parsed.success) {
      return res.status(400).json({
        type: "about:blank",
        title: "Validation Error",
        status: 400,
        detail: parsed.error.issues.map((i) => i.message).join(", "),
      });
    }

    const pythonResult = await pythonBridge.resumeProject(req.params.id, parsed.data);

    project.latestState = pythonResult.state;
    project.currentPhase = (pythonResult.state?.current_phase as string) ?? project.currentPhase;
    project.currentVersion = (pythonResult.state?.version as number) ?? project.currentVersion;
    project.activeCheckpoint = pythonResult.active_checkpoint;
    project.versions = pythonResult.versions ?? project.versions;

    await project.save();

    return res.json(project);
  } catch (error) {
    next(error);
  }
});

// GET /api/projects/:id/versions - get snapshots for project
projectsRouter.get("/:id/versions", async (req: Request, res: Response, next: NextFunction) => {
  try {
    const project = await ProjectRecord.findOne({ projectId: req.params.id });
    if (!project) {
      return res.status(404).json({
        type: "about:blank",
        title: "Not Found",
        status: 404,
        detail: `Project with ID '${req.params.id}' was not found`,
      });
    }
    return res.json(project.versions ?? []);
  } catch (error) {
    next(error);
  }
});
