"""Asynchronous optional HIL adapter; the simulation remains usable without serial hardware."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from app.hil.protocol import HILFeedbackMessage, HILTelemetryMessage
from app.twin.appliance import ApplianceState
from app.twin.building_twin import BuildingTwin


class HILProtocolError(ValueError):
    """Raised when a controller sends invalid or stale protocol data."""


class HILLineTransport(Protocol):
    async def write_line(self, line: str) -> None: ...

    async def read_line(self) -> str: ...

    async def close(self) -> None: ...


class PySerialLineTransport:
    """Optional pySerial transport. Importing the simulation does not require pySerial."""

    def __init__(self, port: str, baud_rate: int = 115200, timeout_s: float = 1.0) -> None:
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError(
                "Install the optional HIL extra with `pip install .[hil]` to use serial"
            ) from exc
        if not port or baud_rate <= 0 or timeout_s <= 0:
            raise ValueError("port, positive baud rate, and positive timeout are required")
        self._serial = serial.Serial(port, baud_rate, timeout=timeout_s, write_timeout=timeout_s)

    async def write_line(self, line: str) -> None:
        await asyncio.to_thread(self._serial.write, (line + "\n").encode("utf-8"))

    async def read_line(self) -> str:
        raw = await asyncio.to_thread(self._serial.readline)
        if not raw:
            raise TimeoutError("serial read timed out")
        return raw.decode("utf-8", errors="strict").strip()

    async def close(self) -> None:
        await asyncio.to_thread(self._serial.close)


@dataclass(frozen=True)
class HILHealth:
    connected: bool
    last_heartbeat_monotonic_s: float | None
    received_messages: int
    transmitted_messages: int
    fallback_active: bool
    last_feedback_latency_ms: float | None
    heartbeat_age_s: float | None
    controller_status: str | None
    acknowledged_appliance_states: dict[str, str]
    last_feedback_sequence: int | None


class HILAdapter:
    """Validate, sequence, and route protocol messages for one virtual building."""

    def __init__(
        self,
        transport: HILLineTransport,
        building_id: str,
        appliance_ids: set[str],
        heartbeat_timeout_s: float = 5.0,
    ) -> None:
        if not building_id or not appliance_ids:
            raise ValueError("HIL must be assigned a building and its appliance IDs")
        if heartbeat_timeout_s <= 0:
            raise ValueError("heartbeat timeout must be positive")
        self.transport = transport
        self.building_id = building_id
        self.appliance_ids = frozenset(appliance_ids)
        self.heartbeat_timeout_s = heartbeat_timeout_s
        self._tx_sequence = 0
        self._rx_sequence = -1
        self._last_heartbeat: float | None = None
        self._received = 0
        self._transmitted = 0
        self._last_telemetry_monotonic_s: float | None = None
        self._last_feedback_latency_ms: float | None = None
        self._controller_status: str | None = None
        self._acknowledged_appliance_states: dict[str, str] = {}

    async def send_telemetry(
        self,
        simulation_time_s: float,
        frequency_hz: float,
        rocof_hz_per_s: float,
        appliances: list[Mapping[str, str | float | bool]],
    ) -> None:
        message = HILTelemetryMessage(
            sequence=self._tx_sequence,
            simulation_time_s=simulation_time_s,
            building_id=self.building_id,
            frequency_hz=frequency_hz,
            rocof_hz_per_s=rocof_hz_per_s,
            appliances=[dict(item) for item in appliances],
        )
        await self.transport.write_line(message.model_dump_json())
        self._last_telemetry_monotonic_s = time.monotonic()
        self._tx_sequence += 1
        self._transmitted += 1

    async def receive_feedback(self, timeout_s: float | None = None) -> HILFeedbackMessage | None:
        timeout = timeout_s if timeout_s is not None else self.heartbeat_timeout_s
        try:
            line = await asyncio.wait_for(self.transport.read_line(), timeout=timeout)
        except (TimeoutError, asyncio.TimeoutError):
            return None
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise HILProtocolError("protocol message must be a JSON object")
            message = HILFeedbackMessage.model_validate(payload)
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise HILProtocolError("controller sent malformed JSON") from exc
        except ValidationError as exc:
            raise HILProtocolError(f"controller message failed validation: {exc}") from exc

        if message.building_id != self.building_id:
            raise HILProtocolError("controller feedback targets a different building")
        if message.sequence <= self._rx_sequence:
            raise HILProtocolError("duplicate or stale controller sequence")
        if set(message.appliance_states) - self.appliance_ids:
            raise HILProtocolError("controller returned an unknown appliance ID")
        if set(message.shed_commands) - self.appliance_ids:
            raise HILProtocolError("controller issued a command for an unknown appliance")
        if set(message.restore_commands) - self.appliance_ids:
            raise HILProtocolError("controller issued a command for an unknown appliance")
        if set(message.shed_commands) & set(message.restore_commands):
            raise HILProtocolError("controller cannot shed and restore the same appliance together")
        self._rx_sequence = message.sequence
        self._received += 1
        if self._last_telemetry_monotonic_s is not None:
            self._last_feedback_latency_ms = max(
                0.0, (time.monotonic() - self._last_telemetry_monotonic_s) * 1000.0
            )
        self._controller_status = message.controller_status
        self._acknowledged_appliance_states = dict(message.appliance_states)
        if message.message_type == "heartbeat":
            self._last_heartbeat = time.monotonic()
        return message

    def apply_feedback(
        self,
        feedback: HILFeedbackMessage,
        building: BuildingTwin,
        sim_time_s: float,
    ) -> dict[str, float]:
        """Apply only explicit commands to the designated twin through appliance guards."""
        if building.building_id != self.building_id:
            raise HILProtocolError("HIL adapter cannot control a different building")
        appliances = {appliance.appliance_id: appliance for appliance in building.appliances}
        if set(feedback.shed_commands + feedback.restore_commands) - set(appliances):
            raise HILProtocolError("controller command references an appliance outside the twin")
        if set(feedback.shed_commands) & set(feedback.restore_commands):
            raise HILProtocolError("controller cannot shed and restore the same appliance together")
        deltas: dict[str, float] = {}
        for appliance_id in feedback.shed_commands:
            appliance = appliances[appliance_id]
            delta = appliance.shed(sim_time_s)
            if delta:
                deltas[appliance_id] = delta
        for appliance_id in feedback.restore_commands:
            appliance = appliances[appliance_id]
            if appliance.state == ApplianceState.SHED:
                appliance.mark_waiting_restoration(sim_time_s)
            if appliance.state == ApplianceState.OFF:
                delta = appliance.start_from_off(sim_time_s)
            else:
                delta = appliance.restore(sim_time_s)
            if delta:
                deltas[appliance_id] = delta
        building.apply_demand_delta()
        return deltas

    def health(self, now_monotonic_s: float | None = None) -> HILHealth:
        now = time.monotonic() if now_monotonic_s is None else now_monotonic_s
        connected = (
            self._last_heartbeat is not None
            and now - self._last_heartbeat <= self.heartbeat_timeout_s
        )
        heartbeat_age = (
            max(0.0, now - self._last_heartbeat)
            if self._last_heartbeat is not None
            else None
        )
        return HILHealth(
            connected=connected,
            last_heartbeat_monotonic_s=self._last_heartbeat,
            received_messages=self._received,
            transmitted_messages=self._transmitted,
            fallback_active=not connected,
            last_feedback_latency_ms=self._last_feedback_latency_ms,
            heartbeat_age_s=heartbeat_age,
            controller_status=self._controller_status,
            acknowledged_appliance_states=dict(self._acknowledged_appliance_states),
            last_feedback_sequence=self._rx_sequence if self._received else None,
        )

    async def close(self) -> None:
        await self.transport.close()
