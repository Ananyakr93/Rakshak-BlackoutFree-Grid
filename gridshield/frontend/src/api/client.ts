import type {
  BuildingSnapshot,
  RunEvent,
  RunMetric,
  RunRecord,
  RunSnapshot,
  SavedExperimentResults,
  ScenarioConfig,
  ScenarioTemplate,
  TelemetrySample,
  NilmEstimate,
  RunIntegrations,
  EdgeAgentSnapshot,
  FeederEstimate,
  LiveComparisonResponse,
  NilmEvaluation,
  NilmSignalSample,
  RestorationSnapshot,
} from "../types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ??
  `${window.location.protocol}//${window.location.hostname}:8080`;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch (error) {
    throw new ApiError(
      error instanceof Error ? error.message : "The backend could not be reached",
      0,
    );
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as {
        detail?: unknown;
        error?: { message?: unknown };
      };
      if (typeof body.error?.message === "string") {
        detail = body.error.message;
      } else if (typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // The response body may not be JSON; preserve the HTTP status message.
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}

export const getHealth = () => request<{ status: string; version: string }>("/health");

export const getScenarioTemplates = () =>
  request<ScenarioTemplate[]>("/api/v1/scenarios/templates");

export const createScenario = (config: ScenarioConfig) =>
  request<{ scenario_id: string; name: string }>("/api/v1/scenarios", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });

export const startRun = (scenarioId: string, policy: string, seed: number) =>
  startConfiguredRun(scenarioId, policy, seed);

export interface RunOptions {
  playback_speed?: number;
  hil_port?: string;
  hil_building_id?: string;
}

export const startConfiguredRun = (
  scenarioId: string,
  policy: string,
  seed: number,
  options: RunOptions = {},
) =>
  request<{ run_id: string; status: string; policy: string }>("/api/v1/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario_id: scenarioId, policy, seed, ...options }),
  });

export const compareControlModes = (
  scenario: ScenarioConfig,
  nSeeds: number,
) =>
  request<LiveComparisonResponse>("/api/v1/experiments/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario, n_seeds: nSeeds }),
  });

const controlRun = (runId: string, action: "pause" | "resume") =>
  request<{ run_id: string; status: string }>(`/api/v1/runs/${runId}/${action}`, {
    method: "POST",
  });

export const pauseRun = (runId: string) => controlRun(runId, "pause");
export const resumeRun = (runId: string) => controlRun(runId, "resume");

export const setRunSpeed = (runId: string, playbackSpeed: number) =>
  request<{ run_id: string; playback_speed: number }>(`/api/v1/runs/${runId}/speed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ playback_speed: playbackSpeed }),
  });

export const stopRun = (runId: string) =>
  request<{ run_id: string; message: string }>(`/api/v1/runs/${runId}/stop`, {
    method: "POST",
  });

export const getRun = (runId: string) =>
  request<RunSnapshot>(`/api/v1/runs/${runId}`);

export const getRunHistory = () => request<RunRecord[]>("/api/v1/runs");

export const getRunBuildings = (runId: string) =>
  request<BuildingSnapshot[]>(`/api/v1/runs/${runId}/buildings`);

export const getRunEvents = (runId: string) =>
  request<RunEvent[]>(`/api/v1/runs/${runId}/events`);

export const getRunIntegrations = (runId: string) =>
  request<RunIntegrations>(`/api/v1/runs/${runId}/integrations`);

export const getRunNilm = (runId: string) =>
  request<NilmEstimate[]>(`/api/v1/runs/${runId}/nilm`);

export const getRunNilmSignal = (runId: string, buildingId?: string | null) => {
  const query = buildingId ? `?building_id=${encodeURIComponent(buildingId)}` : "";
  return request<NilmSignalSample[]>(`/api/v1/runs/${runId}/nilm/signal${query}`);
};

export const getRunNilmEvaluation = (runId: string) =>
  request<NilmEvaluation>(`/api/v1/runs/${runId}/nilm/evaluation`);

export const getRunAgents = (runId: string) =>
  request<EdgeAgentSnapshot[]>(`/api/v1/runs/${runId}/agents`);

export const getRunRestoration = (runId: string) =>
  request<RestorationSnapshot>(`/api/v1/runs/${runId}/restoration`);

export const getRunFeeder = (runId: string) =>
  request<FeederEstimate>(`/api/v1/runs/${runId}/feeder`);

export const getRunMetrics = (runId: string) =>
  request<RunMetric[]>(`/api/v1/runs/${runId}/metrics`);

export const getRunTelemetry = (runId: string, downsample = 1) =>
  request<TelemetrySample[]>(`/api/v1/runs/${runId}/telemetry?downsample=${downsample}`);

export const getSavedExperiment = () =>
  request<SavedExperimentResults>("/api/v1/experiments/baseline");

export function getRunStreamUrl(runId: string, afterSequence = 0): string {
  const url = new URL(`${API_BASE_URL}/api/v1/runs/${runId}/stream`);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("after_sequence", String(afterSequence));
  return url.toString();
}
