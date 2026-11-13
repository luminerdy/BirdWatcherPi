"""Synthetic photos only: no capture data is used by these tests."""

import copy
import hashlib
import json
import os
from pathlib import Path

import cv2
import numpy as np
import pytest


def fixture_model(tmp_path):
    source = tmp_path / "captures"
    photo = source / "2026-01-01" / "synthetic" / "originals" / "1.jpg"
    photo.parent.mkdir(parents=True)
    ok, encoded = cv2.imencode(".jpg", np.zeros((12, 16, 3), dtype=np.uint8))
    assert ok
    photo.write_bytes(encoded.tobytes())
    packet = tmp_path / "packet" / "packet.json"
    packet.parent.mkdir()
    packet.write_text("{}")
    model = dict(
        schema_version=1,
        date_local="2026-01-01",
        timezone="UTC",
        packet_sha256=hashlib.sha256(b"{}").hexdigest(),
        source_root=str(source),
        frames=[
            dict(
                id="F000001",
                source_path=str(photo),
                source_sha256=hashlib.sha256(photo.read_bytes()).hexdigest(),
                analysis_status="bird_candidate",
                confirmed=True,
                keeper=True,
                shortlisted=True,
                score=0.8,
            )
        ],
        hours=[],
        summary={"inventory_frames": 1},
        coverage={},
        groups=[],
        warnings=[],
    )
    return packet, source, photo, model


def exporter(monkeypatch, model):
    from birdwatcher import report_export

    monkeypatch.setattr(report_export, "load_report", lambda *a, **kw: copy.deepcopy(model))
    monkeypatch.setattr(report_export, "render_report", lambda view: json.dumps(view))
    return report_export


def test_private_local_and_bounded_portable_end_to_end(tmp_path, monkeypatch):
    packet, source, photo, model = fixture_model(tmp_path)
    ex = exporter(monkeypatch, model)
    result = ex.build_report(packet, tmp_path / "output", source_root=source)
    assert set(result) == {
        "index_path",
        "portable_path",
        "summary_path",
        "date_local",
        "counts",
        "warnings",
    }
    local = json.loads(Path(result["index_path"]).read_text())
    portable = json.loads(Path(result["portable_path"]).read_text())
    assert local["frames"][0]["available"]
    assert local["frames"][0]["original_url"].endswith("/1.jpg")
    assert portable["frames"][0]["original_url"].startswith("data:image/jpeg;base64,")
    assert str(source) not in Path(result["portable_path"]).read_text()
    assert "source_path" not in Path(result["summary_path"]).read_text()
    assert Path(result["portable_path"]).stat().st_size <= 44_000_000
    for path in Path(tmp_path / "output").rglob("*"):
        assert path.stat().st_mode & 0o077 == 0
    assert ex.build_report(packet, tmp_path / "output", source_root=source) == result
    assert photo.read_bytes().startswith(b"\xff\xd8")


@pytest.mark.parametrize(
    "kind", ["source", "ancestor", "git", "symlink", "hardlink", "inherited", "lock", "foreign"]
)
def test_output_aliases_refused_before_any_mutation(tmp_path, monkeypatch, kind):
    packet, source, photo, model = fixture_model(tmp_path)
    ex = exporter(monkeypatch, model)
    out = tmp_path / "output"
    if kind == "source":
        out = source / "reports"
    elif kind == "ancestor":
        out = tmp_path
    elif kind == "git":
        out.mkdir()
        (out / ".git").mkdir()
    elif kind == "symlink":
        out.symlink_to(source, target_is_directory=True)
    elif kind == "hardlink":
        out.mkdir(mode=0o700)
        os.link(photo, out / "current.json")
    elif kind == "inherited":
        out.mkdir(mode=0o755)
    elif kind == "lock":
        out.mkdir(mode=0o700)
        os.link(photo, out / ".report.lock")
    elif kind == "foreign":
        out.mkdir(mode=0o700)
        (out / "current.json").write_text("unrelated user data")
    before = {
        str(p): (p.lstat().st_mode, p.lstat().st_size, p.lstat().st_mtime_ns)
        for p in tmp_path.rglob("*")
    }
    with pytest.raises((ValueError, OSError)):
        ex.build_report(packet, out, source_root=source)
    after = {
        str(p): (p.lstat().st_mode, p.lstat().st_size, p.lstat().st_mtime_ns)
        for p in tmp_path.rglob("*")
    }
    assert before == after


