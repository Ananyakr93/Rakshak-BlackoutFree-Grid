"""
WebSocket endpoint for real-time simulation streaming.

  WS /api/v1/runs/{run_id}/stream

Streams TelemetrySample JSON at WS_PUSH_INTERVAL_S rate.
Supports multiple simultaneous clients per run.
Handles disconnection gracefully — does not crash the simulation.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.run_manager import run_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/runs/{run_id}/stream")
async def stream_run(
    websocket: WebSocket,
    run_id: uuid.UUID,
    after_sequence: int = Query(default=0, ge=0),
) -> None:
    """Stream telemetry plus replayable appliance transitions for the given run."""
    await websocket.accept()

    q = run_manager.subscribe_ws(run_id)
    if q is None:
        await websocket.send_json({"error": f"Run {run_id} not found"})
        await websocket.close()
        return

    entry = run_manager.get(run_id)
    last_building_sequence = after_sequence
    try:
        oldest_sequence, updates = run_manager.building_updates_after(
            run_id, after_sequence
        )
        if oldest_sequence is not None and after_sequence < oldest_sequence - 1:
            await websocket.send_json(
                {
                    "type": "resync_required",
                    "run_id": str(run_id),
                    "sequence_number": (
                        entry.clock.building_sequence_number
                        if entry and entry.clock
                        else 0
                    ),
                }
            )
            if entry is not None and entry.clock is not None:
                snapshots = entry.clock.building_snapshots()
                last_building_sequence = entry.clock.building_sequence_number
                await websocket.send_json(
                    {
                        "type": "building_snapshot",
                        "schema_version": "1.0",
                        "run_id": str(run_id),
                        "simulation_time_s": entry.clock.current_state().time_s,
                        "sequence_number": last_building_sequence,
                        "buildings": [
                            {**snapshot, "run_id": str(run_id)}
                            for snapshot in snapshots
                        ],
                    }
                )
        else:
            if after_sequence == 0 and entry is not None and entry.clock is not None:
                await websocket.send_json(
                    {
                        "type": "building_snapshot",
                        "schema_version": "1.0",
                        "run_id": str(run_id),
                        "simulation_time_s": 0.0,
                        "sequence_number": 0,
                        "buildings": [
                            {**snapshot, "run_id": str(run_id)}
                            for snapshot in entry.clock.building_snapshots(initial=True)
                        ],
                    }
                )
            for update in updates:
                await websocket.send_json(update.model_dump(mode="json"))
                last_building_sequence = update.sequence_number

        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=2.0)
                if isinstance(payload, dict) and payload.get("type") == "resync_required":
                    await websocket.send_json(payload)
                    entry = run_manager.get(run_id)
                    if entry is not None and entry.clock is not None:
                        last_building_sequence = entry.clock.building_sequence_number
                        await websocket.send_json(
                            {
                                "type": "building_snapshot",
                                "schema_version": "1.0",
                                "run_id": str(run_id),
                                "simulation_time_s": entry.clock.current_state().time_s,
                                "sequence_number": last_building_sequence,
                                "buildings": [
                                    {**snapshot, "run_id": str(run_id)}
                                    for snapshot in entry.clock.building_snapshots()
                                ],
                            }
                        )
                elif isinstance(payload, dict):
                    if payload.get("type") == "building_state_update":
                        sequence = payload.get("sequence_number")
                        if isinstance(sequence, int) and sequence <= last_building_sequence:
                            continue
                        if isinstance(sequence, int):
                            last_building_sequence = sequence
                    await websocket.send_json(payload)
            except asyncio.TimeoutError:
                # Send a heartbeat ping; if the client is gone, this will raise
                entry = run_manager.get(run_id)
                if entry and entry.status in ("completed", "failed"):
                    await websocket.send_json({"type": "run_complete", "status": entry.status})
                    break
                # ping to keep alive
                await websocket.send_json({"type": "ping"})

    except WebSocketDisconnect:
        pass
    finally:
        run_manager.unsubscribe_ws(run_id, q)
        try:
            await websocket.close()
        except Exception:
            pass
