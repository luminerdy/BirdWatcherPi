import json

import pytest

from birdwatcher.config import StorageConfig
from birdwatcher.events import EventAction, Frame


def test_malformed_manifests_do_not_break_pruning(tmp_path):
    from birdwatcher.storage import EventStore

    config = StorageConfig(tmp_path / "data", min_free_bytes=0, retention_days=100000)
    store = EventStore(config)
    f = Frame(1, "2000-01-01T00:00:00Z", 1, b"jpeg")
    store.apply(EventAction("start", "bad", f))
    store.apply(EventAction("end", "bad"))
    manifest = next(config.data_dir.glob("*/*/event.json"))
    data = json.loads(manifest.read_text())
    data["frames"] = [None]
    manifest.write_text(json.dumps(data))
    from dataclasses import replace

    recovered = EventStore(replace(config, retention_days=1))
    assert manifest.exists()
    assert recovered.events() == []


def test_frame_writes_do_not_rescan_and_interrupted_end_is_incomplete(tmp_path, monkeypatch):
    from birdwatcher.storage import EventStore

    store = EventStore(StorageConfig(tmp_path / "data", min_free_bytes=0, retention_days=100000))
    f = Frame(1, "2000-01-01T00:00:00Z", 1, b"jpeg")
    store.apply(EventAction("start", "one", f))
    original_scan = store._scan

    def no_scan():
        raise AssertionError("per-frame directory scan")

    monkeypatch.setattr(store, "_scan", no_scan)
    store.apply(EventAction("frame", "one", f))
    store.apply(EventAction("end", "one", reason="writer_overload"))
    monkeypatch.setattr(store, "_scan", original_scan)
    event = store.events()[0]
    assert event["incomplete"] is True and event["complete"] is False
    assert event["status"] == "incomplete"


def test_full_disk_restart_still_reports_health_and_incomplete(tmp_path, monkeypatch):
    import shutil

    from birdwatcher.storage import EventStore, StorageError

    config = StorageConfig(tmp_path / "data", min_free_bytes=1, retention_days=100000)
    store = EventStore(config)
    f = Frame(1, "2000-01-01T00:00:00Z", 1, b"jpeg")
    store.apply(EventAction("start", "active", f))
    usage = shutil.disk_usage(config.data_dir)
    monkeypatch.setattr(shutil, "disk_usage", lambda _: type(usage)(usage.total, usage.total, 0))
    recovered = EventStore(config)
    assert recovered.health()["storage_full"]
    assert recovered.events()[0]["status"] == "incomplete"
    with pytest.raises(StorageError, match="storage_full"):
        recovered.apply(EventAction("start", "new", f))


def test_rejects_unsafe_frame_identity_and_preserves_unmanaged_children(tmp_path):
    from dataclasses import replace

    from birdwatcher.storage import EventStore, StorageError

    config = StorageConfig(tmp_path / "data", min_free_bytes=0, retention_days=100000)
    store = EventStore(config)
    f = Frame(1, "2000-01-01T00:00:00Z", 1, b"jpeg")
    store.apply(EventAction("start", "safe", f))
    with pytest.raises(StorageError):
        store.apply(EventAction("frame", "safe", replace(f, id="../escape")))
    store.apply(EventAction("frame", "safe", f))
    store.apply(EventAction("end", "safe"))
    manifest = next(config.data_dir.glob("*/*/event.json"))
    unknown = manifest.parent / "originals" / "private.txt"
    unknown.write_text("untouched")
    EventStore(replace(config, retention_days=1))
    assert manifest.exists() and unknown.read_text() == "untouched"


def test_quota_retention_symlinks_pins_unmanaged_and_camera_metadata(tmp_path):
    from dataclasses import replace

    from birdwatcher.storage import EventStore, StorageError

    config = StorageConfig(
        tmp_path / "data", max_bytes=10000, min_free_bytes=0, retention_days=100000
    )
    store = EventStore(config)
    assert store.camera_settings == {}
    store.camera_settings = {"width": 640}
    f = Frame(1, "2000-01-01T00:00:00Z", 1, b"x" * 1000)

    def save(name):
        store.apply(EventAction("start", name, f))
        store.apply(EventAction("frame", name, f))
        store.apply(EventAction("end", name))

    save("first")
    assert store.events()[0]["camera_settings"] == {"width": 640}
    manifest = next(config.data_dir.glob("*/*/event.json"))
    data = json.loads(manifest.read_text())
    data["pinned"] = True
    manifest.write_text(json.dumps(data))
    unmanaged = config.data_dir / "notes.txt"
    unmanaged.write_text("leave me")
    constrained = EventStore(replace(config, max_bytes=2000))
    with pytest.raises(StorageError):
        constrained.apply(EventAction("start", "second", f))
        constrained.apply(EventAction("frame", "second", f))
    assert manifest.exists() and unmanaged.read_text() == "leave me"
    assert constrained.health()["storage_full"]
    outside = tmp_path / "outside"
    outside.mkdir()
    (config.data_dir / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(StorageError):
        EventStore(StorageConfig(config.data_dir / "linked", min_free_bytes=0))
    with pytest.raises(StorageError):
        store.apply(EventAction("start", "../escape", f))
    with pytest.raises(StorageError):
        store.apply(EventAction("start", "first", f))
    # Expired closed events prune; pinning and unmanaged files survive.
    EventStore(replace(config, retention_days=1))
    assert manifest.exists()
    assert unmanaged.exists()
    data["pinned"] = False
    manifest.write_text(json.dumps(data))
    EventStore(replace(config, retention_days=1))
    assert not manifest.exists()


def test_atomic_capture_manifest_and_restart_recovery(tmp_path):
    from birdwatcher.storage import EventStore

    config = StorageConfig(tmp_path / "data", min_free_bytes=0)
    store = EventStore(config)
    f = Frame(1, "2000-01-01T00:00:00Z", 1, b"jpeg")
    store.apply(EventAction("start", "event-1", f, ("near",)))
    store.apply(EventAction("frame", "event-1", f, ("near",)))
    store.apply(EventAction("frame", "event-1", f, ("near",)))
    store.apply(EventAction("end", "event-1", regions=("near", "far"), reason="quiet"))
    event = store.events()[0]
    assert event["complete"] is True
    assert event["analysis_status"] == "not_configured"
    assert event["regions"] == ["near", "far"]
    assert len(event["frames"]) == 1
    manifest = next(config.data_dir.glob("*/*/event.json"))
    assert (manifest.parent / event["frames"][0]["path"]).read_bytes() == b"jpeg"
    assert not list(config.data_dir.rglob("*.tmp"))
    store.apply(EventAction("start", "event-2", f))
    recovered = EventStore(config)
    event = next(e for e in recovered.events() if e["event_id"] == "event-2")
    assert event["complete"] is False and event["status"] == "incomplete"
    assert str(config.data_dir) not in str(recovered.health())
    store.close()
    recovered.close()
