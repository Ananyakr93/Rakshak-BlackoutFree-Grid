export type Priority = "critical" | "essential" | "deferrable";
export type ApplianceState = "ON" | "RUNNING" | "OFF" | "SHED" | "WAITING_RESTORATION" | "LOCKED_OUT" | "UNAVAILABLE";
export type PolicyId =
  | "P0_unmanaged"
  | "P1_adms_feeder"
  | "P2_priority_edge"
  | "P2_priority_edge_synchronized"
  | "P3_priority_edge_no_restoration";
export type RunStatus = "pending" | "running" | "paused" | "completed" | "failed";
export type EdgeMode =
  | "CENTRALIZED"
  | "DISTRIBUTED"
  | "COMMUNICATION_DEGRADED"
  | "ISLANDED_AUTONOMOUS";

export interface ApplianceConfig {
  appliance_id: string;
  appliance_type: string;
  priority: Priority;
  rated_power_kw: number;
  min_on_time_s: number;
  min_off_time_s: number;
  max_shed_minutes: number | null;
  enrolled: boolean;
  initial_state: "ON" | "OFF";
  compressor_lockout_s: number | null;
  inrush_multiplier: number | null;
  inrush_duration_s: number | null;
  startup_recovery_profile: "linear" | "exponential";
}

export interface ScenarioBuildingConfig {
  building_id: string;
  weight_k: number;
  appliances: ApplianceConfig[];
}

export interface GridParameters {
  f0_hz: number;
  H: number;
  D: number;
  R: number;
  deadband_hz: number;
  Tg: number;
  Tt: number;
  up_reserve_pu: number;
  down_reserve_pu: number;
  dt_s: number;
  f_s0_hz: number;
  f_s1_hz: number;
  f_s2_hz: number;
  f_s3_hz: number;
  f_o1_hz: number;
  f_o2_hz: number;
  rocof_s2_threshold: number;
  f_recovery_hz: number;
  t_stable_s: number;
  t_s0_hold_s: number;
  t_s1_hold_s: number;
  t_s2_hold_s: number;
  t_s3_hold_s: number;
  t_p1_recovery_s: number;
  t_o1_hold_s: number;
}

export interface ScenarioConfig {
  scenario_id: string;
  name: string;
  description: string;
  seed: number;
  simulation_duration_s: number;
  area_mode: "scaled" | "islanded";
  edge_mode: EdgeMode;
  disturbance: {
    type: "generation_loss" | "demand_surge" | "combined" | "solar_surplus" | "solar_cloud_drop";
    start_time_s: number;
    magnitude_pu: number;
    duration_s: number;
    recovery_ramp_s: number;
    solar_share_pu: number | null;
  };
  grid_params: GridParameters;
  buildings: ScenarioBuildingConfig[];
  emulated_feeder_stages: Partial<Record<"stage1" | "stage2" | "stage3", string[]>>;
  fault_config: {
    delay_range_s: [number, number];
    loss_probability: number;
    duplicate_probability: number;
    out_of_order: boolean;
    shuffle_window_size: number;
  };
}

export interface ScenarioTemplate {
  template_id: string;
  name: string;
  description: string;
  config: ScenarioConfig;
}

export interface RunRecord {
  run_id: string;
  scenario_id: string;
  scenario_name: string;
  policy: PolicyId;
  seed: number;
  status: RunStatus;
  started_at: string;
}

export interface RunSnapshot {
  run_id: string;
  scenario_id: string;
  scenario: ScenarioConfig;
  policy: PolicyId;
  seed: number;
  status: RunStatus;
  current_time_s: number;
  active_buildings: number;
  latest_frequency_hz: number | null;
  playback_speed: number | null;
  is_paused: boolean;
}

export interface NilmEstimate {
  simulation_time_s: number;
  building_id: string;
  delta_power_kw: number;
  event_type: "switch_on" | "switch_off";
  appliance_type: string | null;
  confidence: number;
  classification: "classified" | "ambiguous" | "unknown";
  source: "simulated_aggregate_load";
}

export interface RunIntegrations {
  hil: {
    status: "connected" | "waiting_for_heartbeat" | "not_configured";
    building_id: string | null;
    fallback_active: boolean;
    received_messages: number;
    transmitted_messages: number;
    last_feedback_latency_ms: number | null;
    heartbeat_age_s: number | null;
    controller_status: string | null;
    acknowledged_appliance_states: Record<string, string>;
    last_feedback_sequence: number | null;
  };
  nilm: {
    status: "simulated_estimates" | "unavailable";
    source: "simulated_aggregate_load";
  };
}

export interface TelemetrySample {
  run_id?: string;
  simulation_time_s: number;
  frequency_hz: number;
  generation_pu: number;
  demand_pu: number;
  generation_disturbance_pu?: number;
  demand_disturbance_pu?: number;
  frequency_stage: string;
  rocof_hz_per_s: number;
  sequence_number: number;
}

