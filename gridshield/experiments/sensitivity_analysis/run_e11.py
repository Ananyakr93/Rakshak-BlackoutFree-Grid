"""Software-only protocol/decision comparison for virtual edge and HIL controller."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.control.edge_agent import EdgeAgent, OperatingMode
from app.control.shedding_policy import PriorityEdgePolicy
from app.hil.adapter import HILAdapter
from app.schemas.scenario import ApplianceConfig, BuildingConfig
from app.twin.building_twin import BuildingTwin
from app.twin.grid_model import GridState


class SoftwareControllerTransport:
    """Test transport that runs P2 from received simulated telemetry."""

    def __init__(self) -> None:
        self.building = BuildingTwin.from_config(
            BuildingConfig(
                building_id="HIL-B1",
                appliances=[
                    ApplianceConfig(
                        appliance_id="HIL-AC",
                        appliance_type="split_ac_1ton",
                        priority="deferrable",
                        rated_power_kw=1.0,
                    )
                ],
            )
        )
        self.policy = PriorityEdgePolicy()
        self.response = ""

    async def write_line(self, line: str) -> None:
        payload = json.loads(line)
        sample = GridState(
            time_s=payload["simulation_time_s"],
            frequency_hz=payload["frequency_hz"],
            delta_omega=(payload["frequency_hz"] - 50.0) / 50.0,
            delta_Pm=0.0,
            delta_Pg=0.0,
            demand_pu=1.0,
            generation_pu=1.0,
            disturbance_pu=0.0,
            rocof_hz_per_s=payload["rocof_hz_per_s"],
        )
        _, events = self.policy.evaluate(
            sample, self.building, payload["simulation_time_s"]
        )
        commands = [
            event.appliance_id
            for event in events
            if event.event_type.startswith("shed") and event.appliance_id
        ]
        self.response = json.dumps(
            {
                "protocol_version": "1.0",
                "message_type": "feedback",
                "sequence": payload["sequence"],
                "building_id": payload["building_id"],
                "shed_commands": commands,
                "controller_status": "software_simulated",
            }
        )

    async def read_line(self) -> str:
        return self.response

    async def close(self) -> None:
        return None


async def run_e11() -> dict[str, object]:
    virtual = BuildingTwin.from_config(
        BuildingConfig(
            building_id="HIL-B1",
            appliances=[
                ApplianceConfig(
                    appliance_id="HIL-AC",
                    appliance_type="split_ac_1ton",
                    priority="deferrable",
                    rated_power_kw=1.0,
                )
            ],
        )
    )
    virtual_agent = EdgeAgent(
        virtual,
        PriorityEdgePolicy(),
        operating_mode=OperatingMode.DISTRIBUTED,
    )
    state = GridState(
        time_s=10.0,
        frequency_hz=49.8,
        delta_omega=-0.004,
        delta_Pm=0.0,
        delta_Pg=0.0,
        demand_pu=1.0,
        generation_pu=1.0,
        disturbance_pu=0.0,
        rocof_hz_per_s=-0.5,
    )
    _, virtual_events = virtual_agent.tick(state, 10.0, "e11", 42)

    adapter = HILAdapter(
        SoftwareControllerTransport(),
        "HIL-B1",
        {"HIL-AC"},
    )
    await adapter.send_telemetry(
        10.0,
        state.frequency_hz,
        state.rocof_hz_per_s,
        [
            {
                "appliance_id": "HIL-AC",
                "appliance_type": "split_ac_1ton",
                "priority": "deferrable",
                "rated_power_kw": 1.0,
                "enrolled": True,
            }
        ],
    )
    feedback = await adapter.receive_feedback()
    await adapter.close()
    return {
        "experiment": "E11",
        "hardware_used": False,
        "data_source": "software-generated telemetry and controller response",
        "virtual_edge_commands": [
            event.appliance_id
            for event in virtual_events
            if event.event_type.startswith("shed")
        ],
        "hil_protocol_commands": feedback.shed_commands if feedback else [],
        "controller_status": feedback.controller_status if feedback else "no response",
        "claim_boundary": "This checks protocol and software parity, not physical ESP32 timing.",
    }


if __name__ == "__main__":
    output = Path(__file__).with_name("results_e11.json")
    output.write_text(json.dumps(asyncio.run(run_e11()), indent=2), encoding="utf-8")
    print(f"E11 software HIL results written to {output}")
