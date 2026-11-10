import { useState, type ReactElement } from "react";
import type {
  EdgeAgentSnapshot,
  FeederEstimate,
  NilmEvaluation,
  NilmSignalSample,
  PolicyId,
  RestorationSnapshot,
  RunIntegrations,
  RunMetric,
  ScenarioConfig,
  RunStatus,
  TelemetrySample,
} from "../types";
import type { CityBuilding } from "./CityTwin";
import NilmSignalChart from "./NilmSignalChart";

type DiagnosticsSection =
  | "run"
  | "critical"
  | "edge"
  | "restoration"
  | "nilm"
  | "feeder"
  | "hardware";

const SECTIONS: Array<{ id: DiagnosticsSection; label: string }> = [
  { id: "run", label: "Run inspector" },
  { id: "critical", label: "Medical loads" },
  { id: "edge", label: "Edge agents" },
  { id: "restoration", label: "Restoration" },
  { id: "nilm", label: "NILM" },
  { id: "feeder", label: "Feeder estimates" },
  { id: "hardware", label: "Hardware / HIL" },
];

interface DiagnosticsViewProps {
  buildings: CityBuilding[];
  selectedBuildingId: string | null;
  runId: string | null;
  runTimeSeconds: number;
  runStatus: RunStatus | "idle" | "starting";
  scenario: ScenarioConfig | null;
  policy: PolicyId | null;
  telemetry: TelemetrySample | null;
  metrics: RunMetric[];
  integrations: RunIntegrations | null;
  agents: EdgeAgentSnapshot[];
  restoration: RestorationSnapshot | null;
  feeder: FeederEstimate | null;
  nilmSamples: NilmSignalSample[];
  nilmEvaluation: NilmEvaluation | null;
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(digits)
    : "—";
}

function applianceIsEnergized(state: string): boolean {
  return state === "ON" || state === "RUNNING";
}