export interface RunEvent {
  event_id: string;
  simulation_time_s: number;
  event_type: string;
  building_id: string;
  appliance_id: string | null;
  reason: string;
  frequency_hz: number;
  priority: Priority | null;
}

export interface RunMetric {
  metric_name: string;
  metric_value: number;
  unit: string;
  notes: string | null;
}

export interface ApplianceSnapshot {
  appliance_id: string;
  appliance_type: string;
  priority: Priority;
  rated_power_kw: number;
  enrolled: boolean;
  state: ApplianceState;
  current_power_kw: number;
  lockout_remaining_s?: number;
}

export interface BuildingSnapshot {
  run_id: string;
  building_id: string;
  weight_k: number;
  demand_kw: number;
  simulation_time_s: number;
  sequence_number: number;
  updated_at: string | null;
  appliances: ApplianceSnapshot[];
}

export interface BuildingStateUpdate {
  type: "building_state_update";
  schema_version: "1.0";
  run_id: string;
  building_id: string;
  appliance_id: string;
  appliance_type: string;
  priority: Priority;
  previous_state: ApplianceState;
  current_state: ApplianceState;
  current_power_kw: number;
  rated_power_kw: number;
  simulation_time_s: number;
  sequence_number: number;
  updated_at: string;
}

export interface SavedPolicySummary {
  policy_name: PolicyId;
  n_seeds: number;
  mean_nadir_hz: number;
  std_nadir_hz: number;
  ci95_nadir: [number, number];
  mean_recovery_time_s: number | null;
  mean_critical_ens_kwh: number;
  mean_feeder_trips: number;
  mean_jains_index: number;
  raw_metrics: Array<Record<string, number>>;
}

export interface SavedExperimentResults {
  experiment_id: string;
  scenario_name: string;
  created_at: string;
  schema_version: string;
  summary: Partial<Record<PolicyId, SavedPolicySummary>>;
}

export interface LiveComparisonSummary {
  policy_name: PolicyId;
  n_seeds: number;
  mean_nadir_hz: number;
  mean_max_rocof_hz_per_s: number;
  std_nadir_hz: number;
  ci95_nadir: [number, number];
  mean_recovery_time_s: number | null;
  mean_critical_ens_kwh: number;
  mean_medical_load_interruption_s: number;
  mean_feeder_trips: number;
  mean_rebound_peak_pu: number;
  mean_jains_index: number;
  raw_metrics: Array<Record<string, number>>;
}

export interface LiveComparisonResponse {
  scenario_name: string;
  base_seed: number;
  n_seeds: number;
  seed_range: [number, number];
  source: "paired_simulation";
  summary: Partial<Record<PolicyId, LiveComparisonSummary>>;
  frequency_trajectories: Partial<Record<PolicyId, TelemetrySample[]>>;
}

export interface EdgeAgentSnapshot {
  building_id: string;
  operating_mode: string;
  communication_available: boolean;
  evaluations: number;
  last_decision: string | null;
  last_decision_reason: string | null;
  last_decision_time_s: number | null;
  autonomous: boolean;
}

export interface RestorationQueueItem {
  building_id: string;
  appliance_id: string;
  appliance_type: string;
  priority: Priority;
  waiting_since_s: number;
  stagger_delay_s: number;
  eligible_at_s: number;
  estimated_pickup_kw: number;
  projected_frequency_hz: number;
  capacity_supported: boolean;
  ready: boolean;
}

export interface RestorationSnapshot {
  enabled: boolean;
  frozen: boolean;
  frequency_hz: number;
  frequency_gate_hz: number;
  freeze_below_hz: number;
  projection_floor_hz: number;
  stable_timer_s: number;
  required_stability_s: number;
  stagger_enabled: boolean;
  available_generation_pu: number;
  headroom_kw: number;
  completed: boolean;
  queue: RestorationQueueItem[];
}

export interface FeederBranchEstimate {
  building_id: string;
  active_power_kw: number;
  estimated_current_a: number;
}

export interface FeederEstimate {
  source: "simulated_load_estimate";
  nominal_line_voltage_v: number;
  assumed_power_factor: number;
  total_active_power_kw: number;
  branches: FeederBranchEstimate[];
}

export interface NilmSignalSample {
  simulation_time_s: number;
  building_id: string;
  aggregate_power_kw: number;
  ground_truth_changes: Array<{
    appliance_id: string;
    appliance_type: string;
    event_type: "switch_on" | "switch_off";
  }>;
  estimated_changes: Array<{
    delta_power_kw: number;
    event_type: "switch_on" | "switch_off";
    appliance_type: string | null;
    confidence: number;
    classification: "classified" | "ambiguous" | "unknown";
  }>;
  source: "simulated_aggregate_load";
}

export interface NilmEvaluation {
  source: "simulated_aggregate_load_vs_twin_state";
  true_positive: number;
  false_positive: number;
  false_negative: number;
  precision: number;
  recall: number;
  f1_score: number;
}
