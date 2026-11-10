from __future__ import annotations

import asyncio

import pytest

from app.control.shedding_policy import PriorityEdgePolicy
from app.hil.adapter import HILAdapter, HILProtocolError
from app.hil.protocol import HILFeedbackMessage
from app.schemas.events import ControlEvent
from app.schemas.scenario import (
    ApplianceConfig,
    BuildingConfig,
    DisturbanceConfig,
    GridParams,
    ScenarioConfig,
)
from app.schemas.telemetry import TelemetrySample
from app.twin.appliance import Appliance, ApplianceState
from app.twin.building_twin import BuildingTwin
from app.twin.disturbances import make_disturbance
from app.twin.grid_model import GridModel
from app.twin.simulation_clock import SimulationClock


class FakeTransport:
    def __init__(self, inbound: list[str] | None = None) -> None:
        self.inbound = inbound or []
        self.outbound: list[str] = []
        self.closed = False

    async def write_line(self, line: str) -> None:
        self.outbound.append(line)

    async def read_line(self) -> str:
        if not self.inbound:
            await asyncio.sleep(10)
        return self.inbound.pop(0)

    async def close(self) -> None:
        self.closed = True


def _feedback(**updates: object) -> str:
    data: dict[str, object] = {
        "protocol_version": "1.0",
        "message_type": "heartbeat",
        "sequence": 1,
        "building_id": "B1",
        "appliance_states": {"B1_AC": "OFF"},
        "shed_commands": ["B1_AC"],
        "controller_status": "ok",
    }
    data.update(updates)
    import json

    return json.dumps(data)


def test_adapter_sends_versioned_building_telemetry_and_tracks_feedback():
    transport = FakeTransport([_feedback()])
    adapter = HILAdapter(transport, "B1", {"B1_AC"})

    asyncio.run(adapter.send_telemetry(12.0, 49.9, -0.2, []))
    feedback = asyncio.run(adapter.receive_feedback())

    assert '"protocol_version":"1.0"' in transport.outbound[0]
    assert feedback is not None
    assert feedback.appliance_states == {"B1_AC": "OFF"}
    health = adapter.health()
    assert health.connected
    assert health.last_feedback_latency_ms is not None
    assert health.heartbeat_age_s is not None
    assert health.acknowledged_appliance_states == {"B1_AC": "OFF"}
    assert health.last_feedback_sequence == 1


@pytest.mark.parametrize(
    "line",
    [
        "{broken",
        _feedback(building_id="B2"),
        _feedback(shed_commands=["unknown"]),
        _feedback(protocol_version="2.0"),
    ],
)
def test_adapter_rejects_malformed_or_wrong_target_feedback(line: str):
    adapter = HILAdapter(FakeTransport([line]), "B1", {"B1_AC"})
    with pytest.raises(HILProtocolError):
        asyncio.run(adapter.receive_feedback())


def test_adapter_rejects_duplicate_sequences_and_reports_fallback_after_timeout():
    transport = FakeTransport([_feedback(), _feedback()])
    adapter = HILAdapter(transport, "B1", {"B1_AC"})
    asyncio.run(adapter.receive_feedback())
    with pytest.raises(HILProtocolError, match="stale"):
        asyncio.run(adapter.receive_feedback())
    assert adapter.health(now_monotonic_s=10**9).fallback_active


def test_timeout_returns_no_feedback_and_transport_closes():
    transport = FakeTransport()
    adapter = HILAdapter(transport, "B1", {"B1_AC"})
    assert asyncio.run(adapter.receive_feedback(timeout_s=0.001)) is None
    asyncio.run(adapter.close())
    assert transport.closed


def test_hil_commands_are_applied_only_through_appliance_safety_guards():
    building = BuildingTwin(
        "B1",
        appliances=[
            Appliance("critical", "B1", "medical_device", "critical", 0.5),
            Appliance(
                "ac",
                "B1",
                "split_ac_1ton",
                "deferrable",
                1.0,
                compressor_lockout_s=10.0,
            ),
        ],
    )
    adapter = HILAdapter(FakeTransport(), "B1", {"critical", "ac"})
    feedback = HILFeedbackMessage(
        message_type="feedback",
        sequence=1,
        building_id="B1",
        shed_commands=["critical", "ac"],
    )

    deltas = adapter.apply_feedback(feedback, building, 5.0)

    assert "critical" not in deltas
    assert building.appliances[0].state == ApplianceState.ON
    assert building.appliances[1].state == ApplianceState.SHED
    assert building.appliances[1].lockout_remaining_s(5.0) == pytest.approx(10.0)


def test_simulation_clock_routes_hil_feedback_to_only_the_designated_building():
    scenario = ScenarioConfig(
        name="HIL smoke",
        seed=3,
        simulation_duration_s=0.51,
        disturbance=DisturbanceConfig(
            type="generation_loss",
            start_time_s=10.0,
            magnitude_pu=0.1,
            duration_s=1.0,
        ),
        grid_params=GridParams(),
        buildings=[
            BuildingConfig(
                building_id="B1",
                appliances=[
                    ApplianceConfig(
                        appliance_id="B1_AC",
                        appliance_type="split_ac_1ton",
                        priority="deferrable",
                        rated_power_kw=1.0,
                    )
                ],
            )
        ],
    )
    building = BuildingTwin.from_config(scenario.buildings[0])
    adapter = HILAdapter(
        FakeTransport([_feedback(shed_commands=["B1_AC"])]),
        "B1",
        {"B1_AC"},
    )

    async def no_op_telemetry(_: TelemetrySample) -> None:
        return None

    async def no_op_event(_: ControlEvent) -> None:
        return None

    clock = SimulationClock(
        scenario=scenario,
        run_id=scenario.scenario_id,
        grid=GridModel(scenario.grid_params),
        disturbance=make_disturbance(scenario.disturbance, seed=scenario.seed),
        buildings=[building],
        policy=PriorityEdgePolicy(),
        telemetry_sink=no_op_telemetry,
        event_sink=no_op_event,
        hil_adapter=adapter,
    )

    asyncio.run(clock.run())

    assert building.appliances[0].state == ApplianceState.LOCKED_OUT
