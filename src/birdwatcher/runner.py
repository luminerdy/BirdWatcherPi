"""Bounded capture-to-disk handoff and foreground capture orchestration."""

import queue
import threading
from dataclasses import replace
from datetime import datetime, timezone


class ActionWriter:
    """Never wait for disk on the producer path; surface missed saves explicitly."""

    def __init__(self, store, max_items=64, max_bytes=64 * 1024 * 1024):
        self.store = store
        self.queue = queue.Queue(maxsize=max_items)
        self.max_bytes = max_bytes
        self.pending_bytes = 0
        self.dropped = 0
        self.errors = 0
        self.last_error = None
        self.bad_events = set()
        self._reserved_endings = set()
        self._ignored_events = set()
        self._lock = threading.Lock()
        self._storage_health = store.health() if hasattr(store, "health") else {}
        self._storage_health_updated_utc = datetime.now(timezone.utc).isoformat()
        self._thread = threading.Thread(target=self._work, daemon=True, name="photo-writer")

    def __enter__(self):
        self._thread.start()
        return self

    def put(self, action):
        size = len(action.frame.jpeg) if action.frame is not None else 0
        with self._lock:
            if action.event_id in self._ignored_events and action.kind != "start":
                self._drop(action)
                if action.kind == "end":
                    self._ignored_events.discard(action.event_id)
                return False
            # Reserve an end slot when admitting each start. Frames can be
            # dropped, but an accepted event must always be able to close.
            needed = 2 if action.kind == "start" else 1
            if action.kind == "end" and action.event_id in self._reserved_endings:
                needed = 0
            if self.queue.qsize() + len(self._reserved_endings) + needed > self.queue.maxsize:
                self._drop(action)
                return False
            if size + self.pending_bytes > self.max_bytes:
                self._drop(action)
                return False
            try:
                self.queue.put_nowait((action, size))
            except queue.Full:
                self._drop(action)
                return False
            self.pending_bytes += size
            if action.kind == "start":
                self._reserved_endings.add(action.event_id)
            elif action.kind == "end":
                self._reserved_endings.discard(action.event_id)
        return True

    def health(self):
        """Cheap snapshot; queued items exclude work already in flight.

        Pending JPEG bytes include in-flight work, not metadata or disk usage.
        Storage fullness is last observed at initialization/after a write attempt,
        not a live disk probe. Errors are cumulative, with the last error retained.
        """
        with self._lock:
            return {
                "writer_queue_depth": self.queue.qsize(),
                "writer_pending_bytes": self.pending_bytes,
                "dropped_saves": self.dropped,
                "storage_errors": self.errors,
                "storage_last_error": self.last_error,
                "storage_full": self._storage_health.get("storage_full"),
                "storage_health_updated_utc": self._storage_health_updated_utc,
            }

    def _drop(self, action):
        self.dropped += 1
        self.bad_events.add(action.event_id)
        if action.kind == "start":
            self._ignored_events.add(action.event_id)
            self.bad_events.discard(action.event_id)
        if action.kind == "end":
            # A missing end leaves an incomplete event for storage recovery.
            self.bad_events.discard(action.event_id)

    def _work(self):
        while True:
            item = self.queue.get()
            if item is None:
                self.queue.task_done()
                return
            action, size = item
            try:
                with self._lock:
                    if action.kind == "end" and action.event_id in self.bad_events:
                        action = replace(action, reason="writer_overload")
                self.store.apply(action)
            except (OSError, ValueError, RuntimeError):
                with self._lock:
                    self.errors += 1
                    self.last_error = "storage_write_failed"
                    self.bad_events.add(action.event_id)
            finally:
                storage_health = self.store.health() if hasattr(self.store, "health") else {}
                with self._lock:
                    self._storage_health = storage_health
                    self._storage_health_updated_utc = datetime.now(timezone.utc).isoformat()
                    self.pending_bytes -= size
                    if action.kind == "end":
                        self.bad_events.discard(action.event_id)
                self.queue.task_done()

    def __exit__(self, *args):
        try:
            self.queue.put(None, timeout=5)
        except queue.Full:
            raise OSError("Storage writer stalled; events may be incomplete") from None
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            raise OSError("Storage writer did not stop; events may be incomplete")


