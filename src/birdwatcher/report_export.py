"""Private, offline report generations. No capture files are ever modified."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import os
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

import cv2
import numpy as np

THUMBNAIL_BUDGET = 6 * 1024 * 1024
ORIGINAL_BUDGET = 24 * 1024 * 1024
MAX_HTML_BYTES = 44_000_000
MAX_IMAGE_BYTES = 24 * 1024 * 1024
MAX_PIXELS = 40_000_000


def load_report(*args, **kwargs) -> dict:
    from .report_data import load_report as load

    return load(*args, **kwargs)


def render_report(view):
    from .report_view import render_report as render

    return render(view)


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False)


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: _clean(v)
            for k, v in value.items()
            if k not in {"source_path", "source_root", "durable_copy"}
        }
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _no_symlinks(path):
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("Symlink paths are not allowed")
    return path


@contextmanager
def _open_regular(path, limit):
    """Share component-wise NOFOLLOW opens for full reads and bounded probes."""
    path = Path(os.path.abspath(path))
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        leaf = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(leaf)
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise ValueError("Not a bounded regular file")
            yield leaf, before
            if _identity(before) != _identity(os.fstat(leaf)):
                raise ValueError("File changed during read")
        finally:
            os.close(leaf)
    finally:
        os.close(fd)


def _identity(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_mode,
        info.st_nlink,
    )


def _read(path, limit):
    """Bound full reads and reject in-flight changes."""
    with _open_regular(path, limit) as (leaf, _):
        chunks = []
        size = 0
        while True:
            chunk = os.read(leaf, min(65536, limit + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > limit:
                raise ValueError("File exceeds byte bound")
        return b"".join(chunks)


def _probe_unsampled(path):
    """Availability only: at most 64 KiB header + 2 EOI bytes, not pixel/hash proof.

    A JPEG whose SOF exceeds the header bound is conservatively withheld.
    Identity in the generation key notices retention and replacement on reruns.
    """
    with _open_regular(path, MAX_IMAGE_BYTES) as (leaf, info):
        if info.st_size < 4:
            raise ValueError("Invalid JPEG")
        header = os.read(leaf, min(65536, info.st_size - 2))
        os.lseek(leaf, -2, os.SEEK_END)
        tail = os.read(leaf, 2)
        _jpeg_dimensions(header + tail)
        return _identity(info)


def _jpeg_dimensions(data):
    """Check bounded JPEG marker structure without decoding unsampled images."""
    if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        raise ValueError("Invalid JPEG")
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 255:
            raise ValueError("Invalid JPEG marker")
        while pos < len(data) and data[pos] == 255:
            pos += 1
        marker = data[pos]
        pos += 1
        if marker in (0xD9, 0xDA):
            break
        length = int.from_bytes(data[pos : pos + 2], "big")
        if length < 2 or pos + length > len(data):
            raise ValueError("Invalid JPEG length")
        if marker in {0xC0, 0xC1, 0xC2} and length >= 8:
            height = int.from_bytes(data[pos + 3 : pos + 5], "big")
            width = int.from_bytes(data[pos + 5 : pos + 7], "big")
            if not width or not height or width * height > MAX_PIXELS:
                raise ValueError("JPEG dimensions exceed bound")
            return width, height
        pos += length
    raise ValueError("Unsupported JPEG")


def _data_url(data):
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")


def _write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        raise


def _validate_output(output, *, own_lock=None):
    if not output.exists():
        return
    if not output.is_dir() or output.stat().st_mode & 0o077:
        raise ValueError("Existing output must be a private directory")
    entries = list(output.iterdir())
    if own_lock is not None:
        lock_info = (output / ".report.lock").lstat()
        held = os.fstat(own_lock)
        if (
            (lock_info.st_dev, lock_info.st_ino) != (held.st_dev, held.st_ino)
            or lock_info.st_nlink != 1
            or not stat.S_ISREG(lock_info.st_mode)
        ):
            raise ValueError("Exclusive lock identity changed")
        entries = [p for p in entries if p.name != ".report.lock"]
    if not entries:
        return
    for root, dirs, files in os.walk(output, followlinks=False):
        for name in dirs + files:
            path = Path(root) / name
            info = path.lstat()
            if (
                stat.S_ISLNK(info.st_mode)
                or info.st_mode & 0o077
                or (
                    not stat.S_ISDIR(info.st_mode)
                    and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)
                )
            ):
                raise ValueError("Unsafe existing output entry")
    owner = json.loads(_read(output / ".report-owner.json", 4096))
    if owner != {"format": "birdwatcher-report-1", "output": str(output)}:
        raise ValueError("Output directory is not owned by this exporter")
    for path in entries:
        if path.name in {".report-owner.json", "current.json"}:
            continue
        if not path.name.startswith("generation-") or not path.is_dir():
            raise ValueError("Unknown output entry; refusing mutation")
        manifest = json.loads(_read(path / "manifest.json", 8192))
        if set(p.name for p in path.iterdir()) != set(manifest) | {"manifest.json"}:
            raise ValueError("Unknown generation entry")
        for name, digest in manifest.items():
            if name not in {"index.html", "report.html", "summary.json", "result.json"}:
                raise ValueError("Invalid generation manifest")
            if hashlib.sha256(_read(path / name, MAX_HTML_BYTES)).hexdigest() != digest:
                raise ValueError("Existing generation has changed")
    current = json.loads(_read(output / "current.json", 1_000_000))
    index = Path(current["index_path"])
    if index.parent.parent != output or index.name != "index.html":
        raise ValueError("Invalid current generation")
    if current != json.loads(_read(index.parent / "result.json", 1_000_000)):
        raise ValueError("Current entry is not exporter-owned")


def build_report(
    packet_path,
    output_dir,
    *,
    source_root,
    receipt_path=None,
    comparison_packets=(),
    visit_gap_seconds=60,
    portable=True,
):
    """Return immutable generation paths; output's current.json is the atomic entry.

    Failed runs may leave private staging directories, never partial published
    generations. Unknown pre-existing output contents are not overwritten.
    """
    if (
        type(visit_gap_seconds) not in (int, float)
        or not math.isfinite(visit_gap_seconds)
        or not 1 <= visit_gap_seconds <= 3600
    ):
        raise ValueError("Visit gap must be numeric within 1..3600 seconds")
    source = _no_symlinks(source_root)
    output = _no_symlinks(output_dir)
    packet = _no_symlinks(packet_path)
    protected = [source, packet.parent]
    if receipt_path is not None:
        protected.append(_no_symlinks(receipt_path).parent)
    comparison_inputs = []
    for item in comparison_packets:
        p, r = item if isinstance(item, (tuple, list)) else (item, None)
        p = _no_symlinks(p)
        r = _no_symlinks(r) if r is not None else None
        comparison_inputs.append((p, r))
        protected.append(p.parent)
        if r is not None:
            protected.append(r.parent)
    if any(output == p or output in p.parents or p in output.parents for p in protected):
        raise ValueError("Output and inputs must be disjoint")
    if any((p / ".git").exists() for p in (output, *output.parents)):
        raise ValueError("Reports cannot be written in Git checkouts")
    _validate_output(output)
    model = load_report(
        packet, source_root=source, receipt_path=receipt_path, visit_gap_seconds=visit_gap_seconds
    )
    comparisons = []
    for p, r in comparison_inputs:
        comparison = load_report(
            p, source_root=source, receipt_path=r, visit_gap_seconds=visit_gap_seconds
        )
        if r is None:
            for key in (
                "confirmed_frames",
                "apparent_groups",
                "first_confirmed_local",
                "last_confirmed_local",
            ):
                comparison["summary"][key] = None
        comparisons.append(comparison)
    # Archive paths are trusted only with an explicitly selected receipt root.
    for loaded, selected_receipt in [
        (model, receipt_path),
        *zip(comparisons, (r for _, r in comparison_inputs)),
    ]:
        for frame in loaded["frames"]:
            if frame.get("durable_copy") is None:
                continue
            if selected_receipt is None or not frame.get("keeper") or not frame.get("confirmed"):
                raise ValueError("Keeper archive requires explicit validated receipt")
            receipt_root = _no_symlinks(selected_receipt).parent
            expected = (
                receipt_root / f"best-{frame['shortlist_index']}-{frame['source_sha256']}.jpg"
            )
            if _no_symlinks(frame["durable_copy"]) != expected:
                raise ValueError("Keeper archive outside explicit receipt root")
            if (
                output == receipt_root
                or output in receipt_root.parents
                or receipt_root in output.parents
            ):
                raise ValueError("Output and keeper archive must be disjoint")
    cv2.setNumThreads(1)
    local = _clean(copy.deepcopy(model))
    local.update(
        mode="local",
        comparison=[
            {
                "date_local": c["date_local"],
                "summary": _clean(c["summary"]),
                "warnings": _clean(c["warnings"]),
            }
            for c in comparisons
        ],
    )
    for comparison, (_, selected_receipt) in zip(comparisons, comparison_inputs):
        if selected_receipt is None:
            warning = (
                f"Comparison {comparison['date_local']}: confirmed counts are unknown "
                "without a validated receipt, not zero or evidence of absence."
            )
            if warning not in local["warnings"]:
                local["warnings"].append(warning)
    # Snapshot/process one image at a time; never accumulate the capture archive.
    # Only budgeted data URLs survive this loop. Availability is checked on reruns.
    for frame in local["frames"]:
        frame.update(thumbnail_url=None, original_url=None, available=False, export_note="")
    remote = copy.deepcopy(local)
    remote["mode"] = "portable"
    local_by_id = {f["id"]: f for f in local["frames"]}
    remote_by_id = {f["id"]: f for f in remote["frames"]}
    states = []
    thumb_bytes = original_bytes = 0
    prioritized = sorted(
        model["frames"],
        key=lambda f: (
            not f.get("keeper"),
            not f.get("confirmed"),
            f.get("analysis_status") != "bird_candidate",
            f["id"],
        ),
    )
    for original in prioritized:
        frame = local_by_id[original["id"]]
        embedded = remote_by_id[original["id"]]
        try:
            path = _no_symlinks(original["source_path"])
            if source not in path.parents:
                raise ValueError("Photo outside selected source")
            sampled = bool(
                original.get("source_sha256")
                or original.get("shortlisted")
                or original.get("confirmed")
                or original.get("keeper")
                or original.get("analysis_status") != "not_analyzed"
            )
            if not sampled:
                identity = _probe_unsampled(path)
                frame["available"] = embedded["available"] = True
                frame["original_url"] = quote(
                    os.path.relpath(path, output / "placeholder"), safe="/"
                )
                frame["thumbnail_url"] = frame["original_url"]
                qualification = "Availability probe only; not fully decoded or hash-validated"
                frame["export_note"] = qualification + "; subject to raw retention"
                embedded["export_note"] = qualification + "; On-Pi original / request photo ID"
                states.append([frame["id"], "availability_probe", identity])
                continue
            archived = False
            try:
                raw = _read(path, MAX_IMAGE_BYTES)
            except FileNotFoundError:
                if not original.get("durable_copy"):
                    raise
                path = _no_symlinks(original["durable_copy"])
                raw = _read(path, MAX_IMAGE_BYTES)
                archived = True
            digest = hashlib.sha256(raw).hexdigest()
            if original.get("source_sha256") and digest != original["source_sha256"]:
                frame["export_note"] = "Changed since analysis; image withheld"
                embedded["export_note"] = frame["export_note"]
                states.append([frame["id"], "changed", digest])
                continue
            _jpeg_dimensions(raw)
            image = None
            if sampled:
                try:
                    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
                except cv2.error:
                    pass
                if image is None:
                    frame["export_note"] = "JPEG decode error; image withheld"
                    embedded["export_note"] = frame["export_note"]
                    states.append([frame["id"], "decode_error", digest])
                    continue
            frame["available"] = embedded["available"] = True
            frame["original_url"] = quote(os.path.relpath(path, output / "placeholder"), safe="/")
            frame["thumbnail_url"] = frame["original_url"]
            frame["export_note"] = (
                "Verified archived keeper; raw original expired"
                if archived
                else "Retained On-Pi original; subject to raw retention"
            )
            embedded["export_note"] = "On-Pi original / request photo ID"
            states.append([frame["id"], digest, archived])
            if portable and sampled:
                height, width = image.shape[:2]
                factor = min(1, 320 / max(height, width))
                if factor < 1:
                    image = cv2.resize(
                        image,
                        (max(1, int(width * factor)), max(1, int(height * factor))),
                        interpolation=cv2.INTER_AREA,
                    )
                ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 75])
                thumb = encoded.tobytes() if ok else b""
                if thumb and thumb_bytes + len(thumb) <= THUMBNAIL_BUDGET:
                    embedded["thumbnail_url"] = _data_url(thumb)
                    thumb_bytes += len(thumb)
                if (
                    frame.get("keeper")
                    or frame.get("confirmed")
                    or frame.get("analysis_status") == "bird_candidate"
                ) and (original_bytes + len(raw) <= ORIGINAL_BUDGET):
                    embedded["original_url"] = _data_url(raw)
                    original_bytes += len(raw)
        except FileNotFoundError:
            frame["export_note"] = "Missing or expired original"
            embedded["export_note"] = frame["export_note"]
            states.append([frame["id"], "missing"])
        except (OSError, ValueError, cv2.error):
            for view_frame in (frame, embedded):
                view_frame.update(
                    available=False,
                    original_url=None,
                    thumbnail_url=None,
                    export_note="Image read or JPEG validation error; image withheld",
                )
            states.append([frame["id"], "error"])
    fingerprint = hashlib.sha256(
        _json(
            {
                "version": 3,
                "model": model,
                "receipt": hashlib.sha256(_read(receipt_path, 16 * 1024 * 1024)).hexdigest()
                if receipt_path
                else None,
                "comparisons": comparisons,
                "portable": portable,
                "gap": visit_gap_seconds,
                "states": states,
                "budgets": [THUMBNAIL_BUDGET, ORIGINAL_BUDGET, MAX_HTML_BYTES],
            }
        ).encode()
    ).hexdigest()
    counts = {
        "inventory_frames": len(local["frames"]),
        "available_images": sum(f["available"] for f in local["frames"]),
        "unavailable_images": sum(not f["available"] for f in local["frames"]),
        "embedded_thumbnails": sum(bool(f["thumbnail_url"]) for f in remote["frames"])
        if portable
        else 0,
        "embedded_originals": sum(bool(f["original_url"]) for f in remote["frames"])
        if portable
        else 0,
        "thumbnail_bytes": thumb_bytes if portable else 0,
        "original_bytes": original_bytes if portable else 0,
    }
    counts["omitted_thumbnails"] = counts["inventory_frames"] - counts["embedded_thumbnails"]
    counts["omitted_originals"] = counts["inventory_frames"] - counts["embedded_originals"]
    note = (
        "All inventory metadata included. Portable images are selected within 6 MiB thumbnail "
        "and 24 MiB original budgets. Unsampled photos remain On-Pi only; retained sources "
        "may expire. No enhancement or upscaling."
    )
    for view in (local, remote):
        view.update(exported=counts, gallery_limit_note=note)
    local_html = render_report(local).encode("utf-8")
    remote_html = render_report(remote).encode("utf-8") if portable else None
    if remote_html is not None and len(remote_html) > MAX_HTML_BYTES:
        raise ValueError("Portable HTML exceeds 44,000,000 bytes; nothing published")
    _no_symlinks(output)
    _validate_output(output)
    missing_dirs = []
    ancestor = output
    while not ancestor.exists():
        missing_dirs.append(ancestor)
        ancestor = ancestor.parent
    for directory in reversed(missing_dirs):
        _no_symlinks(directory.parent)
        directory.mkdir(mode=0o700)
    lock = output / ".report.lock"
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        _no_symlinks(output)
        _validate_output(output, own_lock=fd)
        generation = output / ("generation-" + fingerprint)
        if generation.exists():
            result = json.loads(_read(generation / "result.json", 1_000_000))
            if json.loads(_read(output / "current.json", 1_000_000)) != result:
                entry = output / (".entry-" + uuid.uuid4().hex)
                _write(entry, _json(result).encode())
                os.replace(entry, output / "current.json")
            return result
        stage = output / (".staging-" + uuid.uuid4().hex)
        stage.mkdir(mode=0o700)
        result = dict(
            index_path=str(generation / "index.html"),
            portable_path=str(generation / "report.html") if portable else None,
            summary_path=str(generation / "summary.json"),
            date_local=model["date_local"],
            counts=counts,
            warnings=local.get("warnings", []),
        )
        _write(stage / "index.html", local_html)
        if portable:
            _write(stage / "report.html", remote_html)
        _write(stage / "summary.json", _json(_clean(local)).encode())
        _write(stage / "result.json", _json(result).encode())
        manifest = {
            p.name: hashlib.sha256(_read(p, MAX_HTML_BYTES)).hexdigest() for p in stage.iterdir()
        }
        _write(stage / "manifest.json", _json(manifest).encode())
        os.rename(stage, generation)
        owner = output / ".report-owner.json"
        if not owner.exists():
            _write(owner, _json({"format": "birdwatcher-report-1", "output": str(output)}).encode())
        entry = output / (".entry-" + uuid.uuid4().hex)
        _write(entry, _json(result).encode())
        os.replace(entry, output / "current.json")
        return result
    finally:
        held = os.fstat(fd)
        os.close(fd)
        try:
            _no_symlinks(output)
            present = lock.lstat()
            if (held.st_dev, held.st_ino) == (present.st_dev, present.st_ino):
                lock.unlink()
        except (FileNotFoundError, ValueError):
            pass
