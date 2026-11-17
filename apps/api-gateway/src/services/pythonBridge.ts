export class GatewayHttpError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
    public title: string = "Gateway Error"
  ) {
    super(typeof detail === "string" ? detail : title);
    this.name = "GatewayHttpError";
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

export class PythonBridgeService {
  private baseUrl: string;

  constructor(baseUrl?: string) {
    this.baseUrl = baseUrl ?? process.env.PYTHON_ENGINE_URL ?? "http://localhost:8000";
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${path}`;
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
        throw new GatewayHttpError(504, "Python engine request timed out after 120 seconds", "Gateway Timeout");
      }
      throw new GatewayHttpError(
        503,
        `Unable to connect to Python engine at ${this.baseUrl}: ${error.message}`,
        "Service Unavailable"
      );
    }

    if (!response.ok) {
      let errorBody: any;
      try {
        errorBody = await response.json();
      } catch {
        errorBody = { detail: await response.text() };
      }

      const detail = errorBody?.detail ?? errorBody?.title ?? response.statusText;
      const title = errorBody?.title ?? "Python Engine Error";
      throw new GatewayHttpError(response.status, detail, title);
    }

    return (await response.json()) as T;
  }

  async startProject(userInitialPrompt: string, projectId?: string): Promise<PythonStartResponse> {
    return await this.request<PythonStartResponse>("/orchestrator/start", {
      method: "POST",
      body: JSON.stringify({
        user_initial_prompt: userInitialPrompt,
        project_id: projectId,
      }),
    });
  }

  async resumeProject(projectId: string, payload: PythonResumeRequest): Promise<PythonResumeResponse> {
    return await this.request<PythonResumeResponse>(`/orchestrator/${projectId}/resume`, {
      method: "POST",
      body: JSON.stringify({
        action: payload.action,
        modified_ids: payload.modified_ids ?? [],
        feedback_notes: payload.feedback_notes,
        force_approve: payload.force_approve ?? false,
      }),
    });
  }

  async getProjectState(projectId: string): Promise<PythonStateResponse> {
    return await this.request<PythonStateResponse>(`/orchestrator/${projectId}/state`, {
      method: "GET",
    });
  }

  async getProjectVersions(projectId: string): Promise<Array<Record<string, unknown>>> {
    return await this.request<Array<Record<string, unknown>>>(`/orchestrator/${projectId}/versions`, {
      method: "GET",
    });
  }

  async checkHealth(): Promise<{ status: string; mock_llm?: boolean }> {
    return await this.request<{ status: string; mock_llm?: boolean }>("/health", {
      method: "GET",
    });
  }
}

export const pythonBridge = new PythonBridgeService();
