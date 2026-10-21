"""Shared, conservative request pacing for all worker jobs."""

from __future__ import annotations

import random
import threading
import time


class RequestLimiter:
    """Process-wide minimum-interval limiter with adaptive cooldown.

    It deliberately limits starts rather than trying to infer Google's quota.
    A worker can share one instance across threads; cancellation is checked
    while waiting so a queued job remains responsive.
    """

    def __init__(self, min_interval: float = 1.0, jitter: float = 0.15,
                 max_cooldown: float = 120.0):
        self.min_interval = max(0.0, min_interval)
        self.jitter = max(0.0, jitter)
        self.max_cooldown = max_cooldown
        self._next_allowed = 0.0
        self._cooldown = 0.0
        self._lock = threading.Condition()
        self.requests = 0
        self.throttles = 0

    def acquire(self, cancel_event=None) -> float:
        waited = 0.0
        with self._lock:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise InterruptedError("request cancelled while waiting for limiter")
                now = time.monotonic()
                delay = self._next_allowed - now
                if delay <= 0:
                    spacing = self.min_interval + self._cooldown
                    self._next_allowed = now + spacing + random.uniform(0, self.jitter)
                    self.requests += 1
                    return waited
                self._lock.wait(timeout=min(delay, 0.25))
                waited += min(delay, 0.25)

    def record_throttle(self) -> None:
        with self._lock:
            self.throttles += 1
            self._cooldown = min(
                self.max_cooldown,
                max(0.25, self.min_interval, self._cooldown * 2 or 0.25),
            )

    def record_success(self) -> None:
        with self._lock:
            self._cooldown *= 0.75
            if self._cooldown < 0.01:
                self._cooldown = 0.0

    @property
    def cooldown(self) -> float:
        with self._lock:
            return self._cooldown
