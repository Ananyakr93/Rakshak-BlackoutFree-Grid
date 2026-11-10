"""Typed HTTP response contracts for the REST API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.scenario import ScenarioConfig
from app.schemas.telemetry import TelemetrySample

PolicyName = Literal[
    "P0_unmanaged",
    "P1_adms_feeder",
    "P2_priority_edge",
    "P2_priority_edge_synchronized",
    "P3_priority_edge_no_restoration",
]
RunStatus = Literal["pending", "running", "paused", "completed", "failed"]

class APIResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioCreatedResponse(APIResponse):
    scenario_id: uuid.UUID
    name: str


class ScenarioSummaryResponse(APIResponse):
    scenario_id: uuid.UUID
    name: str
    created_at: datetime


class ScenarioTemplateResponse(APIResponse):
    template_id: str
    name: str
    description: str
    config: ScenarioConfig


class ScenarioDetailsResponse(APIResponse):
    scenario_id: uuid.UUID
    name: str
    config: str


class RunHistoryResponse(APIResponse):
    run_id: uuid.UUID
    scenario_id: uuid.UUID
    scenario_name: str
    policy: PolicyName
    seed: int
    status: RunStatus
    started_at: datetime


class RunSnapshotResponse(APIResponse):
    run_id: uuid.UUID
    status: RunStatus
    playback_speed: float | None
    is_paused: bool
    current_time_s: float
    active_buildings: int
    latest_frequency_hz: float | None
    scenario_id: uuid.UUID
    scenario: ScenarioConfig
    policy: PolicyName
    seed: int


class HILIntegrationResponse(APIResponse):
    status: str
    building_id: str | None
    fallback_active: bool
    received_messages: int
    transmitted_messages: int
    last_feedback_latency_ms: float | None
    heartbeat_age_s: float | None
    controller_status: str | None
    acknowledged_appliance_states: dict[str, str]
    last_feedback_sequence: int | None


class NILMIntegrationResponse(APIResponse):
    status: str
    source: str


class RunIntegrationsResponse(APIResponse):
    hil: HILIntegrationResponse
    nilm: NILMIntegrationResponse


class RunAgentResponse(APIResponse):
    building_id: str
    operating_mode: str
    communication_available: bool
    evaluations: int
    last_decision: str | None
    last_decision_reason: str | None
    last_decision_time_s: float | None
    autonomous: bool


class RestorationQueueItemResponse(APIResponse):
    building_id: str
    appliance_id: str
    appliance_type: str
    priority: str
    state: str
    lockout_remaining_s: float
    waiting_since_s: float
    stagger_delay_s: float
    eligible_at_s: float
    estimated_pickup_kw: float
    projected_frequency_hz: float
    capacity_supported: bool
    ready: bool


class RestorationStatusResponse(APIResponse):
    enabled: bool
    frozen: bool
    frequency_hz: float
    frequency_gate_hz: float
    freeze_below_hz: float
    projection_floor_hz: float
    stable_timer_s: float
    required_stability_s: float
    stagger_enabled: bool
    available_generation_pu: float
    headroom_kw: float
    completed: bool
    queue: list[RestorationQueueItemResponse]


class FeederBranchResponse(APIResponse):
    building_id: str
    active_power_kw: float
    estimated_current_a: float


class FeederEstimateResponse(APIResponse):
    source: str
    nominal_line_voltage_v: float
    assumed_power_factor: float
    total_active_power_kw: float
    branches: list[FeederBranchResponse]


class ApplianceSnapshotResponse(APIResponse):
    appliance_id: str
    appliance_type: str
    priority: str
    state: str
    rated_power_kw: float
    current_power_kw: float
    enrolled: bool
    compressor_lockout_s: float | None
    lockout_remaining_s: float
    inrush_multiplier: float
    inrush_duration_s: float


class BuildingSnapshotResponse(APIResponse):
    run_id: uuid.UUID
    building_id: str
    weight_k: int
    demand_kw: float
    simulation_time_s: float
    sequence_number: int
    updated_at: datetime | None
    appliances: list[ApplianceSnapshotResponse]


class RunMetricResponse(APIResponse):
    metric_name: str
    metric_value: float
    unit: str
    notes: str | None


class RunEventResponse(APIResponse):
    event_id: uuid.UUID
    simulation_time_s: float
    event_type: str
    building_id: str
    appliance_id: str | None
    reason: str
    frequency_hz: float
    priority: str | None


class RunTelemetryResponse(APIResponse):
    simulation_time_s: float
    frequency_hz: float
    generation_pu: float
    demand_pu: float
    generation_disturbance_pu: float
    demand_disturbance_pu: float
    frequency_stage: str
    rocof_hz_per_s: float
    sequence_number: int


class NILMEstimateResponse(APIResponse):
    simulation_time_s: float
    building_id: str
    delta_power_kw: float
    event_type: str
    appliance_type: str | None
    confidence: float
    classification: str
    source: str


class NILMGroundTruthChangeResponse(APIResponse):
    appliance_id: str
    appliance_type: str
    event_type: str


class NILMDetectedChangeResponse(APIResponse):
    delta_power_kw: float
    event_type: str
    appliance_type: str | None
    confidence: float
    classification: str


class NILMSignalResponse(APIResponse):
    simulation_time_s: float
    building_id: str
    aggregate_power_kw: float
    ground_truth_changes: list[NILMGroundTruthChangeResponse]
    estimated_changes: list[NILMDetectedChangeResponse]
    source: str


class NILMEvaluationResponse(APIResponse):
    source: str
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    f1_score: float


class PolicyComparisonSummaryResponse(APIResponse):
    policy_name: PolicyName
    n_seeds: int
    mean_nadir_hz: float
    mean_max_rocof_hz_per_s: float
    std_nadir_hz: float
    ci95_nadir: list[float]
    mean_recovery_time_s: float | None
    mean_critical_ens_kwh: float
    mean_medical_load_interruption_s: float
    mean_feeder_trips: float
    mean_rebound_peak_pu: float
    mean_jains_index: float
    raw_metrics: list[dict[str, float]]


class LiveComparisonResponse(APIResponse):
    scenario_name: str
    base_seed: int
    n_seeds: int
    seed_range: list[int]
    source: str
    summary: dict[str, PolicyComparisonSummaryResponse]
    frequency_trajectories: dict[str, list[TelemetrySample]]


class SavedBaselineSummaryResponse(APIResponse):
    policy_name: str
    n_seeds: int
    mean_nadir_hz: float
    std_nadir_hz: float
    ci95_nadir: list[float]
    mean_recovery_time_s: float | None
    mean_critical_ens_kwh: float
    mean_feeder_trips: float
    mean_rebound_peak_pu: float
    mean_jains_index: float
    raw_metrics: list[dict[str, float]]
    mean_max_rocof_hz_per_s: float | None = None
    mean_medical_load_interruption_s: float | None = None


class SavedBaselineResponse(APIResponse):
    experiment_id: uuid.UUID
    scenario_name: str
    created_at: datetime
    schema_version: str
    summary: dict[str, SavedBaselineSummaryResponse]
