import hashlib
import json

import cv2
import numpy as np
import pytest


class Detector:
    model_info = {
        "name": "fixture",
        "revision": "test",
        "sha256": "a" * 64,
        "threshold": 0.25,
        "preprocess_version": "test",
    }

    def analyze(self, image, regions=()):
        return {
            "status": "bird_candidate",
            "detections": [
                dict(class_id=14, label="bird", score=0.8, box=[1, 1, 3, 3], region="full_frame")
            ],
        }


def event(root, name="event_1", count=5, status="complete"):
    folder = root / "2026-01-01" / name
    (folder / "originals").mkdir(parents=True)
    frames = []
    for n in range(count):
        cv2.imwrite(str(folder / f"originals/{n}.jpg"), np.zeros((8, 8, 3), np.uint8))
        frames.append({"id": n, "path": f"originals/{n}.jpg"})
    (folder / "event.json").write_text(
        json.dumps(
            dict(
                schema_version=1,
                event_id=name,
                status=status,
                complete=status == "complete",
                frames=frames,
            )
        )
    )
    return folder


def snapshot(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize("kind", ["inside", "ancestor", "git", "symlink"])
def test_analysis_directory_isolation(tmp_path, kind):
    from birdwatcher.analysis import AnalysisError, Analyzer

    data = tmp_path / "data"
    data.mkdir()
    if kind == "inside":
        output = data / "analysis"
    elif kind == "ancestor":
        output = tmp_path
    elif kind == "git":
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        (checkout / ".git").write_text("gitdir: elsewhere")
        output = checkout / "analysis"
    else:
        output = tmp_path / "link"
        output.symlink_to(data, target_is_directory=True)
    with pytest.raises(AnalysisError):
        Analyzer(data, output, Detector())


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "day",
        "id",
        "negative",
        "escape",
        "duplicate",
        "manifest_link",
        "original_link",
        "active",
    ],
)
def test_rejects_unsafe_manifests_without_writes(tmp_path, mutation):
    from birdwatcher.analysis import Analyzer

    data = tmp_path / "data"
    folder = event(data)
    manifest = folder / "event.json"
    content = json.loads(manifest.read_text())
    if mutation == "schema":
        content["schema_version"] = 2
    elif mutation == "day":
        folder.parent.rename(data / "2026-02-30")
        folder = data / "2026-02-30" / folder.name
        manifest = folder / "event.json"
    elif mutation == "id":
        content["event_id"] = "../outside"
    elif mutation == "negative":
        content["frames"][0] = {"id": -1, "path": "originals/-1.jpg"}
    elif mutation == "escape":
        content["frames"][0]["path"] = "../../outside.jpg"
    elif mutation == "duplicate":
        content["frames"][1] = content["frames"][0]
    elif mutation == "active":
        content["status"] = "active"
    if mutation == "manifest_link":
        target = tmp_path / "outside.json"
        target.write_text(json.dumps(content))
        manifest.unlink()
        manifest.symlink_to(target)
    else:
        manifest.write_text(json.dumps(content))
    if mutation == "original_link":
        original = folder / "originals/0.jpg"
        target = tmp_path / "outside.jpg"
        target.write_bytes(original.read_bytes())
        original.unlink()
        original.symlink_to(target)
    before = snapshot(data)
    with Analyzer(data, tmp_path / "analysis", Detector()) as analyzer:
        result = analyzer.run()
        assert result["analyzed"] == 0
    assert snapshot(data) == before


