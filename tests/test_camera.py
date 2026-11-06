"""Hardware-independent camera stream and resource safety checks."""

import sys
from pathlib import Path

import pytest


def test_jpeg_parser_preserves_next_frame():
    from birdwatcher.camera import extract_jpeg

    data = bytearray(b"noise\xff\xd8one\xff\xd9\xff\xd8two\xff\xd9")
    assert extract_jpeg(data) == b"\xff\xd8one\xff\xd9"
    assert extract_jpeg(data) == b"\xff\xd8two\xff\xd9"
    assert extract_jpeg(data) is None


def test_jpeg_parser_keeps_split_marker():
    from birdwatcher.camera import extract_jpeg

    data = bytearray(b"noise\xff")
    assert extract_jpeg(data) is None
    data.extend(b"\xd8image\xff\xd9")
    assert extract_jpeg(data) == b"\xff\xd8image\xff\xd9"


def test_jpeg_parser_rejects_unbounded_frame():
    from birdwatcher.camera import CameraError, extract_jpeg

    with pytest.raises(CameraError):
        extract_jpeg(bytearray(b"\xff\xd8" + b"x" * 100), max_bytes=50)


def test_auto_discovery_prefers_capture_endpoint(tmp_path):
    from birdwatcher.camera import discover_device

    by_id = tmp_path / "v4l" / "by-id"
    by_id.mkdir(parents=True)
    (tmp_path / "video0").touch()
    (by_id / "generic-video-index0").symlink_to(tmp_path / "video0")
    assert discover_device("auto", tmp_path) == str(by_id / "generic-video-index0")


def test_camera_lock_rejects_second_owner(tmp_path):
    from birdwatcher.camera import CameraError, CameraLock

    with CameraLock(tmp_path / "camera.lock"):
        with pytest.raises(CameraError, match="busy"):
            with CameraLock(tmp_path / "camera.lock"):
                pass
    with CameraLock(tmp_path / "camera.lock"):
        pass


def test_capture_read_timeout_terminates_child(tmp_path):
    import subprocess

    from birdwatcher.camera import CameraError, read_stream_frame

    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(10)"], stdout=subprocess.PIPE
    )
    try:
        with pytest.raises(CameraError, match="timed out"):
            read_stream_frame(child, bytearray(), 0.02)
    finally:
        child.terminate()
        child.wait(timeout=5)


def test_lock_symlink_is_rejected(tmp_path):
    from birdwatcher.camera import CameraError, CameraLock

    victim = tmp_path / "victim"
    victim.write_text("untouched")
    lock = tmp_path / "lock"
    lock.symlink_to(victim)
    with pytest.raises(CameraError):
        with CameraLock(lock):
            pass
    assert victim.read_text() == "untouched"


def test_metadata_parser_does_not_include_device_identifiers():
    from birdwatcher.camera import parse_settings

    result = parse_settings(
        "Width/Height : 1920/1080\nPixel Format : 'MJPG'\nFrames per second: 15.000 (15/1)"
    )
    assert result == {"width": 1920, "height": 1080, "pixel_format": "MJPG", "fps": 15.0}


def test_snapshot_requires_private_location(tmp_path):
    from birdwatcher.camera import CameraError, validate_output

    checkout = Path(__file__).resolve().parents[1]
    with pytest.raises(CameraError, match="outside"):
        validate_output(checkout / "private" / "image.jpg")
    assert validate_output(tmp_path / "image.jpg") == tmp_path / "image.jpg"
