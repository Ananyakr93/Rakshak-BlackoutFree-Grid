import type { EdgeMode, ScenarioConfig } from "./types";

export interface ScenarioTuning {
  generationLossPercent: number;
  recoveryRampSeconds: number;
  inertiaSeconds: number;
  disturbanceStartSeconds?: number;
  simulationDurationSeconds?: number;
  governorDroopPercent?: number;
  governorTimeConstantSeconds?: number;
  s1ThresholdHz?: number;
  s2ThresholdHz?: number;
  s0HoldSeconds?: number;
  s1HoldSeconds?: number;
  s2HoldSeconds?: number;
  s3HoldSeconds?: number;
  p1RecoveryHoldSeconds?: number;
  o1HoldSeconds?: number;
  restorationStableSeconds?: number;
  disturbanceType?: ScenarioConfig["disturbance"]["type"];
  solarSharePercent?: number;
  edgeMode?: EdgeMode;
  communicationLossPercent?: number;
}

export function withScenarioTuning(
  scenario: ScenarioConfig,
  seed: number,
  tuning: ScenarioTuning,
): ScenarioConfig {
  if (!Number.isInteger(seed) || seed < 0) {
    throw new RangeError("Seed must be a non-negative integer.");
  }
  if (
    !Number.isFinite(tuning.generationLossPercent) ||
    tuning.generationLossPercent <= 0 ||
    tuning.generationLossPercent > 100
  ) {
    throw new RangeError("Generation loss must be between 0 and 100 percent.");
  }
  if (!Number.isFinite(tuning.recoveryRampSeconds) || tuning.recoveryRampSeconds < 0) {
    throw new RangeError("Recovery ramp must not be negative.");
  }
  if (!Number.isFinite(tuning.inertiaSeconds) || tuning.inertiaSeconds <= 0) {
    throw new RangeError("Inertia must be positive.");
  }
  const disturbanceStart = tuning.disturbanceStartSeconds ?? scenario.disturbance.start_time_s;
  const duration = tuning.simulationDurationSeconds ?? scenario.simulation_duration_s;
  const droopPercent = tuning.governorDroopPercent ?? scenario.grid_params.R * 100;
  const governorTimeConstant =
    tuning.governorTimeConstantSeconds ?? scenario.grid_params.Tg ?? 0.1;
  const s1Threshold = tuning.s1ThresholdHz ?? scenario.grid_params.f_s1_hz;
  const s2Threshold = tuning.s2ThresholdHz ?? scenario.grid_params.f_s2_hz;
  const communicationLossPercent =
    tuning.communicationLossPercent ?? scenario.fault_config.loss_probability * 100;
  const disturbanceType = tuning.disturbanceType ?? scenario.disturbance.type;
  const solarSharePercent =
    tuning.solarSharePercent ?? (scenario.disturbance.solar_share_pu ?? 0.4) * 100;
  const protectionHolds = {
    t_s0_hold_s: tuning.s0HoldSeconds ?? scenario.grid_params.t_s0_hold_s ?? 10,
    t_s1_hold_s: tuning.s1HoldSeconds ?? scenario.grid_params.t_s1_hold_s ?? 5,
    t_s2_hold_s: tuning.s2HoldSeconds ?? scenario.grid_params.t_s2_hold_s ?? 2,
    t_s3_hold_s: tuning.s3HoldSeconds ?? scenario.grid_params.t_s3_hold_s ?? 0,
    t_p1_recovery_s:
      tuning.p1RecoveryHoldSeconds ?? scenario.grid_params.t_p1_recovery_s ?? 120,
    t_o1_hold_s: tuning.o1HoldSeconds ?? scenario.grid_params.t_o1_hold_s ?? 30,
    t_stable_s:
      tuning.restorationStableSeconds ?? scenario.grid_params.t_stable_s,
  };
  if (!Number.isFinite(disturbanceStart) || disturbanceStart < 0) {
    throw new RangeError("Disturbance start time must be non-negative.");
  }
  if (!Number.isFinite(duration) || duration <= disturbanceStart) {
    throw new RangeError("Simulation duration must be later than the disturbance start.");
  }
  if (!Number.isFinite(droopPercent) || droopPercent <= 0 || droopPercent > 20) {
    throw new RangeError("Governor droop must be between 0 and 20 percent.");
  }
  if (!Number.isFinite(governorTimeConstant) || governorTimeConstant <= 0) {
    throw new RangeError("Governor response time must be positive.");
  }
  if (
    !Number.isFinite(s1Threshold) ||
    !Number.isFinite(s2Threshold) ||
    s1Threshold <= s2Threshold ||
    s2Threshold <= scenario.grid_params.f_s3_hz
  ) {
    throw new RangeError("Protection thresholds must be ordered S1 > S2 > S3.");
  }
  if (
    !Number.isFinite(communicationLossPercent) ||
    communicationLossPercent < 0 ||
    communicationLossPercent > 100
  ) {
    throw new RangeError("Communication loss must be between 0 and 100 percent.");
  }
  if (
    disturbanceType === "solar_cloud_drop" &&
    (!Number.isFinite(solarSharePercent) ||
      solarSharePercent <= 0 ||
      solarSharePercent > 100)
  ) {
    throw new RangeError("Solar share must be between 0 and 100 percent for a cloud dip.");
  }
  if (
    Object.values(protectionHolds).some((seconds) => !Number.isFinite(seconds) || seconds < 0) ||
    protectionHolds.t_stable_s <= 0
  ) {
    throw new RangeError(
      "Protection holds must be non-negative and restoration stability must be positive.",
    );
  }

  return {
    ...scenario,
    seed,
    simulation_duration_s: duration,
    disturbance: {
      ...scenario.disturbance,
      type: disturbanceType,
      magnitude_pu: tuning.generationLossPercent / 100,
      recovery_ramp_s: tuning.recoveryRampSeconds,
      start_time_s: disturbanceStart,
      solar_share_pu:
        disturbanceType === "solar_cloud_drop" ? solarSharePercent / 100 : null,
    },
    grid_params: {
      ...scenario.grid_params,
      H: tuning.inertiaSeconds,
      R: droopPercent / 100,
      Tg: governorTimeConstant,
      f_s1_hz: s1Threshold,
      f_s2_hz: s2Threshold,
      ...protectionHolds,
    },
    edge_mode: tuning.edgeMode ?? scenario.edge_mode ?? "DISTRIBUTED",
    fault_config: {
      ...scenario.fault_config,
      loss_probability: communicationLossPercent / 100,
    },
  };
}
