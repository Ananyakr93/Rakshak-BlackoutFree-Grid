"""
In-memory run manager for GridShield.

Tracks active SimulationClock instances, their telemetry buffers,
and WebSocket subscriber sets. Provides thread-safe access for the
API layer to check run status and push state to clients.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

from app.schemas.events import ApplianceStateUpdate, ControlEvent
from app.schemas.telemetry import RunState, TelemetrySample
from app.twin.simulation_clock import SimulationClock

MAX_RETAINED_TERMINAL_RUNS = 20
MAX_RETAINED_TELEMETRY = 10_000
MAX_RETAINED_EVENTS = 20_000
MAX_RETAINED_BUILDING_UPDATES = 10_000
WEBSOCKET_QUEUE_SIZE = 5_000


@dataclass
class RunEntry:
    run_id: uuid.UUID
    policy: str
    status: str = "pending"
    clock: SimulationClock | None = None
    latest_sample: TelemetrySample | None = None
    telemetry_buffer: list[TelemetrySample] = field(default_factory=list)
    event_buffer: list[ControlEvent] = field(default_factory=list)
    building_update_buffer: list[ApplianceStateUpdate] = field(default_factory=list)
    ws_queues: set[asyncio.Queue[object]] = field(default_factory=set)
    active_buildings: int = 0
    playback_speed: float = 30.0
    hil_building_id: str | None = None


class RunManager:
    """Singleton that tracks all simulation runs in this process."""

    def __init__(self) -> None:
        self._runs: dict[uuid.UUID, RunEntry] = {}

    def register(self, run_id: uuid.UUID, policy: str, n_buildings: int) -> RunEntry:
        self._prune_terminal_runs()
        entry = RunEntry(run_id=run_id, policy=policy, active_buildings=n_buildings)
        self._runs[run_id] = entry
        return entry

    def get(self, run_id: uuid.UUID) -> RunEntry | None:
        return self._runs.get(run_id)

    def set_status(self, run_id: uuid.UUID, status: str) -> None:
        entry = self._runs.get(run_id)
        if entry is None:
            return
        entry.status = status
        if status in {"completed", "failed"}:
            self._prune_terminal_runs()

    def _prune_terminal_runs(self) -> None:
        terminal_ids = [
            run_id
            for run_id, entry in self._runs.items()
            if entry.status in {"completed", "failed"} and not entry.ws_queues
        ]
        for run_id in terminal_ids[:-MAX_RETAINED_TERMINAL_RUNS]:
            del self._runs[run_id]

    async def push_telemetry(self, run_id: uuid.UUID, sample: TelemetrySample) -> None:
        entry = self._runs.get(run_id)
        if entry is None:
            return
        entry.latest_sample = sample
        entry.telemetry_buffer.append(sample)
        if len(entry.telemetry_buffer) > MAX_RETAINED_TELEMETRY:
            del entry.telemetry_buffer[: len(entry.telemetry_buffer) - MAX_RETAINED_TELEMETRY]
        payload = sample.model_dump(mode="json")
        for q in entry.ws_queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # Telemetry can be recovered from the REST endpoint; keep the
                # subscriber connected so state updates can still be delivered.
                continue

    def push_building_update(self, run_id: uuid.UUID, update: ApplianceStateUpdate) -> None:
        """Retain and publish state transitions, signaling clients to reconcile on overflow."""
        entry = self._runs.get(run_id)
        if entry is None:
            return
        entry.building_update_buffer.append(update)
        if len(entry.building_update_buffer) > MAX_RETAINED_BUILDING_UPDATES:
            del entry.building_update_buffer[
                : len(entry.building_update_buffer) - MAX_RETAINED_BUILDING_UPDATES
            ]
        payload = update.model_dump(mode="json")
        for q in entry.ws_queues:
            if q.full():
                while q.qsize() > WEBSOCKET_QUEUE_SIZE - 2:
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                q.put_nowait(
                    {
                        "type": "resync_required",
                        "run_id": str(run_id),
                        "sequence_number": update.sequence_number,
                    }
                )
            q.put_nowait(payload)

    def building_updates_after(
        self, run_id: uuid.UUID, sequence_number: int
    ) -> tuple[int | None, list[ApplianceStateUpdate]]:
        """Return the retained update range after a client sequence cursor."""
        entry = self._runs.get(run_id)
        if entry is None or not entry.building_update_buffer:
            return None, []
        updates = entry.building_update_buffer
        return updates[0].sequence_number, [
            update for update in updates if update.sequence_number > sequence_number
        ]

    def push_event(self, run_id: uuid.UUID, event: ControlEvent) -> None:
        """Retain actual run events for live API consumers."""
        entry = self._runs.get(run_id)
        if entry is not None:
            entry.event_buffer.append(event)
            if len(entry.event_buffer) > MAX_RETAINED_EVENTS:
                del entry.event_buffer[: len(entry.event_buffer) - MAX_RETAINED_EVENTS]
            payload = {"type": "control_event", **event.model_dump(mode="json")}
            for q in entry.ws_queues:
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    continue

    def subscribe_ws(self, run_id: uuid.UUID) -> asyncio.Queue[object] | None:
        entry = self._runs.get(run_id)
        if entry is None:
            return None
        q: asyncio.Queue[object] = asyncio.Queue(maxsize=WEBSOCKET_QUEUE_SIZE)
        entry.ws_queues.add(q)
        return q

    def unsubscribe_ws(self, run_id: uuid.UUID, q: asyncio.Queue[object]) -> None:
        entry = self._runs.get(run_id)
        if entry:
            entry.ws_queues.discard(q)
            self._prune_terminal_runs()

    def get_run_state(self, run_id: uuid.UUID) -> RunState | None:
        entry = self._runs.get(run_id)
        if entry is None:
            return None
        clock = entry.clock
        current_time = clock.current_state().time_s if clock else 0.0
        return RunState(
            run_id=run_id,
            status=entry.status,  # type: ignore[arg-type]
            current_time_s=current_time,
            latest_sample=entry.latest_sample,
            active_buildings=entry.active_buildings,
            playback_speed=entry.playback_speed,
            is_paused=clock.is_paused() if clock else False,
        )


# Module-level singleton
run_manager = RunManager()
