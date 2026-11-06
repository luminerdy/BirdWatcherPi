"""The writer is bounded and must not block the camera producer."""

from dataclasses import dataclass


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