def real_fixture(tmp_path):
    """Real loader/renderer schema with visibly synthetic black photographs."""
    packet, source, photo, _ = fixture_model(tmp_path)
    inventory = []
    for i in range(1, 5):
        path = photo.with_name(f"{i}.jpg")
        path.write_bytes(photo.read_bytes())
        inventory.append(
            dict(
                event_key="2026-01-01/synthetic/event.json",
                event_id="synthetic",
                frame_id=i,
                source_path=str(path),
                utc=f"2026-01-01T12:00:0{i}+00:00",
                local=f"2026-01-01T12:00:0{i}+00:00",
                input_status="retained",
            )
        )
    digest = hashlib.sha256(photo.read_bytes()).hexdigest()
    results = [
        dict(
            inventory[0],
            status="bird_candidate",
            detections=[dict(score=0.8)],
            score=0.8,
            source_sha256=digest,
        ),
        dict(inventory[1], status="unknown", detections=[], score=None, source_sha256=digest),
        dict(
            inventory[2],
            status="unknown",
            detections=[],
            score=None,
            source_sha256=None,
            error={"code": "synthetic"},
        ),
    ]
    data = dict(
        schema_version=1,
        date_local="2026-01-01",
        timezone="UTC",
        source_root=str(source),
        inventory_path=str(packet.parent / "inventory.json"),
        results_path=str(packet.parent / "results.json"),
        shortlist=[dict(results[0], index=1)],
        recording_coverage={"sessions": []},
    )
    packet.write_text(json.dumps(data))
    Path(data["inventory_path"]).write_text(json.dumps(inventory))
    Path(data["results_path"]).write_text(json.dumps(results))
    receipt = tmp_path / "archive" / "receipt.json"
    receipt.parent.mkdir()
    receipt.write_text(
        json.dumps(
            dict(
                status="prepared",
                date_local=data["date_local"],
                timezone="UTC",
                packet_sha256=hashlib.sha256(packet.read_bytes()).hexdigest(),
                confirmed_indices=[1],
                best_indices=[1],
                observations=[dict(results[0], index=1)],
            )
        )
    )
    return packet, source, photo, receipt


def html_model(path):
    import re

    text = Path(path).read_text()
    return json.loads(
        re.search(
            r'<script id="report-data" type="application/json">(.*?)</script>', text, re.S
        ).group(1)
    )


def test_real_analytics_renderer_comparison_receipt_pairs(tmp_path):
    from birdwatcher.report_export import build_report

    packet, source, photo, receipt = real_fixture(tmp_path)
    result = build_report(
        packet,
        tmp_path / "output",
        source_root=source,
        receipt_path=receipt,
        comparison_packets=[(packet, receipt), (packet, None), packet],
    )
    view = json.loads(Path(result["summary_path"]).read_text())
    assert view["summary"]["inventory_frames"] == 4
    assert view["summary"]["analyzed_frames"] == 2
    assert view["summary"]["confirmed_frames"] == 1
    assert view["hours"][12]["candidate_frames"] == 1
    assert len(view["groups"]) == 1
    assert view["comparison"][0]["summary"]["confirmed_frames"] == 1
    for comparison in view["comparison"][1:]:
        assert comparison["summary"]["confirmed_frames"] is None
        assert comparison["warnings"]
    local = html_model(result["index_path"])
    remote = html_model(result["portable_path"])
    assert len(local["frames"]) == len(remote["frames"]) == 4
    assert all(f["original_url"] for f in local["frames"])
    assert remote["frames"][3]["original_url"] is None
    assert remote["frames"][3]["thumbnail_url"] is None
    assert remote["frames"][0]["original_url"].startswith("data:")
    for path in (result["index_path"], result["portable_path"]):
        text = Path(path).read_text()
        assert str(tmp_path) not in text
        assert "source_path" not in text
    assert "file://" not in Path(result["portable_path"]).read_text()
    assert "Unknown" in Path(result["portable_path"]).read_text()
    assert (
        "Comparison 2026-01-01: confirmed counts are unknown"
        in Path(result["portable_path"]).read_text()
    )


