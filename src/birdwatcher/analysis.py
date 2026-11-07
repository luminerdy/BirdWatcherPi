"""Optional offline shadow worker; capture files are only ever read."""

import hashlib
import json
import os
import re
import stat
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

import cv2

from .analysis_queue import AnalysisError, AnalysisQueue, safe_path

SCAN_LIMIT = 1000


def read_source(path, max_bytes):
    """Read a regular file through no-follow directory descriptors (Linux)."""
    path = safe_path(path)
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    fd = None
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise AnalysisError("Source file exceeds limit or is not regular")
        with os.fdopen(fd, "rb") as stream:
            fd = None
            payload = stream.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise AnalysisError("Source file exceeds limit")
        return payload
    finally:
        os.close(directory)
        if fd is not None:
            os.close(fd)


class Analyzer:
    def __init__(
        self,
        data_dir: Path,
        analysis_dir: Path,
        detector,
        regions=(),
        frames_per_event: int = 3,
        queue_limit: int = 100,
    ):
        if type(frames_per_event) is not int or not 1 <= frames_per_event <= 100:
            raise ValueError("frames_per_event must be in [1, 100]")
        self.data_dir = safe_path(data_dir)
        output = safe_path(analysis_dir)
        if output.is_relative_to(self.data_dir) or self.data_dir.is_relative_to(output):
            raise AnalysisError("Analysis and capture directories must be disjoint")
        if any((p / ".git").exists() for p in (output, *output.parents)):
            raise AnalysisError("Analysis directory must be outside Git checkouts")
        if output.exists():
            for base, dirs, files in os.walk(output, followlinks=False):
                if ".git" in dirs or ".git" in files:
                    raise AnalysisError("Analysis directory must not contain Git checkouts")
        self.detector = detector
        self.regions = tuple(regions)
        self.frames_per_event = frames_per_event
        self.settings = dict(
            model=detector.model_info,
            regions=[asdict(r) for r in regions],
            frames_per_event=frames_per_event,
        )
        self.queue = AnalysisQueue(analysis_dir, queue_limit)
        self._path_iterator = None

    def _paths(self):
        try:
            with os.scandir(self.data_dir) as days:
                for day in days:
                    yield None  # Charge traversal, including invalid entries.
                    if not day.is_dir(follow_symlinks=False):
                        continue
                    try:
                        with os.scandir(day.path) as folders:
                            for folder in folders:
                                yield (
                                    Path(folder.path) / "event.json"
                                    if folder.is_dir(follow_symlinks=False)
                                    else None
                                )
                    except OSError:
                        continue
        except OSError:
            return

    def _scan(self):
        if self._path_iterator is None:
            self._path_iterator = self._paths()
        for _ in range(SCAN_LIMIT):
            try:
                manifest = next(self._path_iterator)
            except StopIteration:
                self._path_iterator = None
                break
            if manifest is None:
                continue
            try:
                safe_path(manifest)
                relative = manifest.relative_to(self.data_dir)
                day, event_id, _ = relative.parts
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                    continue
                date.fromisoformat(day)
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}", event_id):
                    continue
                raw = read_source(manifest, 1024 * 1024)
                data = json.loads(raw)
                if (
                    not isinstance(data, dict)
                    or type(data.get("schema_version")) is not int
                    or data["schema_version"] != 1
                    or data.get("event_id") != event_id
                ):
                    continue
                frames = data.get("frames")
                if not isinstance(frames, list) or len(frames) > 10000:
                    continue
                ids = set()
                valid = True
                for f in frames:
                    if (
                        not isinstance(f, dict)
                        or type(f.get("id")) is not int
                        or f["id"] < 0
                        or f.get("path") != f"originals/{f['id']}.jpg"
                        or f["id"] in ids
                    ):
                        valid = False
                        break
                    ids.add(f["id"])
                    original = safe_path(manifest.parent / f["path"])
                    if not original.is_relative_to(self.data_dir):
                        valid = False
                if not valid:
                    continue
            except (OSError, ValueError, AnalysisError):
                continue
            if data.get("status") != "complete" or data.get("complete") is not True:
                continue
            n = min(len(frames), self.frames_per_event)
            indices = (
                [round(i * (len(frames) - 1) / (n - 1)) for i in range(n)]
                if n > 1
                else ([0] if n else [])
            )
            identity = dict(
                event=str(manifest.relative_to(self.data_dir)),
                data_root_sha256=hashlib.sha256(str(self.data_dir).encode()).hexdigest(),
                manifest_sha256=hashlib.sha256(raw).hexdigest(),
                **self.settings,
            )
            key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            yield (
                key,
                dict(
                    event_id=data["event_id"],
                    manifest=str(manifest),
                    manifest_sha256=identity["manifest_sha256"],
                    frames=[frames[i] for i in indices],
                    total_frames=len(frames),
                    settings=self.settings,
                ),
            )

    def _analyze(self, payload):
        outcomes = []
        errors = []
        mismatch = payload["settings"] != self.settings
        import numpy as np

        for frame in payload["frames"]:
            try:
                if mismatch:
                    raise AnalysisError("settings_changed")
                path = safe_path(Path(payload["manifest"]).parent / frame["path"])
                if not path.is_relative_to(self.data_dir):
                    raise AnalysisError("Source outside capture root")
                image = cv2.imdecode(
                    np.frombuffer(read_source(path, 32 * 1024 * 1024), dtype=np.uint8),
                    cv2.IMREAD_COLOR,
                )
                if image is None:
                    raise ValueError("Invalid image")
                outcome = self.detector.analyze(image, self.regions)
                outcomes.append(dict(frame_id=frame["id"], **outcome))
            except Exception as exc:
                error = dict(
                    frame_id=frame["id"],
                    code="settings_changed" if mismatch else type(exc).__name__,
                )
                errors.append(error)
                outcomes.append(
                    dict(frame_id=frame["id"], status="analysis_failed", detections=[], error=error)
                )
        scores = [d["score"] for outcome in outcomes for d in outcome["detections"]]
        usable = len(outcomes) - len(errors)
        return dict(
            schema_version=1,
            analyzed_utc=datetime.now(timezone.utc).isoformat(),
            event_id=payload["event_id"],
            manifest_sha256=payload["manifest_sha256"],
            selected_frame_ids=[f["id"] for f in payload["frames"]],
            frames=outcomes,
            highest_score=max(scores, default=None),
            model=payload["settings"]["model"],
            regions=payload["settings"]["regions"],
            sampling=dict(
                method="evenly_spaced",
                total_frames=payload["total_frames"],
                whole_event_claim=False,
            ),
            errors=errors,
            partial_errors=bool(errors and usable),
            status="bird_candidate" if scores else ("unknown" if usable else "analysis_failed"),
        )

    def run(self, limit: int = 20):
        if type(limit) is not int or not 0 <= limit <= 1000:
            raise ValueError("limit must be in [0, 1000]")
        summary = dict(
            discovered=0, enqueued=0, analyzed=0, candidates=0, unknown=0, failed=0, deferred=0
        )
        for key, payload in self._scan():
            summary["discovered"] += 1
            state = self.queue.enqueue(key, payload)
            if state in ("enqueued", "deferred"):
                summary[state] += 1
        for _ in range(limit):
            job = self.queue.claim()
            if job is None:
                break
            result = self._analyze(job["payload"])
            self.queue.finish(job["key"], result)
            summary["analyzed"] += 1
            counter = {
                "bird_candidate": "candidates",
                "unknown": "unknown",
                "analysis_failed": "failed",
            }[result["status"]]
            summary[counter] += 1
        return summary

    def close(self):
        if self._path_iterator is not None:
            self._path_iterator.close()
            self._path_iterator = None
        self.queue.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
