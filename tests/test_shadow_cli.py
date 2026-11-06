"""Shadow-analysis CLI remains separate from camera capture."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cli(*args):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    return subprocess.run(
        [sys.executable, "-m", "birdwatcher", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )


def test_analyze_help_explains_shadow_mode():
    result = cli("analyze", "--help")
    assert result.returncode == 0, result.stderr
    assert "shadow" in result.stdout.lower()
    assert "--model" in result.stdout
    assert "--watch-seconds" in result.stdout


def test_analyze_rejects_bad_limits_without_touching_camera_or_model(tmp_path):
    cases = [
        ("--threshold", "nan"),
        ("--threshold", "0"),
        ("--threshold", "1.1"),
        ("--frames-per-event", "0"),
        ("--limit", "101"),
        ("--watch-seconds", "-1"),
    ]
    for flag, value in cases:
        result = cli("analyze", "--model", str(tmp_path / "missing.onnx"), flag, value)
        assert result.returncode != 0, (flag, value, result.stdout)
        assert "Traceback" not in result.stderr


def test_analyze_requires_private_regions_or_explicit_full_frame(tmp_path):
    result = cli("analyze", "--model", str(tmp_path / "missing.onnx"))
    assert result.returncode != 0
    assert "region" in result.stderr.lower()
    assert "Traceback" not in result.stderr


def test_analyze_one_pass_does_not_construct_camera(tmp_path, monkeypatch, capsys):
    import json
    from types import SimpleNamespace

    import birdwatcher.camera
    from birdwatcher import cli as app

    config = tmp_path / "settings.toml"
    config.write_text('[storage]\ndata_dir = "' + str(tmp_path / "captures") + '"\n')
    calls = []

    class FakeAnalyzer:
        def __init__(self, data_dir, analysis_dir, detector, regions=(), frames_per_event=3):
            calls.append(("open", data_dir, analysis_dir))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            calls.append(("closed",))

        def run(self, limit=20):
            calls.append(("run", limit))
            return {"analyzed": 2, "candidates": 1, "unknown": 1, "failed": 0}

    class FakeDetector:
        model_info = {"name": "test-model", "threshold": 0.25}

        def __init__(self, model_path, threshold=0.25):
            pass

    def no_camera(*args, **kwargs):
        raise AssertionError("Shadow analysis must not open the camera")

    monkeypatch.setitem(
        sys.modules,
        "birdwatcher.analysis",
        SimpleNamespace(Analyzer=FakeAnalyzer, AnalysisError=RuntimeError),
    )
    monkeypatch.setitem(
        sys.modules,
        "birdwatcher.bird_detector",
        SimpleNamespace(BirdDetector=FakeDetector, DetectorError=RuntimeError),
    )
    monkeypatch.setattr(birdwatcher.camera, "Camera", no_camera)
    monkeypatch.setattr(os, "nice", lambda *_: None)
    result = app.main(
        [
            "--config",
            str(config),
            "analyze",
            "--model",
            str(tmp_path / "model.onnx"),
            "--full-frame",
        ]
    )
    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "shadow" and payload["filtering_enabled"] is False
    assert payload["totals"]["analyzed"] == 2
    assert calls[-1] == ("closed",)
