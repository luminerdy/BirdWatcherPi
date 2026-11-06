"""Recovery and conservative retention regression tests."""

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace

import pytest

from birdwatcher.config import StorageConfig
from birdwatcher.events import EventAction, Frame
from birdwatcher.storage import EventStore


def test_persisted_recovery_can_be_pruned_for_new_event(tmp_path):
    config = StorageConfig(tmp_path / "data", min_free_bytes=0, retention_days=100000)
    frame = Frame(1, "2020-01-01T00:00:00Z", 1.0, b"x" * 1000)
    store = EventStore(config)
    store.apply(EventAction("start", "old", frame))
    store.apply(EventAction("frame", "old", frame))
    manifest = next(config.data_dir.glob("*/*/event.json"))

    recovered = EventStore(replace(config, max_bytes=1800))
    assert recovered.events()[0]["status"] == "incomplete"
    recovered.apply(EventAction("start", "new", frame))

    assert not manifest.exists()
    assert [event["event_id"] for event in recovered.events()] == ["new"]


def test_interrupted_frame_is_reconciled_and_pruned_across_two_restarts(tmp_path, monkeypatch):
    config = StorageConfig(tmp_path / "data", min_free_bytes=0, retention_days=100000)
    frame = Frame(1, "2020-01-01T00:00:00Z", 1.0, b"x" * 1000)
    store = EventStore(config)
    store.apply(EventAction("start", "old", frame))
    manifest = next(config.data_dir.glob("*/*/event.json"))
    write_json = store._json

    def interrupted(path, data):
        if path == manifest:
            raise OSError("manifest commit interrupted")
        write_json(path, data)

    monkeypatch.setattr(store, "_json", interrupted)
    with pytest.raises(OSError, match="manifest commit interrupted"):
        store.apply(EventAction("frame", "old", frame))
    assert json.loads(manifest.read_text())["frames"] == []
    assert (manifest.parent / "originals/1.jpg").exists()

    recovered = EventStore(replace(config, max_bytes=1800))
    event = recovered.events()[0]
    assert event["status"] == "incomplete"
    assert event["reason"] == "interrupted"
    assert [item["path"] for item in event["frames"]] == ["originals/1.jpg"]
    assert not (manifest.parent / ".frame-intent.json").exists()
    # Recovery is durable; neither a second restart nor repeated quota pressure leaks it.
    for index in range(2):
        recovered = EventStore(replace(config, max_bytes=1800))
        recovered.apply(EventAction("start", f"new-{index}", frame))
        assert not manifest.exists()
        recovered.close()


@pytest.mark.parametrize("checkpoint", ["jpeg", "recovery_manifest", "intent_cleanup"])
def test_interrupted_frame_protocol_retries_safely(tmp_path, monkeypatch, checkpoint):
    config = StorageConfig(tmp_path / "data", min_free_bytes=0, retention_days=100000)
    frame = Frame(1, "2020-01-01T00:00:00Z", 1.0, b"jpeg")
    store = EventStore(config)
    store.apply(EventAction("start", "old", frame))
    manifest = next(config.data_dir.glob("*/*/event.json"))
    intent = manifest.parent / ".frame-intent.json"
    atomic = store._atomic

    def interrupted(path, payload):
        if (checkpoint == "jpeg" and path.suffix == ".jpg") or (
            checkpoint == "recovery_manifest" and path == manifest
        ):
            raise OSError("interrupted")
        atomic(path, payload)

    def cleanup_interrupted(path):
        raise OSError("interrupted")

    monkeypatch.setattr(store, "_atomic", interrupted)
    if checkpoint == "intent_cleanup":
        monkeypatch.setattr(store, "_remove_intent", cleanup_interrupted)
    with pytest.raises(OSError):
        store.apply(EventAction("frame", "old", frame))
    assert intent.exists()

    if checkpoint == "recovery_manifest":
        with monkeypatch.context() as patch:
            patch.setattr(EventStore, "_json", lambda *args: cleanup_interrupted(manifest))
            failed = EventStore(config)
        assert failed.health()["storage_full"]
        assert failed.events()[0]["status"] == "incomplete"
        assert len(failed.events()[0]["frames"]) == 1
        assert intent.exists()
        failed.config = replace(config, max_bytes=1)
        failed._prune(0, enforce=False)
        assert manifest.exists()
    recovered = EventStore(config)
    assert recovered.events()[0]["status"] == "incomplete"
    assert len(recovered.events()[0]["frames"]) == (0 if checkpoint == "jpeg" else 1)
    assert not intent.exists()
    assert len(EventStore(config).events()[0]["frames"]) == (0 if checkpoint == "jpeg" else 1)


