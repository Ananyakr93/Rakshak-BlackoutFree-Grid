from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.core.run_manager import (
    MAX_RETAINED_TERMINAL_RUNS,
    WEBSOCKET_QUEUE_SIZE,
    RunManager,
)
from app.db.repository import mark_unfinished_runs_failed
from app.schemas.events import ApplianceStateUpdate


def test_terminal_run_retention_is_bounded_without_evicting_active_runs() -> None:
    manager = RunManager()
    active_id = uuid.uuid4()
    manager.register(active_id, "P2_priority_edge", 1)

    terminal_ids = []
    for _ in range(MAX_RETAINED_TERMINAL_RUNS + 5):
        run_id = uuid.uuid4()
        terminal_ids.append(run_id)
        manager.register(run_id, "P2_priority_edge", 1)
        manager.set_status(run_id, "completed")

    assert manager.get(active_id) is not None
    assert manager.get(terminal_ids[0]) is None
    assert all(manager.get(run_id) is not None for run_id in terminal_ids[-MAX_RETAINED_TERMINAL_RUNS:])


def _building_update(run_id: uuid.UUID, sequence: int) -> ApplianceStateUpdate:
    return ApplianceStateUpdate(
        run_id=run_id,
        building_id="B1",
        appliance_id="light",
        appliance_type="lighting_led",
        priority="essential",
        previous_state="ON",
        current_state="SHED",
        current_power_kw=0,
        rated_power_kw=0.1,
        simulation_time_s=float(sequence),
        sequence_number=sequence,
    )


def test_building_update_replay_returns_only_sequences_after_cursor() -> None:
    manager = RunManager()
    run_id = uuid.uuid4()
    manager.register(run_id, "P2_priority_edge", 1)
    for sequence in range(1, 4):
        manager.push_building_update(run_id, _building_update(run_id, sequence))

    oldest, updates = manager.building_updates_after(run_id, 1)

    assert oldest == 1
    assert [update.sequence_number for update in updates] == [2, 3]


def test_full_websocket_queue_is_drained_and_signaled_for_resync() -> None:
    manager = RunManager()
    run_id = uuid.uuid4()
    manager.register(run_id, "P2_priority_edge", 1)
    queue = manager.subscribe_ws(run_id)
    assert queue is not None
    for value in range(WEBSOCKET_QUEUE_SIZE):
        queue.put_nowait({"type": "telemetry", "sequence_number": value})

    manager.push_building_update(run_id, _building_update(run_id, 1))

    assert queue.qsize() == WEBSOCKET_QUEUE_SIZE
    retained = list(queue._queue)
    assert any(payload.get("type") == "resync_required" for payload in retained)
    assert retained[-1]["type"] == "building_state_update"


async def test_startup_reconciliation_marks_only_unfinished_runs_failed() -> None:
    runs = [
        SimpleNamespace(status=status, completed_at=None)
        for status in ("pending", "running", "paused", "completed", "failed")
    ]

    class FakeSession:
        committed = False

        async def exec(self, _statement):
            active_runs = [
                run for run in runs if run.status in {"pending", "running", "paused"}
            ]
            return SimpleNamespace(all=lambda: active_runs)

        def add(self, _record):
            pass

        async def commit(self):
            self.committed = True

    session = FakeSession()
    count = await mark_unfinished_runs_failed(session)

    assert count == 3
    assert [run.status for run in runs] == [
        "failed",
        "failed",
        "failed",
        "completed",
        "failed",
    ]
    assert all(run.completed_at is not None for run in runs[:3])
    assert session.committed
