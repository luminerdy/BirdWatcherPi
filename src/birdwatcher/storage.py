"""Atomic capture-only manifests; no index or durable analysis queue yet."""

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .config import StorageConfig
from .events import EventAction


class StorageError(OSError):
    pass


class EventStore:
    def __init__(self, config: StorageConfig):
        self.config = config
        self.root = Path(config.data_dir).absolute()
        self._safe(self.root)
        project = Path(__file__).resolve().parents[2]
        resolved = self.root.resolve()
        if resolved.is_relative_to(project) or project.is_relative_to(resolved):
            raise StorageError("Unsafe data root")
        self.root.mkdir(parents=True, exist_ok=True)
        self.camera_settings = {}
        self._active = {}
        self._storage_full = False
        self._recovered = {}
        self._used = self._usage()
        self._writing = None
        self._recovery_credit = None
        self._frame_temporary = None
        self._manifest_temporary = None
        self._prune(0, enforce=False)
        for path, data in self._scan():
            try:
                intent = self._recover_frame(path, data)
                if data["status"] == "active" or intent is not None:
                    data.update(status="incomplete", complete=False, reason="interrupted")
                    if intent is not None:
                        self._recovery_credit = (path, intent.stat().st_size)
                    self._json(path, data)
                    if intent is not None:
                        self._remove_intent(intent)
            except OSError:
                self._storage_full = True
                self._recovered[data["event_id"]] = data
            finally:
                self._recovery_credit = None
                self._manifest_temporary = None
        self._storage_full = (
            bool(self._recovered)
            or self._used > self.config.max_bytes
            or shutil.disk_usage(self.root).free < self.config.min_free_bytes
        )

    def _recover_frame(self, path, data):
        """Trust only an exact, content-verified pending application frame."""
        intent = path.parent / ".frame-intent.json"
        try:
            self._safe(intent)
            record = json.loads(intent.read_text())
            frame = record["frame"]
            if not (
                record["schema_version"] == 1
                and record["event_id"] == data["event_id"]
                and type(frame["id"]) is int
                and frame["id"] >= 0
                and frame["path"] == f"originals/{frame['id']}.jpg"
                and isinstance(frame["utc"], str)
                and type(frame["monotonic"]) in (int, float)
                and type(record["size"]) is int
                and record["size"] >= 0
                and isinstance(record["sha256"], str)
                and re.fullmatch(r"[0-9a-f]{64}", record["sha256"])
            ):
                return None
            image = path.parent / frame["path"]
            self._safe(image)
            temporary = None
            if "temporary" in record:
                name = record["temporary"]
                if not isinstance(name, str) or not re.fullmatch(
                    rf"originals/\.{frame['id']}\.jpg\.[0-9a-f]{{32}}\.tmp", name
                ):
                    return None
                temporary = path.parent / name
                self._safe(temporary)
            # Validate every identified file before moving or removing either one.
            for candidate in (image, temporary):
                if (
                    candidate is not None
                    and candidate.exists()
                    and (
                        not candidate.is_file()
                        or candidate.stat().st_size != record["size"]
                        or hashlib.sha256(candidate.read_bytes()).hexdigest() != record["sha256"]
                    )
                ):
                    return None
            existing = next((f for f in data["frames"] if f["id"] == frame["id"]), None)
            if existing is not None and existing != frame:
                return None
            manifest_temp = None
            if "manifest_temporary" in record:
                name = record["manifest_temporary"]
                if not isinstance(name, str) or not re.fullmatch(
                    r"\.event\.json\.[0-9a-f]{32}\.tmp", name
                ):
                    return None
                manifest_temp = path.parent / name
                self._safe(manifest_temp)
                if not (
                    type(record.get("manifest_size")) is int
                    and record["manifest_size"] >= 0
                    and isinstance(record.get("manifest_sha256"), str)
                    and re.fullmatch(r"[0-9a-f]{64}", record["manifest_sha256"])
                ):
                    return None
                pending = dict(data, frames=[*data["frames"]])
                if existing is None and (
                    image.exists() or (temporary is not None and temporary.exists())
                ):
                    pending["frames"].append(frame)
                pending.update(status="incomplete", complete=False, reason="interrupted")
                expected = json.dumps(pending, sort_keys=True).encode()
                if manifest_temp.exists():
                    if not manifest_temp.is_file():
                        return None
                    payload = manifest_temp.read_bytes()
                    if not (
                        (
                            len(payload) == record["manifest_size"]
                            and hashlib.sha256(payload).hexdigest() == record["manifest_sha256"]
                        )
                        or payload == expected
                    ):
                        return None
                    manifest_temp.unlink()
                    self._used -= len(payload)
                    self._sync_directory(path.parent)
            self._manifest_temporary = manifest_temp
            if temporary is not None and temporary.exists():
                if image.exists():
                    size = temporary.stat().st_size
                    temporary.unlink()
                    self._used -= size
                else:
                    os.replace(temporary, image)
                self._sync_directory(image.parent)
            if image.exists():
                if existing is None:
                    data["frames"].append(frame)
            return intent
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def _remove_intent(self, intent):
        self._safe(intent)
        size = intent.stat().st_size
        intent.unlink()
        self._used -= size
        self._sync_directory(intent.parent)

    @staticmethod
    def _sync_directory(path):
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _safe(path):
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise StorageError("Symlink paths are not allowed")

    def _scan(self):
        result = []
        self._safe(self.root)
        for day in self.root.iterdir():
            if (
                day.is_symlink()
                or not day.is_dir()
                or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day.name)
            ):
                continue
            for folder in day.iterdir():
                if folder.is_symlink() or not folder.is_dir():
                    continue
                path = folder / "event.json"
                try:
                    self._safe(path)
                    data = json.loads(path.read_text())
                    if (
                        isinstance(data, dict)
                        and data.get("schema_version") == 1
                        and data.get("event_id") == folder.name
                        and data.get("status") in ("active", "complete", "incomplete")
                        and isinstance(data.get("frames"), list)
                        and all(
                            isinstance(f, dict)
                            and type(f.get("id")) is int
                            and isinstance(f.get("path"), str)
                            and f["path"] == f"originals/{f['id']}.jpg"
                            for f in data["frames"]
                        )
                        and isinstance(data.get("started_utc"), str)
                    ):
                        result.append((path, data))
                except (OSError, ValueError, TypeError):
                    continue
        return result

    def _usage(self):
        total = 0
        for base, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = [d for d in dirs if not (Path(base) / d).is_symlink()]
            for name in files:
                path = Path(base) / name
                if not path.is_symlink():
                    total += path.stat().st_size
        return total

    def _delete_managed(self, path, data):
        folder = path.parent
        allowed = {"event.json", "originals"}
        if any(item.is_symlink() or item.name not in allowed for item in folder.iterdir()):
            return False
        originals = folder / "originals"
        known = {str(f.get("path")) for f in data["frames"]}
        if originals.exists():
            for child in originals.iterdir():
                if (
                    child.is_symlink()
                    or not child.is_file()
                    or str(child.relative_to(folder)) not in known
                ):
                    return False
            for child in originals.iterdir():
                child.unlink()
            originals.rmdir()
        path.unlink()
        folder.rmdir()
        return True

    def _prune(self, additional, enforce=True, quota_credit=0):
        now = datetime.now(timezone.utc)
        for path, data in sorted(self._scan(), key=lambda pair: pair[1]["started_utc"]):
            try:
                timestamp = datetime.fromisoformat(data["started_utc"].replace("Z", "+00:00"))
                expired = (now - timestamp).total_seconds() > self.config.retention_days * 86400
            except (ValueError, TypeError):
                expired = False
            over = (
                self._usage() + additional > self.config.max_bytes + quota_credit
                or shutil.disk_usage(self.root).free - additional < self.config.min_free_bytes
            )
            if not expired and not over:
                continue
            if (
                data.get("pinned")
                or data["status"] == "active"
                or data["event_id"] in self._active
                or data["event_id"] in self._recovered
                or path.parent == getattr(self, "_writing", None)
            ):
                continue
            self._delete_managed(path, data)
        self._used = self._usage()
        self._storage_full = (
            self._used + additional > self.config.max_bytes + quota_credit
            or shutil.disk_usage(self.root).free - additional < self.config.min_free_bytes
        )
        if enforce and self._storage_full:
            raise StorageError("storage_full")

    def _atomic(self, path, payload):
        self._safe(path)
        self._writing = path.parent
        prior_size = path.stat().st_size if path.exists() else 0
        additional = max(0, len(payload) - prior_size)
        credit = (
            self._recovery_credit[1]
            if self._recovery_credit is not None and self._recovery_credit[0] == path
            else 0
        )
        if (
            self._used + additional > self.config.max_bytes + credit
            or shutil.disk_usage(self.root).free - len(payload) < self.config.min_free_bytes
        ):
            self._prune(additional, quota_credit=credit)
            if shutil.disk_usage(self.root).free - len(payload) < self.config.min_free_bytes:
                self._storage_full = True
                raise StorageError("storage_full")
        temp = (
            self._frame_temporary
            if path.suffix == ".jpg" and self._frame_temporary is not None
            else self._manifest_temporary
            if path.name == "event.json" and self._manifest_temporary is not None
            else path.with_name("." + path.name + "." + uuid4().hex + ".tmp")
        )
        self._safe(temp)
        created = False
        try:
            with temp.open("xb") as stream:
                created = True
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
            self._used += len(payload) - prior_size
            self._sync_directory(path.parent)
        finally:
            if created:
                temp.unlink(missing_ok=True)
            self._writing = None

    def _json(self, path, data):
        self._atomic(path, json.dumps(data, sort_keys=True).encode())

    def apply(self, action: EventAction) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", action.event_id):
            raise StorageError("Invalid event ID")
        if action.kind not in ("start", "frame", "end"):
            raise StorageError("Unknown action kind")
        if action.kind in ("start", "frame") and (
            action.frame is None or type(action.frame.id) is not int or action.frame.id < 0
        ):
            raise StorageError("Frame with a nonnegative integer identity required")
        if action.kind == "start":
            if any(data["event_id"] == action.event_id for _, data in self._scan()):
                raise StorageError("Duplicate event ID")
            day = datetime.fromisoformat(action.frame.utc.replace("Z", "+00:00")).date().isoformat()
            folder = self.root / day / action.event_id
            self._safe(folder)
            if folder.exists():
                raise StorageError("Duplicate event ID")
            self._prune(1024)
            folder.mkdir(parents=True, exist_ok=False)
            (folder / "originals").mkdir()
            data = dict(
                schema_version=1,
                event_id=action.event_id,
                started_utc=action.frame.utc,
                regions=list(action.regions),
                reason=action.reason,
                frames=[],
                pinned=False,
                status="active",
                complete=False,
                analysis_status="not_configured",
                camera_settings=dict(self.camera_settings),
            )
            path = folder / "event.json"
            self._json(path, data)
            self._active[action.event_id] = (path, data)
            return
        try:
            path, data = self._active[action.event_id]
        except KeyError:
            raise StorageError("Event is not active; its start may have failed") from None
        data["regions"] = list(dict.fromkeys((*data["regions"], *action.regions)))
        if action.kind == "frame":
            frame = action.frame
            if any(f["id"] == frame.id for f in data["frames"]):
                return
            relative = f"originals/{frame.id}.jpg"
            intent = path.parent / ".frame-intent.json"
            self._safe(intent)
            self._safe(path.parent / relative)
            if intent.exists() or (path.parent / relative).exists():
                raise StorageError("Pending frame or unrecognized frame file")
            metadata = dict(id=frame.id, utc=frame.utc, monotonic=frame.monotonic, path=relative)
            temporary = f"originals/.{frame.id}.jpg.{uuid4().hex}.tmp"
            record = dict(
                temporary=temporary,
                schema_version=1,
                event_id=action.event_id,
                frame=metadata,
                size=len(frame.jpeg),
                sha256=hashlib.sha256(frame.jpeg).hexdigest(),
            )
            pending = dict(data, frames=[*data["frames"], metadata])
            manifest_size = len(json.dumps(pending, sort_keys=True).encode())
            record.update(
                manifest_temporary=f".event.json.{uuid4().hex}.tmp",
                manifest_size=manifest_size,
                manifest_sha256=hashlib.sha256(
                    json.dumps(pending, sort_keys=True).encode()
                ).hexdigest(),
            )
            journal_size = len(json.dumps(record, sort_keys=True).encode())
            additional = (
                journal_size + len(frame.jpeg) + max(0, manifest_size - path.stat().st_size)
            )
            peak = journal_size + len(frame.jpeg) + manifest_size
            self._writing = path.parent
            try:
                if (
                    self._used + additional > self.config.max_bytes
                    or shutil.disk_usage(self.root).free - peak < self.config.min_free_bytes
                ):
                    self._prune(additional)
                # Unlike logical quota, reserve must cover the whole replacement
                # manifest while the previous manifest and journal still exist.
                if shutil.disk_usage(self.root).free - peak < self.config.min_free_bytes:
                    self._storage_full = True
                    raise StorageError("storage_full")
            finally:
                self._writing = None
            self._json(intent, record)
            self._frame_temporary = path.parent / temporary
            try:
                self._atomic(path.parent / relative, frame.jpeg)
            finally:
                self._frame_temporary = None
            data["frames"].append(metadata)
        elif action.kind == "end":
            incomplete = action.reason in (
                "writer_overload",
                "camera_lost",
                "interrupted",
                "storage_error",
            )
            data.update(
                status="incomplete" if incomplete else "complete",
                complete=not incomplete,
                incomplete=incomplete,
                end_reason=action.reason,
            )
        else:
            raise StorageError("Unknown action kind")
        if action.kind == "frame":
            self._manifest_temporary = path.parent / record["manifest_temporary"]
        try:
            self._json(path, data)
        finally:
            self._manifest_temporary = None
        if action.kind == "frame":
            self._remove_intent(intent)
        if action.kind == "end":
            self._active.pop(action.event_id)

    def events(self, limit: int = 20) -> list[dict]:
        records = (self._recovered.get(data["event_id"], data) for _, data in self._scan())
        return sorted(records, key=lambda d: (d["started_utc"], d["event_id"]), reverse=True)[
            : max(0, limit)
        ]

    def close(self) -> None:
        for path, data in self._active.values():
            data.update(status="incomplete", complete=False, reason="interrupted")
            self._json(path, data)
        self._active.clear()

    def health(self) -> dict:
        return {"storage_full": self._storage_full, "active_events": len(self._active)}