@pytest.mark.parametrize("bad_count, expected", [(1, "bird_candidate"), (3, "analysis_failed")])
def test_partial_corruption_and_retention_errors(tmp_path, bad_count, expected, capsys):
    from birdwatcher.analysis import Analyzer

    data = tmp_path / "data"
    folder = event(data, count=3)
    for n in range(bad_count):
        (folder / f"originals/{n}.jpg").write_bytes(b"corrupt")
    with Analyzer(data, tmp_path / "analysis", Detector()) as analyzer:
        analyzer.run(limit=0)
        # A retention race after the job has been durably accepted.
        if bad_count == 3:
            (folder / "originals/2.jpg").unlink()
        summary = analyzer.run()
        result = json.loads(analyzer.queue.db.execute("SELECT result FROM jobs").fetchone()[0])
        assert result["status"] == expected
        assert len(result["errors"]) == bad_count
        assert result["partial_errors"] is (bad_count == 1)
        assert result["frames"][0]["status"] == "analysis_failed"
        assert summary["failed"] == (1 if bad_count == 3 else 0)
    assert not capsys.readouterr().err


def test_empty_event_is_failed_and_detector_error_is_contained(tmp_path):
    from birdwatcher.analysis import Analyzer

    data = tmp_path / "data"
    event(data, count=0)
    with Analyzer(data, tmp_path / "analysis", Detector()) as analyzer:
        assert analyzer.run()["failed"] == 1
    event(data, name="event_2", count=1)

    class Broken(Detector):
        def analyze(self, image, regions=()):
            raise RuntimeError("private diagnostic /do/not/print")

    with Analyzer(data, tmp_path / "analysis2", Broken()) as analyzer:
        assert analyzer.run()["failed"] == 2
        rows = analyzer.queue.db.execute("SELECT result FROM jobs").fetchall()
        assert "/do/not/print" not in str([r[0] for r in rows])


@pytest.mark.parametrize("frames", [0, -1, True, 101])
def test_invalid_sampling_limits(tmp_path, frames):
    from birdwatcher.analysis import Analyzer

    with pytest.raises(ValueError):
        Analyzer(tmp_path / "data", tmp_path / "analysis", Detector(), frames_per_event=frames)


def test_backlog_is_bounded_and_settings_change_reanalyzes(tmp_path):
    from birdwatcher.analysis import Analyzer

    data = tmp_path / "data"
    event(data, "first", count=1)
    event(data, "second", count=1)
    with Analyzer(data, tmp_path / "analysis", Detector(), queue_limit=1) as analyzer:
        result = analyzer.run(limit=0)
        assert result["enqueued"] == result["deferred"] == 1
        assert analyzer.run(limit=1)["analyzed"] == 1
        assert analyzer.run(limit=1)["analyzed"] == 1
        with pytest.raises(ValueError):
            analyzer.run(limit=-1)

    class Changed(Detector):
        model_info = dict(Detector.model_info, threshold=0.4)

    with Analyzer(data, tmp_path / "analysis", Changed()) as analyzer:
        assert analyzer.run()["enqueued"] == 2


def test_restart_does_not_label_old_job_with_new_detector(tmp_path):
    from birdwatcher.analysis import Analyzer

    data = tmp_path / "data"
    event(data, count=1)
    with Analyzer(data, tmp_path / "analysis", Detector()) as analyzer:
        analyzer.run(limit=0)

    class Changed(Detector):
        model_info = dict(Detector.model_info, threshold=0.4)

    with Analyzer(data, tmp_path / "analysis", Changed()) as analyzer:
        summary = analyzer.run()
        assert summary["failed"] == 1
        assert summary["candidates"] == 1
        results = [json.loads(r[0]) for r in analyzer.queue.db.execute("SELECT result FROM jobs")]
        assert results[0]["errors"][0]["code"] == "settings_changed"


def test_bounded_scan_advances_across_calls(tmp_path, monkeypatch):
    import birdwatcher.analysis as module

    monkeypatch.setattr(module, "SCAN_LIMIT", 2, raising=False)
    data = tmp_path / "data"
    for i in range(5):
        event(data, f"event_{i}", count=1)
    with module.Analyzer(data, tmp_path / "analysis", Detector()) as analyzer:
        summaries = [analyzer.run() for _ in range(4)]
        assert all(s["discovered"] <= 2 for s in summaries)
        assert sum(s["analyzed"] for s in summaries) == 5