@pytest.mark.parametrize("state", ["valid", "changed", "symlink"])
def test_receipt_keeper_fallback_after_raw_expiry(tmp_path, state):
    from birdwatcher.report_export import build_report

    packet, source, photo, receipt = real_fixture(tmp_path)
    data = json.loads(receipt.read_text())
    digest = data["observations"][0]["source_sha256"]
    durable = receipt.parent / f"best-1-{digest}.jpg"
    if state == "symlink":
        durable.symlink_to(photo.with_name("2.jpg"))
    else:
        durable.write_bytes(photo.read_bytes() if state == "valid" else b"changed")
    data["observations"][0]["durable_copy"] = str(durable)
    receipt.write_text(json.dumps(data))
    photo.unlink()
    if state == "symlink":
        with pytest.raises(ValueError):
            build_report(packet, tmp_path / "output", source_root=source, receipt_path=receipt)
        assert not (tmp_path / "output").exists()
        return
    result = build_report(packet, tmp_path / "output", source_root=source, receipt_path=receipt)
    local = html_model(result["index_path"])
    assert local["frames"][0]["available"] is (state == "valid")
    assert bool(local["frames"][0]["original_url"]) is (state == "valid")
    if state == "valid":
        from urllib.parse import unquote

        link = Path(result["index_path"]).parent / unquote(local["frames"][0]["original_url"])
        assert link.resolve() == durable
    for key in ("index_path", "portable_path", "summary_path"):
        text = Path(result[key]).read_text()
        assert str(durable) not in text
        assert "durable_copy" not in text


def test_durable_receipt_parent_is_protected_input(tmp_path, monkeypatch):
    packet, source, photo, model = fixture_model(tmp_path)
    archive = tmp_path / "archive"
    archive.mkdir()
    durable = archive / ("best-1-" + model["frames"][0]["source_sha256"] + ".jpg")
    durable.write_bytes(photo.read_bytes())
    model["frames"][0].update(durable_copy=str(durable), shortlist_index=1)
    ex = exporter(monkeypatch, model)
    with pytest.raises(ValueError):
        ex.build_report(packet, archive / "output", source_root=source)
    assert not (archive / "output").exists()


def test_reselecting_prior_generation_updates_current(tmp_path, monkeypatch):
    packet, source, photo, model = fixture_model(tmp_path)
    ex = exporter(monkeypatch, model)
    out = tmp_path / "output"
    first = ex.build_report(packet, out, source_root=source)
    second = ex.build_report(packet, out, source_root=source, portable=False)
    assert second != first
    assert Path(first["index_path"]).exists()
    assert ex.build_report(packet, out, source_root=source) == first
    assert json.loads((out / "current.json").read_text()) == first


def test_late_unknown_output_file_refused_before_lock_mutation(tmp_path, monkeypatch):
    packet, source, photo, model = fixture_model(tmp_path)
    ex = exporter(monkeypatch, model)
    out = tmp_path / "output"
    out.mkdir(mode=0o700)

    def render(view):
        (out / "foreign").write_text("DO NOT TOUCH")
        return json.dumps(view)

    monkeypatch.setattr(ex, "render_report", render)
    with pytest.raises((ValueError, OSError)):
        ex.build_report(packet, out, source_root=source)
    assert set(p.name for p in out.iterdir()) == {"foreign"}
    assert (out / "foreign").read_text() == "DO NOT TOUCH"


@pytest.mark.parametrize("gap", [0, 3601, True, float("nan"), "60"])
def test_gap_rejected_even_with_loader_adapter(tmp_path, monkeypatch, gap):
    packet, source, photo, model = fixture_model(tmp_path)
    ex = exporter(monkeypatch, model)
    with pytest.raises(ValueError):
        ex.build_report(packet, tmp_path / "output", source_root=source, visit_gap_seconds=gap)
    assert not (tmp_path / "output").exists()


