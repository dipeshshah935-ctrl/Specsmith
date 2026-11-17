export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  detail: unknown;
}

export class GatewayHttpError extends Error {
  public status: number;
  public problemDetails: ProblemDetails;

  constructor(status: number, problemDetails: ProblemDetails) {
    super(typeof problemDetails.detail === "string" ? problemDetails.detail : problemDetails.title);
    this.name = "GatewayHttpError";
    this.status = status;
    this.problemDetails = problemDetails;
  }
}

export interface PythonStartResponse {
  project_id: string;
  active_checkpoint: string | null;
  state: Record<string, unknown>;
  versions: Array<Record<string, unknown>>;
}

export interface PythonResumeResponse {
  project_id: string;
  active_checkpoint: string | null;
  state: Record<string, unknown>;
  versions: Array<Record<string, unknown>>;
}

export interface PythonStateResponse {
  project_id: string;
  active_checkpoint: string | null;
  state: Record<string, unknown>;
}

export interface PythonResumeRequest {
  action: "APPROVE" | "REVISE";
  modified_ids?: string[];
  feedback_notes?: string;
  force_approve?: boolean;
}

function getBaseUrl(): string {
  return process.env.PYTHON_ENGINE_URL || "http://127.0.0.1:8000";
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${getBaseUrl()}${path}`;
  const headers = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
      signal: AbortSignal.timeout(120_000),
    });
  } catch (err: unknown) {
    const error = err as Error;
    if (error.name === "TimeoutError") {
      throw new GatewayHttpError(504, {
        type: "about:blank",
        title: "Gateway Timeout",
        status: 504,
        detail: "Python engine request timed out after 120 seconds",
      });
    }
    throw new GatewayHttpError(503, {
      type: "about:blank",
      title: "Service Unavailable",
      status: 503,
      detail: `Unable to connect to Python engine at ${getBaseUrl()}: ${error.message}`,
    });
  }

  if (!response.ok) {
    let errorBody: any;
    try {
      errorBody = await response.json();
    } catch {
      errorBody = { detail: await response.text() };
    }

    const problemDetails: ProblemDetails = {
      type: errorBody?.type ?? "about:blank",
      title: errorBody?.title ?? (response.statusText || "Python Engine Error"),
      status: response.status,
      detail: errorBody?.detail ?? errorBody?.title ?? "An error occurred in Python engine",
    };
    throw new GatewayHttpError(response.status, problemDetails);
  }

  return (await response.json()) as T;
}

export async function startOrchestrator(
  userInitialPrompt: string,
  projectId?: string
): Promise<PythonStartResponse> {
  return await request<PythonStartResponse>("/orchestrator/start", {
    method: "POST",
    body: JSON.stringify({
      user_initial_prompt: userInitialPrompt,
      project_id: projectId,
    }),
  });
}

export async function resumeOrchestrator(
  projectId: string,
  payload: PythonResumeRequest
): Promise<PythonResumeResponse> {
  return await request<PythonResumeResponse>(`/orchestrator/${projectId}/resume`, {
    method: "POST",
    body: JSON.stringify({
      action: payload.action,
      modified_ids: payload.modified_ids ?? [],
      feedback_notes: payload.feedback_notes,
      force_approve: payload.force_approve ?? false,
    }),
  });
}

export async function getOrchestratorState(projectId: string): Promise<PythonStateResponse> {
  return await request<PythonStateResponse>(`/orchestrator/${projectId}/state`, {
    method: "GET",
  });
}

export async function getOrchestratorVersions(projectId: string): Promise<Array<Record<string, unknown>>> {
  return await request<Array<Record<string, unknown>>>(`/orchestrator/${projectId}/versions`, {
    method: "GET",
  });
}

export async function checkHealth(): Promise<{ status: string; mock_llm?: boolean }> {
  return await request<{ status: string; mock_llm?: boolean }>("/health", {
    method: "GET",
  });
}

// Backward-compatibility class & instance
export class PythonBridgeService {
  startProject = startOrchestrator;
  resumeProject = resumeOrchestrator;
  getProjectState = getOrchestratorState;
  getProjectVersions = getOrchestratorVersions;
  checkHealth = checkHealth;
}

export const pythonBridge = new PythonBridgeService();
