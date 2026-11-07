"""CLI contract tests: exercise the actual module in a subprocess."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cli(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "birdwatcher", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )


def test_help_lists_capture_commands():
    result = cli("--help")
    assert result.returncode == 0, result.stderr
    for command in ("doctor", "snapshot", "run", "status", "events"):
        assert command in result.stdout


def test_version_is_available_without_camera():
    result = cli("--version")
    assert result.returncode == 0, result.stderr
    assert "0.2.0" in result.stdout


def test_unconfigured_run_fails_before_opening_camera():
    result = cli("run", "--duration", "1")
    assert result.returncode != 0
    assert "region" in result.stderr.lower()
    assert "Traceback" not in result.stderr


def test_invalid_config_has_no_traceback(tmp_path):
    config = tmp_path / "bad.toml"
    config.write_text("[camera]\nwidth = -1\n")
    result = cli("--config", str(config), "run", "--duration", "1")
    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def test_events_without_data_do_not_create_root(tmp_path):
    config = tmp_path / "config.toml"
    data = tmp_path / "private-data"
    config.write_text('[storage]\ndata_dir = "' + str(data) + '"\n')
    result = cli("--config", str(config), "events")
    assert result.returncode == 0, result.stderr
    assert not data.exists()


def test_duration_must_be_positive():
    result = cli("run", "--duration", "-1")
    assert result.returncode != 0
    assert "duration" in result.stderr.lower()


def test_events_are_sorted_by_capture_time_not_random_event_id(tmp_path):
    import json

    config = tmp_path / "config.toml"
    data = tmp_path / "events"
    config.write_text('[storage]\ndata_dir = "' + str(data) + '"\n')
    for event_id, timestamp in (("zzz", "2020-01-01T01:00:00Z"), ("aaa", "2020-01-01T02:00:00Z")):
        folder = data / "2020-01-01" / event_id
        folder.mkdir(parents=True)
        (folder / "event.json").write_text(
            json.dumps({"event_id": event_id, "started_utc": timestamp})
        )
    result = cli("--config", str(config), "events", "--limit", "1")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[0]["event_id"] == "aaa"


def test_run_without_any_camera_frames_returns_failure(tmp_path):
    import json

    config = tmp_path / "settings.toml"
    config.write_text(
        '[camera]\ndevice = "/dev/video999999"\n'
        '[[motion.regions]]\nname = "test"\nx = 0.0\ny = 0.0\nwidth = 1.0\nheight = 1.0\n'
        '[storage]\ndata_dir = "' + str(tmp_path / "events") + '"\n'
    )
    result = cli("--config", str(config), "run", "--duration", "0.01")
    assert result.returncode != 0
    assert json.loads(result.stdout)["frames_received"] == 0
