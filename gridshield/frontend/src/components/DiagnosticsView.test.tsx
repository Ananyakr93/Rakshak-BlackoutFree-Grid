import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { ScenarioConfig, TelemetrySample } from "../types";
import DiagnosticsView from "./DiagnosticsView";

const scenario: ScenarioConfig = {
  scenario_id: "saved-scenario",
  name: "Saved effective config",
  description: "",
  seed: 73,
  simulation_duration_s: 900,
  area_mode: "scaled",
  edge_mode: "CENTRALIZED",
  emulated_feeder_stages: { stage2: ["B12"] },
  disturbance: {
    type: "generation_loss",
    start_time_s: 17,
    magnitude_pu: 0.22,
    duration_s: 41,
    recovery_ramp_s: 30,
    solar_share_pu: null,
  },
  grid_params: {
    f0_hz: 50,
    H: 7,
    D: 1.5,
    R: 0.06,
    deadband_hz: 0.03,
    Tg: 0.2,
    Tt: 0.4,
    up_reserve_pu: 0.2,
    down_reserve_pu: 0.1,
    dt_s: 0.02,
    f_s0_hz: 49.9,
    f_s1_hz: 49.85,
    f_s2_hz: 49.6,
    f_s3_hz: 49.4,
    f_o1_hz: 50.05,
    f_o2_hz: 50.2,
    rocof_s2_threshold: -0.3,
    f_recovery_hz: 49.95,
    t_stable_s: 60,
    t_s0_hold_s: 10,
    t_s1_hold_s: 5,
    t_s2_hold_s: 2,
    t_s3_hold_s: 0,
    t_p1_recovery_s: 120,
    t_o1_hold_s: 30,
  },
  buildings: [],
  fault_config: {
    delay_range_s: [0, 0],
    loss_probability: 0.35,
    duplicate_probability: 0,
    out_of_order: false,
    shuffle_window_size: 5,
  },
};

const telemetry: TelemetrySample = {
  simulation_time_s: 23.5,
  frequency_hz: 49.87,
  generation_pu: 0.94,
  demand_pu: 1.03,
  frequency_stage: "S1",
  rocof_hz_per_s: -0.12,
  sequence_number: 47,
};

describe("run inspector", () => {
  it("shows effective saved run configuration and live telemetry", () => {
    const markup = renderToStaticMarkup(
      <DiagnosticsView
        agents={[]}
        buildings={[]}
        feeder={null}
        integrations={null}
        nilmEvaluation={null}
        nilmSamples={[]}
        restoration={null}
        runId="run-12345678"
        runStatus="running"
        runTimeSeconds={23.5}
        scenario={scenario}
        policy="P1_adms_feeder"
        telemetry={telemetry}
        metrics={[]}
        selectedBuildingId={null}
      />,
    );

    expect(markup).toContain("Saved effective config · 73 · 900s");
    expect(markup).toContain("P1 adms feeder");
    expect(markup).toContain("generation loss · 22% at 17s · 41s");
    expect(markup).toContain("CENTRALIZED · 35%");
    expect(markup).toContain("stage2: B12");
    expect(markup).toContain("49.870 Hz · S1");
    expect(markup).toContain("23.5 s");
  });
});
