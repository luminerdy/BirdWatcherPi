"""The writer is bounded and must not block the camera producer."""

import errno
from dataclasses import dataclass

import pytest


@dataclass
class Action:
    kind: str
    event_id: str = "test-event"
    frame: object = None
    reason: str | None = None


class Store:
    def __init__(self):
        self.actions = []

    def apply(self, action):
        self.actions.append(action)


def test_writer_drains_actions_on_close():
    from birdwatcher.runner import ActionWriter

    store = Store()
    with ActionWriter(store) as writer:
        assert writer.put(Action("start"))
        assert writer.put(Action("end"))
    assert [a.kind for a in store.actions] == ["start", "end"]


def test_writer_reports_storage_errors_without_crashing_producer():
    from birdwatcher.runner import ActionWriter

    class BrokenStore:
        def apply(self, action):
            raise OSError("disk unavailable")

    with ActionWriter(BrokenStore()) as writer:
        assert writer.put(Action("start"))
    assert writer.errors == 1


def test_writer_rejects_oversized_work_without_waiting():
    from types import SimpleNamespace

    from birdwatcher.runner import ActionWriter

    store = Store()
    with ActionWriter(store, max_bytes=10) as writer:
        assert not writer.put(Action("frame", frame=SimpleNamespace(jpeg=b"x" * 11)))
        assert writer.dropped == 1
        assert writer.pending_bytes == 0


def test_writer_marks_dropped_event_incomplete():
    from types import SimpleNamespace

    from birdwatcher.runner import ActionWriter

    store = Store()
    with ActionWriter(store, max_bytes=10) as writer:
        assert writer.put(Action("start"))
        assert not writer.put(Action("frame", frame=SimpleNamespace(jpeg=b"x" * 11)))
        assert writer.put(Action("end"))
    assert store.actions[-1].reason == "writer_overload"


def test_writer_bytes_released_after_error():
    from types import SimpleNamespace

    from birdwatcher.runner import ActionWriter

    class BrokenStore:
        def apply(self, action):
            raise OSError("disk unavailable")

    with ActionWriter(BrokenStore(), max_bytes=10) as writer:
        writer.put(Action("frame", frame=SimpleNamespace(jpeg=b"x" * 5)))
    assert writer.pending_bytes == 0


def test_writer_reserves_space_for_event_end_under_frame_overload():
    import threading
    from types import SimpleNamespace

    from birdwatcher.runner import ActionWriter

    entered = threading.Event()
    release = threading.Event()

    class SlowStore(Store):
        def apply(self, action):
            if action.kind == "start":
                entered.set()
                assert release.wait(timeout=3)
            super().apply(action)

    store = SlowStore()
    with ActionWriter(store, max_items=2) as writer:
        try:
            assert writer.put(Action("start"))
            assert entered.wait(timeout=2)
            for _ in range(4):
                writer.put(Action("frame", frame=SimpleNamespace(jpeg=b"jpeg")))
            assert writer.put(Action("end"))
        finally:
            release.set()
    assert store.actions[-1].kind == "end"
    assert store.actions[-1].reason == "writer_overload"


def test_writer_health_counts_queued_items_and_inflight_bytes_without_waiting():
    import threading
    from types import SimpleNamespace

    from birdwatcher.runner import ActionWriter

    entered = threading.Event()
    release = threading.Event()

    class SlowStore(Store):
        def apply(self, action):
            entered.set()
            assert release.wait(timeout=3)
            super().apply(action)

    with ActionWriter(SlowStore()) as writer:
        try:
            assert writer.put(Action("frame", frame=SimpleNamespace(jpeg=b"first")))
            assert entered.wait(timeout=2)
            assert writer.put(Action("frame", frame=SimpleNamespace(jpeg=b"next")))
            snapshot = writer.health()
            assert snapshot["writer_queue_depth"] == 1
            assert snapshot["writer_pending_bytes"] == 9
        finally:
            release.set()
    assert writer.health()["writer_queue_depth"] == 0
    assert writer.health()["writer_pending_bytes"] == 0


def test_writer_health_caches_storage_full_and_retains_write_error(tmp_path, monkeypatch):
    from dataclasses import replace
    from datetime import datetime

    from birdwatcher.config import StorageConfig
    from birdwatcher.events import EventAction, Frame
    from birdwatcher.runner import ActionWriter
    from birdwatcher.storage import EventStore

    store = EventStore(StorageConfig(tmp_path / "data", min_free_bytes=0, max_bytes=1))
    frame = Frame(1, "2020-01-01T00:00:00Z", 1.0, b"synthetic")
    with ActionWriter(store) as writer:
        assert writer.put(EventAction("start", "failed", frame))
        writer.queue.join()
        snapshot = writer.health()
        assert snapshot["storage_full"] is True
        assert snapshot["storage_errors"] == 1
        assert snapshot["storage_last_error"] == "storage_write_failed"
        assert datetime.fromisoformat(snapshot["storage_health_updated_utc"]).tzinfo is not None
        # A later successful attempt refreshes fullness, not the cumulative error.
        store.config = replace(store.config, max_bytes=100000)
        assert writer.put(EventAction("start", "accepted", frame))
        assert writer.put(EventAction("end", "accepted", reason="quiet"))
        writer.queue.join()

        def forbidden():
            raise AssertionError("Producer health must not call or scan the store")

        monkeypatch.setattr(store, "health", forbidden)
        monkeypatch.setattr(store, "_scan", forbidden)
        monkeypatch.setattr(store, "_usage", forbidden)
        snapshot = writer.health()
        assert snapshot["storage_full"] is False
        assert snapshot["storage_errors"] == 1
        assert snapshot["storage_last_error"] == "storage_write_failed"


