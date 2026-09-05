"""In-process sliding-window rate limiting keyed by action + identity."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from .. import config


class RateLimiter:
    def __init__(self):
        self._hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self._last_sweep = time.monotonic()

    def check(self, action: str, identity: str) -> tuple[bool, float]:
        """Returns (allowed, retry_after_seconds)."""
        limit, window = config.RATE_LIMITS.get(
            action, config.RATE_LIMITS["default"])
        now = time.monotonic()
        key = (action, identity)
        bucket = self._hits[key]
        cutoff = now - window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            return False, max(0.5, bucket[0] + window - now)
        bucket.append(now)
        if now - self._last_sweep > 120:
            self._sweep(now)
        return True, 0.0

    def reset(self, action: str, identity: str):
        self._hits.pop((action, identity), None)

    def _sweep(self, now: float):
        self._last_sweep = now
        dead = []
        for key, bucket in self._hits.items():
            limit, window = config.RATE_LIMITS.get(
                key[0], config.RATE_LIMITS["default"])
            while bucket and bucket[0] < now - window:
                bucket.popleft()
            if not bucket:
                dead.append(key)
        for key in dead:
            self._hits.pop(key, None)


limiter = RateLimiter()