def test_output_changed_during_lock_acquisition_is_revalidated(tmp_path, monkeypatch):
    packet, source, photo, model = fixture_model(tmp_path)
    ex = exporter(monkeypatch, model)
    out = tmp_path / "output"
    first = ex.build_report(packet, out, source_root=source)
    original_open = os.open

    def open_with_race(path, flags, *args, **kwargs):
        fd = original_open(path, flags, *args, **kwargs)
        if Path(path).name == ".report.lock":
            current = out / "current.json"
            current.unlink()
            os.link(photo, current)
        return fd

    monkeypatch.setattr(ex.os, "open", open_with_race)
    before = photo.read_bytes()
    with pytest.raises((ValueError, OSError)):
        ex.build_report(packet, out, source_root=source, portable=False)
    assert photo.read_bytes() == before
    assert (out / "current.json").samefile(photo)
    assert Path(first["index_path"]).exists()
    assert len(list(out.glob("generation-*"))) == 1


def test_nested_export_directories_are_private(tmp_path, monkeypatch):
    packet, source, photo, model = fixture_model(tmp_path)
    ex = exporter(monkeypatch, model)
    out = tmp_path / "new-parent" / "nested" / "output"
    ex.build_report(packet, out, source_root=source)
    for path in (out, out.parent, out.parent.parent):
        assert path.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("kind", ["missing", "changed", "invalid", "decode", "decode_exception"])
def test_per_frame_image_failures_keep_historical_record(tmp_path, monkeypatch, kind):
    packet, source, photo, model = fixture_model(tmp_path)
    ex = exporter(monkeypatch, model)
    if kind == "missing":
        photo.unlink()
    elif kind == "changed":
        photo.write_bytes(b"changed")
    elif kind == "invalid":
        photo.write_bytes(b"not jpeg")
        model["frames"][0]["source_sha256"] = hashlib.sha256(photo.read_bytes()).hexdigest()
    elif kind == "decode":
        monkeypatch.setattr(ex.cv2, "imdecode", lambda *a: None)
    else:

        def bad_decode(*args):
            raise cv2.error("synthetic decoder failure")

        monkeypatch.setattr(ex.cv2, "imdecode", bad_decode)
    result = ex.build_report(packet, tmp_path / "output", source_root=source)
    assert result["counts"]["inventory_frames"] == 1
    assert result["counts"]["unavailable_images"] == 1
    assert result["counts"]["embedded_originals"] == 0
    for key in ("index_path", "portable_path"):
        view = json.loads(Path(result[key]).read_text())
        assert view["frames"][0]["confirmed"]
        assert not view["frames"][0]["available"]
        assert view["frames"][0]["original_url"] is None
        assert view["frames"][0]["export_note"]


def test_sampled_images_processed_one_at_a_time(tmp_path, monkeypatch):
    from birdwatcher import report_export as ex

    packet, source, photo, receipt = real_fixture(tmp_path)
    real_read, real_decode = ex._read, cv2.imdecode
    state = {"pending": False, "decoded": 0}

    def read_one(path, limit):
        if Path(path).suffix == ".jpg" and Path(path).stem in ("1", "2", "3"):
            assert not state["pending"], "Exporter accumulated original snapshots before decoding"
            state["pending"] = True
        return real_read(path, limit)

    def decode_one(*args):
        state["pending"] = False
        state["decoded"] += 1
        return real_decode(*args)

    monkeypatch.setattr(ex, "_read", read_one)
    monkeypatch.setattr(ex.cv2, "imdecode", decode_one)
    result = ex.build_report(packet, tmp_path / "output", source_root=source, receipt_path=receipt)
    assert result["counts"]["inventory_frames"] == 4
    assert state["decoded"] == 3