@pytest.mark.parametrize("private_name", ["private.txt", "42.jpg"])
def test_recovered_orphan_does_not_authorize_private_files(tmp_path, monkeypatch, private_name):
    config = StorageConfig(tmp_path / "data", min_free_bytes=0, retention_days=100000)
    frame = Frame(1, "2020-01-01T00:00:00Z", 1.0, b"jpeg")
    store = EventStore(config)
    store.apply(EventAction("start", "old", frame))
    manifest = next(config.data_dir.glob("*/*/event.json"))
    write_json = store._json

    def interrupted(path, data):
        if path == manifest:
            raise OSError("interrupted")
        write_json(path, data)

    monkeypatch.setattr(store, "_json", interrupted)
    with pytest.raises(OSError):
        store.apply(EventAction("frame", "old", frame))
    private = manifest.parent / "originals" / private_name
    private.write_text("private test fixture")
    recovered = EventStore(config)
    assert len(recovered.events()[0]["frames"]) == 1
    EventStore(replace(config, max_bytes=1, retention_days=1))
    assert manifest.exists()
    assert private.read_text() == "private test fixture"


@pytest.mark.parametrize(
    "corruption",
    [
        "malformed",
        "escape",
        "absolute",
        "wrong_event",
        "negative",
        "hash",
        "size",
        "intent_symlink",
        "image_symlink",
        "originals_symlink",
    ],
)
def test_untrusted_intent_never_authorizes_unmanaged_deletion(tmp_path, monkeypatch, corruption):
    config = StorageConfig(tmp_path / "data", min_free_bytes=0, retention_days=100000)
    frame = Frame(1, "2020-01-01T00:00:00Z", 1.0, b"jpeg")
    store = EventStore(config)
    store.apply(EventAction("start", "old", frame))
    manifest = next(config.data_dir.glob("*/*/event.json"))
    write_json = store._json

    def interrupted(path, data):
        if path == manifest:
            raise OSError("interrupted")
        write_json(path, data)

    monkeypatch.setattr(store, "_json", interrupted)
    with pytest.raises(OSError):
        store.apply(EventAction("frame", "old", frame))
    intent = manifest.parent / ".frame-intent.json"
    record = json.loads(intent.read_text())
    outside = tmp_path / "private.txt"
    outside.write_bytes(b"jpeg")
    image = manifest.parent / "originals/1.jpg"
    if corruption == "malformed":
        intent.write_text("[]")
    elif corruption == "intent_symlink":
        external_intent = tmp_path / "external-intent.json"
        external_intent.write_text(intent.read_text())
        intent.unlink()
        intent.symlink_to(external_intent)
    elif corruption == "image_symlink":
        image.unlink()
        image.symlink_to(outside)
    elif corruption == "originals_symlink":
        image.unlink()
        image.parent.rmdir()
        external_originals = tmp_path / "external-originals"
        external_originals.mkdir()
        (external_originals / "1.jpg").write_bytes(b"jpeg")
        image.parent.symlink_to(external_originals, target_is_directory=True)
    else:
        if corruption == "escape":
            record["frame"]["path"] = "../../../private.txt"
        elif corruption == "absolute":
            record["frame"]["path"] = str(outside)
        elif corruption == "wrong_event":
            record["event_id"] = "other"
        elif corruption == "negative":
            record["frame"].update(id=-1, path="originals/-1.jpg")
        elif corruption == "hash":
            record["sha256"] = "0" * 64
        elif corruption == "size":
            record["size"] += 1
        intent.write_text(json.dumps(record))
    recovered = EventStore(config)
    assert recovered.events()[0]["frames"] == []
    EventStore(replace(config, max_bytes=1, retention_days=1))
    assert manifest.exists()
    assert intent.exists()
    assert outside.read_bytes() == b"jpeg"
    if corruption == "intent_symlink":
        assert external_intent.exists()
    if corruption == "originals_symlink":
        assert (external_originals / "1.jpg").read_bytes() == b"jpeg"