export default function DiagnosticsView({
  buildings,
  selectedBuildingId,
  runId,
  runTimeSeconds,
  runStatus,
  scenario,
  policy,
  telemetry,
  metrics,
  integrations,
  agents,
  restoration,
  feeder,
  nilmSamples,
  nilmEvaluation,
}: DiagnosticsViewProps): ReactElement {
  const [section, setSection] = useState<DiagnosticsSection>("run");
  const inspectedBuilding =
    buildings.find((building) => building.building_id === selectedBuildingId) ?? null;
  const inspectedAgent =
    agents.find((agent) => agent.building_id === selectedBuildingId) ?? null;
  const feederAssignments = scenario
    ? Object.entries(scenario.emulated_feeder_stages)
      .flatMap(([stage, buildingIds]) =>
        buildingIds.map((buildingId) => `${stage}: ${buildingId}`),
      )
    : [];
  const medicalBuildings = buildings.filter((building) =>
    building.appliances.some((appliance) => appliance.appliance_type === "medical_device"),
  );
  const criticalOffCount = medicalBuildings.reduce(
    (count, building) =>
      count + building.appliances.filter(
        (appliance) =>
          appliance.appliance_type === "medical_device" &&
          !applianceIsEnergized(appliance.state),
      ).length,
    0,
  );
  const hil = integrations?.hil;
  const medicalInterruption = metrics.find(
    (metric) => metric.metric_name === "medical_load_interruption_s",
  );
  const criticalEns = metrics.find((metric) => metric.metric_name === "critical_ens_kwh");
  const missingMetricLabel =
    runStatus === "completed" ? "Not recorded for this run" : "Computed after run";

  return (
    <main className="systems-view">
      <header className="systems-header">
        <div>
          <span className="eyebrow">SIMULATION DIAGNOSTICS / {runId ? runId.slice(0, 8) : "PRE-RUN"}</span>
          <h2>Resilience systems</h2>
          <p>
            Live twin state and estimates are separated from physical measurements. Select a building
            in the city to focus its appliance and load diagnostics.
          </p>
        </div>
        <span className="systems-time">t = {runTimeSeconds.toFixed(1)} s</span>
      </header>
      <nav className="systems-tabs" aria-label="Resilience system panels">
        {SECTIONS.map((item) => (
          <button
            aria-pressed={section === item.id}
            className={section === item.id ? "active" : ""}
            key={item.id}
            onClick={() => setSection(item.id)}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </nav>

      {section === "run" ? (
        <section className="systems-grid">
          <article className="systems-card systems-card-wide">
            <div className="systems-card-heading">
              <div><span className="eyebrow">EFFECTIVE BACKEND SNAPSHOT</span><h3>Run inspector</h3></div>
              <span className="systems-status">
                {runId ? `${runStatus} · t=${runTimeSeconds.toFixed(1)} s` : "No selected run"}
              </span>
            </div>
            {!scenario || !policy ? (
              <div className="systems-empty">
                {runId
                  ? "Loading the selected run configuration from the backend."
                  : "Start or select a run to inspect its saved configuration and live state."}
              </div>
            ) : (
              <>
                <h4>Saved run configuration</h4>
                <div className="clinical-metrics" aria-label="Saved run configuration">
                  <div><span>Policy</span><strong>{policy.replace(/_/g, " ")}</strong></div>
                  <div><span>Scenario / seed / duration</span><strong>{scenario.name} · {scenario.seed} · {scenario.simulation_duration_s}s</strong></div>
                  <div>
                    <span>Disturbance</span>
                    <strong>
                      {scenario.disturbance.type.replace(/_/g, " ")} ·
                      {" "}{(scenario.disturbance.magnitude_pu * 100).toFixed(0)}% at
                      {" "}{scenario.disturbance.start_time_s}s ·
                      {" "}{scenario.disturbance.duration_s}s
                    </strong>
                  </div>
                  <div><span>Grid response</span><strong>H {scenario.grid_params.H}s · droop {(scenario.grid_params.R * 100).toFixed(1)}% · Tg {scenario.grid_params.Tg}s</strong></div>
                  <div><span>Protection thresholds</span><strong>S0 {scenario.grid_params.f_s0_hz} · S1 {scenario.grid_params.f_s1_hz} · S2 {scenario.grid_params.f_s2_hz} · S3 {scenario.grid_params.f_s3_hz} Hz</strong></div>
                  <div><span>Edge mode / communication loss</span><strong>{scenario.edge_mode ?? "DISTRIBUTED"} · {(scenario.fault_config.loss_probability * 100).toFixed(0)}%</strong></div>
                  <div>
                    <span>Feeder-stage assignments</span>
                    <strong>{feederAssignments.length ? feederAssignments.join(" · ") : "No explicit assignments"}</strong>
                  </div>
                </div>
                <h4>Live simulation state</h4>
                <div className="clinical-metrics" aria-label="Live simulation state">
                  <div><span>Frequency / stage</span><strong>{telemetry ? `${formatNumber(telemetry.frequency_hz, 3)} Hz · ${telemetry.frequency_stage}` : "Awaiting telemetry"}</strong></div>
                  <div><span>Demand / generation</span><strong>{telemetry ? `${formatNumber(telemetry.demand_pu, 3)} / ${formatNumber(telemetry.generation_pu, 3)} pu` : "Awaiting telemetry"}</strong></div>
                  <div><span>RoCoF</span><strong>{telemetry ? `${formatNumber(telemetry.rocof_hz_per_s, 3)} Hz/s` : "Awaiting telemetry"}</strong></div>
                  <div><span>Selected building</span><strong>{inspectedBuilding ? `${inspectedBuilding.building_id} · ${formatNumber(inspectedBuilding.demand_kw, 3)} kW` : "No building selected"}</strong></div>
                  <div><span>Selected edge agent</span><strong>{inspectedAgent ? `${inspectedAgent.operating_mode.replace(/_/g, " ")} · ${inspectedAgent.communication_available ? "connected" : "disconnected"} · ${inspectedAgent.last_decision ?? "monitor"}` : "No edge-agent status"}</strong></div>
                  <div><span>Restoration</span><strong>{restoration ? `${restoration.enabled ? "enabled" : "disabled"} · ${restoration.frozen ? "safety-frozen" : "active"} · ${restoration.queue.length} queued` : "Not available"}</strong></div>
                </div>
                <p className="systems-caveat">
                  Configuration values come from the selected run snapshot; live readings come from its telemetry and state stream.
                </p>
              </>
            )}
          </article>
        </section>
      ) : null}

      {section === "critical" ? (
        <section className="systems-grid">
          <article className="systems-card systems-card-wide">
            <div className="systems-card-heading">
              <div><span className="eyebrow">CLINICAL CONTINUITY</span><h3>Medical-priority appliances</h3></div>
              <span className={`systems-status${criticalOffCount ? " warning" : ""}`}>
                {medicalBuildings.length} care assets · {criticalOffCount} critical loads off
              </span>
            </div>
            {medicalBuildings.length ? (
              <div className="systems-table-wrap">
                <table className="systems-table">
                  <thead><tr><th>Building</th><th>Appliance</th><th>State</th><th>Power</th><th>Priority</th></tr></thead>
                  <tbody>
                    {medicalBuildings.flatMap((building) =>
                      building.appliances
                        .filter((appliance) =>
                          appliance.appliance_type === "medical_device" ||
                          appliance.appliance_type === "inverter_backed_load" ||
                          appliance.priority === "critical",
                        )
                        .map((appliance) => (
                          <tr
                            className={building.building_id === selectedBuildingId ? "selected-row" : ""}
                            key={`${building.building_id}-${appliance.appliance_id}`}
                          >
                            <td>{building.building_id}</td>
                            <td>{appliance.appliance_type.replace(/_/g, " ")}</td>
                            <td><span className={`system-state ${applianceIsEnergized(appliance.state) ? "good" : "bad"}`}>{appliance.state.replace(/_/g, " ")}</span></td>
                            <td>{formatNumber(appliance.current_power_kw, 3)} kW</td>
                            <td>{appliance.priority}</td>
                          </tr>
                        )),
                    )}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="systems-empty">This scenario has no explicitly modeled medical-device loads.</div>
            )}
            <p className="systems-caveat">
              This view reports the virtual appliance state. It is not a patient monitor and does not
              certify uninterrupted clinical power.
            </p>
            <div className="clinical-metrics" aria-label="Clinical continuity metrics">
              <div>
                <span>Medical-device interruption</span>
                <strong>
                  {medicalInterruption
                    ? `${formatNumber(medicalInterruption.metric_value, 1)} device-s`
                    : missingMetricLabel}
                </strong>
              </div>
              <div>
                <span>Critical energy not served</span>
                <strong>
                  {criticalEns
                    ? `${formatNumber(criticalEns.metric_value, 3)} kWh`
                    : missingMetricLabel}
                </strong>
              </div>
              <div>
                <span>Backup supply</span>
                <strong>Not modeled</strong>
              </div>
            </div>
          </article>
        </section>
      ) : null}

      {section === "edge" ? (
        <section className="systems-grid">
          <article className="systems-card systems-card-wide">
            <div className="systems-card-heading">
              <div><span className="eyebrow">DISTRIBUTED CONTROL</span><h3>Building edge agents</h3></div>
              <span className="systems-status">{agents.length ? `${agents.length} active agents` : "No active edge-agent telemetry"}</span>
            </div>
            {agents.length ? (
              <div className="systems-table-wrap">
                <table className="systems-table">
                  <thead><tr><th>Agent</th><th>Mode</th><th>Link</th><th>Evaluations</th><th>Last decision</th><th>Decision basis</th></tr></thead>
                  <tbody>
                    {agents.map((agent) => (
                      <tr key={agent.building_id}>
                        <td>{agent.building_id}</td>
                        <td>{agent.operating_mode.replace(/_/g, " ")}</td>
                        <td><span className={`system-state ${agent.communication_available ? "good" : "bad"}`}>{agent.communication_available ? "connected" : "degraded"}</span></td>
                        <td>{agent.evaluations}</td>
                        <td>{agent.last_decision?.replace(/_/g, " ") ?? "Awaiting first tick"}</td>
                        <td className="reason-cell">{agent.last_decision_reason ?? "No decision recorded yet."}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="systems-empty">
                Start a P2 simulation to inspect per-building edge decisions. P0/P1 use their
                configured centralized baseline behavior.
              </div>
            )}
          </article>
        </section>
      ) : null}

      {section === "restoration" ? (
        <section className="systems-grid">
          <article className="systems-card systems-card-wide">
            <div className="systems-card-heading">
              <div><span className="eyebrow">SAFETY-GATED RE-ENERGIZATION</span><h3>Restoration queue</h3></div>
              <span className={`systems-status${restoration?.frozen ? " warning" : ""}`}>
                {restoration?.enabled
                  ? restoration.frozen ? "Frozen after frequency relapse" : "Policy active"
                  : "Not enabled for this mode"}
              </span>
            </div>
            {restoration?.enabled ? (
              <>
                <div className="gate-strip">
                  <div><span>Current frequency</span><strong>{formatNumber(restoration.frequency_hz, 3)} Hz</strong></div>
                  <div><span>Recovery gate</span><strong>≥ {formatNumber(restoration.frequency_gate_hz, 3)} Hz</strong></div>
                  <div><span>Stable timer</span><strong>{formatNumber(restoration.stable_timer_s, 1)} / {formatNumber(restoration.required_stability_s, 1)} s</strong></div>
                  <div><span>Projection floor</span><strong>≥ {formatNumber(restoration.projection_floor_hz, 3)} Hz</strong></div>
                </div>
                {restoration.queue.length ? (
                  <div className="systems-table-wrap">
                    <table className="systems-table">
                      <thead><tr><th>Building / appliance</th><th>Priority</th><th>Stagger</th><th>Eligible at</th><th>Projected f</th><th>Gate</th></tr></thead>
                      <tbody>
                        {restoration.queue.map((item) => (
                          <tr key={`${item.building_id}-${item.appliance_id}`}>
                            <td>{item.building_id} / {item.appliance_type.replace(/_/g, " ")}</td>
                            <td>{item.priority}</td>
                            <td>{formatNumber(item.stagger_delay_s, 1)} s</td>
                            <td>t = {formatNumber(item.eligible_at_s, 1)} s</td>
                            <td>{formatNumber(item.projected_frequency_hz, 3)} Hz</td>
                            <td><span className={`system-state ${item.ready ? "good" : "waiting"}`}>{item.ready ? "ready" : "held"}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : <div className="systems-empty">No appliances are currently waiting for restoration.</div>}
              </>
            ) : (
              <div className="systems-empty">
                Choose a policy with restoration enabled to see its queue. In the no-restoration
                comparison mode, shed loads intentionally remain off for the rest of the run.
              </div>
            )}
            <p className="systems-caveat">Projected frequency is a first-order policy guard, not a validated network stability prediction.</p>
          </article>
        </section>
      ) : null}

      {section === "nilm" ? (
        <section className="systems-grid">
          <article className="systems-card systems-card-wide">
            <div className="systems-card-heading">
              <div><span className="eyebrow">NON-INTRUSIVE LOAD MONITORING</span><h3>Aggregate signal &amp; step estimates</h3></div>
              <span className="systems-status">Model-derived · not a physical meter</span>
            </div>
            <NilmSignalChart samples={nilmSamples} buildingId={selectedBuildingId} />
            {nilmEvaluation ? (
              <div className="metric-strip">
                <div><span>Precision</span><strong>{(nilmEvaluation.precision * 100).toFixed(1)}%</strong></div>
                <div><span>Recall</span><strong>{(nilmEvaluation.recall * 100).toFixed(1)}%</strong></div>
                <div><span>F1</span><strong>{(nilmEvaluation.f1_score * 100).toFixed(1)}%</strong></div>
                <div><span>Matched transitions</span><strong>{nilmEvaluation.true_positive}</strong></div>
                <div><span>Missed / extra</span><strong>{nilmEvaluation.false_negative} / {nilmEvaluation.false_positive}</strong></div>
              </div>
            ) : (
              <div className="systems-empty">NILM evaluation becomes available after a run produces signal samples.</div>
            )}
            <p className="systems-caveat">
              Evaluation compares the signature detector against simulated appliance-state changes
              for this run; it is not field accuracy or an independent meter validation.
            </p>
          </article>
        </section>
      ) : null}

      {section === "feeder" ? (
        <section className="systems-grid">
          <article className="systems-card systems-card-wide">
            <div className="systems-card-heading">
              <div><span className="eyebrow">REDUCED-ORDER NETWORK VIEW</span><h3>Branch load &amp; current estimates</h3></div>
              <span className="systems-status">Not live electrical measurements</span>
            </div>
            {feeder ? (
              <>
                <div className="metric-strip">
                  <div><span>Total served load</span><strong>{formatNumber(feeder.total_active_power_kw)} kW</strong></div>
                  <div><span>Assumed line voltage</span><strong>{formatNumber(feeder.nominal_line_voltage_v, 0)} V</strong></div>
                  <div><span>Assumed power factor</span><strong>{formatNumber(feeder.assumed_power_factor, 2)}</strong></div>
                </div>
                <div className="systems-table-wrap">
                  <table className="systems-table">
                    <thead><tr><th>Branch / building</th><th>Served active load</th><th>Estimated 3-phase current</th></tr></thead>
                    <tbody>
                      {feeder.branches.map((branch) => (
                        <tr className={branch.building_id === selectedBuildingId ? "selected-row" : ""} key={branch.building_id}>
                          <td>{branch.building_id}</td>
                          <td>{formatNumber(branch.active_power_kw, 3)} kW</td>
                          <td>{formatNumber(branch.estimated_current_a, 2)} A</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : <div className="systems-empty">Start a run to calculate branch-load estimates from served appliance power.</div>}
            <p className="systems-caveat">
              Estimates assume balanced three-phase 400 V and 0.95 power factor. The current model
              does not solve feeder impedance, voltage drop, reactive power, or short-circuit behavior.
            </p>
          </article>
        </section>
      ) : null}

      {section === "hardware" ? (
        <section className="systems-grid">
          <article className="systems-card systems-card-wide">
            <div className="systems-card-heading">
              <div><span className="eyebrow">OPTIONAL SERIAL CONTROLLER</span><h3>Hardware-in-the-loop status</h3></div>
              <span className={`systems-status${hil?.status === "connected" ? "" : " warning"}`}>
                {hil?.status.replace(/_/g, " ") ?? "not configured"}
              </span>
            </div>
            <div className="metric-strip">
              <div><span>Target building</span><strong>{hil?.building_id ?? "—"}</strong></div>
              <div><span>Fallback</span><strong>{hil ? hil.fallback_active ? "Rakshak active" : "Not active" : "—"}</strong></div>
              <div><span>Last feedback latency</span><strong>{hil?.last_feedback_latency_ms == null ? "—" : `${formatNumber(hil.last_feedback_latency_ms, 1)} ms`}</strong></div>
              <div><span>Heartbeat age</span><strong>{hil?.heartbeat_age_s == null ? "—" : `${formatNumber(hil.heartbeat_age_s, 1)} s`}</strong></div>
              <div><span>Controller status</span><strong>{hil?.controller_status ?? "No feedback"}</strong></div>
              <div><span>RX / TX</span><strong>{hil ? `${hil.received_messages} / ${hil.transmitted_messages}` : "—"}</strong></div>
              <div><span>Last sequence</span><strong>{hil?.last_feedback_sequence ?? "—"}</strong></div>
            </div>
            <h4>Acknowledged appliance states</h4>
            {hil && Object.keys(hil.acknowledged_appliance_states).length ? (
              <ul className="acknowledged-states">
                {Object.entries(hil.acknowledged_appliance_states).map(([applianceId, state]) => (
                  <li key={applianceId}><span>{applianceId}</span><strong>{state.replace(/_/g, " ")}</strong></li>
                ))}
              </ul>
            ) : (
              <div className="systems-empty">No valid controller state acknowledgement has been received.</div>
            )}
            <p className="systems-caveat">
              A connected status requires a recent valid device heartbeat. Until then this panel reports
              configuration or waiting state only; no physical relay operation is claimed.
            </p>
          </article>
        </section>
      ) : null}
    </main>
  );
}
