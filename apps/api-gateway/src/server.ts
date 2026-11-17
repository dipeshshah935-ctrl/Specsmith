import express, { Request, Response, NextFunction } from "express";
import cors from "cors";
import { projectsRouter } from "./routes/projects.js";
import { GatewayHttpError, checkHealth } from "./services/pythonBridge.js";

export const app = express();

app.use(
  cors({
    origin: process.env.ALLOWED_ORIGINS
      ? process.env.ALLOWED_ORIGINS.split(",")
      : ["http://localhost:5173", "http://localhost:4000"],
    credentials: true,
  })
);

app.use(express.json({ limit: "10mb" }));

// Health check endpoint
app.get("/health", async (_req: Request, res: Response) => {
  let pythonEngineStatus = "unavailable";
  try {
    const health = await checkHealth();
    pythonEngineStatus = health.status ?? "ok";
  } catch {
    pythonEngineStatus = "unreachable";
  }

  res.json({
    status: "ok",
    gateway: true,
    python_engine: pythonEngineStatus,
  });
});

// Project endpoints
app.use("/api/projects", projectsRouter);

// RFC 7807 Error Handling Middleware
app.use((err: unknown, _req: Request, res: Response, _next: NextFunction) => {
  res.setHeader("Content-Type", "application/problem+json");

  if (err instanceof GatewayHttpError) {
    return res.status(err.status).json(err.problemDetails);
  }

  const error = err as Error;
  const status = (err as any)?.status || 500;
  return res.status(status).json({
    type: "about:blank",
    title: (err as any)?.title || "Internal Server Error",
    status,
    detail: error.message || "An unexpected error occurred",
  });
});