@pytest.mark.parametrize("error_code", [errno.ENOSPC, errno.EDQUOT, errno.EIO, errno.EACCES, None])
@pytest.mark.parametrize("failing_sync", [1, 2], ids=["file-fsync", "directory-fsync"])
def test_writer_health_observes_fullness_after_fsync_failure(
    tmp_path, monkeypatch, error_code, failing_sync
):
    from datetime import datetime

    from birdwatcher import storage
    from birdwatcher.config import StorageConfig
    from birdwatcher.events import EventAction, Frame
    from birdwatcher.runner import ActionWriter

    store = storage.EventStore(StorageConfig(tmp_path / "data", min_free_bytes=0))
    frame = Frame(1, "2020-01-01T00:00:00Z", 1.0, b"synthetic")
    real_fsync = storage.os.fsync
    calls = 0

    def fail_sync(descriptor):
        nonlocal calls
        calls += 1
        if calls == failing_sync:
            raise OSError(error_code, "Synthetic write failure")
        return real_fsync(descriptor)

    with ActionWriter(store) as writer:
        before = writer.health()["storage_health_updated_utc"]
        with monkeypatch.context() as patch:
            patch.setattr(storage.os, "fsync", fail_sync)
            assert writer.put(EventAction("start", "failed", frame))
            writer.queue.join()
        snapshot = writer.health()
        assert calls == failing_sync
        assert snapshot["storage_errors"] == 1
        assert snapshot["storage_last_error"] == "storage_write_failed"
        assert datetime.fromisoformat(
            snapshot["storage_health_updated_utc"]
        ) > datetime.fromisoformat(before)
        expected_full = error_code in (errno.ENOSPC, errno.EDQUOT)
        assert store.health()["storage_full"] is expected_full
        assert snapshot["storage_full"] is expected_full

        # A health read is cached, not an opportunity to re-probe/clear fullness.
        with monkeypatch.context() as patch:

            def forbidden(*args, **kwargs):
                raise AssertionError("Producer health must not probe storage")

            patch.setattr(store, "health", forbidden)
            patch.setattr(store, "_scan", forbidden)
            patch.setattr(store, "_usage", forbidden)
            patch.setattr(storage.shutil, "disk_usage", forbidden)
            assert writer.health() == snapshot

        # A later successful start rechecks capacity, retaining cumulative errors.
        assert writer.put(EventAction("start", "accepted", frame))
        assert writer.put(EventAction("end", "accepted", reason="quiet"))
        writer.queue.join()
        recovered = writer.health()
        assert recovered["storage_full"] is False
        assert recovered["storage_errors"] == 1
        assert recovered["storage_last_error"] == "storage_write_failed"
    store.close()


def test_capture_publishes_writer_health_periodically_on_reconnect_and_stop(tmp_path, monkeypatch):
    import json
    from dataclasses import replace

    import cv2
    import numpy as np

    from birdwatcher import runner
    from birdwatcher.camera import CameraError
    from birdwatcher.config import AppConfig

    config = AppConfig()
    config = replace(
        config,
        storage=replace(config.storage, data_dir=tmp_path / "data", min_free_bytes=0, max_bytes=1),
    )
    ok, encoded = cv2.imencode(".jpg", np.zeros((16, 16, 3), dtype=np.uint8))
    assert ok

    class ReplayCamera:
        settings = {"pixel_format": "MJPG"}

        def __init__(self, config):
            self.reads = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            self.reads += 1
            if self.reads > 1:
                raise CameraError("synthetic disconnect")
            return encoded.tobytes()

    class Arrival:
        def __init__(self, config):
            pass

        def reset(self):
            pass

        def update(self, frame):
            return ("synthetic",)

    snapshots = []
    write_health = runner._write_health

    def record_health(root, health):
        snapshots.append(dict(health))
        write_health(root, health)

    monkeypatch.setattr(runner, "_write_health", record_health)
    result = runner.run_capture(
        config, duration=0.2, camera_factory=ReplayCamera, motion_factory=Arrival
    )
    assert {snapshot["state"] for snapshot in snapshots} == {"capturing", "reconnecting", "stopped"}
    for snapshot in snapshots:
        assert "writer_queue_depth" in snapshot
        assert "writer_pending_bytes" in snapshot
        assert "storage_full" in snapshot
        assert "storage_last_error" in snapshot
        assert "storage_health_updated_utc" in snapshot
    assert result["storage_full"] is True
    assert result["storage_errors"] >= 1
    assert result["storage_last_error"] == "storage_write_failed"
    assert result["writer_queue_depth"] == result["writer_pending_bytes"] == 0
    assert json.loads((config.storage.data_dir / "health.json").read_text()) == result
