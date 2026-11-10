"""
Unit tests for the in-process message bus with fault injection (Prompt 7).

Tests:
  1. loss_probability=1.0 → no messages delivered
  2. loss_probability=0.0 → all messages delivered exactly once
  3. duplicate_probability=1.0 → messages delivered exactly twice
  4. Delayed messages not delivered before their scheduled time
  5. Out-of-order flag causes at least one reordering across 20 messages
  6. flush() delivers all pending messages
  7. Subscribing to one topic receives only messages for that topic
"""

from __future__ import annotations

import numpy as np
import pytest

from app.messaging.in_process_bus import FaultConfig, InProcessBus

TOPIC_A = "gridshield/v1/buildings/B1/commands"
TOPIC_B = "gridshield/v1/buildings/B2/commands"


def _rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


# --------------------------------------------------------------------------
# Test 1: loss_probability=1.0 → no messages delivered
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_all_messages_lost():
    cfg = FaultConfig(loss_probability=1.0)
    bus = InProcessBus(cfg, _rng())
    received = []

    async def handler(payload: dict) -> None:
        received.append(payload)

    bus.subscribe(TOPIC_A, handler)

    for _ in range(5):
        await bus.publish(TOPIC_A, {"cmd": "shed"})

    await bus.flush()
    assert len(received) == 0, f"Expected 0 deliveries, got {len(received)}"


# --------------------------------------------------------------------------
# Test 2: loss_probability=0.0 → all messages delivered exactly once
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_loss_all_delivered_once():
    cfg = FaultConfig(loss_probability=0.0)
    bus = InProcessBus(cfg, _rng())
    received = []

    async def handler(payload: dict) -> None:
        received.append(payload)

    bus.subscribe(TOPIC_A, handler)

    n = 5
    for i in range(n):
        await bus.publish(TOPIC_A, {"i": i})

    await bus.flush()
    assert len(received) == n, f"Expected {n} deliveries, got {len(received)}"


# --------------------------------------------------------------------------
# Test 3: duplicate_probability=1.0 → messages delivered exactly twice
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_duplicate_probability_one():
    cfg = FaultConfig(duplicate_probability=1.0)
    bus = InProcessBus(cfg, _rng())
    received = []

    async def handler(payload: dict) -> None:
        received.append(payload)

    bus.subscribe(TOPIC_A, handler)

    n = 3
    for i in range(n):
        await bus.publish(TOPIC_A, {"i": i})

    await bus.flush()
    assert len(received) == n * 2, f"Expected {n*2} deliveries (duplicates), got {len(received)}"


# --------------------------------------------------------------------------
# Test 4: Delayed messages not delivered before scheduled time
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delayed_messages_held():
    cfg = FaultConfig(delay_range_s=(10.0, 10.0))  # 10s delay
    bus = InProcessBus(cfg, _rng(), sim_time_s=0.0)
    received = []

    async def handler(payload: dict) -> None:
        received.append(payload)

    bus.subscribe(TOPIC_A, handler)
    await bus.publish(TOPIC_A, {"cmd": "shed"})

    # Flush at t=5 — message has delay=10, not eligible
    await bus.flush(sim_time_s=5.0)
    assert len(received) == 0, "Message should not be delivered before delay expires"

    # Flush at t=11 — now eligible
    await bus.flush(sim_time_s=11.0)
    assert len(received) == 1, "Message should be delivered after delay expires"


# --------------------------------------------------------------------------
# Test 5: Out-of-order delivers messages in shuffled order
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_out_of_order_causes_reordering():
    cfg = FaultConfig(out_of_order=True, shuffle_window_size=5)
    # Use a fixed seed that we know shuffles; test 100 seeds if needed
    bus = InProcessBus(cfg, _rng(seed=0))
    received_order = []

    async def handler(payload: dict) -> None:
        received_order.append(payload["seq"])

    bus.subscribe(TOPIC_A, handler)

    n = 20
    for i in range(n):
        await bus.publish(TOPIC_A, {"seq": i})

    await bus.flush()

    assert len(received_order) == n, f"Expected {n} messages, got {len(received_order)}"
    # Check that at least one message arrived out of sequential order
    is_reordered = any(
        received_order[j] < received_order[j - 1]
        for j in range(1, len(received_order))
    )
    assert is_reordered, (
        f"Expected at least one out-of-order delivery, got sequence: {received_order}"
    )


# --------------------------------------------------------------------------
# Test 6: flush() delivers all pending messages
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flush_delivers_all_pending():
    cfg = FaultConfig(delay_range_s=(100.0, 100.0))  # large delay
    bus = InProcessBus(cfg, _rng(), sim_time_s=0.0)
    received = []

    async def handler(payload: dict) -> None:
        received.append(payload)

    bus.subscribe(TOPIC_A, handler)

    for i in range(4):
        await bus.publish(TOPIC_A, {"i": i})

    assert bus.pending_count == 4

    # flush with no sim_time → deliver all regardless of delay
    await bus.flush()
    assert len(received) == 4


# --------------------------------------------------------------------------
# Test 7: Subscribe to one topic only receives messages on that topic
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_topic_isolation():
    cfg = FaultConfig()
    bus = InProcessBus(cfg, _rng())
    received_a = []
    received_b = []

    async def handler_a(payload: dict) -> None:
        received_a.append(payload)

    async def handler_b(payload: dict) -> None:
        received_b.append(payload)

    bus.subscribe(TOPIC_A, handler_a)
    bus.subscribe(TOPIC_B, handler_b)

    await bus.publish(TOPIC_A, {"topic": "A"})
    await bus.publish(TOPIC_A, {"topic": "A"})
    await bus.publish(TOPIC_B, {"topic": "B"})

    await bus.flush()

    assert len(received_a) == 2, f"Expected 2 on topic A, got {len(received_a)}"
    assert len(received_b) == 1, f"Expected 1 on topic B, got {len(received_b)}"
