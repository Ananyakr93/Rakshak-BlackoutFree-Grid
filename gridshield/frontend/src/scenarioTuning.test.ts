import { describe, expect, it } from "vitest";
import { withScenarioTuning } from "./scenarioTuning";
import type { ScenarioConfig } from "./types";

const scenario = {
  seed: 1,
  name: "test",
  description: "",
  scenario_id: "scenario",
  simulation_duration_s: 30,
  area_mode: "scaled",
  edge_mode: "DISTRIBUTED",
  disturbance: {
    type: "generation_loss",
    start_time_s: 2,
    magnitude_pu: 0.1,
    duration_s: 20,
    recovery_ramp_s: 5,
    solar_share_pu: null,
  },
  grid_params: {
    f0_hz: 50,
    H: 4,
    D: 1.5,
    R: 0.05,
    deadband_hz: 0.03,
    Tg: 0.1,
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
  emulated_feeder_stages: { stage1: ["B1"] },
  fault_config: {
    delay_range_s: [0, 0],
    loss_probability: 0,
    duplicate_probability: 0,
    out_of_order: false,
    shuffle_window_size: 5,
  },
} as ScenarioConfig;

describe("scenario tuning", () => {
  it("applies requested values without mutating the selected preset", () => {
    const tuned = withScenarioTuning(scenario, 18, {
      generationLossPercent: 22,
      recoveryRampSeconds: 45,
      inertiaSeconds: 5,
    });

    expect(tuned.seed).toBe(18);
    expect(tuned.disturbance.magnitude_pu).toBe(0.22);
    expect(tuned.disturbance.recovery_ramp_s).toBe(45);
    expect(tuned.grid_params.H).toBe(5);
    expect(scenario.disturbance.magnitude_pu).toBe(0.1);
    expect(scenario.grid_params.H).toBe(4);
  });

  it("rejects unsafe or invalid tuning values", () => {
    expect(() => withScenarioTuning(scenario, -1, {
      generationLossPercent: 20,
      recoveryRampSeconds: 45,
      inertiaSeconds: 5,
    })).toThrow(RangeError);
  });

  it("applies exposure time, governor, protection, and edge communication settings", () => {
    const tuned = withScenarioTuning(scenario, 18, {
      generationLossPercent: 22,
      recoveryRampSeconds: 45,
      inertiaSeconds: 5,
      disturbanceStartSeconds: 15,
      simulationDurationSeconds: 240,
      governorDroopPercent: 6,
      governorTimeConstantSeconds: 0.25,
      s1ThresholdHz: 49.88,
      s2ThresholdHz: 49.65,
      s0HoldSeconds: 12,
      s1HoldSeconds: 4,
      s2HoldSeconds: 3,
      s3HoldSeconds: 1,
      p1RecoveryHoldSeconds: 90,
      o1HoldSeconds: 25,
      restorationStableSeconds: 45,
      edgeMode: "ISLANDED_AUTONOMOUS",
      communicationLossPercent: 15,
    });

    expect(tuned.disturbance.start_time_s).toBe(15);
    expect(tuned.simulation_duration_s).toBe(240);
    expect(tuned.grid_params.R).toBe(0.06);
    expect(tuned.grid_params.Tg).toBe(0.25);
    expect(tuned.grid_params.f_s1_hz).toBe(49.88);
    expect(tuned.grid_params.f_s2_hz).toBe(49.65);
    expect(tuned.grid_params.t_s0_hold_s).toBe(12);
    expect(tuned.grid_params.t_s1_hold_s).toBe(4);
    expect(tuned.grid_params.t_s2_hold_s).toBe(3);
    expect(tuned.grid_params.t_s3_hold_s).toBe(1);
    expect(tuned.grid_params.t_p1_recovery_s).toBe(90);
    expect(tuned.grid_params.t_o1_hold_s).toBe(25);
    expect(tuned.grid_params.t_stable_s).toBe(45);
    expect(tuned.edge_mode).toBe("ISLANDED_AUTONOMOUS");
    expect(tuned.fault_config.loss_probability).toBe(0.15);
  });

  it("rejects incorrectly ordered protection thresholds", () => {
    expect(() => withScenarioTuning(scenario, 1, {
      generationLossPercent: 20,
      recoveryRampSeconds: 30,
      inertiaSeconds: 4,
      s1ThresholdHz: 49.5,
      s2ThresholdHz: 49.6,
    })).toThrow(RangeError);
  });

  it("rejects invalid restoration timing", () => {
    expect(() => withScenarioTuning(scenario, 1, {
      generationLossPercent: 20,
      recoveryRampSeconds: 30,
      inertiaSeconds: 4,
      restorationStableSeconds: 0,
    })).toThrow(RangeError);
  });

  it("applies solar cloud dips to the configured share of area generation", () => {
    const tuned = withScenarioTuning(
      {
        ...scenario,
        disturbance: { ...scenario.disturbance, solar_share_pu: 0.4 },
      },
      1,
      {
        generationLossPercent: 30,
        recoveryRampSeconds: 30,
        inertiaSeconds: 4,
        disturbanceType: "solar_cloud_drop",
        solarSharePercent: 40,
      },
    );

    expect(tuned.disturbance.magnitude_pu).toBe(0.3);
    expect(tuned.disturbance.solar_share_pu).toBe(0.4);
  });

  it("preserves backend contract fields when applying UI tuning", () => {
    const tuned = withScenarioTuning(scenario, 2, {
      generationLossPercent: 20,
      recoveryRampSeconds: 30,
      inertiaSeconds: 4,
    });

    expect(tuned.grid_params.deadband_hz).toBe(0.03);
    expect(tuned.grid_params.Tt).toBe(0.4);
    expect(tuned.grid_params.up_reserve_pu).toBe(0.2);
    expect(tuned.grid_params.down_reserve_pu).toBe(0.1);
    expect(tuned.grid_params.dt_s).toBe(0.02);
    expect(tuned.grid_params.rocof_s2_threshold).toBe(-0.3);
    expect(tuned.emulated_feeder_stages.stage1).toEqual(["B1"]);
  });

  it("rejects a solar cloud dip without a valid PV share", () => {
    expect(() => withScenarioTuning(scenario, 1, {
      generationLossPercent: 30,
      recoveryRampSeconds: 30,
      inertiaSeconds: 4,
      disturbanceType: "solar_cloud_drop",
      solarSharePercent: 0,
    })).toThrow(RangeError);
  });
});
