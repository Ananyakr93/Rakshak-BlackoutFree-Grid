"""
Simulation clock: the main async loop driving GridShield.

Integrates the grid model step by step, ticks edge agents at the
configured sample interval, accumulates appliance demand deltas,
and pushes telemetry to the injected sink. Decoupled from wall-clock
time and from the database (sinks are injected).

Loop invariants
---------------
1. Grid model advances by dt_s per step.
2. Every AGENT_SAMPLE_INTERVAL_S, all edge agent .tick() calls are made.
3. All appliance demand deltas accumulated since the previous grid step
   are summed and passed to the next GridModel.step() call.
4. Every WS_PUSH_INTERVAL_S, telemetry_sink is called with a TelemetrySample.
5. asyncio.sleep(0) is called every tick to yield control and not block the loop.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np

from app.control.edge_agent import EdgeAgent, OperatingMode
from app.control.shedding_policy import PriorityEdgePolicy
from app.core.config import settings
from app.hil.adapter import HILAdapter
from app.nilm.detector import AggregatePowerSample, NILMEventDetector
from app.schemas.events import ApplianceStateUpdate, ControlEvent
from app.schemas.scenario import ScenarioConfig
from app.schemas.telemetry import TelemetrySample
from app.twin.appliance import ApplianceState
from app.twin.disturbances import DisturbanceProfile
from app.twin.grid_model import GridModel, GridState


@dataclass
class SimulationResult:
    """Outcome of a completed simulation run."""

    run_id: uuid.UUID
    scenario_id: uuid.UUID
    policy: str
    seed: int
    final_state: GridState
    events: list[ControlEvent]
    metrics: dict[str, float] = field(default_factory=dict)
    telemetry: list[TelemetrySample] = field(default_factory=list)


def _restoration_incident_id(scenario: ScenarioConfig) -> str:
    payload = scenario.model_dump_json(exclude={"scenario_id", "seed"})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SimulationClock:
    """
    Drives the GridShield simulation loop asynchronously.

    Buildings and policy are injected so this class has no direct
    knowledge of the database or the web layer.
    """

    def __init__(
        self,
        scenario: ScenarioConfig,
        run_id: uuid.UUID,
        grid: GridModel,
        disturbance: DisturbanceProfile,
        buildings: list,  # list[BuildingTwin]  (typed loosely to avoid circular)
        policy,  # BasePolicy instance
        telemetry_sink: Callable[[TelemetrySample], Awaitable[None]],
        event_sink: Callable[[ControlEvent], Awaitable[None]],
        building_state_sink: Callable[[ApplianceStateUpdate], Awaitable[None]] | None = None,
        hil_adapter: HILAdapter | None = None,
        playback_speed: float | None = None,
        agent_sample_interval_s: float | None = None,
        ws_push_interval_s: float | None = None,
    ) -> None:
        self.scenario = scenario
        self.run_id = run_id
        self.grid = grid
        self.disturbance = disturbance
        self.buildings = buildings
        self.policy = policy
        self.telemetry_sink = telemetry_sink
        self.event_sink = event_sink
        self.building_state_sink = building_state_sink
        self.hil_adapter = hil_adapter
        self.agent_sample_interval_s = (
            settings.AGENT_SAMPLE_INTERVAL_S
            if agent_sample_interval_s is None
            else agent_sample_interval_s
        )
        self.ws_push_interval_s = (
            settings.WS_PUSH_INTERVAL_S
            if ws_push_interval_s is None
            else ws_push_interval_s
        )
        for label, interval in (
            ("agent sample interval", self.agent_sample_interval_s),
            ("WebSocket interval", self.ws_push_interval_s),
        ):
            steps = interval / grid.params.dt_s
            if interval < grid.params.dt_s:
                raise ValueError(f"{label} must be at least the grid integration step")
            if abs(steps - round(steps)) > 1e-9:
                raise ValueError(
                    f"{label} must be an integer multiple of the grid integration step"
                )
        if policy is not None:
            policy_interval = getattr(policy, "sample_interval_s", self.agent_sample_interval_s)
            if policy_interval != self.agent_sample_interval_s:
                raise ValueError("policy and simulation clock sample intervals must match")
            restoration = getattr(policy, "restoration_policy", None)
            if (
                restoration is not None
                and restoration.sample_interval_s != self.agent_sample_interval_s
            ):
                raise ValueError(
                    "restoration and simulation clock sample intervals must match"
                )
        if playback_speed is not None and playback_speed <= 0:
            raise ValueError("playback speed must be positive")
        self._playback_speed = playback_speed
        self._playback_speed_generation = 0
        self._paused = False

        self._state: GridState = grid.initial_state()
        self._running = False
        self._sequence: int = 0
        self._events: list[ControlEvent] = []
        self._telemetry: list[TelemetrySample] = []
        self._nilm_detector = NILMEventDetector()
        self._nilm_previous: dict[str, AggregatePowerSample] = {}
        self._nilm_events: list[dict[str, str | float | None]] = []
        self._nilm_previous_states: dict[str, dict[str, bool]] = {}
        self._nilm_signal: list[dict[str, object]] = []
        self._agents: dict[str, EdgeAgent] = {}
        self._building_sequence = 0
        self._building_updated_at: dict[str, datetime] = {}
        self._initial_appliance_states = {
            (building.building_id, appliance.appliance_id): (
                appliance.state,
                appliance.current_power_kw,
            )
            for building in self.buildings
            for appliance in building.appliances
        }

    def building_snapshots(self, initial: bool = False) -> list[dict[str, object]]:
        """Serialize the current authoritative in-memory building state."""
        return [
            {
                "run_id": self.run_id,
                "building_id": building.building_id,
                "weight_k": building.weight_k,
                "demand_kw": sum(
                    (
                        self._initial_appliance_states[
                            (building.building_id, appliance.appliance_id)
                        ][1]
                        if initial
                        else appliance.current_power_kw
                    ) * building.weight_k
                    for appliance in building.appliances
                ),
                "simulation_time_s": 0.0 if initial else self._state.time_s,
                "sequence_number": 0 if initial else self._building_sequence,
                "updated_at": (
                    None if initial else self._building_updated_at.get(building.building_id)
                ),
                "appliances": [
                    {
                        "appliance_id": appliance.appliance_id,
                        "appliance_type": appliance.appliance_type,
                        "priority": appliance.priority,
                        "state": (
                            self._initial_appliance_states[
                                (building.building_id, appliance.appliance_id)
                            ][0].value
                            if initial
                            else appliance.state.value
                        ),
                        "rated_power_kw": appliance.rated_power_kw * building.weight_k,
                        "current_power_kw": (
                            self._initial_appliance_states[
                                (building.building_id, appliance.appliance_id)
                            ][1]
                            if initial
                            else appliance.current_power_kw
                        ) * building.weight_k,
                        "enrolled": appliance.enrolled,
                        "compressor_lockout_s": appliance.compressor_lockout_s,
                        "lockout_remaining_s": (
                            0.0
                            if initial
                            else appliance.lockout_remaining_s(self._state.time_s)
                        ),
                        "inrush_multiplier": appliance.inrush_multiplier,
                        "inrush_duration_s": appliance.inrush_duration_s,
                    }
                    for appliance in building.appliances
                ],
            }
            for building in self.buildings
        ]

    def current_state(self) -> GridState:
        """Return the latest grid state (thread-safe for reads)."""
        return self._state

    @property
    def building_sequence_number(self) -> int:
        """Return the latest monotonically increasing appliance-state sequence."""
        return self._building_sequence

    def stop(self) -> None:
        """Request a graceful stop after the current step."""
        self._running = False
        self._paused = False

    def pause(self) -> None:
        """Pause simulation advancement without discarding the active run."""
        self._paused = True

    def resume(self) -> None:
        """Resume simulation advancement."""
        self._paused = False

    def set_playback_speed(self, speed: float) -> None:
        """Set simulated seconds advanced per wall-clock second."""
        if not 1 <= speed <= 120:
            raise ValueError("playback speed must be between 1 and 120")
        self._playback_speed = speed
        self._playback_speed_generation += 1

    def playback_speed(self) -> float | None:
        """Return the current speed, or None when running as fast as possible."""
        return self._playback_speed

    def is_paused(self) -> bool:
        return self._paused

    def nilm_events(self) -> list[dict[str, str | float | None]]:
        """Return estimates from simulated aggregate load, separate from twin state."""
        return list(self._nilm_events)

    def nilm_signal(self) -> list[dict[str, object]]:
        """Return bounded aggregate-load samples and model ground-truth transitions."""
        return list(self._nilm_signal)

    def agent_status(self) -> list[dict[str, object]]:
        """Return current per-building edge-agent state for the diagnostics view."""
        return [
            {
                "building_id": agent.building_id,
                "operating_mode": agent.operating_mode.value,
                "communication_available": agent.communication_available,
                "evaluations": agent.evaluation_count,
                "last_decision": agent.last_decision,
                "last_decision_reason": agent.last_decision_reason,
                "last_decision_time_s": agent.last_decision_time_s,
                "autonomous": agent.should_evaluate_policy,
            }
            for agent in self._agents.values()
        ]

    def restoration_status(self) -> dict[str, object]:
        """Expose the current restoration safety gate and queued appliances."""
        restoration = getattr(self.policy, "restoration_policy", None)
        if restoration is None:
            area_base_kw = max(
                sum(
                    appliance.rated_power_kw * building.weight_k
                    for building in self.buildings
                    for appliance in building.appliances
                ),
                1.0,
            )
            available_generation_pu = max(
                0.0,
                1.0
                + self.scenario.grid_params.up_reserve_pu
                + self._state.generation_disturbance_pu,
            )
            return {
                "enabled": False,
                "frozen": False,
                "frequency_hz": self._state.frequency_hz,
                "frequency_gate_hz": self.scenario.grid_params.f_recovery_hz,
                "freeze_below_hz": self.scenario.grid_params.f_s1_hz,
                "projection_floor_hz": 49.90,
                "stable_timer_s": 0.0,
                "required_stability_s": self.scenario.grid_params.t_stable_s,
                "stagger_enabled": False,
                "available_generation_pu": available_generation_pu,
                "headroom_kw": max(
                    0.0,
                    (available_generation_pu - self._state.demand_pu) * area_base_kw,
                ),
                "completed": False,
                "queue": [],
            }
        return restoration.snapshot(
            self._state,
            self.buildings,
            str(self.run_id),
            self.scenario.seed,
        )

    async def run(self) -> SimulationResult:
        """
        Execute the full simulation loop asynchronously.

        Returns a SimulationResult when the scenario duration is reached
        or stop() is called.
        """
        p = self.scenario.grid_params
        dt = p.dt_s
        agent_sample_interval = self.agent_sample_interval_s
        ws_push_interval = self.ws_push_interval_s

        duration = self.scenario.simulation_duration_s
        incident_id = _restoration_incident_id(self.scenario)
        seed = self.scenario.seed

        self._running = True
        state = self.grid.initial_state()

        # Timers
        agent_timer = 0.0
        ws_timer = 0.0
        loop = asyncio.get_running_loop()
        next_step_wall_time = loop.time()
        playback_speed_generation = self._playback_speed_generation

        # Assume total area demand base for per-unit conversion
        # In scaled mode: total kW of all buildings / area_base
        # We use a simple approach: 1 pu = sum of all rated powers
        area_base_kw = max(
            sum(
                a.rated_power_kw * b.weight_k
                for b in self.buildings
                for a in b.appliances
            ),
            1.0,  # prevent division by zero when no buildings
        )
        previous_appliance_demand_kw = sum(
            appliance.current_power_kw * building.weight_k
            for building in self.buildings
            for appliance in building.appliances
        )
        previous_appliance_values = {
            (building.building_id, appliance.appliance_id): (
                appliance.state,
                appliance.current_power_kw,
            )
            for building in self.buildings
            for appliance in building.appliances
        }
        agents = (
            {
                building.building_id: EdgeAgent(
                    building,
                    self.policy,
                    operating_mode=OperatingMode(self.scenario.edge_mode),
                )
                for building in self.buildings
            }
            if isinstance(self.policy, PriorityEdgePolicy)
            else {}
        )
        self._agents = agents
        communication_rng = np.random.default_rng(seed)

        while self._running and state.time_s < duration:
            if self._paused and self._running:
                await asyncio.sleep(0.05)
                next_step_wall_time = loop.time()
                playback_speed_generation = self._playback_speed_generation
                continue
            if self._playback_speed is None:
                await asyncio.sleep(0)
            else:
                if playback_speed_generation != self._playback_speed_generation:
                    playback_speed_generation = self._playback_speed_generation
                    next_step_wall_time = loop.time()
                next_step_wall_time += dt / self._playback_speed
                await asyncio.sleep(max(0.0, next_step_wall_time - loop.time()))
                if not self._running:
                    break
                if self._paused:
                    next_step_wall_time = loop.time()
                    continue

            for building in self.buildings:
                building.tick(state.time_s, dt)
            appliance_demand_kw = sum(
                appliance.current_power_kw * building.weight_k
                for building in self.buildings
                for appliance in building.appliances
            )
            current_demand_delta_pu = (
                appliance_demand_kw - previous_appliance_demand_kw
            ) / area_base_kw
            previous_appliance_demand_kw = appliance_demand_kw

            # 1. Get disturbance for this step
            generation_disturbance_pu, demand_disturbance_pu = (
                self.disturbance.get_disturbance_components(state.time_s)
            )
            dist_pu = demand_disturbance_pu - generation_disturbance_pu

            # 2. Advance grid model one RK4 step
            state = self.grid.step(
                state,
                dist_pu,
                current_demand_delta_pu,
                generation_disturbance_pu=generation_disturbance_pu,
                demand_disturbance_pu=demand_disturbance_pu,
            )
            self._state = state

            # 3. Agent tick every agent_sample_interval
            agent_timer += dt
            if agent_timer + dt * 1e-9 >= agent_sample_interval:
                agent_timer = max(0.0, agent_timer - agent_sample_interval)
                if self.buildings and self.policy is not None:
                    hil_controlled_buildings: set[str] = set()
                    for building in self.buildings:
                        if (
                            self.hil_adapter is not None
                            and building.building_id == self.hil_adapter.building_id
                        ):
                            await self.hil_adapter.send_telemetry(
                                simulation_time_s=state.time_s,
                                frequency_hz=state.frequency_hz,
                                rocof_hz_per_s=state.rocof_hz_per_s,
                                appliances=[
                                    {
                                        "appliance_id": appliance.appliance_id,
                                        "appliance_type": appliance.appliance_type,
                                        "priority": appliance.priority,
                                        "state": appliance.state.value,
                                        "enrolled": appliance.enrolled,
                                        "rated_power_kw": appliance.rated_power_kw,
                                    }
                                    for appliance in building.appliances
                                ],
                            )
                            feedback = await self.hil_adapter.receive_feedback(
                                timeout_s=0.1
                            )
                            if feedback is not None:
                                self.hil_adapter.apply_feedback(
                                    feedback, building, state.time_s
                                )
                            if self.hil_adapter.health().connected:
                                hil_controlled_buildings.add(building.building_id)

                        if building.building_id in agents:
                            agent = agents[building.building_id]
                            if building.building_id in hil_controlled_buildings:
                                events = []
                            else:
                                connected = (
                                    communication_rng.random()
                                    >= self.scenario.fault_config.loss_probability
                                )
                                agent.set_communication_available(connected, state.time_s)
                                events = []
                                if agent.should_evaluate_policy:
                                    _, events = agent.tick(
                                        state,
                                        state.time_s,
                                        incident_id,
                                        seed,
                                    )
                        else:
                            if building.building_id in hil_controlled_buildings:
                                events = []
                            else:
                                _, events = self.policy.evaluate(
                                    state, building, state.time_s
                                )
                        for appliance in building.appliances:
                            if appliance.state.value == "SHED":
                                appliance.mark_waiting_restoration(state.time_s)
                        for evt in events:
                            self._events.append(evt)
                            await self.event_sink(evt)

                    # Restoration tick
                    restoration_policy = getattr(self.policy, "restoration_policy", None)
                    if restoration_policy is not None:
                        restoration_buildings = [
                            building
                            for building in self.buildings
                            if building.building_id not in hil_controlled_buildings
                        ]
                        rest_events = restoration_policy.tick(
                            state,
                            restoration_buildings,
                            incident_id,
                            seed,
                            state.time_s,
                        )
                        for evt in rest_events:
                            self._events.append(evt)
                            await self.event_sink(evt)

            if self.building_state_sink is not None:
                for building in self.buildings:
                    for appliance in building.appliances:
                        key = (building.building_id, appliance.appliance_id)
                        previous_value = previous_appliance_values.get(key)
                        if previous_value is None:
                            continue
                        previous_state, previous_power_kw = previous_value
                        power_changed = (
                            abs(previous_power_kw - appliance.current_power_kw) > 1e-9
                            and previous_state != ApplianceState.RUNNING
                            and appliance.state != ApplianceState.RUNNING
                        )
                        if previous_state == appliance.state and not power_changed:
                            continue
                        self._building_sequence += 1
                        updated_at = datetime.now(tz=timezone.utc)
                        self._building_updated_at[building.building_id] = updated_at
                        await self.building_state_sink(
                            ApplianceStateUpdate(
                                run_id=self.run_id,
                                building_id=building.building_id,
                                appliance_id=appliance.appliance_id,
                                appliance_type=appliance.appliance_type,
                                priority=appliance.priority,
                                previous_state=previous_state.value,
                                current_state=appliance.state.value,
                                current_power_kw=(
                                    appliance.current_power_kw * building.weight_k
                                ),
                                rated_power_kw=(
                                    appliance.rated_power_kw * building.weight_k
                                ),
                                simulation_time_s=state.time_s,
                                sequence_number=self._building_sequence,
                                updated_at=updated_at,
                            )
                        )
                        previous_appliance_values[key] = (
                            appliance.state,
                            appliance.current_power_kw,
                        )

            # 4. Push telemetry every ws_push_interval
            ws_timer += dt
            if ws_timer + dt * 1e-9 >= ws_push_interval:
                ws_timer = max(0.0, ws_timer - ws_push_interval)
                for building in self.buildings:
                    aggregate_power_kw = sum(
                        appliance.current_power_kw for appliance in building.appliances
                    )
                    current_sample = AggregatePowerSample(state.time_s, aggregate_power_kw)
                    current_states = {
                        appliance.appliance_id: appliance.state.value in {"ON", "RUNNING"}
                        for appliance in building.appliances
                    }
                    previous_states = self._nilm_previous_states.get(
                        building.building_id, {}
                    )
                    ground_truth_changes = [
                        {
                            "appliance_id": appliance.appliance_id,
                            "appliance_type": appliance.appliance_type,
                            "event_type": (
                                "switch_on"
                                if appliance.state.value in {"ON", "RUNNING"}
                                else "switch_off"
                            ),
                        }
                        for appliance in building.appliances
                        if appliance.appliance_id in previous_states
                        and previous_states[appliance.appliance_id]
                        != (appliance.state.value in {"ON", "RUNNING"})
                    ]
                    previous_sample = self._nilm_previous.get(building.building_id)
                    detected_changes: list[dict[str, object]] = []
                    if previous_sample is not None:
                        estimates = self._nilm_detector.detect(
                            [previous_sample, current_sample]
                        )
                        detected_changes = [
                            {
                                "delta_power_kw": estimate.delta_power_kw,
                                "event_type": estimate.event_type,
                                "appliance_type": estimate.appliance_type,
                                "confidence": estimate.confidence,
                                "classification": estimate.classification,
                            }
                            for estimate in estimates
                        ]
                        self._nilm_events.extend(
                            {
                                "simulation_time_s": estimate.simulation_time_s,
                                "building_id": building.building_id,
                                "delta_power_kw": estimate.delta_power_kw,
                                "event_type": estimate.event_type,
                                "appliance_type": estimate.appliance_type,
                                "confidence": estimate.confidence,
                                "classification": estimate.classification,
                                "source": "simulated_aggregate_load",
                            }
                            for estimate in estimates
                        )
                    self._nilm_previous[building.building_id] = current_sample
                    self._nilm_previous_states[building.building_id] = current_states
                    self._nilm_signal.append(
                        {
                            "simulation_time_s": state.time_s,
                            "building_id": building.building_id,
                            "aggregate_power_kw": aggregate_power_kw,
                            "ground_truth_changes": ground_truth_changes,
                            "estimated_changes": detected_changes,
                            "source": "simulated_aggregate_load",
                        }
                    )
                self._sequence += 1
                sample = TelemetrySample(
                    run_id=self.run_id,
                    simulation_time_s=state.time_s,
                    wall_clock_ts=datetime.now(tz=timezone.utc),
                    frequency_hz=state.frequency_hz,
                    generation_pu=state.generation_pu,
                    demand_pu=state.demand_pu,
                    generation_disturbance_pu=state.generation_disturbance_pu,
                    demand_disturbance_pu=state.demand_disturbance_pu,
                    frequency_stage=self.grid.frequency_stage(state),
                    rocof_hz_per_s=state.rocof_hz_per_s,
                    sequence_number=self._sequence,
                )
                self._telemetry.append(sample)
                await self.telemetry_sink(sample)

            # 5. Yield control to event loop
            await asyncio.sleep(0)

        self._running = False

        return SimulationResult(
            run_id=self.run_id,
            scenario_id=self.scenario.scenario_id,
            policy=getattr(self.policy, "policy_name", "none") if self.policy else "none",
            seed=self.scenario.seed,
            final_state=state,
            events=self._events,
            telemetry=self._telemetry,
        )


def _extract_demand_delta(event: ControlEvent, buildings: list) -> float:
    """
    Helper: look up how much demand changed from a restoration event.
    Returns kW value (positive = load added).
    """
    if event.event_type not in ("restore",):
        return 0.0
    for b in buildings:
        if b.building_id == event.building_id:
            for a in b.appliances:
                if a.appliance_id == event.appliance_id:
                    return a.rated_power_kw * b.weight_k
    return 0.0