def test_pinned_recovered_orphan_and_live_event_remain_protected(tmp_path, monkeypatch):
    from birdwatcher.storage import StorageError

    config = StorageConfig(tmp_path / "data", min_free_bytes=0, retention_days=100000)
    frame = Frame(1, "2020-01-01T00:00:00Z", 1.0, b"jpeg")
    store = EventStore(config)
    store.apply(EventAction("start", "old", frame))
    manifest = next(config.data_dir.glob("*/*/event.json"))
    data = json.loads(manifest.read_text())
    data["pinned"] = True
    manifest.write_text(json.dumps(data))
    write_json = store._json

    def interrupted(path, data):
        if path == manifest:
            raise OSError("interrupted")
        write_json(path, data)

    monkeypatch.setattr(store, "_json", interrupted)
    with pytest.raises(OSError):
        store.apply(EventAction("frame", "old", frame))
    # The persisted pin, not the failed writer's stale in-memory copy, governs recovery.
    recovered = EventStore(config)
    assert recovered.events()[0]["pinned"]
    assert len(recovered.events()[0]["frames"]) == 1
    recovered.apply(EventAction("start", "live", frame))
    recovered.config = replace(config, max_bytes=1)
    with pytest.raises(StorageError, match="storage_full"):
        recovered._prune(0)
    assert {event["event_id"] for event in recovered.events()} == {"old", "live"}
    assert manifest.exists()


def test_exact_legacy_quota_stranding_recovers_before_removing_journal(tmp_path, monkeypatch):
    config = StorageConfig(
        tmp_path / "data", max_bytes=1468, min_free_bytes=0, retention_days=100000
    )
    frame = Frame(1, "2020-01-01T00:00:00Z", 1.0, b"x" * 1000)
    store = EventStore(config)
    store.apply(EventAction("start", "old", frame))
    manifest = next(config.data_dir.glob("*/*/event.json"))
    metadata = dict(id=1, utc=frame.utc, monotonic=1.0, path="originals/1.jpg")
    intent = manifest.parent / ".frame-intent.json"
    intent.write_text(
        json.dumps(
            dict(
                schema_version=1,
                event_id="old",
                frame=metadata,
                size=1000,
                sha256=hashlib.sha256(frame.jpeg).hexdigest(),
            ),
            sort_keys=True,
        )
    )
    (manifest.parent / metadata["path"]).write_bytes(frame.jpeg)
    assert store._usage() == 1468
    remove = EventStore._remove_intent

    def verified_remove(self, journal):
        persisted = json.loads(manifest.read_text())
        assert persisted["status"] == "incomplete"
        assert persisted["frames"] == [metadata]
        assert self._usage() <= config.max_bytes + journal.stat().st_size
        remove(self, journal)

    monkeypatch.setattr(EventStore, "_remove_intent", verified_remove)
    for _ in range(2):
        recovered = EventStore(config)
        assert json.loads(manifest.read_text())["status"] == "incomplete"
        assert not intent.exists()
        assert recovered._usage() == 1338
    recovered.apply(EventAction("start", "new", frame))
    assert not manifest.exists()