def test_unsampled_large_jpeg_only_reads_bounded_probe(tmp_path, monkeypatch):
    packet, source, photo, model = fixture_model(tmp_path)
    rng = np.random.default_rng(7)
    ok, encoded = cv2.imencode(".jpg", rng.integers(0, 256, (768, 1024, 3), dtype=np.uint8))
    assert ok and len(encoded) > 65538
    photo.write_bytes(encoded.tobytes())
    model["frames"][0].update(
        source_sha256=None,
        analysis_status="not_analyzed",
        confirmed=False,
        keeper=False,
        shortlisted=False,
    )
    ex = exporter(monkeypatch, model)
    real_read, real_os_read = ex._read, os.read
    identity = (photo.stat().st_dev, photo.stat().st_ino)
    bytes_read = []

    def no_full_image_read(path, limit):
        assert Path(path) != photo, "Unsampled original must not use full _read"
        return real_read(path, limit)

    def count_source_reads(fd, size):
        info = os.fstat(fd)
        data = real_os_read(fd, size)
        if (info.st_dev, info.st_ino) == identity:
            bytes_read.append(len(data))
        return data

    def no_decode(*args):
        pytest.fail("Unsampled original must not be decoded")

    monkeypatch.setattr(ex, "_read", no_full_image_read)
    monkeypatch.setattr(ex.os, "read", count_source_reads)
    monkeypatch.setattr(ex.cv2, "imdecode", no_decode)
    before = photo.stat()
    result = ex.build_report(packet, tmp_path / "output", source_root=source)
    assert 0 < sum(bytes_read) <= 65538
    local = json.loads(Path(result["index_path"]).read_text())["frames"][0]
    remote = json.loads(Path(result["portable_path"]).read_text())["frames"][0]
    assert local["available"] and local["original_url"]
    assert "not fully decoded or hash-validated" in local["export_note"]
    assert "not fully decoded or hash-validated" in remote["export_note"]
    assert remote["original_url"] is None and remote["thumbnail_url"] is None
    after = photo.stat()
    assert (before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )


@pytest.mark.parametrize("change", ["replace", "entropy", "expire"])
def test_unsampled_identity_and_expiry_refresh_generation(tmp_path, monkeypatch, change):
    packet, source, photo, model = fixture_model(tmp_path)
    model["frames"][0].update(
        source_sha256=None,
        analysis_status="not_analyzed",
        confirmed=False,
        keeper=False,
        shortlisted=False,
    )
    ex = exporter(monkeypatch, model)
    out = tmp_path / "output"
    first = ex.build_report(packet, out, source_root=source)
    old_html = Path(first["index_path"]).read_bytes()
    assert ex.build_report(packet, out, source_root=source) == first
    before = photo.stat()
    if change == "expire":
        photo.unlink()
    elif change == "replace":
        replacement = photo.with_suffix(".replacement")
        replacement.write_bytes(photo.read_bytes())
        os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
        os.replace(replacement, photo)
    else:
        data = bytearray(photo.read_bytes())
        data[-3] ^= 1  # Interior data changes; identical dimensions, size and EOI.
        photo.write_bytes(data)
        os.utime(photo, ns=(before.st_atime_ns, before.st_mtime_ns))
    second = ex.build_report(packet, out, source_root=source)
    assert second["index_path"] != first["index_path"]
    assert second["counts"]["available_images"] == (0 if change == "expire" else 1)
    assert ex.build_report(packet, out, source_root=source) == second
    assert Path(first["index_path"]).read_bytes() == old_html
    assert json.loads((out / "current.json").read_text()) == second


@pytest.mark.parametrize("required", ["hash", "analyzed", "shortlisted", "confirmed", "keeper"])
def test_non_probe_frames_still_fully_read_and_decoded(tmp_path, monkeypatch, required):
    packet, source, photo, model = fixture_model(tmp_path)
    frame = model["frames"][0]
    digest = frame["source_sha256"]
    frame.update(
        source_sha256=None,
        analysis_status="not_analyzed",
        confirmed=False,
        keeper=False,
        shortlisted=False,
    )
    if required == "hash":
        frame["source_sha256"] = digest
    elif required == "analyzed":
        frame["analysis_status"] = "unknown"
    else:
        frame[required] = True
    ex = exporter(monkeypatch, model)
    real_read, real_decode = ex._read, ex.cv2.imdecode
    reads, decodes = [], []

    def read(path, limit):
        data = real_read(path, limit)
        if Path(path) == photo:
            reads.append(data)
        return data

    def decode(*args):
        decodes.append(True)
        return real_decode(*args)

    def no_probe(*args):
        pytest.fail("Verification-required frame must not use availability probe")

    monkeypatch.setattr(ex, "_read", read)
    monkeypatch.setattr(ex.cv2, "imdecode", decode)
    monkeypatch.setattr(ex, "_probe_unsampled", no_probe)
    result = ex.build_report(packet, tmp_path / "output", source_root=source)
    assert reads == [photo.read_bytes()]
    assert decodes == [True]
    assert result["counts"]["available_images"] == 1


