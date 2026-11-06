"""Replay integration test; its generated images are explicitly synthetic."""

import json
import time
from dataclasses import replace

import cv2
import numpy as np


def test_replay_capture_writes_originals_and_health(tmp_path):
    from birdwatcher.config import AppConfig, Region
    from birdwatcher.runner import run_capture

    config = AppConfig()
    config = replace(
        config,
        storage=replace(config.storage, data_dir=tmp_path / "events", min_free_bytes=0),
        motion=replace(config.motion, regions=(Region("test", 0, 0, 1, 1),)),
        capture=replace(
            config.capture,
            sample_fps=100,
            post_seconds=0.05,
            pre_seconds=0.05,
            quiet_seconds=0.06,
            max_event_seconds=1,
        ),
    )
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok

    class ReplayCamera:
        settings = {"width": 160, "height": 120, "pixel_format": "MJPG"}

        def __init__(self, camera_config):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            time.sleep(0.01)
            return encoded.tobytes()

    class Arrival:
        def __init__(self, motion_config):
            pass

        def update(self, frame):
            return ("test",)

        def reset(self):
            pass

    result = run_capture(config, duration=0.3, camera_factory=ReplayCamera, motion_factory=Arrival)
    assert result["frames_received"] > 0
    assert result["events_started"] >= 1
    assert result["storage_errors"] == 0
    manifests = list(config.storage.data_dir.glob("*/*/event.json"))
    assert manifests
    images = list(config.storage.data_dir.glob("*/*/originals/*.jpg"))
    assert images
    assert cv2.imread(str(images[0])).shape[:2] == (120, 160)
    health = json.loads((config.storage.data_dir / "health.json").read_text())
    assert health["state"] == "stopped"
    assert health["species_identification"] == "not_implemented"
