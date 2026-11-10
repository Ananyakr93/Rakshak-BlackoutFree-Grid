import { useCallback, useEffect, useMemo, useRef, useState, type ReactElement } from "react";
import {
  ApiError,
  compareControlModes,
  createScenario,
  getHealth,
  getRun,
  getRunBuildings,
  getRunAgents,
  getRunEvents,
  getRunFeeder,
  getRunHistory,
  getRunIntegrations,
  getRunMetrics,
  getRunNilm,
  getRunNilmEvaluation,
  getRunNilmSignal,
  getRunRestoration,
  getRunStreamUrl,
  getRunTelemetry,
  getSavedExperiment,
  getScenarioTemplates,
  pauseRun,
  resumeRun,
  setRunSpeed,
  startConfiguredRun,
  stopRun,
} from "./api/client";
import CityTwin, {
  liveBuildings,
  scenarioBuildings,
  type CityBuilding,
} from "./components/CityTwin";
import FrequencyChart from "./components/FrequencyChart";
import DiagnosticsView from "./components/DiagnosticsView";
import { getBuildingStatus } from "./scene/buildings";
import { mergeBuildingStateUpdate } from "./scene/buildingUpdates";
import type {
  BuildingSnapshot,
  BuildingStateUpdate,
  EdgeMode,
  PolicyId,
  RunEvent,
  RunMetric,
  RunRecord,
  RunStatus,
  SavedExperimentResults,
  SavedPolicySummary,
  LiveComparisonSummary,
  EdgeAgentSnapshot,
  FeederEstimate,
  NilmEvaluation,
  NilmSignalSample,
  RestorationSnapshot,
  NilmEstimate,
  RunIntegrations,
  ScenarioConfig,
  ScenarioTemplate,
  TelemetrySample,
} from "./types";
import { withScenarioTuning } from "./scenarioTuning";

type ViewTab = "operations" | "systems" | "results";
type EventFilter = "all" | "shed" | "restore" | "fault";
type MobilePanel = "controls" | "stats" | "charts" | "building" | "log";

const POLICY_OPTIONS: Array<{ value: PolicyId; label: string; detail: string }> = [
  { value: "P0_unmanaged", label: "Unmanaged · no protection", detail: "No demand-side action; a blackout is not forced" },
  { value: "P1_adms_feeder", label: "Feeder UFLS", detail: "Emulated feeder-stage trip; may disconnect critical loads" },
  { value: "P2_priority_edge", label: "Priority DR · Staggered", detail: "Sheds deferrable loads first; essential lights stay on unless the lower S3 stage is reached. Restoration is stability-gated and staggered." },
  { value: "P2_priority_edge_synchronized", label: "Priority DR · Synchronized", detail: "Priority-aware protection with combined-pickup-gated batch restoration" },
  { value: "P3_priority_edge_no_restoration", label: "Priority edge · no restoration (advanced)", detail: "Priority-aware shedding; restoration disabled" },
];

const POLICY_ORDER: PolicyId[] = [
  "P0_unmanaged",
  "P1_adms_feeder",
  "P2_priority_edge",
  "P2_priority_edge_synchronized",
];
const SAVED_POLICY_ORDER: PolicyId[] = [
  "P0_unmanaged",
  "P1_adms_feeder",
  "P2_priority_edge",
  "P2_priority_edge_synchronized",
  "P3_priority_edge_no_restoration",
];

function isTerminal(status: RunStatus | "idle" | "starting"): boolean {
  return status === "completed" || status === "failed";
}

function isBuildingStateUpdate(value: unknown): value is BuildingStateUpdate {
  const states = [
    "ON",
    "RUNNING",
    "OFF",
    "SHED",
    "WAITING_RESTORATION",
    "LOCKED_OUT",
    "UNAVAILABLE",
  ];
  return (
    isRecord(value) &&
    value.type === "building_state_update" &&
    value.schema_version === "1.0" &&
    typeof value.run_id === "string" &&
    typeof value.building_id === "string" &&
    typeof value.appliance_id === "string" &&
    typeof value.appliance_type === "string" &&
    ["critical", "essential", "deferrable"].includes(String(value.priority)) &&
    states.includes(String(value.previous_state)) &&
    states.includes(String(value.current_state)) &&
    typeof value.current_power_kw === "number" &&
    Number.isFinite(value.current_power_kw) &&
    value.current_power_kw >= 0 &&
    typeof value.rated_power_kw === "number" &&
    Number.isFinite(value.rated_power_kw) &&
    value.rated_power_kw > 0 &&
    typeof value.simulation_time_s === "number" &&
    Number.isFinite(value.simulation_time_s) &&
    value.simulation_time_s >= 0 &&
    typeof value.sequence_number === "number" &&
    Number.isInteger(value.sequence_number) &&
    value.sequence_number >= 1 &&
    typeof value.updated_at === "string"
  );
}

function isBuildingSnapshot(value: unknown): value is BuildingSnapshot {
  return (
    isRecord(value) &&
    typeof value.run_id === "string" &&
    typeof value.building_id === "string" &&
    typeof value.weight_k === "number" &&
    Number.isFinite(value.weight_k) &&
    typeof value.demand_kw === "number" &&
    Number.isFinite(value.demand_kw) &&
    typeof value.simulation_time_s === "number" &&
    Number.isFinite(value.simulation_time_s) &&
    typeof value.sequence_number === "number" &&
    Number.isInteger(value.sequence_number) &&
    (typeof value.updated_at === "string" || value.updated_at === null) &&
    Array.isArray(value.appliances) &&
    value.appliances.every((appliance) =>
      isRecord(appliance) &&
      typeof appliance.appliance_id === "string" &&
      typeof appliance.appliance_type === "string" &&
      ["critical", "essential", "deferrable"].includes(String(appliance.priority)) &&
      [
        "ON",
        "RUNNING",
        "OFF",
        "SHED",
        "WAITING_RESTORATION",
        "LOCKED_OUT",
        "UNAVAILABLE",
      ].includes(String(appliance.state)) &&
      typeof appliance.rated_power_kw === "number" &&
      Number.isFinite(appliance.rated_power_kw) &&
      typeof appliance.current_power_kw === "number" &&
      Number.isFinite(appliance.current_power_kw)
    )
  );
}