@pytest.mark.parametrize(
    "kind",
    [
        "symlink",
        "ancestor_symlink",
        "escape",
        "fifo",
        "oversize",
        "pixels",
        "eoi",
        "late_sof",
        "race",
    ],
)
def test_unsampled_probe_conservatively_withholds_unsafe_inputs(tmp_path, monkeypatch, kind):
    packet, source, photo, model = fixture_model(tmp_path)
    model["frames"][0].update(
        source_sha256=None,
        analysis_status="not_analyzed",
        confirmed=False,
        keeper=False,
        shortlisted=False,
    )
    ex = exporter(monkeypatch, model)
    data = photo.read_bytes()
    if kind in ("symlink", "escape"):
        outside = tmp_path / "outside.jpg"
        outside.write_bytes(data)
        if kind == "symlink":
            photo.unlink()
            photo.symlink_to(outside)
        else:
            model["frames"][0]["source_path"] = str(outside)
    elif kind == "ancestor_symlink":
        directory = photo.parent
        directory.rename(directory.with_name("renamed"))
        directory.symlink_to(directory.with_name("renamed"), target_is_directory=True)
    elif kind == "fifo":
        photo.unlink()
        os.mkfifo(photo)
    elif kind == "oversize":
        with photo.open("wb") as stream:
            stream.truncate(ex.MAX_IMAGE_BYTES + 1)
    elif kind == "pixels":
        photo.write_bytes(b"\xff\xd8\xff\xc0\x00\x08\x08\xff\xff\xff\xff\x03\xff\xd9")
    elif kind == "eoi":
        photo.write_bytes(data[:-2])
    elif kind == "late_sof":
        photo.write_bytes(data[:2] + b"\xff\xe1\xff\xff" + b"X" * 65533 + data[2:])
    elif kind == "race":
        real_read = os.read
        identity = photo.stat().st_ino

        def racing_read(fd, size):
            chunk = real_read(fd, size)
            if os.fstat(fd).st_ino == identity:
                photo.write_bytes(data + b"changed")
            return chunk

        monkeypatch.setattr(ex.os, "read", racing_read)
    result = ex.build_report(packet, tmp_path / "output", source_root=source)
    assert result["counts"]["unavailable_images"] == 1
    for key in ("index_path", "portable_path"):
        view = json.loads(Path(result[key]).read_text())["frames"][0]
        assert not view["available"]
        assert view["original_url"] is None and view["thumbnail_url"] is None


def test_replaced_lock_is_never_unlinked(tmp_path, monkeypatch):
    packet, source, photo, model = fixture_model(tmp_path)
    ex = exporter(monkeypatch, model)
    out = tmp_path / "output"
    out.mkdir(mode=0o700)
    original_open = os.open

    def replace_lock(path, flags, *args, **kwargs):
        fd = original_open(path, flags, *args, **kwargs)
        if Path(path).name == ".report.lock":
            Path(path).unlink()
            os.link(photo, path)
        return fd

    monkeypatch.setattr(ex.os, "open", replace_lock)
    with pytest.raises((ValueError, OSError)):
        ex.build_report(packet, out, source_root=source)
    assert (out / ".report.lock").samefile(photo)
    assert set(p.name for p in out.iterdir()) == {".report.lock"}


def test_zero_image_budgets_disclose_omissions_without_file_links(tmp_path, monkeypatch):
    from birdwatcher import report_export as ex

    packet, source, photo, receipt = real_fixture(tmp_path)
    monkeypatch.setattr(ex, "THUMBNAIL_BUDGET", 0)
    monkeypatch.setattr(ex, "ORIGINAL_BUDGET", 0)
    result = ex.build_report(packet, tmp_path / "output", source_root=source, receipt_path=receipt)
    assert result["counts"]["embedded_originals"] == 0
    assert result["counts"]["omitted_originals"] == 4
    assert result["counts"]["omitted_thumbnails"] == 4
    view = html_model(result["portable_path"])
    assert all(f["original_url"] is None and f["thumbnail_url"] is None for f in view["frames"])
    assert all(f["available"] for f in view["frames"])
    assert Path(result["portable_path"]).stat().st_size <= 44_000_000