def crash_frame(root, checkpoint="before"):
    script = """
import os
import sys
from pathlib import Path
from birdwatcher.config import StorageConfig
from birdwatcher.events import EventAction, Frame
from birdwatcher.storage import EventStore
store = EventStore(StorageConfig(Path(sys.argv[1]), min_free_bytes=0, retention_days=100000))
frame = Frame(1, "2020-01-01T00:00:00Z", 1.0, b"x" * 1000)
store.apply(EventAction("start", "old", frame))
original = os.replace
def replace(src, dst):
    if str(dst).endswith(".jpg") and sys.argv[2] in ("before", "after"):
        if sys.argv[2] == "after":
            original(src, dst)
        os._exit(77)
    if str(dst).endswith("event.json") and sys.argv[2] in ("manifest_before", "manifest_after"):
        if sys.argv[2] == "manifest_after":
            original(src, dst)
        os._exit(77)
    return original(src, dst)
os.replace = replace
store.apply(EventAction("frame", "old", frame))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(root), checkpoint],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 77, result.stderr
    return next(root.glob("*/*/event.json"))


@pytest.mark.parametrize("checkpoint", ["before", "after", "manifest_before", "manifest_after"])
def test_real_jpeg_rename_crash_is_recoverable_at_exact_quota(tmp_path, checkpoint):
    root = tmp_path / "data"
    manifest = crash_frame(root, checkpoint)
    intent = manifest.parent / ".frame-intent.json"
    record = json.loads(intent.read_text())
    temps = list((manifest.parent / "originals").glob(".*.tmp"))
    if checkpoint == "before":
        assert len(temps) == 1
        assert not (manifest.parent / "originals/1.jpg").exists()
        assert record["temporary"] == str(temps[0].relative_to(manifest.parent))
    config = StorageConfig(root, max_bytes=1338, min_free_bytes=0, retention_days=100000)
    for _ in range(3):
        store = EventStore(config)
        assert json.loads(manifest.read_text())["status"] == "incomplete"
        assert len(store.events()[0]["frames"]) == 1
        assert (manifest.parent / "originals/1.jpg").read_bytes() == b"x" * 1000
        assert not intent.exists()
        assert not list((manifest.parent / "originals").glob(".*.tmp"))
        assert store._usage() == 1338
        assert not store.health()["storage_full"]
    store.apply(EventAction("start", "new", Frame(2, "2020-01-01T00:00:01Z", 2.0, b"x")))
    assert not manifest.exists()


def test_impossible_frame_is_rejected_before_journal_or_jpeg(tmp_path):
    from birdwatcher.storage import StorageError

    config = StorageConfig(
        tmp_path / "data", max_bytes=1468, min_free_bytes=0, retention_days=100000
    )
    store = EventStore(config)
    frame = Frame(1, "2020-01-01T00:00:00Z", 1.0, b"x" * 1000)
    store.apply(EventAction("start", "old", frame))
    manifest = next(config.data_dir.glob("*/*/event.json"))
    before = manifest.read_bytes()
    with pytest.raises(StorageError, match="storage_full"):
        store.apply(EventAction("frame", "old", frame))
    assert manifest.read_bytes() == before
    assert not (manifest.parent / ".frame-intent.json").exists()
    assert list((manifest.parent / "originals").iterdir()) == []


@pytest.mark.parametrize("max_bytes", [1337, 1338])
def test_recovery_credit_is_measured_and_never_relaxes_free_reserve(
    tmp_path, monkeypatch, max_bytes
):
    from collections import namedtuple

    from birdwatcher import storage

    root = tmp_path / "data"
    manifest = crash_frame(root)
    intent = manifest.parent / ".frame-intent.json"
    record = json.loads(intent.read_text())
    assert record["temporary"]
    usage = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    config = StorageConfig(root, max_bytes=max_bytes, min_free_bytes=0, retention_days=100000)
    failed = EventStore(config)
    if max_bytes == 1337:
        assert intent.exists()
        assert json.loads(manifest.read_text())["status"] == "active"
        assert failed.health()["storage_full"]
        assert failed._usage() == usage
    else:
        assert not intent.exists()
        assert failed._usage() == 1338

    # Recreate an interrupted frame in a separate isolated root; logical credit
    # cannot fund the real bytes needed for the atomic manifest replacement.
    root2 = tmp_path / "reserve-data"
    manifest2 = crash_frame(root2)
    Disk = namedtuple("Disk", "total used free")
    monkeypatch.setattr(storage.shutil, "disk_usage", lambda _: Disk(10000, 9600, 400))
    reserved = EventStore(replace(config, data_dir=root2, min_free_bytes=100))
    assert reserved.health()["storage_full"]
    assert (manifest2.parent / ".frame-intent.json").exists()
    assert json.loads(manifest2.read_text())["status"] == "active"


@pytest.mark.parametrize("pinned", [False, True])
@pytest.mark.parametrize("private_name", ["42.jpg", ".1.jpg.unknown.tmp", "private.txt"])
def test_identified_temp_recovery_preserves_unknown_files_and_pins(tmp_path, private_name, pinned):
    root = tmp_path / "data"
    manifest = crash_frame(root)
    private = manifest.parent / "originals" / private_name
    private.write_bytes(b"private fixture")
    data = json.loads(manifest.read_text())
    data["pinned"] = pinned
    manifest.write_text(json.dumps(data, sort_keys=True))
    config = StorageConfig(root, min_free_bytes=0, retention_days=100000)
    recovered = EventStore(config)
    assert len(recovered.events()[0]["frames"]) == 1
    assert recovered.events()[0]["pinned"] is pinned
    assert not (manifest.parent / ".frame-intent.json").exists()
    EventStore(replace(config, max_bytes=1, retention_days=1))
    assert manifest.exists()
    assert private.read_bytes() == b"private fixture"


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "corrupt",
        "short",
        "escape",
        "absolute",
        "nonce",
        "wrong_event",
        "symlink",
        "directory",
    ],
)
def test_identified_temporary_validation_is_conservative(tmp_path, damage):
    root = tmp_path / "data"
    manifest = crash_frame(root)
    intent = manifest.parent / ".frame-intent.json"
    record = json.loads(intent.read_text())
    temporary = manifest.parent / record["temporary"]
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"x" * 1000)
    if damage == "missing":
        temporary.unlink()
    elif damage == "corrupt":
        temporary.write_bytes(b"z" * 1000)
    elif damage == "short":
        temporary.write_bytes(b"x")
    elif damage == "symlink":
        temporary.unlink()
        temporary.symlink_to(outside)
    elif damage == "directory":
        temporary.unlink()
        temporary.mkdir()
    else:
        if damage == "escape":
            record["temporary"] = "../../../outside.txt"
        elif damage == "absolute":
            record["temporary"] = str(outside)
        elif damage == "nonce":
            record["temporary"] = "originals/.1.jpg.invalid.tmp"
        elif damage == "wrong_event":
            record["event_id"] = "other"
        intent.write_text(json.dumps(record))
    config = StorageConfig(root, min_free_bytes=0, retention_days=100000)
    recovered = EventStore(config)
    assert recovered.events()[0]["frames"] == []
    assert outside.read_bytes() == b"x" * 1000
    if damage == "missing":
        assert not intent.exists()
        EventStore(replace(config, max_bytes=1, retention_days=1))
        assert not manifest.exists()
    else:
        assert intent.exists()
        assert temporary.exists()
        EventStore(replace(config, max_bytes=1, retention_days=1))
        assert manifest.exists()
        assert temporary.exists()


def test_real_recovery_manifest_crash_can_retry_without_new_orphans(tmp_path):
    root = tmp_path / "data"
    manifest = crash_frame(root)
    script = """
