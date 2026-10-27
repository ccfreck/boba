"""Bounded sliding-window detection scoped to one configured agent/server."""

from collections import deque
from time import monotonic


class RateDetector:
    def __init__(self) -> None:
        self.windows: dict[str, deque[float]] = {}

    def observe(self, rule_id: str, threshold: int, window: int, now: float | None = None) -> bool:
        current = monotonic() if now is None else now
        timestamps = self.windows.setdefault(rule_id, deque(maxlen=threshold + 1))
        while timestamps and timestamps[0] <= current - window:
            timestamps.popleft()
        timestamps.append(current)
        return len(timestamps) > threshold
