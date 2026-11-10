"""
In-process message bus with fault injection for GridShield.

Implements publish/subscribe with configurable faults:
  - loss_probability:       fraction of messages silently dropped
  - delay_range_s:          uniform random delivery delay (sim-time-based)
  - duplicate_probability:  fraction of messages delivered twice
  - out_of_order:           shuffle messages within a window

All randomness uses an injected numpy.random.Generator (seeded from
the scenario seed) — no calls to the stdlib random module.

Topics (MQTT-compatible for future migration):
  gridshield/v1/grid/telemetry
  gridshield/v1/buildings/{building_id}/meter
  gridshield/v1/buildings/{building_id}/commands
  gridshield/v1/buildings/{building_id}/events
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FaultConfig:
    """Communication fault injection parameters for the in-process bus."""

    delay_range_s: tuple[float, float] = (0.0, 0.0)
    loss_probability: float = 0.0
    duplicate_probability: float = 0.0
    out_of_order: bool = False
    shuffle_window_size: int = 5

    def __post_init__(self) -> None:
        lo, hi = self.delay_range_s
        assert 0.0 <= lo <= hi, "delay_range_s must satisfy 0 <= lo <= hi"
        assert 0.0 <= self.loss_probability <= 1.0
        assert 0.0 <= self.duplicate_probability <= 1.0
        assert self.shuffle_window_size >= 2


# ---------------------------------------------------------------------------
# Pending message
# ---------------------------------------------------------------------------

@dataclass
class _PendingMessage:
    topic: str
    payload: dict
    deliver_at_s: float   # sim_time_s at or after which this message is eligible


# ---------------------------------------------------------------------------
# InProcessBus
# ---------------------------------------------------------------------------

Handler = Callable[[dict], Awaitable[None]]


class InProcessBus:
    """
    In-process publish/subscribe bus with optional fault injection.

    Usage
    -----
    bus = InProcessBus(FaultConfig(), rng)
    bus.subscribe("gridshield/v1/buildings/B1/commands", my_handler)
    await bus.publish("gridshield/v1/buildings/B1/commands", {"cmd": "shed", "appliance_id": "A1"})
    await bus.flush(sim_time_s=current_time)
    """

    def __init__(
        self,
        fault_config: FaultConfig,
        rng: np.random.Generator,
        sim_time_s: float = 0.0,
    ) -> None:
        self._config = fault_config
        self._rng = rng
        self._sim_time_s = sim_time_s

        # topic -> list of subscriber handlers
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)

        # Pending delivery queue (delayed / out-of-order messages)
        self._pending: list[_PendingMessage] = []

        # Out-of-order shuffle buffer per topic
        self._shuffle_buffers: dict[str, list[_PendingMessage]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Handler) -> None:
        """Register a handler for messages on the given topic."""
        self._subscribers[topic].append(handler)

    async def publish(self, topic: str, payload: dict) -> None:
        """
        Publish a message to a topic.

        Applies fault injection: loss, delay, and duplication.
        Immediate delivery happens during flush().
        """
        cfg = self._config

        # Loss
        if cfg.loss_probability > 0.0:
            if self._rng.random() < cfg.loss_probability:
                return  # silently dropped

        # Compute delivery time
        lo, hi = cfg.delay_range_s
        delay = float(self._rng.uniform(lo, hi)) if hi > 0.0 else 0.0
        deliver_at = self._sim_time_s + delay

        msg = _PendingMessage(topic=topic, payload=payload, deliver_at_s=deliver_at)

        # Out-of-order: buffer on topic
        if cfg.out_of_order:
            buf = self._shuffle_buffers[topic]
            buf.append(msg)
            if len(buf) >= cfg.shuffle_window_size:
                # Shuffle and flush into pending queue
                indices = list(range(len(buf)))
                self._rng.shuffle(indices)
                for i in indices:
                    self._pending.append(buf[i])
                buf.clear()
        else:
            self._pending.append(msg)

        # Duplicate
        if cfg.duplicate_probability > 0.0:
            if self._rng.random() < cfg.duplicate_probability:
                delay2 = float(self._rng.uniform(lo, hi)) if hi > 0.0 else 0.0
                dup = _PendingMessage(
                    topic=topic,
                    payload=dict(payload),  # shallow copy
                    deliver_at_s=self._sim_time_s + delay2,
                )
                self._pending.append(dup)

    async def flush(self, sim_time_s: float | None = None) -> None:
        """
        Deliver all pending messages whose deliver_at_s <= sim_time_s.

        If sim_time_s is None, deliver all pending messages immediately.
        Also flushes any remaining out-of-order shuffle buffers.
        """
        if sim_time_s is not None:
            self._sim_time_s = sim_time_s

        # Flush remaining out-of-order buffers
        for _topic, buf in self._shuffle_buffers.items():
            if buf:
                indices = list(range(len(buf)))
                self._rng.shuffle(indices)
                for i in indices:
                    self._pending.append(buf[i])
                buf.clear()

        # Deliver eligible messages
        remaining = []
        for msg in self._pending:
            if sim_time_s is None or msg.deliver_at_s <= self._sim_time_s:
                handlers = self._subscribers.get(msg.topic, [])
                for handler in handlers:
                    await handler(msg.payload)
            else:
                remaining.append(msg)
        self._pending = remaining

    def advance_time(self, sim_time_s: float) -> None:
        """Update the internal simulation time without flushing."""
        self._sim_time_s = sim_time_s

    @property
    def pending_count(self) -> int:
        """Number of messages waiting to be delivered."""
        return len(self._pending)