import os
import sys
from pathlib import Path
from birdwatcher.config import StorageConfig
from birdwatcher.storage import EventStore
original = os.replace
def replace(src, dst):
    if str(dst).endswith("event.json"):
        os._exit(78)
    return original(src, dst)
os.replace = replace
EventStore(StorageConfig(Path(sys.argv[1]), max_bytes=1338, min_free_bytes=0, retention_days=100000))
"""
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-c", script, str(root)],
            env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 78, result.stderr
        intent = json.loads((manifest.parent / ".frame-intent.json").read_text())
        assert (manifest.parent / intent["manifest_temporary"]).is_file()
        assert len(list(manifest.parent.glob(".*.tmp"))) == 1
    config = StorageConfig(root, max_bytes=1338, min_free_bytes=0, retention_days=100000)
    store = EventStore(config)
    assert store._usage() == 1338
    assert len(store.events()[0]["frames"]) == 1
    assert not list(manifest.parent.glob(".*.tmp"))
    store.apply(EventAction("start", "new", Frame(2, "2020-01-01T00:00:01Z", 2.0, b"x")))
    assert not manifest.exists()


@pytest.mark.parametrize("damage", ["escape", "nonce", "hash", "corrupt", "symlink"])
def test_manifest_temporary_never_authorizes_unknown_cleanup(tmp_path, damage):
    root = tmp_path / "data"
    manifest = crash_frame(root, "manifest_before")
    intent = manifest.parent / ".frame-intent.json"
    record = json.loads(intent.read_text())
    temporary = manifest.parent / record["manifest_temporary"]
    outside = tmp_path / "outside.txt"
    outside.write_text("private fixture")
    if damage == "escape":
        record["manifest_temporary"] = "../../../outside.txt"
    elif damage == "nonce":
        record["manifest_temporary"] = ".event.json.unknown.tmp"
    elif damage == "hash":
        record["manifest_sha256"] = "0" * 64
    elif damage == "corrupt":
        temporary.write_text("private fixture")
    elif damage == "symlink":
        temporary.unlink()
        temporary.symlink_to(outside)
    intent.write_text(json.dumps(record))
    config = StorageConfig(root, min_free_bytes=0, retention_days=100000)
    for _ in range(2):
        EventStore(config)
        assert temporary.exists()
        assert intent.exists()
        assert outside.read_text() == "private fixture"
    EventStore(replace(config, max_bytes=1, retention_days=1))
    assert manifest.exists()


@pytest.mark.parametrize("checkpoint", ["jpeg_sync", "cleanup_sync"])
def test_directory_sync_failure_keeps_usage_accounting_truthful(tmp_path, monkeypatch, checkpoint):
    config = StorageConfig(tmp_path / "data", min_free_bytes=0, retention_days=100000)
    store = EventStore(config)
    frame = Frame(1, "2020-01-01T00:00:00Z", 1.0, b"x" * 1000)
    store.apply(EventAction("start", "old", frame))
    manifest = next(config.data_dir.glob("*/*/event.json"))
    intent = manifest.parent / ".frame-intent.json"
    sync = store._sync_directory

    def interrupted(directory):
        if (checkpoint == "jpeg_sync" and directory.name == "originals") or (
            checkpoint == "cleanup_sync" and directory == manifest.parent and not intent.exists()
        ):
            raise OSError("directory sync interrupted")
        sync(directory)

    monkeypatch.setattr(store, "_sync_directory", interrupted)
    with pytest.raises(OSError, match="directory sync interrupted"):
        store.apply(EventAction("frame", "old", frame))
    assert store._used == store._usage()
    recovered = EventStore(config)
    assert len(recovered.events()[0]["frames"]) == 1
    assert not intent.exists()