def test_secure_bounded_reads_reject_symlinks_and_large_files(tmp_path):
    from birdwatcher.analysis import AnalysisError, read_source

    path = tmp_path / "file"
    path.write_bytes(b"abcd")
    assert read_source(path, 4) == b"abcd"
    with pytest.raises(AnalysisError):
        read_source(path, 3)
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises((OSError, AnalysisError)):
        read_source(link / "file", 4)


def test_data_root_identity_and_manifest_changes_make_new_jobs(tmp_path):
    from birdwatcher.analysis import Analyzer

    for name in ("one", "two"):
        data = tmp_path / name
        folder = event(data, count=1)
        with Analyzer(data, tmp_path / "analysis", Detector()) as analyzer:
            assert analyzer.run()["enqueued"] == 1
            result = json.loads(
                analyzer.queue.db.execute("SELECT result FROM jobs ORDER BY rowid DESC").fetchone()[
                    0
                ]
            )
            assert (
                result["manifest_sha256"]
                == hashlib.sha256((folder / "event.json").read_bytes()).hexdigest()
            )
        content = json.loads((folder / "event.json").read_text())
        content["annotation"] = "changed"
        (folder / "event.json").write_text(json.dumps(content))
        with Analyzer(data, tmp_path / "analysis", Detector()) as analyzer:
            assert analyzer.run()["enqueued"] == 1


def test_unknown_result_is_explicit_sample_not_absence_claim(tmp_path):
    from birdwatcher.analysis import Analyzer

    class Unknown(Detector):
        def analyze(self, image, regions=()):
            return {"status": "unknown", "detections": []}

    data = tmp_path / "data"
    event(data, count=4)
    with Analyzer(data, tmp_path / "analysis", Unknown(), frames_per_event=2) as analyzer:
        summary = analyzer.run()
        assert summary["unknown"] == 1
        result = json.loads(analyzer.queue.db.execute("SELECT result FROM jobs").fetchone()[0])
        assert result["schema_version"] == 1
        assert result["analyzed_utc"].endswith("+00:00")
        assert result["selected_frame_ids"] == [0, 3]
        assert result["highest_score"] is None
        assert result["status"] == "unknown"
        assert "no_bird" not in json.dumps(result)
        assert "bird_count" not in result


def test_exhausted_interrupted_job_keeps_source_and_model_metadata(tmp_path):
    from birdwatcher.analysis import Analyzer

    data = tmp_path / "data"
    event(data, count=1)
    output = tmp_path / "analysis"
    for _ in range(3):
        with Analyzer(data, output, Detector()) as analyzer:
            analyzer.run(limit=0)
            assert analyzer.queue.claim() is not None
    with Analyzer(data, output, Detector()) as analyzer:
        assert analyzer.queue.claim() is None
        result = json.loads(analyzer.queue.db.execute("SELECT result FROM jobs").fetchone()[0])
        assert result["event_id"] == "event_1"
        assert result["selected_frame_ids"] == [0]
        assert result["model"] == Detector.model_info
        assert result["frames"][0]["status"] == "analysis_failed"


def test_analyzer_sampling_idempotence_and_original_safety(tmp_path):
    from birdwatcher.analysis import Analyzer

    data = tmp_path / "data"
    event(data)
    before = snapshot(data)
    with Analyzer(data, tmp_path / "analysis", Detector()) as analyzer:
        summary = analyzer.run()
        assert summary == dict(
            discovered=1, enqueued=1, analyzed=1, candidates=1, unknown=0, failed=0, deferred=0
        )
        row = analyzer.queue.db.execute("SELECT result FROM jobs").fetchone()
        result = json.loads(row[0])
        assert result["status"] == "bird_candidate"
        assert result["selected_frame_ids"] == [0, 2, 4]
        assert result["sampling"]["whole_event_claim"] is False
        assert result["highest_score"] == 0.8
        assert result["model"] == Detector.model_info
        assert analyzer.run()["analyzed"] == 0
    with Analyzer(data, tmp_path / "analysis", Detector()) as analyzer:
        assert analyzer.run()["enqueued"] == 0
    assert snapshot(data) == before