def _write_health(root, health):
    import json
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", dir=root, prefix=".health-", delete=False) as file:
        temporary = file.name
        try:
            json.dump(health, file, indent=2)
            file.flush()
            os.fsync(file.fileno())
            os.replace(temporary, root / "health.json")
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def run_capture(config, duration=None, camera_factory=None, motion_factory=None):
    """Run foreground capture with a bounded writer; no inference or uploads.

    Camera receipt timestamps are used, not claimed sensor exposure timestamps.
    Dependency injection permits explicit synthetic/replay integration tests.
    """
    import signal
    import time
    from datetime import datetime, timezone

    import cv2
    import numpy as np

    from .camera import Camera, CameraError, CameraLock
    from .events import EventMachine, Frame
    from .motion import MotionDetector
    from .storage import EventStore

    camera_factory = camera_factory or Camera
    motion_factory = motion_factory or MotionDetector
    stopped = threading.Event()
    previous_handlers = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, lambda *_: stopped.set())
    root = config.storage.data_dir
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    health = {
        "state": "starting",
        "frames_received": 0,
        "events_started": 0,
        "reconnects": 0,
        "invalid_frames": 0,
        "dropped_saves": 0,
        "storage_errors": 0,
        "species_identification": "not_implemented",
    }
    started = time.monotonic()
    deadline = started + duration if duration is not None else float("inf")
    last_health = 0

    def running():
        return not stopped.is_set() and time.monotonic() < deadline

    try:
        # Protect recovery and writes even while the camera is reconnecting.
        with CameraLock(root / ".run.lock"):
            store = EventStore(config.storage)
            detector = motion_factory(config.motion)
            machine = EventMachine(config.capture)
            backoff = 1
            frame_id = 0
            try:
                with ActionWriter(store) as writer:
                    while running():
                        try:
                            with camera_factory(config.camera) as camera:
                                detector.reset()
                                last_motion = last_sample = 0
                                active = ()
                                while running():
                                    jpeg = camera.read()
                                    now = time.monotonic()
                                    health["frames_received"] += 1
                                    health["state"] = "capturing"
                                    health["capture"] = dict(camera.settings)
                                    store.camera_settings = dict(camera.settings)
                                    backoff = 1
                                    if now - last_motion >= 1 / 8:
                                        image = cv2.imdecode(
                                            np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR
                                        )
                                        if image is None:
                                            health["invalid_frames"] += 1
                                            continue
                                        active = detector.update(image)
                                        last_motion = now
                                    if now - last_sample >= 1 / config.capture.sample_fps:
                                        frame_id += 1
                                        frame = Frame(
                                            frame_id,
                                            datetime.now(timezone.utc).isoformat(),
                                            now,
                                            jpeg,
                                        )
                                        for action in machine.update(frame, active):
                                            if action.kind == "start":
                                                health["events_started"] += 1
                                            writer.put(action)
                                        last_sample = now
                                    if now - last_health >= 1:
                                        health.update(writer.health())
                                        health.update(
                                            updated_utc=datetime.now(timezone.utc).isoformat(),
                                        )
                                        _write_health(root, health)
                                        last_health = now
                        except CameraError:
                            for action in machine.close():
                                writer.put(replace(action, reason="camera_lost"))
                            machine = EventMachine(config.capture)
                            health["state"] = "reconnecting"
                            health["reconnects"] += 1
                            health["last_error"] = "camera_unavailable"
                            health.update(writer.health())
                            _write_health(root, health)
                            stopped.wait(max(0, min(backoff, deadline - time.monotonic())))
                            backoff = min(backoff * 2, 30)
                    for action in machine.close():
                        writer.put(action)
                health.update(writer.health())
            finally:
                store.close()
            health["state"] = "stopped"
            health["updated_utc"] = datetime.now(timezone.utc).isoformat()
            _write_health(root, health)
        return health
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