interface PolicyComparisonResult {
  policy: PolicyId;
  telemetry: TelemetrySample[];
  summary: LiveComparisonSummary;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isTelemetrySample(value: unknown): value is TelemetrySample {
  return (
    isRecord(value) &&
    typeof value.run_id === "string" &&
    typeof value.simulation_time_s === "number" &&
    Number.isFinite(value.simulation_time_s) &&
    typeof value.frequency_hz === "number" &&
    Number.isFinite(value.frequency_hz) &&
    typeof value.generation_pu === "number" &&
    Number.isFinite(value.generation_pu) &&
    typeof value.demand_pu === "number" &&
    Number.isFinite(value.demand_pu) &&
    (value.generation_disturbance_pu === undefined ||
      typeof value.generation_disturbance_pu === "number") &&
    (value.demand_disturbance_pu === undefined ||
      typeof value.demand_disturbance_pu === "number") &&
    typeof value.frequency_stage === "string" &&
    typeof value.rocof_hz_per_s === "number" &&
    Number.isFinite(value.rocof_hz_per_s) &&
    typeof value.sequence_number === "number" &&
    Number.isInteger(value.sequence_number)
  );
}

function isRunEvent(value: unknown): value is RunEvent {
  return (
    isRecord(value) &&
    value.type === "control_event" &&
    typeof value.run_id === "string" &&
    typeof value.event_id === "string" &&
    typeof value.simulation_time_s === "number" &&
    typeof value.event_type === "string" &&
    typeof value.building_id === "string" &&
    (typeof value.appliance_id === "string" || value.appliance_id === null) &&
    typeof value.reason === "string" &&
    typeof value.frequency_hz === "number" &&
    (typeof value.priority === "string" || value.priority === null)
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "An unexpected error occurred";
}

function formatHz(value: number | null): string {
  return value === null ? "Not available" : `${value.toFixed(3)} Hz`;
}

function formatMetric(value: number | null, unit: string, digits = 2): string {
  return value === null ? "Not available" : `${value.toFixed(digits)} ${unit}`.trim();
}

function formatDuration(value: number | null): string {
  if (value === null) return "Not available";
  const totalSeconds = Math.round(value);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

function statusLabel(status: RunStatus | "idle" | "starting"): string {
  return status.replace(/_/g, " ");
}

function policyLabel(policy: string): string {
  return POLICY_OPTIONS.find((option) => option.value === policy)?.label ?? policy;
}

function eventTone(event: RunEvent): string {
  if (/fault|trip/i.test(event.event_type)) return "critical";
  if (/shed/i.test(event.event_type)) return "warning";
  if (/restore/i.test(event.event_type)) return "restored";
  return "neutral";
}

function eventMatchesFilter(event: RunEvent, filter: EventFilter): boolean {
  if (filter === "all") return true;
  if (filter === "shed") return /shed/i.test(event.event_type);
  if (filter === "restore") return /restore/i.test(event.event_type);
  return /fault|trip/i.test(event.event_type);
}

function eventTitle(event: RunEvent): string {
  return event.event_type.replace(/_/g, " ");
}

function getMetric(metrics: RunMetric[], name: string): number | null {
  const value = metrics.find((metric) => metric.metric_name === name)?.metric_value;
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

interface EventTimelineProps {
  events: RunEvent[];
  filter: EventFilter;
  onFilterChange: (filter: EventFilter) => void;
}

function EventTimeline({ events, filter, onFilterChange }: EventTimelineProps): ReactElement {
  const [page, setPage] = useState(0);
  const filteredEvents = events.filter((event) => eventMatchesFilter(event, filter));
  const orderedEvents = filteredEvents
    .slice()
    .sort((a, b) => a.simulation_time_s - b.simulation_time_s);
  const pageSize = 8;
  const pageCount = Math.max(1, Math.ceil(orderedEvents.length / pageSize));
  const pageEvents = orderedEvents.slice(
    Math.max(0, pageCount - page - 1) * pageSize,
    Math.max(0, pageCount - page) * pageSize,
  );
  useEffect(() => setPage(0), [filter]);

  return (
    <details className="floating-panel log-panel" open>
      <summary className="panel-summary">
        <strong>Event log</strong>
        <span>{events.length} entries</span>
      </summary>
      <div className="log-controls">
        <select
          aria-label="Filter events"
          className="compact-select"
          value={filter}
          onChange={(event) => onFilterChange(event.target.value as EventFilter)}
        >
          <option value="all">All events</option>
          <option value="shed">Shedding</option>
          <option value="restore">Restoration</option>
          <option value="fault">Trips / faults</option>
        </select>
      </div>
      {filteredEvents.length > 0 ? (
        <ol className="event-list">
          {pageEvents.map((event) => (
              <li className="event-item" key={event.event_id}>
                <span className={`event-marker ${eventTone(event)}`} />
                <div className="event-copy">
                  <div className="event-topline">
                    <strong>{eventTitle(event)}</strong>
                    <time>t={event.simulation_time_s.toFixed(1)}s</time>
                  </div>
                  <span>
                    {event.building_id}
                    {event.appliance_id ? ` / ${event.appliance_id}` : ""}
                    {event.priority ? ` / ${event.priority}` : ""}
                  </span>
                  <small className="event-reason" title={event.reason}>{event.reason}</small>
                </div>
              </li>
            ))}
        </ol>
      ) : (
        <div className="empty-note">
          {events.length === 0 ? "No events in this run yet." : "No events match this filter."}
        </div>
      )}
      {pageCount > 1 ? (
        <div className="event-pagination">
          <button
            className="quiet-button"
            disabled={page >= pageCount - 1}
            onClick={() => setPage((current) => Math.min(pageCount - 1, current + 1))}
            type="button"
          >
            Older
          </button>
          <span>Page {pageCount - page} of {pageCount}</span>
          <button
            className="quiet-button"
            disabled={page === 0}
            onClick={() => setPage((current) => Math.max(0, current - 1))}
            type="button"
          >
            Newer
          </button>
        </div>
      ) : null}
    </details>
  );
}

interface BuildingInspectorProps {
  building: CityBuilding | null;
  nilmEstimates: NilmEstimate[];
  events: RunEvent[];
}

function BuildingInspector({ building, nilmEstimates, events }: BuildingInspectorProps): ReactElement {
  if (!building) {
    return (
      <details className="floating-panel building-panel" open>
        <summary className="panel-summary"><strong>Building</strong><span>Choose an asset</span></summary>
        <div className="empty-note">Select a modeled building to inspect its appliance inventory.</div>
      </details>
    );
  }

  const criticalLoadUnavailable = building.appliances.some(
    (appliance) => appliance.priority === "critical" &&
      appliance.state !== "ON" && appliance.state !== "RUNNING",
  );
  const latestEventByAppliance = new Map<string, RunEvent>();
  for (const event of events) {
    if (event.appliance_id) {
      const previous = latestEventByAppliance.get(event.appliance_id);
      if (previous === undefined || event.simulation_time_s >= previous.simulation_time_s) {
        latestEventByAppliance.set(event.appliance_id, event);
      }
    }
  }

  return (
    <details className="floating-panel building-panel" open>
      <summary className="panel-summary">
        <strong>{building.building_id}</strong>
        <span className={`asset-state ${criticalLoadUnavailable ? "critical" : ""}`}>
          {criticalLoadUnavailable ? "Critical load off" : `${building.weight_k} representative`}
        </span>
      </summary>
      <div className="building-summary">
        <div>
          <span>Current demand</span>
          <strong>{building.appliances.reduce((sum, item) => sum + item.current_power_kw, 0).toFixed(3)} <small>kW</small></strong>
        </div>
        <div>
          <span>Appliances</span>
          <strong>{building.appliances.length}</strong>
        </div>
        <div>
          <span>Estimated feeder current</span>
          <strong>{building.estimated_current_a.toFixed(1)} <small>A</small></strong>
        </div>
      </div>
      {criticalLoadUnavailable ? (
        <p className="critical-notice">
          A critical appliance is not ON in the backend model. This transition is shown as reported.
        </p>
      ) : null}
      <div className="appliance-list">
        {building.appliances.map((appliance) => (
          <div className="appliance-row" key={appliance.appliance_id}>
            <span className={`priority-mark ${appliance.priority}`}>{appliance.priority}</span>
            <div className="appliance-name">
              <strong>{appliance.appliance_type.replace(/_/g, " ")}</strong>
              <span>{appliance.appliance_id}</span>
            </div>
            <div className="appliance-status">
              <strong className={`state-${appliance.state.toLowerCase()}`}>
                {appliance.state.replace(/_/g, " ")}
              </strong>
              <span>{appliance.current_power_kw.toFixed(2)} kW</span>
              {appliance.state === "RUNNING" ? <span>Startup transient</span> : null}
              {(appliance.lockout_remaining_s ?? 0) > 0 ? (
                <span>Restart lockout · {appliance.lockout_remaining_s?.toFixed(1)} s</span>
              ) : null}
              <span>
                {latestEventByAppliance.get(appliance.appliance_id)?.reason ?? "No control event recorded"}
              </span>
            </div>
          </div>
        ))}
      </div>
      <section className="nilm-estimate-list" aria-label="NILM estimates">
        <div className="integration-heading">
          <strong>Load-step estimates</strong>
          <span>Simulated signal</span>
        </div>
        {nilmEstimates.length ? (
          <ul>
            {nilmEstimates.slice(-4).reverse().map((estimate, index) => (
              <li key={`${estimate.simulation_time_s}-${estimate.building_id}-${index}`}>
                <span>
                  {estimate.appliance_type?.replace(/_/g, " ") ??
                    `${estimate.classification} load step`}
                </span>
                <small>
                  {estimate.event_type.replace("switch_", "")} ·
                  {" "}{Math.round(estimate.confidence * 100)}% ·
                  {" "}t={estimate.simulation_time_s.toFixed(1)}s
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <p>No detectable load steps yet. These estimates do not change twin state.</p>
        )}
      </section>
    </details>
  );
}

interface ResultsViewProps {
  results: SavedExperimentResults | null;
  resultsError: string | null;
  history: RunRecord[];
  comparisonResults: PolicyComparisonResult[];
  comparisonScenario: ScenarioConfig | null;
  comparisonSeed: number | null;
  comparisonSeedCount: number;
  comparisonProgress: string | null;
  comparisonError: string | null;
  onRefresh: () => void;
  onOpenRun: (run: RunRecord) => void;
}

function ResultsView({
  results,
  resultsError,
  history,
  comparisonResults,
  comparisonScenario,
  comparisonSeed,
  comparisonSeedCount,
  comparisonProgress,
  comparisonError,
  onRefresh,
  onOpenRun,
}: ResultsViewProps): ReactElement {
  return (
    <main className="results-view">
      <section className="panel results-hero">
        <div>
          <span className="eyebrow">EXPERIMENT ARCHIVE / E1-E4</span>
          <h2>Policy comparison</h2>
          <p>
            Saved experimental summaries are historical model outputs, separate from the currently
            selected live run.
          </p>
        </div>
        <button className="quiet-button" onClick={onRefresh} type="button">Refresh records</button>
      </section>

      {comparisonResults.length > 0 || comparisonProgress || comparisonError ? (
        <section className="panel comparison-panel live-comparison-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">LIVE COMPARISON / PAIRED SEEDS</span>
              <h2>{comparisonScenario?.name ?? "Policy comparison"}</h2>
            </div>
            <span className={`saved-badge${comparisonProgress ? " comparison-running" : ""}`}>
              {comparisonProgress ?? `${comparisonResults.length} / ${POLICY_ORDER.length} policies`}
            </span>
          </div>
          <div className="comparison-notes">
            <span>
              Seeds {comparisonSeed ?? "—"}–{comparisonSeed === null ? "—" : comparisonSeed + comparisonSeedCount - 1}
              {" "}· {comparisonSeedCount} per mode
            </span>
            <span>Each mode uses the same scenario and deterministic seed set.</span>
            <span>Model output; not a grid-operational guarantee.</span>
          </div>
          {comparisonError ? <p className="comparison-error" role="alert">{comparisonError}</p> : null}
          <div className="comparison-scroll">
            <table className="comparison-table">
              <thead>
                <tr>
                  <th>Policy</th>
                  <th>Mean nadir · 95% CI</th>
                  <th>Mean max |RoCoF|</th>
                  <th>Mean recovery</th>
                  <th>Feeder trips</th>
                  <th>Critical ENS</th>
                  <th>Medical interruption</th>
                  <th>Fairness</th>
                </tr>
              </thead>
              <tbody>
                {comparisonResults.map((item) => (
                  <tr key={item.policy}>
                    <th>{policyLabel(item.policy)}</th>
                    <td>
                      {formatMetric(item.summary.mean_nadir_hz, "Hz", 3)}
                      {" · ["}{formatMetric(item.summary.ci95_nadir[0], "", 3)}
                      {", "}{formatMetric(item.summary.ci95_nadir[1], "", 3)}{"]"}
                    </td>
                    <td>{formatMetric(item.summary.mean_max_rocof_hz_per_s, "Hz/s", 3)}</td>
                    <td>
                      {item.summary.mean_recovery_time_s === null
                        ? "Not recovered"
                        : formatDuration(item.summary.mean_recovery_time_s)}
                    </td>
                    <td>{formatMetric(item.summary.mean_feeder_trips, "events", 1)}</td>
                    <td>{formatMetric(item.summary.mean_critical_ens_kwh, "kWh")}</td>
                    <td>{formatMetric(item.summary.mean_medical_load_interruption_s, "device-s", 1)}</td>
                    <td>{item.summary.mean_jains_index.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {comparisonResults.length > 0 ? (
            <div className="comparison-chart">
              <FrequencyChart
                comparisonSeries={comparisonResults.map((item) => ({
                  policy: policyLabel(item.policy),
                  telemetry: item.telemetry,
                }))}
                disturbanceStart={comparisonScenario?.disturbance.start_time_s ?? null}
                events={[]}
                grid={comparisonScenario?.grid_params ?? null}
                telemetry={[]}
              />
            </div>
          ) : null}
        </section>
      ) : null}

      {results ? (
        <>
          <section className="panel comparison-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">SAVED EXPERIMENT / {results.experiment_id.slice(0, 8)}</span>
                <h2>{results.scenario_name}</h2>
              </div>
              <span className="saved-badge">SAVED EXPERIMENT</span>
            </div>
            <div className="comparison-scroll">
              <table className="comparison-table">
                <thead>
                  <tr>
                    <th>Policy</th>
                    <th>Runs</th>
                    <th>Frequency nadir</th>
                    <th>Recovery time</th>
                    <th>Feeder trips</th>
                    <th>Critical ENS</th>
                    <th>Jain fairness</th>
                  </tr>
                </thead>
                <tbody>
                  {SAVED_POLICY_ORDER.map((policy) => {
                    const summary: SavedPolicySummary | undefined = results.summary[policy];
                    return (
                      <tr key={policy}>
                        <th>
                          <span className={`policy-dot ${policy.toLowerCase()}`} />
                          {policyLabel(policy)}
                        </th>
                        <td>{summary ? summary.n_seeds : "Not available"}</td>
                        <td>{summary ? formatMetric(summary.mean_nadir_hz, "Hz", 3) : "Not available"}</td>
                        <td>
                          {summary
                            ? summary.mean_recovery_time_s === null
                              ? "Not available"
                              : formatDuration(summary.mean_recovery_time_s)
                            : "Not available"}
                        </td>
                        <td>{summary ? summary.mean_feeder_trips.toFixed(1) : "Not available"}</td>
                        <td>{summary ? formatMetric(summary.mean_critical_ens_kwh, "kWh") : "Not available"}</td>
                        <td>{summary ? summary.mean_jains_index.toFixed(3) : "Not available"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="comparison-notes">
              <span>Recorded {new Date(results.created_at).toLocaleString()}</span>
              <span>Seed identifiers and frequency trajectories are not included in this saved summary.</span>
              <span>Three runs per policy; descriptive statistics only, no significance claim.</span>
            </div>
          </section>
          <p className="result-caveat">
            The saved artifact contains summary metrics, not time-series samples. The frequency chart
            is therefore shown only for a run with actual telemetry.
          </p>
        </>
      ) : (
        <section className="panel results-error">
          <span className="eyebrow">SAVED RESULTS</span>
          <h2>{resultsError ? "Results could not be loaded" : "Loading saved experiment"}</h2>
          {resultsError ? <p>{resultsError}</p> : <span className="loading-line" />}
        </section>
      )}

      <section className="panel history-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">DATABASE / RUN RECORDS</span>
            <h2>Recent simulations</h2>
          </div>
          <span className="record-count">{history.length} records</span>
        </div>
        {history.length > 0 ? (
          <div className="comparison-scroll">
            <table className="history-table">
              <thead>
                <tr>
                  <th>Scenario</th>
                  <th>Policy</th>
                  <th>Seed</th>
                  <th>Status</th>
                  <th>Started</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {history.slice(0, 10).map((run) => (
                  <tr key={run.run_id}>
                    <td>{run.scenario_name || run.scenario_id.slice(0, 8)}</td>
                    <td>{policyLabel(run.policy)}</td>
                    <td>{run.seed}</td>
                    <td><span className={`history-status ${run.status}`}>{run.status}</span></td>
                    <td>{new Date(run.started_at).toLocaleString()}</td>
                    <td>
                      <button className="table-action" onClick={() => onOpenRun(run)} type="button">
                        Inspect run
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-note">No persisted simulation runs are available yet.</div>
        )}
      </section>
    </main>
  );
}

function App(): ReactElement {
  const [activeTab, setActiveTab] = useState<ViewTab>("operations");
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>("controls");
  const [aboutOpen, setAboutOpen] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  const [panelLayoutKey, setPanelLayoutKey] = useState(0);
  const [backendConnected, setBackendConnected] = useState<boolean | null>(null);
  const [streamStatus, setStreamStatus] = useState<
    "idle" | "connecting" | "connected" | "reconnecting" | "closed" | "invalid"
  >("idle");
  const [templates, setTemplates] = useState<ScenarioTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [policy, setPolicy] = useState<PolicyId>("P2_priority_edge");
  const [seed, setSeed] = useState(42);
  const [generationLossPercent, setGenerationLossPercent] = useState(15);
  const [recoveryRampSeconds, setRecoveryRampSeconds] = useState(30);
  const [inertiaSeconds, setInertiaSeconds] = useState(4);
  const [disturbanceStartSeconds, setDisturbanceStartSeconds] = useState(10);
  const [simulationDurationSeconds, setSimulationDurationSeconds] = useState(300);
  const [governorDroopPercent, setGovernorDroopPercent] = useState(5);
  const [governorTimeConstantSeconds, setGovernorTimeConstantSeconds] = useState(0.1);
  const [s1ThresholdHz, setS1ThresholdHz] = useState(49.85);
  const [s2ThresholdHz, setS2ThresholdHz] = useState(49.6);
  const [s0HoldSeconds, setS0HoldSeconds] = useState(10);
  const [s1HoldSeconds, setS1HoldSeconds] = useState(5);
  const [s2HoldSeconds, setS2HoldSeconds] = useState(2);
  const [s3HoldSeconds, setS3HoldSeconds] = useState(0);
  const [p1RecoveryHoldSeconds, setP1RecoveryHoldSeconds] = useState(120);
  const [o1HoldSeconds, setO1HoldSeconds] = useState(30);
  const [restorationStableSeconds, setRestorationStableSeconds] = useState(60);
  const [disturbanceType, setDisturbanceType] =
    useState<ScenarioConfig["disturbance"]["type"]>("generation_loss");
  const [solarSharePercent, setSolarSharePercent] = useState(40);
  const [edgeMode, setEdgeMode] = useState<EdgeMode>("DISTRIBUTED");
  const [communicationLossPercent, setCommunicationLossPercent] = useState(0);
  const [comparisonSeedCount, setComparisonSeedCount] = useState(3);
  const [playbackSpeed, setPlaybackSpeed] = useState(30);
  const [hilEnabled, setHilEnabled] = useState(false);
  const [hilPort, setHilPort] = useState("");
  const [hilBuildingId, setHilBuildingId] = useState("B12");
  const [runId, setRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<RunStatus | "idle" | "starting">("idle");
  const [runPolicy, setRunPolicy] = useState<PolicyId>("P2_priority_edge");
  const [runScenario, setRunScenario] = useState<ScenarioConfig | null>(null);
  const [telemetry, setTelemetry] = useState<TelemetrySample[]>([]);
  const [lastTelemetryAt, setLastTelemetryAt] = useState<number | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [metrics, setMetrics] = useState<RunMetric[]>([]);
  const [buildingSnapshots, setBuildingSnapshots] = useState<BuildingSnapshot[] | null>(null);
  const buildingSnapshotsRef = useRef<BuildingSnapshot[] | null>(null);
  const [integrations, setIntegrations] = useState<RunIntegrations | null>(null);
  const [nilmEstimates, setNilmEstimates] = useState<NilmEstimate[]>([]);
  const [nilmSignal, setNilmSignal] = useState<NilmSignalSample[]>([]);
  const [nilmEvaluation, setNilmEvaluation] = useState<NilmEvaluation | null>(null);
  const [edgeAgents, setEdgeAgents] = useState<EdgeAgentSnapshot[]>([]);
  const [restorationState, setRestorationState] = useState<RestorationSnapshot | null>(null);
  const [feederEstimate, setFeederEstimate] = useState<FeederEstimate | null>(null);
  const [selectedBuildingId, setSelectedBuildingId] = useState<string | null>(null);
  const [eventFilter, setEventFilter] = useState<EventFilter>("all");
  const [history, setHistory] = useState<RunRecord[]>([]);
  const [savedResults, setSavedResults] = useState<SavedExperimentResults | null>(null);
  const [savedResultsError, setSavedResultsError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [runNotice, setRunNotice] = useState<string | null>(null);
  const [scenarioError, setScenarioError] = useState<string | null>(null);
  const usesAdmsPolicy = policy === "P1_adms_feeder";
  const usesPriorityEdgePolicy =
    policy === "P2_priority_edge" ||
    policy === "P2_priority_edge_synchronized" ||
    policy === "P3_priority_edge_no_restoration";
  const usesRestoringPriorityPolicy =
    usesPriorityEdgePolicy && policy !== "P3_priority_edge_no_restoration";
  const usesProtectionThresholds = usesAdmsPolicy || usesPriorityEdgePolicy;
  const [runRefreshKey, setRunRefreshKey] = useState(0);
  const [comparisonResults, setComparisonResults] = useState<PolicyComparisonResult[]>([]);
  const [comparisonScenario, setComparisonScenario] = useState<ScenarioConfig | null>(null);
  const [comparisonSeed, setComparisonSeed] = useState<number | null>(null);
  const [comparisonProgress, setComparisonProgress] = useState<string | null>(null);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const submissionLock = useRef(false);
  const highestSequence = useRef(0);
  const highestBuildingSequence = useRef(0);
  const activeBuildingRunId = useRef<string | null>(runId);
  const lastBuildingStreamActivityAt = useRef(Date.now());
  const streamStatusRef = useRef(streamStatus);
  const runStatusRef = useRef(runStatus);
  streamStatusRef.current = streamStatus;
  runStatusRef.current = runStatus;
  activeBuildingRunId.current = runId;

  const selectedTemplate = templates.find((template) => template.template_id === selectedTemplateId) ?? null;
  const displayScenario = runScenario ?? selectedTemplate?.config ?? null;
  const visibleBuildings = useMemo(() => {
    if (runId && buildingSnapshots) return liveBuildings(buildingSnapshots);
    return displayScenario ? scenarioBuildings(displayScenario.buildings) : [];
  }, [buildingSnapshots, displayScenario, runId]);
  const selectedBuilding =
    visibleBuildings.find((building) => building.building_id === selectedBuildingId) ??
    visibleBuildings[0] ??
    null;
  const nilmBuildingId = selectedBuildingId ?? visibleBuildings[0]?.building_id ?? null;
  const latestSample = telemetry.length > 0 ? telemetry[telemetry.length - 1] : null;
  const [clockNow, setClockNow] = useState(Date.now());
  const telemetryAgeSeconds =
    lastTelemetryAt === null ? null : Math.max(0, Math.floor((clockNow - lastTelemetryAt) / 1000));
  const telemetryIsStale =
    runStatus === "running" && telemetryAgeSeconds !== null && telemetryAgeSeconds > 5;
  const measuredNadir =
    telemetry.length > 0
      ? Math.min(...telemetry.map((sample) => sample.frequency_hz))
      : null;
  const measuredRoCoF =
    telemetry.length > 0
      ? Math.max(...telemetry.map((sample) => Math.abs(sample.rocof_hz_per_s)))
      : null;
  const recoveredTime = getMetric(metrics, "recovery_time_s");
  const curtailedEnergy = [
    getMetric(metrics, "energy_curtailed_critical_kwh"),
    getMetric(metrics, "energy_curtailed_essential_kwh"),
    getMetric(metrics, "energy_curtailed_deferrable_kwh"),
  ].every((value) => value !== null)
    ? metrics
        .filter((metric) => metric.metric_name.startsWith("energy_curtailed_"))
        .reduce((sum, metric) => sum + metric.metric_value, 0)
    : null;
  const isRunActive =
    runStatus === "pending" ||
    runStatus === "running" ||
    runStatus === "paused" ||
    runStatus === "starting";
  const isComparisonActive = comparisonProgress !== null;
  const disturbanceStart = displayScenario?.disturbance.start_time_s ?? null;

  const mergeTelemetry = useCallback((incoming: TelemetrySample[]) => {
    const newestSequence = incoming.reduce(
      (highest, sample) => Math.max(highest, sample.sequence_number),
      highestSequence.current,
    );
    if (newestSequence > highestSequence.current) {
      highestSequence.current = newestSequence;
      setLastTelemetryAt(Date.now());
    }
    setTelemetry((current) => {
      const bySequence = new Map(current.map((sample) => [sample.sequence_number, sample]));
      incoming.forEach((sample) => {
        if (Number.isFinite(sample.sequence_number) && Number.isFinite(sample.frequency_hz)) {
          bySequence.set(sample.sequence_number, sample);
        }
      });
      return [...bySequence.values()]
        .sort((left, right) => left.sequence_number - right.sequence_number)
        .slice(-1600);
    });
  }, []);

  const applyBuildingSnapshots = useCallback((
    incoming: BuildingSnapshot[],
    expectedRunId: string,
    forceReconcile = false,
  ) => {
    if (
      activeBuildingRunId.current !== expectedRunId ||
      incoming.length === 0 ||
      !incoming.every((building) => building.run_id === expectedRunId)
    ) {
      return;
    }
    const sequence = incoming.reduce(
      (highest, building) => Math.max(highest, building.sequence_number),
      0,
    );
    if (sequence < highestBuildingSequence.current) return;
    if (
      sequence > highestBuildingSequence.current &&
      !forceReconcile &&
      streamStatusRef.current === "connected"
    ) {
      return;
    }
    highestBuildingSequence.current = sequence;
    buildingSnapshotsRef.current = incoming;
    setBuildingSnapshots(incoming);
  }, []);

  const reconcileBuildingSnapshots = useCallback(async (expectedRunId: string) => {
    try {
      const snapshots = await getRunBuildings(expectedRunId);
      if (activeBuildingRunId.current !== expectedRunId) return;
      applyBuildingSnapshots(snapshots, expectedRunId, true);
    } catch (error) {
      if (activeBuildingRunId.current === expectedRunId) {
        setActionError(`Building state reconciliation failed: ${errorMessage(error)}`);
      }
    }
  }, [applyBuildingSnapshots]);

  useEffect(() => {
    const clockTimer = window.setInterval(() => setClockNow(Date.now()), 1000);
    return () => window.clearInterval(clockTimer);
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      await getHealth();
      setBackendConnected(true);
    } catch {
      setBackendConnected(false);
    }
  }, []);

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await getRunHistory());
    } catch (error) {
      setActionError(`Run history could not be loaded: ${errorMessage(error)}`);
    }
  }, []);

  const refreshSavedResults = useCallback(async () => {
    setSavedResultsError(null);
    try {
      setSavedResults(await getSavedExperiment());
    } catch (error) {
      setSavedResults(null);
      setSavedResultsError(errorMessage(error));
    }
  }, []);

  useEffect(() => {
    let active = true;
    const loadTemplates = async () => {
      try {
        const available = await getScenarioTemplates();
        if (!active) return;
        setTemplates(available);
        setSelectedTemplateId(
          available.some((template) => template.template_id === "default_scenario")
            ? "default_scenario"
            : available[0]?.template_id ?? "",
        );
        setScenarioError(null);
      } catch (error) {
        if (active) setScenarioError(errorMessage(error));
      }
    };

    void refreshHealth();
    void loadTemplates();
    void refreshHistory();
    void refreshSavedResults();
    const healthTimer = window.setInterval(() => void refreshHealth(), 10000);
    return () => {
      active = false;
      window.clearInterval(healthTimer);
    };
  }, [refreshHealth, refreshHistory, refreshSavedResults]);

  useEffect(() => {
    if (!selectedTemplate) return;
    setGenerationLossPercent(Math.round(selectedTemplate.config.disturbance.magnitude_pu * 100));
    setRecoveryRampSeconds(selectedTemplate.config.disturbance.recovery_ramp_s);
    setInertiaSeconds(selectedTemplate.config.grid_params.H);
    setDisturbanceStartSeconds(selectedTemplate.config.disturbance.start_time_s);
    setSimulationDurationSeconds(selectedTemplate.config.simulation_duration_s);
    setGovernorDroopPercent(selectedTemplate.config.grid_params.R * 100);
    setGovernorTimeConstantSeconds(selectedTemplate.config.grid_params.Tg ?? 0.1);
    setS1ThresholdHz(selectedTemplate.config.grid_params.f_s1_hz);
    setS2ThresholdHz(selectedTemplate.config.grid_params.f_s2_hz);
    setS0HoldSeconds(selectedTemplate.config.grid_params.t_s0_hold_s ?? 10);
    setS1HoldSeconds(selectedTemplate.config.grid_params.t_s1_hold_s ?? 5);
    setS2HoldSeconds(selectedTemplate.config.grid_params.t_s2_hold_s ?? 2);
    setS3HoldSeconds(selectedTemplate.config.grid_params.t_s3_hold_s ?? 0);
    setP1RecoveryHoldSeconds(selectedTemplate.config.grid_params.t_p1_recovery_s ?? 120);
    setO1HoldSeconds(selectedTemplate.config.grid_params.t_o1_hold_s ?? 30);
    setRestorationStableSeconds(selectedTemplate.config.grid_params.t_stable_s);
    setDisturbanceType(
      selectedTemplate.config.disturbance.type === "solar_cloud_drop"
        ? "solar_cloud_drop"
        : selectedTemplate.config.disturbance.type,
    );
    setSolarSharePercent((selectedTemplate.config.disturbance.solar_share_pu ?? 0.4) * 100);
    setEdgeMode(selectedTemplate.config.edge_mode ?? "DISTRIBUTED");
    setCommunicationLossPercent(
      selectedTemplate.config.fault_config.loss_probability * 100,
    );
  }, [selectedTemplateId, selectedTemplate]);

  useEffect(() => {
    if (!runId) {
      setStreamStatus("idle");
      return;
    }

    let disposed = false;
    let retryTimer: number | undefined;
    let socket: WebSocket | null = null;

    const connect = () => {
      if (disposed) return;
      if (isTerminal(runStatusRef.current)) {
        setStreamStatus("closed");
        return;
      }
      setStreamStatus("connecting");
      socket = new WebSocket(
        getRunStreamUrl(runId, highestBuildingSequence.current),
      );
      socket.onopen = () => {
        if (!disposed) {
          lastBuildingStreamActivityAt.current = Date.now();
          setStreamStatus("connected");
        }
      };
      socket.onmessage = (message: MessageEvent<string>) => {
        let payload: unknown;
        try {
          payload = JSON.parse(message.data) as unknown;
        } catch {
          setStreamStatus("invalid");
          return;
        }
        if (!isRecord(payload)) {
          setStreamStatus("invalid");
          return;
        }
        if (payload.type === "ping") return;
        if (payload.type === "building_snapshot") {
          if (
            payload.run_id !== runId ||
            !Array.isArray(payload.buildings) ||
            !payload.buildings.every(isBuildingSnapshot)
          ) {
            setStreamStatus("invalid");
            return;
          }
          lastBuildingStreamActivityAt.current = Date.now();
          applyBuildingSnapshots(payload.buildings, runId, true);
          return;
        }
        if (payload.type === "resync_required") {
          if (payload.run_id !== runId) return;
          lastBuildingStreamActivityAt.current = Date.now();
          void reconcileBuildingSnapshots(runId);
          return;
        }
        if (payload.type === "run_complete") {
          if (payload.status === "completed" || payload.status === "failed") {
            setRunStatus(payload.status);
          }
          return;
        }
        if (isRunEvent(payload)) {
          if (payload.run_id !== runId) return;
          setEvents((current) => (
            current.some((event) => event.event_id === payload.event_id)
              ? current
              : [...current, payload]
          ));
          return;
        }
        if (payload.error) {
          setActionError(String(payload.error));
          return;
        }
        if (isBuildingStateUpdate(payload)) {
          if (payload.run_id !== runId) return;
          if (payload.sequence_number <= highestBuildingSequence.current) return;
          if (
            payload.sequence_number !== highestBuildingSequence.current + 1
          ) {
            void reconcileBuildingSnapshots(runId);
            return;
          }
          lastBuildingStreamActivityAt.current = Date.now();
          const current = buildingSnapshotsRef.current;
          if (!current) {
            void reconcileBuildingSnapshots(runId);
            return;
          }
          const updated = mergeBuildingStateUpdate(current, payload);
          if (updated === current) {
            void reconcileBuildingSnapshots(runId);
            return;
          }
          highestBuildingSequence.current = payload.sequence_number;
          buildingSnapshotsRef.current = updated;
          setBuildingSnapshots(updated);
          return;
        }
        if (!isTelemetrySample(payload) || payload.run_id !== runId) {
          setStreamStatus("invalid");
          return;
        }
        setStreamStatus("connected");
        mergeTelemetry([payload]);
      };
      socket.onerror = () => {
        if (!disposed) setStreamStatus("reconnecting");
      };
      socket.onclose = () => {
        if (disposed) return;
        if (isTerminal(runStatusRef.current)) {
          setStreamStatus("closed");
          return;
        }
        setStreamStatus("reconnecting");
        retryTimer = window.setTimeout(connect, 1200);
      };
    };

    connect();
    return () => {
      disposed = true;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, [
    applyBuildingSnapshots,
    mergeTelemetry,
    reconcileBuildingSnapshots,
    runId,
    runRefreshKey,
  ]);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    let polling = false;
    let interval: number | undefined;

    const reportPollFailure = (label: string, error: unknown) => {
      if (!cancelled) setActionError(`${label}: ${errorMessage(error)}`);
    };

    const pollRun = async () => {
      if (polling || cancelled) return;
      polling = true;
      try {
        const snapshot = await getRun(runId);
        if (cancelled) return;
        setRunStatus(snapshot.status);
        setRunScenario((current) =>
          current?.scenario_id === snapshot.scenario_id ? current : snapshot.scenario,
        );
        setRunPolicy(snapshot.policy);
        setSeed(snapshot.seed);

        const [
          buildingResult,
          eventResult,
          integrationResult,
          nilmResult,
          agentResult,
          restorationResult,
          feederResult,
          nilmSignalResult,
        ] = await Promise.allSettled([
          getRunBuildings(runId),
          getRunEvents(runId),
          getRunIntegrations(runId),
          getRunNilm(runId),
          getRunAgents(runId),
          getRunRestoration(runId),
          getRunFeeder(runId),
          getRunNilmSignal(runId, nilmBuildingId),
        ]);
        if (cancelled) return;
        if (buildingResult.status === "fulfilled") {
          const disconnectedLongEnough =
            streamStatusRef.current !== "connected" &&
            Date.now() - lastBuildingStreamActivityAt.current > 3000;
          applyBuildingSnapshots(
            buildingResult.value,
            runId,
            isTerminal(snapshot.status) || disconnectedLongEnough,
          );
          setScenarioError(null);
        } else if (!(buildingResult.reason instanceof ApiError && buildingResult.reason.status === 404)) {
          reportPollFailure("Building state could not be refreshed", buildingResult.reason);
        }
        if (eventResult.status === "fulfilled") {
          setEvents(eventResult.value);
        } else {
          reportPollFailure("Run events could not be refreshed", eventResult.reason);
        }
        if (integrationResult.status === "fulfilled") {
          setIntegrations(integrationResult.value);
        } else if (!(integrationResult.reason instanceof ApiError && integrationResult.reason.status === 404)) {
          reportPollFailure("Integration status could not be refreshed", integrationResult.reason);
        }
        if (nilmResult.status === "fulfilled") setNilmEstimates(nilmResult.value);
        else if (!(nilmResult.reason instanceof ApiError && nilmResult.reason.status === 404)) {
          reportPollFailure("NILM estimates could not be refreshed", nilmResult.reason);
        }
        if (agentResult.status === "fulfilled") setEdgeAgents(agentResult.value);
        else if (!(agentResult.reason instanceof ApiError && agentResult.reason.status === 404)) {
          reportPollFailure("Edge-agent status could not be refreshed", agentResult.reason);
        }
        if (restorationResult.status === "fulfilled") setRestorationState(restorationResult.value);
        else if (!(restorationResult.reason instanceof ApiError && restorationResult.reason.status === 404)) {
          reportPollFailure("Restoration status could not be refreshed", restorationResult.reason);
        }
        if (feederResult.status === "fulfilled") setFeederEstimate(feederResult.value);
        else if (!(feederResult.reason instanceof ApiError && feederResult.reason.status === 404)) {
          reportPollFailure("Feeder estimates could not be refreshed", feederResult.reason);
        }
        if (nilmSignalResult.status === "fulfilled") setNilmSignal(nilmSignalResult.value);
        else if (!(nilmSignalResult.reason instanceof ApiError && nilmSignalResult.reason.status === 404)) {
          reportPollFailure("NILM signal could not be refreshed", nilmSignalResult.reason);
        }

        if (streamStatusRef.current !== "connected" || isTerminal(snapshot.status)) {
          const samples = await getRunTelemetry(runId);
          if (!cancelled) mergeTelemetry(samples);
        }

        if (isTerminal(snapshot.status)) {
          if (interval !== undefined) window.clearInterval(interval);
          const [metricResult, historyResult, nilmEvaluationResult] = await Promise.allSettled([
            getRunMetrics(runId),
            getRunHistory(),
            getRunNilmEvaluation(runId),
          ]);
          if (cancelled) return;
          if (metricResult.status === "fulfilled") {
            setMetrics(metricResult.value);
          } else if (snapshot.status === "completed") {
            reportPollFailure("Run metrics could not be loaded", metricResult.reason);
          }
          if (historyResult.status === "fulfilled") setHistory(historyResult.value);
          else reportPollFailure("Run history could not be refreshed", historyResult.reason);
          if (nilmEvaluationResult.status === "fulfilled") {
            setNilmEvaluation(nilmEvaluationResult.value);
          } else if (!(nilmEvaluationResult.reason instanceof ApiError && nilmEvaluationResult.reason.status === 404)) {
            reportPollFailure("NILM evaluation could not be loaded", nilmEvaluationResult.reason);
          }
          if (snapshot.status === "failed") {
            setRunNotice("The backend reported that this simulation failed.");
          } else {
            setRunNotice("Run completed. Displayed values are from its recorded telemetry and metrics.");
          }
        }
      } catch (error) {
        reportPollFailure("Run status could not be refreshed", error);
      } finally {
        polling = false;
      }
    };

    void pollRun();
    interval = window.setInterval(() => void pollRun(), 1000);
    return () => {
      cancelled = true;
      if (interval !== undefined) window.clearInterval(interval);
    };
  }, [applyBuildingSnapshots, mergeTelemetry, nilmBuildingId, runId, runRefreshKey]);

  const startSimulation = async () => {
    if (submissionLock.current || isRunActive || !selectedTemplate) return;
    if (hilEnabled && (
      !hilPort.trim() ||
      !hilBuildingId ||
      !["P2_priority_edge", "P2_priority_edge_synchronized"].includes(policy)
    )) {
      setActionError("HIL requires a serial port, a target building, and the P2 policy.");
      return;
    }
    let scenarioConfig: ScenarioConfig;
    try {
      scenarioConfig = withScenarioTuning(selectedTemplate.config, seed, {
        generationLossPercent,
        recoveryRampSeconds,
        inertiaSeconds,
        disturbanceStartSeconds,
        simulationDurationSeconds,
        governorDroopPercent,
        governorTimeConstantSeconds,
        s1ThresholdHz,
        s2ThresholdHz,
        s0HoldSeconds,
        s1HoldSeconds,
        s2HoldSeconds,
        s3HoldSeconds,
        p1RecoveryHoldSeconds,
        o1HoldSeconds,
        restorationStableSeconds,
        disturbanceType,
        solarSharePercent,
        edgeMode,
        communicationLossPercent,
      });
    } catch (error) {
      setActionError(`Scenario settings are invalid: ${errorMessage(error)}`);
      return;
    }
    submissionLock.current = true;
    setActionError(null);
    setRunNotice(null);
    setRunStatus("starting");
    setRunId(null);
    setRunScenario(scenarioConfig);
    setTelemetry([]);
    setLastTelemetryAt(null);
    highestSequence.current = 0;
    highestBuildingSequence.current = 0;
    lastBuildingStreamActivityAt.current = Date.now();
    setEvents([]);
    setMetrics([]);
    setBuildingSnapshots(null);
    buildingSnapshotsRef.current = null;
    setIntegrations(null);
    setNilmEstimates([]);
    setNilmSignal([]);
    setNilmEvaluation(null);
    setEdgeAgents([]);
    setRestorationState(null);
    setFeederEstimate(null);
    setSelectedBuildingId(null);

    try {
      scenarioConfig = {
        ...scenarioConfig,
        scenario_id: window.crypto.randomUUID(),
      };
      const createdScenario = await createScenario(scenarioConfig);
      const started = await startConfiguredRun(createdScenario.scenario_id, policy, seed, {
        playback_speed: playbackSpeed,
        ...(hilEnabled ? {
          hil_port: hilPort.trim(),
          hil_building_id: hilBuildingId,
        } : {}),
      });
      setRunScenario(scenarioConfig);
      setRunPolicy(policy);
      setRunStatus(started.status === "running" ? "running" : "pending");
      setRunId(started.run_id);
      setRunNotice(`Run ${started.run_id.slice(0, 8)} accepted by the backend.`);
      await refreshHistory();
    } catch (error) {
      setRunStatus("idle");
      setRunNotice(null);
      setActionError(`Simulation could not be started: ${errorMessage(error)}`);
    } finally {
      submissionLock.current = false;
    }
  };

  const requestStop = async () => {
    if (!runId || submissionLock.current || !["running", "paused"].includes(runStatus)) return;
    if (!window.confirm("Stop this simulation run? The backend will finalize its recorded results.")) return;
    submissionLock.current = true;
    setActionError(null);
    try {
      await stopRun(runId);
      setRunNotice("Stop requested. Waiting for the backend to publish the final run status.");
    } catch (error) {
      setActionError(`Stop request failed: ${errorMessage(error)}`);
    } finally {
      submissionLock.current = false;
    }
  };

  const togglePause = async () => {
    if (!runId || submissionLock.current) return;
    submissionLock.current = true;
    setActionError(null);
    try {
      if (runStatus === "paused") {
        await resumeRun(runId);
        setRunStatus("running");
      } else if (runStatus === "running") {
        await pauseRun(runId);
        setRunStatus("paused");
      }
    } catch (error) {
      setActionError(`Playback control failed: ${errorMessage(error)}`);
    } finally {
      submissionLock.current = false;
    }
  };

  const changePlaybackSpeed = async (speed: number) => {
    const previousSpeed = playbackSpeed;
    setPlaybackSpeed(speed);
    if (!runId || !["running", "paused"].includes(runStatus)) return;
    try {
      await setRunSpeed(runId, speed);
    } catch (error) {
      setPlaybackSpeed(previousSpeed);
      setActionError(`Playback speed could not be changed: ${errorMessage(error)}`);
    }
  };

  const comparePolicies = async () => {
    if (isRunActive || isComparisonActive || !selectedTemplate || !backendConnected) return;
    let tunedScenario: ScenarioConfig;
    try {
      tunedScenario = withScenarioTuning(selectedTemplate.config, seed, {
        generationLossPercent,
        recoveryRampSeconds,
        inertiaSeconds,
        disturbanceStartSeconds,
        simulationDurationSeconds,
        governorDroopPercent,
        governorTimeConstantSeconds,
        s1ThresholdHz,
        s2ThresholdHz,
        s0HoldSeconds,
        s1HoldSeconds,
        s2HoldSeconds,
        s3HoldSeconds,
        p1RecoveryHoldSeconds,
        o1HoldSeconds,
        restorationStableSeconds,
        disturbanceType,
        solarSharePercent,
        edgeMode,
        communicationLossPercent,
      });
    } catch (error) {
      setComparisonError(`Scenario settings are invalid: ${errorMessage(error)}`);
      return;
    }

    setComparisonResults([]);
    setComparisonScenario(tunedScenario);
    setComparisonSeed(seed);
    setComparisonError(null);
    setComparisonProgress(`Running four modes · ${comparisonSeedCount} paired seeds`);
    setActiveTab("results");
    try {
      const response = await compareControlModes(
        { ...tunedScenario, scenario_id: window.crypto.randomUUID() },
        comparisonSeedCount,
      );
      setComparisonResults(
        POLICY_ORDER.flatMap((comparisonPolicy) => {
          const summary = response.summary[comparisonPolicy];
          return summary
            ? [{
                policy: comparisonPolicy,
                summary,
                telemetry: response.frequency_trajectories[comparisonPolicy] ?? [],
              }]
            : [];
        }),
      );
    } catch (error) {
      setComparisonError(`Four-mode comparison failed: ${errorMessage(error)}`);
    } finally {
      setComparisonProgress(null);
    }
  };

  const beginNewRun = () => {
    setRunId(null);
    setRunStatus("idle");
    setRunScenario(null);
    setRunPolicy(policy);
    setTelemetry([]);
    setLastTelemetryAt(null);
    highestSequence.current = 0;
    highestBuildingSequence.current = 0;
    lastBuildingStreamActivityAt.current = Date.now();
    setEvents([]);
    setMetrics([]);
    setBuildingSnapshots(null);
    buildingSnapshotsRef.current = null;
    setSelectedBuildingId(null);
    setIntegrations(null);
    setNilmEstimates([]);
    setNilmSignal([]);
    setNilmEvaluation(null);
    setEdgeAgents([]);
    setRestorationState(null);
    setFeederEstimate(null);
    setRunNotice(null);
    setActionError(null);
    setStreamStatus("idle");
  };

  const openHistoryRun = async (run: RunRecord) => {
    setActiveTab("operations");
    setActionError(null);
    setRunId(run.run_id);
    setRunStatus(run.status);
    setRunPolicy(run.policy);
    setPolicy(run.policy);
    setTelemetry([]);
    setLastTelemetryAt(null);
    highestSequence.current = 0;
    highestBuildingSequence.current = 0;
    lastBuildingStreamActivityAt.current = Date.now();
    setEvents([]);
    setMetrics([]);
    setBuildingSnapshots(null);
    buildingSnapshotsRef.current = null;
    setIntegrations(null);
    setNilmEstimates([]);
    setNilmSignal([]);
    setNilmEvaluation(null);
    setEdgeAgents([]);
    setRestorationState(null);
    setFeederEstimate(null);
    setRunScenario(null);
    setRunNotice(`Inspecting recorded run ${run.run_id.slice(0, 8)}.`);
    setRunRefreshKey((current) => current + 1);
    try {
      const snapshot = await getRun(run.run_id);
      setRunScenario(snapshot.scenario);
      setSeed(snapshot.seed);
    } catch (error) {
      setActionError(`Run configuration could not be loaded: ${errorMessage(error)}`);
    }
  };

  const currentMetricValue = (name: string, liveValue: number | null) =>
    isTerminal(runStatus) ? getMetric(metrics, name) : liveValue;
  const blackedOutBuildings = visibleBuildings.filter(
    (building) => getBuildingStatus(building) === "blackout",
  ).length;
  const poweredMedicalDevices = visibleBuildings.reduce(
    (count, building) => count + building.appliances.filter(
      (appliance) => appliance.appliance_type === "medical_device" &&
        (appliance.state === "ON" || appliance.state === "RUNNING") &&
          appliance.current_power_kw > 0,
    ).length,
    0,
  );
  const peakDemandPu = telemetry.length
    ? Math.max(...telemetry.map((sample) => sample.demand_pu))
    : null;
  const frequencyStage = latestSample?.frequency_stage ?? "awaiting samples";
  const frequencyBand = !latestSample ? "unknown" :
    latestSample.frequency_hz <= (displayScenario?.grid_params.f_s3_hz ?? 49.4) ? "collapse" :
      latestSample.frequency_stage.toLowerCase().includes("s") &&
        latestSample.frequency_stage !== "S0" ? "warning" : "stable";
  const runStatusLine = [
    latestSample ? `t = ${latestSample.simulation_time_s.toFixed(1)} s` : "Waiting for telemetry",
    runId ? policyLabel(runPolicy) : policyLabel(policy),
    displayScenario ?     displayScenario.disturbance.type === "solar_cloud_drop"
      ? `cloud dip ${(displayScenario.disturbance.magnitude_pu * 100).toFixed(0)}% of PV · ${((displayScenario.disturbance.solar_share_pu ?? 0) * 100).toFixed(0)}% solar share`
      : `${displayScenario.disturbance.type.replace(/_/g, " ")} ${(displayScenario.disturbance.magnitude_pu * 100).toFixed(0)}%`
    : "",
  ].filter(Boolean).join(" · ");

  return (
    <div className={`control-room${frequencyBand === "collapse" ? " frequency-collapse" : ""}${focusMode ? " focus-mode" : ""}`}>
      <CityTwin
        buildings={visibleBuildings}
        isLive={Boolean(runId && buildingSnapshots)}
        demandPu={latestSample?.demand_pu ?? null}
        generationPu={latestSample?.generation_pu ?? null}
        isPaused={runStatus === "paused"}
        onSelectBuilding={setSelectedBuildingId}
        selectedBuildingId={selectedBuildingId ?? visibleBuildings[0]?.building_id ?? null}
      />
      <header className="topbar">
        <div className="brand-lockup">
          <svg className="brand-mark" aria-hidden="true" viewBox="0 0 34 34">
            <path d="M4 10h10l3 4 3-4h10M4 18h8l5 7 5-7h8M4 26h8l5-5 5 5h8" />
          </svg>
          <div>
            <div className="brand-name">Rakshak</div>
            <div className="brand-subtitle">BlackoutFree · {displayScenario?.name ?? "Grid operations model"}</div>
          </div>
        </div>
        <nav className="view-tabs" aria-label="Dashboard views">
          <button
            className={activeTab === "operations" ? "active" : ""}
            onClick={() => setActiveTab("operations")}
            type="button"
          >Operations</button>
          <button
            className={activeTab === "systems" ? "active" : ""}
            onClick={() => setActiveTab("systems")}
            type="button"
          >Resilience systems</button>
          <button
            className={activeTab === "results" ? "active" : ""}
            onClick={() => setActiveTab("results")}
            type="button"
          >Results &amp; history</button>
        </nav>
        <div className="connection-cluster">
          <span className="connection-item">
            <i className={`connection-dot ${backendConnected ? "online" : backendConnected === false ? "offline" : ""}`} />
            API {backendConnected ? "connected" : backendConnected === false ? "offline" : "checking"}
          </span>
          <span className="connection-item">
            <i className={`connection-dot ${streamStatus === "connected" ? "online" : streamStatus === "invalid" ? "offline" : ""}`} />
            Stream {streamStatus}
          </span>
          <span className={`run-chip ${runStatus}`}>{statusLabel(runStatus)}</span>
          {integrations?.hil.status === "connected" ? (
            <span className="integration-pill connected">HIL · {integrations.hil.building_id}</span>
          ) : null}
        </div>
        <div className="data-provenance" aria-label="Data source status">
          <span><i className="provenance-mark simulated" />Twin / simulated</span>
          <span>
            <i className={`provenance-mark ${integrations?.hil.status === "connected" ? "online" : "disconnected"}`} />
            HIL / {integrations?.hil.status.replace(/_/g, " ") ?? "not configured"}
          </span>
          <span>
            <i className={`provenance-mark ${integrations?.nilm.status === "simulated_estimates" ? "simulated" : "inactive"}`} />
            NILM / {integrations?.nilm.status === "simulated_estimates" ? "model-derived" : "not active"}
          </span>
        </div>
        <button className="about-button" type="button" onClick={() => setAboutOpen((open) => !open)}>
          About this model
        </button>
        <button
          className="about-button focus-toggle"
          type="button"
          onClick={() => setFocusMode((active) => !active)}
        >
          {focusMode ? "Exit focus" : "Simulation focus"}
        </button>
        {aboutOpen ? (
          <div className="about-popover" role="dialog" aria-label="About this model">
            <button type="button" aria-label="Close model information" onClick={() => setAboutOpen(false)}>×</button>
            <strong>About this model</strong>
            <p>Frequency is model output, not a live grid measurement. This reduced-order simulation is not a utility protection guarantee.</p>
          </div>
        ) : null}
      </header>

      {backendConnected === false ? (
        <div className="connection-banner" role="status">
          <strong>API unavailable.</strong> Connect the Rakshak / BlackoutFree service to load scenarios and run state.
          <button type="button" onClick={() => void refreshHealth()}>Retry</button>
        </div>
      ) : null}
      {actionError ? (
        <div className="error-banner" role="alert">
          <strong>Request issue</strong><span>{actionError}</span>
          <button aria-label="Dismiss error" type="button" onClick={() => setActionError(null)}>Dismiss</button>
        </div>
      ) : null}
      {scenarioError && backendConnected !== false ? (
        <div className="scenario-error" role="status">{scenarioError}</div>
      ) : null}

      {activeTab === "results" ? (
        <div className="results-backdrop">
          <ResultsView
            results={savedResults}
            resultsError={savedResultsError}
            history={history}
            comparisonResults={comparisonResults}
            comparisonScenario={comparisonScenario}
            comparisonSeed={comparisonSeed}
            comparisonSeedCount={comparisonSeedCount}
            comparisonProgress={comparisonProgress}
            comparisonError={comparisonError}
            onRefresh={() => {
              void refreshSavedResults();
              void refreshHistory();
            }}
            onOpenRun={(run) => void openHistoryRun(run)}
          />
        </div>
      ) : activeTab === "systems" ? (
        <div className="results-backdrop systems-backdrop">
          <DiagnosticsView
            agents={edgeAgents}
            buildings={visibleBuildings}
            feeder={feederEstimate}
            integrations={integrations}
            nilmEvaluation={nilmEvaluation}
            nilmSamples={nilmSignal}
            restoration={restorationState}
            runId={runId}
            runStatus={runStatus}
            runTimeSeconds={latestSample?.simulation_time_s ?? 0}
            scenario={runScenario}
            policy={runId ? runPolicy : null}
            telemetry={latestSample}
            metrics={metrics}
            selectedBuildingId={selectedBuildingId ?? visibleBuildings[0]?.building_id ?? null}
          />
        </div>
      ) : (
        <>
          <div className="frequency-readout floating-panel" aria-live="polite">
            <strong className={`frequency-value ${frequencyBand}`}>
              {latestSample ? `${latestSample.frequency_hz.toFixed(2)} Hz` : "— — Hz"}
            </strong>
            <span className={`frequency-condition ${frequencyBand}`}>
              {frequencyBand === "collapse" ? "Collapse band" : frequencyBand === "warning" ? `Stage ${frequencyStage}` : latestSample ? "Within operating band" : "Awaiting samples"}
            </span>
            <small>{runStatusLine}</small>
          </div>
          <nav className="mobile-sheet-tabs" aria-label="Dashboard panels">
            {([
              ["controls", "Controls"],
              ["stats", "Stats"],
              ["charts", "Charts"],
              ["building", "Building"],
              ["log", "Log"],
            ] as Array<[MobilePanel, string]>).map(([panel, label]) => (
              <button
                className={mobilePanel === panel ? "active" : ""}
                key={panel}
                onClick={() => setMobilePanel(panel)}
                type="button"
              >{label}</button>
            ))}
          </nav>
          <main className="operations-overlay" key={panelLayoutKey}>
            <details className={`floating-panel controls-panel${mobilePanel === "controls" ? " mobile-active" : ""}`} open>
              <summary className="panel-summary"><strong>Run controls</strong><span>{templates.length} scenarios</span></summary>
              <div className="panel-body">
                <label className="field-label" htmlFor="scenario-select">Scenario</label>
                <select
                  className="field-control"
                  disabled={isRunActive}
                  id="scenario-select"
                  value={selectedTemplateId}
                  onChange={(event) => {
                    setSelectedTemplateId(event.target.value);
                    setScenarioError(null);
                    setSelectedBuildingId(null);
                  }}
                >
                  {templates.map((template) => (
                    <option key={template.template_id} value={template.template_id}>{template.name}</option>
                  ))}
                </select>
                {selectedTemplate ? (
                  <div className="scenario-meta">
                    <span>{selectedTemplate.config.disturbance.type.replace(/_/g, " ")}</span>
                    <span>{selectedTemplate.config.buildings.length} buildings · {selectedTemplate.config.simulation_duration_s}s</span>
                  </div>
                ) : <p className="scenario-meta muted">Waiting for scenario definitions from the API.</p>}
                <div className="control-actions">
                  {!isRunActive ? (
                    <button
                      className="primary-button"
                      disabled={!selectedTemplate || !backendConnected || isComparisonActive || submissionLock.current}
                      onClick={() => void startSimulation()}
                      type="button"
                    >{runId ? "Start another run" : "Start simulation"}</button>
                  ) : (
                    <>
                      <button
                        className="quiet-button"
                        disabled={runStatus !== "running" && runStatus !== "paused"}
                        onClick={() => void togglePause()}
                        type="button"
                      >
                        {runStatus === "paused" ? "Resume" : "Pause"}
                      </button>
                      <button
                        className="stop-button"
                        disabled={runStatus !== "running" && runStatus !== "paused"}
                        onClick={() => void requestStop()}
                        type="button"
                      >Stop</button>
                    </>
                  )}
                  {isRunActive ? (
                    <label className="playback-speed-control">
                      Speed
                      <select
                        aria-label="Simulation playback speed"
                        disabled={runStatus === "pending" || runStatus === "starting"}
                        onChange={(event) => void changePlaybackSpeed(Number(event.target.value))}
                        value={playbackSpeed}
                      >
                        {[1, 5, 15, 30, 60, 120].map((speed) => (
                          <option key={speed} value={speed}>{speed}×</option>
                        ))}
                      </select>
                    </label>
                  ) : null}
                  {isTerminal(runStatus) ? (
                    <button className="quiet-button" onClick={beginNewRun} type="button">Clear run</button>
                  ) : null}
                </div>
                {runNotice ? <p className="run-notice">{runNotice}</p> : null}
                <details className="tuning-disclosure">
                  <summary>
                    <strong>Scenario tuning</strong>
                    <span>Disturbance and protection settings</span>
                  </summary>
                  <fieldset className="tuning-controls" disabled={isRunActive || isComparisonActive}>
                  <legend>Adjustment parameters</legend>
                  {!usesProtectionThresholds ? (
                    <p className="scenario-meta">
                      The unmanaged policy ignores protection, restoration, and edge-communication settings. It does not force a blackout; choose Feeder UFLS to demonstrate modeled feeder trips.
                    </p>
                  ) : null}
                  <label className="field-label" htmlFor="disturbance-type">
                    Disturbance profile
                  </label>
                  <select
                    className="field-control"
                    id="disturbance-type"
                    value={disturbanceType}
                    onChange={(event) =>
                      setDisturbanceType(event.target.value as ScenarioConfig["disturbance"]["type"])
                    }
                  >
                    <option value="generation_loss">Generation dip</option>
                    <option value="demand_surge">Demand surge</option>
                    <option value="combined">Combined generation + demand</option>
                    <option value="solar_surplus">Solar surplus</option>
                    <option value="solar_cloud_drop">Solar cloud dip</option>
                  </select>
                  <label htmlFor="disturbance-magnitude">
                    {disturbanceType === "solar_cloud_drop"
                      ? "PV output reduction"
                      : "Disturbance magnitude"} <strong>{generationLossPercent}%</strong>
                  </label>
                  <input
                    id="disturbance-magnitude"
                    max={100}
                    min={1}
                    onChange={(event) => setGenerationLossPercent(Number(event.target.value))}
                    step={1}
                    type="range"
                    value={generationLossPercent}
                  />
                  {disturbanceType === "solar_cloud_drop" ? (
                    <>
                      <label htmlFor="solar-share">
                        Solar share of area generation <strong>{solarSharePercent}%</strong>
                      </label>
                      <input
                        id="solar-share"
                        max={100}
                        min={1}
                        onChange={(event) => setSolarSharePercent(Number(event.target.value))}
                        step={1}
                        type="range"
                        value={solarSharePercent}
                      />
                      <p className="scenario-meta">
                        Cloud dip scales this solar share by the selected PV output reduction.
                      </p>
                    </>
                  ) : null}
                  <label htmlFor="recovery-ramp">
                    Recovery ramp <strong>{recoveryRampSeconds}s</strong>
                  </label>
                  <input
                    id="recovery-ramp"
                    max={120}
                    min={0}
                    onChange={(event) => setRecoveryRampSeconds(Number(event.target.value))}
                    step={5}
                    type="range"
                    value={recoveryRampSeconds}
                  />
                  <label htmlFor="grid-inertia">
                    Grid inertia <strong>{inertiaSeconds.toFixed(1)}s</strong>
                  </label>
                  <input
                    id="grid-inertia"
                    max={10}
                    min={1}
                    onChange={(event) => setInertiaSeconds(Number(event.target.value))}
                    step={0.5}
                    type="range"
                    value={inertiaSeconds}
                  />
                  <label htmlFor="disturbance-start">
                    Disturbance begins <strong>{disturbanceStartSeconds}s</strong>
                  </label>
                  <input
                    id="disturbance-start"
                    max={60}
                    min={0}
                    onChange={(event) => setDisturbanceStartSeconds(Number(event.target.value))}
                    step={5}
                    type="range"
                    value={disturbanceStartSeconds}
                  />
                  <label htmlFor="simulation-duration">
                    Simulation duration <strong>{simulationDurationSeconds}s</strong>
                  </label>
                  <input
                    id="simulation-duration"
                    max={1800}
                    min={90}
                    onChange={(event) => setSimulationDurationSeconds(Number(event.target.value))}
                    step={30}
                    type="range"
                    value={simulationDurationSeconds}
                  />
                  <label htmlFor="governor-droop">
                    Governor droop <strong>{governorDroopPercent.toFixed(1)}%</strong>
                  </label>
                  <input
                    id="governor-droop"
                    max={20}
                    min={0.1}
                    onChange={(event) => setGovernorDroopPercent(Number(event.target.value))}
                    step={0.1}
                    type="range"
                    value={governorDroopPercent}
                  />
                  <label htmlFor="governor-response">
                    Governor response <strong>{governorTimeConstantSeconds.toFixed(2)}s</strong>
                  </label>
                  <input
                    id="governor-response"
                    max={1}
                    min={0.05}
                    onChange={(event) => setGovernorTimeConstantSeconds(Number(event.target.value))}
                    step={0.05}
                    type="range"
                    value={governorTimeConstantSeconds}
                  />
                  <label htmlFor="s1-threshold">
                    S1 protection threshold <strong>{s1ThresholdHz.toFixed(2)} Hz</strong>
                  </label>
                  <input
                    id="s1-threshold"
                    disabled={!usesProtectionThresholds}
                    max={49.95}
                    min={49.8}
                    onChange={(event) => setS1ThresholdHz(Number(event.target.value))}
                    step={0.01}
                    type="range"
                    value={s1ThresholdHz}
                  />
                  <label htmlFor="s2-threshold">
                    S2 protection threshold <strong>{s2ThresholdHz.toFixed(2)} Hz</strong>
                  </label>
                  <input
                    id="s2-threshold"
                    disabled={!usesProtectionThresholds}
                    max={49.75}
                    min={49.45}
                    onChange={(event) => setS2ThresholdHz(Number(event.target.value))}
                    step={0.01}
                    type="range"
                    value={s2ThresholdHz}
                  />
                  <details className="advanced-tuning">
                    <summary>Protection and restoration timing</summary>
                    <label htmlFor="s0-hold">S0 advisory hold <strong>{s0HoldSeconds}s</strong></label>
                    <input id="s0-hold" disabled={!usesPriorityEdgePolicy} min={0} max={60} step={1} type="range"
                      value={s0HoldSeconds} onChange={(event) => setS0HoldSeconds(Number(event.target.value))} />
                    <label htmlFor="s1-hold">S1 shedding hold <strong>{s1HoldSeconds}s</strong></label>
                    <input id="s1-hold" disabled={!usesProtectionThresholds} min={0} max={30} step={0.5} type="range"
                      value={s1HoldSeconds} onChange={(event) => setS1HoldSeconds(Number(event.target.value))} />
                    <label htmlFor="s2-hold">P1 S2 feeder-trip hold <strong>{s2HoldSeconds}s</strong></label>
                    <input id="s2-hold" disabled={!usesAdmsPolicy} min={0} max={20} step={0.5} type="range"
                      value={s2HoldSeconds} onChange={(event) => setS2HoldSeconds(Number(event.target.value))} />
                    <label htmlFor="s3-hold">P1 S3 feeder-trip hold <strong>{s3HoldSeconds}s</strong></label>
                    <input id="s3-hold" disabled={!usesAdmsPolicy} min={0} max={10} step={0.5} type="range"
                      value={s3HoldSeconds} onChange={(event) => setS3HoldSeconds(Number(event.target.value))} />
                    <label htmlFor="p1-recovery-hold">P1 recovery hold <strong>{p1RecoveryHoldSeconds}s</strong></label>
                    <input id="p1-recovery-hold" disabled={!usesAdmsPolicy} min={0} max={600} step={10} type="range"
                      value={p1RecoveryHoldSeconds}
                      onChange={(event) => setP1RecoveryHoldSeconds(Number(event.target.value))} />
                    <label htmlFor="o1-hold">O1 absorption hold <strong>{o1HoldSeconds}s</strong></label>
                    <input id="o1-hold" disabled={!usesPriorityEdgePolicy} min={0} max={120} step={5} type="range"
                      value={o1HoldSeconds} onChange={(event) => setO1HoldSeconds(Number(event.target.value))} />
                    <label htmlFor="restoration-stable-hold">Restoration stability hold <strong>{restorationStableSeconds}s</strong></label>
                    <input id="restoration-stable-hold" disabled={!usesRestoringPriorityPolicy} min={1} max={180} step={5} type="range"
                      value={restorationStableSeconds}
                      onChange={(event) => setRestorationStableSeconds(Number(event.target.value))} />
                  </details>
                  <label htmlFor="communication-loss">
                    Communication loss probability <strong>{communicationLossPercent}%</strong>
                  </label>
                  <input
                    id="communication-loss"
                    disabled={!usesPriorityEdgePolicy}
                    max={100}
                    min={0}
                    onChange={(event) => setCommunicationLossPercent(Number(event.target.value))}
                    step={5}
                    type="range"
                    value={communicationLossPercent}
                  />
                  <button
                    className="quiet-button tuning-reset"
                    onClick={() => {
                      if (!selectedTemplate) return;
                      setGenerationLossPercent(
                        Math.round(selectedTemplate.config.disturbance.magnitude_pu * 100),
                      );
                      setRecoveryRampSeconds(selectedTemplate.config.disturbance.recovery_ramp_s);
                      setInertiaSeconds(selectedTemplate.config.grid_params.H);
                      setDisturbanceStartSeconds(selectedTemplate.config.disturbance.start_time_s);
                      setSimulationDurationSeconds(selectedTemplate.config.simulation_duration_s);
                      setGovernorDroopPercent(selectedTemplate.config.grid_params.R * 100);
                      setGovernorTimeConstantSeconds(selectedTemplate.config.grid_params.Tg ?? 0.1);
                      setS1ThresholdHz(selectedTemplate.config.grid_params.f_s1_hz);
                      setS2ThresholdHz(selectedTemplate.config.grid_params.f_s2_hz);
                      setS0HoldSeconds(selectedTemplate.config.grid_params.t_s0_hold_s ?? 10);
                      setS1HoldSeconds(selectedTemplate.config.grid_params.t_s1_hold_s ?? 5);
                      setS2HoldSeconds(selectedTemplate.config.grid_params.t_s2_hold_s ?? 2);
                      setS3HoldSeconds(selectedTemplate.config.grid_params.t_s3_hold_s ?? 0);
                      setP1RecoveryHoldSeconds(
                        selectedTemplate.config.grid_params.t_p1_recovery_s ?? 120,
                      );
                      setO1HoldSeconds(selectedTemplate.config.grid_params.t_o1_hold_s ?? 30);
                      setRestorationStableSeconds(selectedTemplate.config.grid_params.t_stable_s);
                      setEdgeMode(selectedTemplate.config.edge_mode ?? "DISTRIBUTED");
                      setCommunicationLossPercent(
                        selectedTemplate.config.fault_config.loss_probability * 100,
                      );
                    }}
                    type="button"
                  >
                    Reset preset values
                  </button>
                  </fieldset>
                </details>
                <label className="field-label" htmlFor="edge-mode-select">Edge operating mode</label>
                <select
                  className="field-control"
                  disabled={isRunActive || isComparisonActive || !usesPriorityEdgePolicy}
                  id="edge-mode-select"
                  onChange={(event) => setEdgeMode(event.target.value as EdgeMode)}
                  value={edgeMode}
                >
                  <option value="CENTRALIZED">Central dispatch</option>
                  <option value="DISTRIBUTED">Distributed edge</option>
                  <option value="COMMUNICATION_DEGRADED">Communication degraded</option>
                  <option value="ISLANDED_AUTONOMOUS">Islanded autonomous</option>
                </select>
                <label className="field-label" htmlFor="policy-select">Control policy</label>
                <select
                  className="field-control"
                  disabled={isRunActive}
                  id="policy-select"
                  value={policy}
                  onChange={(event) => setPolicy(event.target.value as PolicyId)}
                >
                  {POLICY_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
                <p className="policy-description">{POLICY_OPTIONS.find((option) => option.value === policy)?.detail}</p>
                <div className="seed-row">
                  <label className="field-label" htmlFor="seed-input">Seed</label>
                  <input
                    className="field-control seed-input"
                    disabled={isRunActive}
                    id="seed-input"
                    min={0}
                    step={1}
                    type="number"
                    value={seed}
                    onChange={(event) => {
                      const value = Number(event.target.value);
                      if (Number.isInteger(value) && value >= 0) setSeed(value);
                    }}
                  />
                </div>
                <label className="field-label" htmlFor="comparison-seeds">
                  Benchmark seeds <strong>{comparisonSeedCount}</strong>
                </label>
                <input
                  aria-label="Benchmark seed count"
                  className="field-control"
                  disabled={isRunActive || isComparisonActive}
                  id="comparison-seeds"
                  max={10}
                  min={2}
                  onChange={(event) => setComparisonSeedCount(Number(event.target.value))}
                  type="range"
                  value={comparisonSeedCount}
                />
                <button
                  className="comparison-launch"
                  disabled={!selectedTemplate || !backendConnected || isRunActive || isComparisonActive}
                  onClick={() => void comparePolicies()}
                  type="button"
                >
                  {comparisonProgress ?? `Compare four modes · ${comparisonSeedCount} seeds`}
                </button>
                {comparisonError ? (
                  <p className="comparison-error" role="alert">{comparisonError}</p>
                ) : null}
                {scenarioError ? <p className="field-error">{scenarioError}</p> : null}
                <details className="hardware-controls">
                  <summary>Hardware &amp; signal integrations</summary>
                  <label className="integration-toggle">
                    <input
                      checked={hilEnabled}
                      disabled={isRunActive || isComparisonActive || ![
                        "P2_priority_edge",
                        "P2_priority_edge_synchronized",
                      ].includes(policy)}
                      onChange={(event) => setHilEnabled(event.target.checked)}
                      type="checkbox"
                    />
                    <span>Connect serial HIL controller</span>
                  </label>
                  {hilEnabled ? (
                    <>
                      <label className="field-label" htmlFor="hil-port">Serial port</label>
                      <input
                        className="field-control"
                        disabled={isRunActive || isComparisonActive}
                        id="hil-port"
                        onChange={(event) => setHilPort(event.target.value)}
                        placeholder="COM3"
                        value={hilPort}
                      />
                      <label className="field-label" htmlFor="hil-building">Controlled building</label>
                      <select
                        className="field-control"
                        disabled={isRunActive || isComparisonActive}
                        id="hil-building"
                        onChange={(event) => setHilBuildingId(event.target.value)}
                        value={hilBuildingId}
                      >
                        {(selectedTemplate?.config.buildings ?? []).map((building) => (
                          <option key={building.building_id} value={building.building_id}>
                            {building.building_id}
                          </option>
                        ))}
                      </select>
                    </>
                  ) : null}
                  <p className="integration-note">
                    HIL commands require a connected laboratory controller. NILM below is estimated
                    from simulated aggregate load, not a physical meter.
                  </p>
                  {integrations ? (
                    <div className="integration-status-list">
                      <span>
                        HIL · {integrations.hil.status.replace(/_/g, " ")}
                        {integrations.hil.fallback_active ? " · Rakshak fallback active" : ""}
                      </span>
                      <span>NILM · simulated estimates</span>
                    </div>
                  ) : null}
                </details>
              </div>
            </details>

            <div className="right-stack">
              <details className={`floating-panel stats-panel${mobilePanel === "stats" ? " mobile-active" : ""}`} open>
              <summary className="panel-summary"><strong>Run summary</strong><span>{visibleBuildings.length} buildings</span></summary>
              <dl className="stats-list">
                <div><dt>Frequency nadir</dt><dd>{formatHz(currentMetricValue("frequency_nadir_hz", measuredNadir))}</dd></div>
                <div><dt>Maximum |RoCoF|</dt><dd>{formatMetric(currentMetricValue("max_rocof_hz_per_s", measuredRoCoF), "Hz/s", 3)}</dd></div>
                <div><dt>Recovery time</dt><dd>{formatDuration(recoveredTime)}</dd></div>
                <div><dt>Buildings blacked out</dt><dd>{blackedOutBuildings} / {visibleBuildings.length}</dd></div>
                <div><dt>Medical devices powered</dt><dd>{poweredMedicalDevices}</dd></div>
                <div><dt>Critical energy not served</dt><dd>{formatMetric(getMetric(metrics, "critical_ens_kwh"), "kWh")}</dd></div>
                <div><dt>Peak sampled demand</dt><dd>{peakDemandPu === null ? "Not available" : `${peakDemandPu.toFixed(3)} pu`}</dd></div>
                <div><dt>Edge mode</dt><dd>{displayScenario?.edge_mode ?? "DISTRIBUTED"}</dd></div>
                <div>
                  <dt>HIL status</dt>
                  <dd>
                    {integrations?.hil.status.replace(/_/g, " ") ??
                      (hilEnabled ? "waiting for run" : "not configured")}
                  </dd>
                </div>
                <div><dt>Feeder trips</dt><dd>{formatMetric(getMetric(metrics, "feeder_trips_count"), "events", 0)}</dd></div>
                <div><dt>Curtailed energy</dt><dd>{formatMetric(curtailedEnergy, "kWh")}</dd></div>
              </dl>
              {runId ? <div className="run-id-line"><span>Run ID</span><code>{runId}</code></div> : null}
              </details>

              <div className={`log-slot${mobilePanel === "log" ? " mobile-active" : ""}`}>
                <EventTimeline events={events} filter={eventFilter} onFilterChange={setEventFilter} />
              </div>
            </div>
            <div className="bottom-dock">
              <details className={`floating-panel charts-panel${mobilePanel === "charts" ? " mobile-active" : ""}`} open>
              <summary className="panel-summary">
                <strong>Frequency response</strong>
                <span>
                  {latestSample
                    ? `${latestSample.frequency_hz.toFixed(2)} Hz · nadir ${measuredNadir?.toFixed(2) ?? "--"} · ${latestSample.frequency_stage.replace(/_/g, " ")}`
                    : "No samples"}
                </span>
              </summary>
              <div className="panel-body">
                <FrequencyChart
                  disturbanceStart={disturbanceStart}
                  events={events}
                  grid={displayScenario?.grid_params ?? null}
                  telemetry={telemetry}
                />
                <div className="frequency-footnote">
                  <span>Nominal {displayScenario?.grid_params.f0_hz.toFixed(2) ?? "50.00"} Hz</span>
                  <span>
                    {latestSample
                      ? `${telemetryIsStale ? `Stale ${telemetryAgeSeconds}s` : isTerminal(runStatus) ? "Final sample" : `Sample ${telemetryAgeSeconds ?? 0}s ago`} · ${latestSample.rocof_hz_per_s.toFixed(3)} Hz/s RoCoF`
                      : "Waiting for telemetry"}
                  </span>
                </div>
                <div className="chart-secondary-readout">
                  <span>Demand / generation</span>
                  <strong>{latestSample ? `${latestSample.demand_pu.toFixed(3)} / ${latestSample.generation_pu.toFixed(3)} pu` : "No sample"}</strong>
                </div>
              </div>
              </details>
              <div className={`building-slot${mobilePanel === "building" ? " mobile-active" : ""}`}>
                <BuildingInspector
                  building={selectedBuilding}
                  events={events.filter(
                    (event) => event.building_id === selectedBuilding?.building_id,
                  )}
                  nilmEstimates={nilmEstimates.filter(
                    (estimate) => estimate.building_id === selectedBuilding?.building_id,
                  )}
                />
              </div>
            </div>
            <button
              className="panel-reset-button"
              type="button"
              onClick={() => setPanelLayoutKey((current) => current + 1)}
            >
              Restore panels
            </button>
          </main>
        </>
      )}
    </div>
  );
}

export default App;
