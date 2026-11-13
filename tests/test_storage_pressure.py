"""Synthetic retention pressure regressions; no camera or real photographs."""

from dataclasses import replace

import pytest

from birdwatcher.config import StorageConfig
from birdwatcher.events import EventAction, Frame
from birdwatcher.storage import EventStore


@pytest.mark.parametrize("event_count", [4, 32])
@pytest.mark.parametrize("pressure", [False, True])
def test_prune_usage_scans_follow_deletions_not_retained_events(
    tmp_path, monkeypatch, event_count, pressure
):
    store = EventStore(StorageConfig(tmp_path / "data", min_free_bytes=0, retention_days=100000))
    for index in range(event_count):
        frame = Frame(index, f"2020-01-01T00:00:{index:02d}Z", float(index), b"synthetic")
        store.apply(EventAction("start", f"event-{index}", frame))
        store.apply(EventAction("end", f"event-{index}", reason="quiet"))
    additional = 100
    if pressure:
        store.config = replace(store.config, max_bytes=store._usage() + additional - 1)
    usage = store._usage
    scans = []

    def counted_usage():
        scans.append(None)
        return usage()

    monkeypatch.setattr(store, "_usage", counted_usage)
    store._prune(additional)

    assert len(store.events(event_count)) == event_count - int(pressure)
    assert store._used == usage()
    assert store._used + additional <= store.config.max_bytes
    assert not store.health()["storage_full"]
    # Initial/final reconciliation plus one refresh per deletion, not per event.
    assert len(scans) <= 2 + int(pressure)


def test_quota_failure_drains_writer_and_persists_incomplete_end(tmp_path):
    from birdwatcher.runner import ActionWriter

    store = EventStore(StorageConfig(tmp_path / "data", min_free_bytes=0, retention_days=100000))
    frame = Frame(1, "2020-01-01T00:00:00Z", 1.0, b"synthetic" * 1000)
    store.apply(EventAction("start", "active", frame))
    # Enough for the incomplete end marker, but not a frame transaction. Active
    # events must not be reclaimed to make space for their own failed writes.
    store.config = replace(store.config, max_bytes=store._used + 200)

    with ActionWriter(store) as writer:
        assert writer.put(EventAction("frame", "active", frame))
        assert writer.put(EventAction("end", "active", reason="shutdown"))

    assert writer.errors == 1
    assert writer.pending_bytes == 0
    assert not writer._thread.is_alive()
    event = store.events()[0]
    assert event["status"] == "incomplete"
    assert event["end_reason"] == "writer_overload"
    assert event["frames"] == []
    assert store.health()["active_events"] == 0
    assert store._used == store._usage()
    assert store._used <= store.config.max_bytes
    assert not list(store.root.rglob(".frame-intent.json"))
    assert not list(store.root.rglob("*.tmp"))
