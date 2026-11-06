"""Filesystem-independent sampled-JPEG event lifecycle."""

from collections import deque
from dataclasses import dataclass
from uuid import uuid4

from .config import CaptureConfig


@dataclass(frozen=True)
class Frame:
    id: int
    utc: str
    monotonic: float
    jpeg: bytes


@dataclass(frozen=True)
class EventAction:
    kind: str
    event_id: str
    frame: Frame | None = None
    regions: tuple[str, ...] = ()
    reason: str | None = None


class EventMachine:
    def __init__(self, config: CaptureConfig):
        self.config = config
        self._buffer = deque()
        self._event = None
        self._regions = ()
        self._saved = set()
        self._cooldown_until = float("-inf")
        self._last_time = float("-inf")
        self._buffer_bytes = 0

    def _end(self, reason):
        result = EventAction("end", self._event, regions=self._regions, reason=reason)
        self._event = None
        self._saved.clear()
        return result

    def update(self, frame: Frame, active_regions: tuple[str, ...]) -> list[EventAction]:
        import math

        t, c = frame.monotonic, self.config
        if not math.isfinite(t) or t < self._last_time:
            raise ValueError("Frame monotonic time must not go backwards")
        self._last_time = t
        while self._buffer and self._buffer[0].monotonic < t - c.pre_seconds - 1e-9:
            self._buffer_bytes -= len(self._buffer.popleft().jpeg)
        actions = []
        previous = None
        if self._event is not None:
            if t - self._started >= c.max_event_seconds:
                previous = self._event
                actions.append(self._end("max_duration"))
                if not active_regions:
                    self._cooldown_until = t + c.cooldown_seconds
            elif not active_regions and t - self._last_active >= c.quiet_seconds:
                actions.append(self._end("quiet"))
                self._cooldown_until = t + c.cooldown_seconds
        if self._event is None and active_regions and t >= self._cooldown_until:
            self._event = uuid4().hex
            self._regions = tuple(dict.fromkeys(active_regions))
            self._started = self._last_active = self._burst_start = t
            self._bursts = 1
            actions.append(
                EventAction(
                    "start",
                    self._event,
                    frame,
                    self._regions,
                    "continuation:" + previous if previous else "motion",
                )
            )
            for item in self._buffer:
                self._save(item, actions)
        if self._event is not None:
            if active_regions:
                self._regions = tuple(dict.fromkeys((*self._regions, *active_regions)))
                self._last_active = t
                if t - self._burst_start >= c.repeat_seconds and self._bursts < c.max_bursts:
                    self._burst_start = t
                    self._bursts += 1
            if t - self._burst_start < c.post_seconds - 1e-9:
                self._save(frame, actions)
        self._buffer.append(frame)
        self._buffer_bytes += len(frame.jpeg)
        count = max(0, math.ceil(c.pre_seconds * c.sample_fps))
        while self._buffer and (
            len(self._buffer) > count or self._buffer_bytes > c.max_buffer_bytes
        ):
            self._buffer_bytes -= len(self._buffer.popleft().jpeg)
        return actions

    def _save(self, frame, actions):
        if frame.id not in self._saved:
            self._saved.add(frame.id)
            actions.append(EventAction("frame", self._event, frame, self._regions))

    def close(self) -> list[EventAction]:
        if self._event is None:
            return []
        action = EventAction("end", self._event, regions=self._regions, reason="shutdown")
        self._event = None
        self._saved.clear()
        return [action]