def test_final_html_byte_limit_checked_before_mutation(tmp_path, monkeypatch):
    packet, source, photo, model = fixture_model(tmp_path)
    ex = exporter(monkeypatch, model)
    monkeypatch.setattr(ex, "MAX_HTML_BYTES", 128)
    with pytest.raises(ValueError, match="Portable HTML exceeds"):
        ex.build_report(packet, tmp_path / "output", source_root=source)
    assert not (tmp_path / "output").exists()


def test_changed_receipt_publishes_new_generation_keeps_previous(tmp_path):
    from birdwatcher.report_export import build_report

    packet, source, photo, receipt = real_fixture(tmp_path)
    out = tmp_path / "output"
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in source.rglob("*.jpg")}
    first = build_report(packet, out, source_root=source, receipt_path=receipt)
    old_html = Path(first["index_path"]).read_bytes()
    data = json.loads(receipt.read_text())
    data.update(confirmed_indices=[], best_indices=[], observations=[])
    receipt.write_text(json.dumps(data))
    second = build_report(packet, out, source_root=source, receipt_path=receipt)
    assert second["index_path"] != first["index_path"]
    assert json.loads(Path(second["summary_path"]).read_text())["summary"]["confirmed_frames"] == 0
    assert Path(first["index_path"]).read_bytes() == old_html
    assert json.loads((out / "current.json").read_text()) == second
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in source.rglob("*.jpg")}


@pytest.mark.parametrize("kind", ["unknown", "generation_unknown", "hardlink", "symlink", "lock"])
def test_existing_generation_tampering_refused_before_mutation(tmp_path, monkeypatch, kind):
    packet, source, photo, model = fixture_model(tmp_path)
    ex = exporter(monkeypatch, model)
    out = tmp_path / "output"
    first = ex.build_report(packet, out, source_root=source)
    target = out / "foreign"
    if kind == "generation_unknown":
        target = Path(first["index_path"]).parent / "foreign"
    if kind in ("hardlink", "lock"):
        target = out / (".report.lock" if kind == "lock" else "foreign")
        os.link(photo, target)
    elif kind == "symlink":
        target.symlink_to(photo)
    else:
        target.write_text("foreign content")
        target.chmod(0o600)
    before = {
        str(p): (
            p.lstat().st_mode,
            p.lstat().st_size,
            p.lstat().st_mtime_ns,
            p.lstat().st_ino,
            p.lstat().st_nlink,
        )
        for p in out.rglob("*")
    }
    with pytest.raises((ValueError, OSError)):
        ex.build_report(packet, out, source_root=source, portable=False)
    assert before == {
        str(p): (
            p.lstat().st_mode,
            p.lstat().st_size,
            p.lstat().st_mtime_ns,
            p.lstat().st_ino,
            p.lstat().st_nlink,
        )
        for p in out.rglob("*")
    }


def test_failed_staged_write_preserves_published_generation(tmp_path, monkeypatch):
    packet, source, photo, model = fixture_model(tmp_path)
    ex = exporter(monkeypatch, model)
    out = tmp_path / "output"
    first = ex.build_report(packet, out, source_root=source)
    current = (out / "current.json").read_bytes()
    real_write = ex._write

    def fail_summary(path, data):
        if Path(path).name == "summary.json":
            raise OSError("synthetic disk-full failure")
        return real_write(path, data)

    monkeypatch.setattr(ex, "_write", fail_summary)
    with pytest.raises(OSError, match="synthetic disk-full"):
        ex.build_report(packet, out, source_root=source, portable=False)
    assert (out / "current.json").read_bytes() == current
    assert Path(first["index_path"]).exists()
    assert not (out / ".report.lock").exists()
    assert len(list(out.glob("generation-*"))) == 1
    stages = list(out.glob(".staging-*"))
    assert len(stages) == 1
    assert all(p.stat().st_mode & 0o077 == 0 for p in stages[0].rglob("*"))
