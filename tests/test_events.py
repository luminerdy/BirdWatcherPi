from birdwatcher.config import CaptureConfig


def test_timing_bounds_burst_cap_cooldown_and_segments():
    from dataclasses import replace

    from birdwatcher.events import EventMachine, Frame

    config = replace(
        CaptureConfig(),
        pre_seconds=0.4,
        max_buffer_bytes=8,
        max_bursts=1,
        max_event_seconds=6,
        quiet_seconds=3,
        cooldown_seconds=1,
    )
    machine = EventMachine(config)

    def step(i, active=()):
        return machine.update(Frame(i, "2000-01-01T00:00:00Z", i / 5, b"1234"), active)

    for i in range(10):
        step(i)
    actions = step(10, ("near",))
    assert [a.frame.id for a in actions if a.kind == "frame"] == [8, 9, 10]
    event_id = actions[0].event_id
    collected = []
    for i in range(11, 26):
        collected += step(i, ("far",))
    assert [a.frame.id for a in collected if a.kind == "frame"] == list(range(11, 20))
    assert all(a.event_id == event_id for a in collected)
    ended = step(40)
    assert ended[-1].kind == "end"
    assert set(ended[-1].regions) == {"near", "far"}
    assert step(41, ("near",)) == []
    assert step(45, ("near",))[0].kind == "start"
    segmented = step(75, ("near",))
    assert [a.kind for a in segmented[:2]] == ["end", "start"]
    assert segmented[0].reason == "max_duration"
    assert event_id != segmented[1].event_id


def test_prebuffer_shared_regions_unique_frames_and_shutdown():
    from birdwatcher.events import EventMachine, Frame

    machine = EventMachine(CaptureConfig())

    def frame(i):
        return Frame(i, "2000-01-01T00:00:00Z", i / 5, b"jpeg")

    assert machine.update(frame(0), ()) == []
    actions = machine.update(frame(1), ("near", "far"))
    assert actions[0].kind == "start"
    assert actions[0].regions == ("near", "far")
    assert [a.frame.id for a in actions if a.kind == "frame"] == [0, 1]
    assert machine.update(frame(1), ("near",)) == []
    assert machine.close()[0].kind == "end"
    assert machine.close() == []
