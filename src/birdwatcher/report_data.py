"""Bounded read-only metadata normalization. Never reads images or infers absence."""

import hashlib
import json
import math
import os
import re
import stat
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_ROWS = 100_000
IDENTITY_FIELDS = (
    "event_key",
    "event_id",
    "frame_id",
    "source_path",
    "utc",
    "local",
    "input_status",
)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _path(value):
    _require(isinstance(value, (str, os.PathLike)), "Invalid path")
    text = os.fspath(value)
    _require(".." not in text.split("/") and "\x00" not in text, "Unsafe path")
    path = Path(text).absolute()
    for part in (*reversed(path.parents), path):
        _require(not part.is_symlink(), "Symlink path")
    return path


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def _finite(value):
    if isinstance(value, float):
        _require(math.isfinite(value), "Nonfinite number")
    elif isinstance(value, dict):
        for item in value.values():
            _finite(item)
    elif isinstance(value, list):
        _require(len(value) <= MAX_ROWS, "Too many rows")
        for item in value:
            _finite(item)


def _read(path):
    path = _path(path)
    parent_fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            next_fd = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd
            )
            os.close(parent_fd)
            parent_fd = next_fd
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
    finally:
        os.close(parent_fd)
    try:
        info = os.fstat(fd)
        _require(
            stat.S_ISREG(info.st_mode) and info.st_size <= MAX_JSON_BYTES,
            "Invalid metadata file size/type",
        )
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(MAX_JSON_BYTES + 1)
        _require(len(raw) <= MAX_JSON_BYTES, "Metadata too large")
    finally:
        os.close(fd)
    try:
        value = json.loads(raw, object_pairs_hook=_pairs)
        _finite(value)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid JSON") from exc
    return raw, value


def _aware(value):
    _require(isinstance(value, str), "Timestamp must be text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require(parsed.utcoffset() is not None, "Timestamp needs offset")
    return parsed


def _row(row, root, day, zone):
    _require(isinstance(row, dict), "Invalid frame row")
    key = row.get("event_key")
    _require(isinstance(key, str), "Invalid event key")
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})/([A-Za-z0-9][A-Za-z0-9_.-]{0,159})/event\.json", key)
    _require(match is not None, "Invalid event key")
    date.fromisoformat(match[1])
    _require(row.get("event_id") == match[2], "Event ID mismatch")
    number = row.get("frame_id")
    _require(type(number) is int and number >= 0, "Invalid frame ID")
    expected = root / match[1] / match[2] / "originals" / f"{number}.jpg"
    _require(row.get("source_path") == str(expected), "Source path mismatch")
    _path(expected)  # Missing historical originals are permitted; symlinks are not.
    utc = _aware(row.get("utc"))
    _require(utc.utcoffset() == timedelta(0), "UTC field must have zero offset")
    local = _aware(row.get("local"))
    expected_local = utc.astimezone(zone)
    _require(
        local == utc
        and local.utcoffset() == expected_local.utcoffset()
        and local.replace(tzinfo=None) == expected_local.replace(tzinfo=None)
        and expected_local.date() == day,
        "Frame time/day mismatch",
    )
    _require(
        row.get("input_status") in ("retained", "missing_inputs", "invalid_inputs"),
        "Invalid input status",
    )
    return key, number


def _result(row):
    _require(
        "error" not in row
        or row["error"] is None
        or isinstance(row["error"], dict)
        and bool(row["error"]),
        "Invalid analysis error",
    )
    _require(row.get("status") in ("bird_candidate", "unknown"), "Invalid result status")
    detections = row.get("detections")
    _require(isinstance(detections, list), "Invalid detections")
    scores = []
    for detection in detections:
        _require(isinstance(detection, dict), "Invalid detection")
        score = detection.get("score")
        _require(type(score) in (int, float) and math.isfinite(score), "Invalid detection score")
        scores.append(float(score))
    score = row.get("score")
    _require(score is None or type(score) in (int, float), "Invalid score")
    _require(score == max(scores, default=None), "Inconsistent result score")
    digest = row.get("source_sha256")
    _require(
        digest is None or isinstance(digest, str) and re.fullmatch("[0-9a-f]{64}", digest),
        "Invalid hash",
    )
    if not row.get("error"):
        _require(
            row["status"] == ("bird_candidate" if detections else "unknown"),
            "Inconsistent result status",
        )
        _require(digest is not None, "Successful analysis needs hash")


def _confirm(packet, digest, receipt_path, frames, results):
    by_key = {(f["event_key"], f["frame_id"]): f for f in frames}
    shortlist = packet.get("shortlist")
    _require(isinstance(shortlist, list), "Invalid shortlist")
    indexed = {}
    used = set()
    for item in shortlist:
        _require(isinstance(item, dict), "Invalid shortlist item")
        index = item.get("index")
        _require(
            type(index) is int and index > 0 and index not in indexed, "Invalid shortlist index"
        )
        _require(
            isinstance(item.get("event_key"), str) and type(item.get("frame_id")) is int,
            "Invalid shortlist identity",
        )
        key = (item.get("event_key"), item.get("frame_id"))
        _require(key in results and key not in used, "Invalid shortlist frame")
        result = results[key]
        _require(
            not result.get("error")
            and all(
                item.get(k) == result.get(k)
                for k in (*IDENTITY_FIELDS, "source_sha256", "score", "detections", "status")
            ),
            "Shortlist provenance mismatch",
        )
        indexed[index] = item
        used.add(key)
        by_key[key].update(shortlisted=True, shortlist_index=index)
    if receipt_path is None:
        return ["No validated receipt; zero confirmed records does not mean no birds."]
    _, receipt = _read(receipt_path)
    _require(isinstance(receipt, dict), "Invalid receipt")
    _require(
        receipt.get("status") == "prepared"
        and receipt.get("packet_sha256") == digest
        and receipt.get("date_local") == packet["date_local"]
        and receipt.get("timezone") == packet["timezone"],
        "Receipt packet provenance mismatch",
    )
    choices = []
    for field in ("confirmed_indices", "best_indices"):
        values = receipt.get(field)
        _require(
            isinstance(values, list) and all(type(v) is int for v in values),
            "Invalid receipt indices",
        )
        _require(
            len(set(values)) == len(values) and set(values) <= indexed.keys(),
            "Duplicate/unknown receipt index",
        )
        choices.append(set(values))
    confirmed, best = choices
    if "reviewed_indices" in receipt:
        reviewed = receipt["reviewed_indices"]
        _require(
            isinstance(reviewed, list) and all(type(v) is int for v in reviewed),
            "Invalid reviewed indices",
        )
        _require(
            len(set(reviewed)) == len(reviewed)
            and set(reviewed) <= indexed.keys()
            and confirmed <= set(reviewed),
            "Invalid reviewed subset",
        )
    _require(best <= confirmed, "Best must be confirmed")
    observations = receipt.get("observations")
    _require(
        isinstance(observations, list) and len(observations) == len(confirmed),
        "Receipt observations mismatch",
    )
    seen = set()
    for observation in observations:
        _require(isinstance(observation, dict), "Invalid observation")
        index = observation.get("index")
        _require(
            type(index) is int and index in confirmed and index not in seen,
            "Invalid observation index",
        )
        item = indexed[index]
        _require(
            all(
                observation.get(k) == item.get(k)
                for k in ("source_path", "source_sha256", "utc", "local", "event_id")
            ),
            "Receipt image provenance mismatch",
        )
        _require(
            observation.get("timezone", packet["timezone"]) == packet["timezone"],
            "Observation timezone mismatch",
        )
        # Optional identity fields, if present, must not contradict original provenance.
        if "frame_id" in observation:
            _require(type(observation["frame_id"]) is int, "Invalid observation frame ID")
        for field in ("event_key", "frame_id"):
            _require(
                field not in observation or observation[field] == item[field],
                "Observation identity mismatch",
            )
        frame = by_key[(item["event_key"], item["frame_id"])]
        frame.update(confirmed=True, keeper=index in best)
        durable = observation.get("durable_copy")
        if durable is not None:
            expected = _path(receipt_path).parent / f"best-{index}-{item['source_sha256']}.jpg"
            _require(
                index in best and durable == str(expected), "Invalid keeper archive provenance"
            )
            frame["durable_copy"] = str(_path(durable))
        seen.add(index)
    return [
        "Receipt is prepared, not proof of delivered messages.",
        "Apparent groups are a UTC-gap heuristic, not visits or distinct birds.",
    ]


def _groups(frames, gap):
    groups = []
    last = None
    for frame in frames:
        if not frame["confirmed"]:
            continue
        utc = _aware(frame["utc"])
        if last is None or (utc - last).total_seconds() > gap:
            groups.append(
                dict(
                    id=f"G{len(groups) + 1:04d}",
                    start_utc=frame["utc"],
                    end_utc=frame["utc"],
                    start_local=frame["local"],
                    end_local=frame["local"],
                    frame_ids=[],
                    confirmed_frames=0,
                )
            )
        group = groups[-1]
        group["end_utc"], group["end_local"] = frame["utc"], frame["local"]
        group["frame_ids"].append(frame["id"])
        group["confirmed_frames"] += 1
        last = utc
    return groups


def _coverage(packet, root, start, end, hours, warnings):
    note = (
        "Session launch/exit bounds include warm-up/shutdown, not verified continuous coverage; "
        "counters are snapshots, not reconciled day totals. Gaps describe session bounds only."
    )
    coverage = packet.get("recording_coverage")
    valid = isinstance(coverage, dict) and isinstance(coverage.get("sessions"), list)
    rows = coverage["sessions"] if valid else []
    complete = bool(valid and rows and not coverage.get("errors"))
    intervals = []
    for row in rows:
        try:
            _require(
                isinstance(row, dict)
                and row.get("data_root") == str(root)
                and row.get("matches_source_root") is True
                and row.get("date_local") == packet["date_local"],
                "Nonmatching session",
            )
            launch = _aware(row.get("launch_utc")).astimezone(timezone.utc)
            finish = _aware(row.get("finished_utc")).astimezone(timezone.utc)
            _require(launch < finish, "Incomplete session")
            left, right = max(start, launch), min(end, finish)
            if left < right:
                intervals.append((left, right))
        except (ValueError, TypeError):
            complete = False
    merged = []
    for left, right in sorted(intervals):
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))
        else:
            merged.append((left, right))
    complete = complete and bool(merged)
    sessions = [dict(start_utc=a.isoformat(), end_utc=b.isoformat()) for a, b in merged]
    gaps = []
    if complete:
        cursor = start
        for left, right in merged:
            if cursor < left:
                gaps.append(dict(start_utc=cursor.isoformat(), end_utc=left.isoformat()))
            cursor = right
        if cursor < end:
            gaps.append(dict(start_utc=cursor.isoformat(), end_utc=end.isoformat()))
        for hour in hours:
            left = _aware(hour["key"]).astimezone(timezone.utc)
            right = min(left + timedelta(hours=1), end)
            hour["session_seconds"] = float(
                sum(max(0, (min(b, right) - max(a, left)).total_seconds()) for a, b in merged)
            )
    else:
        warnings.append(
            "Coverage is missing, mismatched, or incomplete; session totals are unknown."
        )
    return dict(
        sessions=sessions,
        estimated_seconds=float(sum((b - a).total_seconds() for a, b in merged))
        if complete
        else None,
        gaps=gaps,
        note=note,
    )


def load_report(packet_path, *, source_root, receipt_path=None, visit_gap_seconds=60):
    """Return schema-1 normalized metadata; reject inconsistent or unsafe provenance."""
    _require(
        type(visit_gap_seconds) in (int, float)
        and math.isfinite(visit_gap_seconds)
        and 1 <= visit_gap_seconds <= 3600,
        "Visit gap must be numeric within 1..3600 seconds",
    )
    root = _path(source_root)
    _require(root.is_dir(), "Source root must exist")
    packet_path = _path(packet_path)
    raw, packet = _read(packet_path)
    _require(
        isinstance(packet, dict)
        and type(packet.get("schema_version")) is int
        and packet["schema_version"] == 1,
        "Invalid packet schema",
    )
    _require(packet.get("source_root") == str(root), "Source root mismatch")
    _require(
        isinstance(packet.get("date_local"), str) and isinstance(packet.get("timezone"), str),
        "Packet needs date and timezone",
    )
    day = date.fromisoformat(packet["date_local"])
    _require(day.isoformat() == packet["date_local"], "Invalid day")
    try:
        zone = ZoneInfo(packet["timezone"])
    except KeyError as exc:
        raise ValueError("Unknown timezone") from exc
    start = datetime.combine(day, time(), zone).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time(), zone).astimezone(timezone.utc)
    tables = []
    for field in ("inventory_path", "results_path"):
        path = _path(packet[field])
        _require(
            path.parent == packet_path.parent and path.name == field.replace("_path", ".json"),
            "Metadata must be selected inventory/results file in packet directory",
        )
        _, rows = _read(path)
        _require(isinstance(rows, list) and len(rows) <= MAX_ROWS, "Invalid metadata rows")
        indexed = {}
        for row in rows:
            key = _row(row, root, day, zone)
            _require(key not in indexed, "Duplicate frame")
            indexed[key] = row
        tables.append(indexed)
    inventory, results = tables
    for key, result in results.items():
        _require(key in inventory, "Orphan result")
        _require(
            all(result.get(k) == inventory[key].get(k) for k in IDENTITY_FIELDS),
            "Result provenance mismatch",
        )
        _result(result)
    hours = []
    cursor = start
    while cursor < end:
        local = cursor.astimezone(zone)
        hours.append(
            dict(
                key=local.isoformat(),
                label=local.strftime("%H:00 %z"),
                inventory_frames=0,
                analyzed_frames=0,
                candidate_frames=0,
                confirmed_frames=0,
                session_seconds=None,
            )
        )
        cursor += timedelta(hours=1)
    frames = []
    for row in sorted(
        inventory.values(), key=lambda r: (_aware(r["utc"]), r["event_key"], r["frame_id"])
    ):
        result = results.get((row["event_key"], row["frame_id"]))
        status = (
            "not_analyzed"
            if result is None
            else "analysis_failed"
            if result.get("error")
            else "bird_candidate"
            if result["detections"]
            else "unknown"
        )
        utc = _aware(row["utc"]).astimezone(timezone.utc)
        frames.append(
            dict(
                id=f"F{len(frames) + 1:06d}",
                utc=utc.isoformat(),
                local=utc.astimezone(zone).isoformat(),
                event_key=row["event_key"],
                event_id=row["event_id"],
                frame_id=row["frame_id"],
                source_path=row["source_path"],
                source_sha256=result.get("source_sha256") if result else None,
                analysis_status=status,
                score=float(result["score"]) if result and result["score"] is not None else None,
                detection_count=len(result["detections"]) if result else 0,
                shortlisted=False,
                shortlist_index=None,
                confirmed=False,
                keeper=False,
            )
        )
    digest = hashlib.sha256(raw).hexdigest()
    warnings = _confirm(packet, digest, receipt_path, frames, results)
    groups = _groups(frames, visit_gap_seconds)
    summary = dict(
        inventory_frames=len(frames),
        analyzed_frames=0,
        candidate_frames=0,
        confirmed_frames=0,
        apparent_groups=len(groups),
        first_confirmed_local=None,
        last_confirmed_local=None,
        analysis_errors=0,
    )
    for frame in frames:
        utc = _aware(frame["utc"])
        hour = hours[int((utc - start).total_seconds() // 3600)]
        hour["inventory_frames"] += 1
        for key, condition in [
            ("analyzed_frames", frame["analysis_status"] in ("unknown", "bird_candidate")),
            ("candidate_frames", frame["analysis_status"] == "bird_candidate"),
            ("confirmed_frames", frame["confirmed"]),
        ]:
            summary[key] += int(condition)
            hour[key] += int(condition)
        summary["analysis_errors"] += frame["analysis_status"] == "analysis_failed"
    confirmed_frames = [f for f in frames if f["confirmed"]]
    if confirmed_frames:
        summary["first_confirmed_local"] = confirmed_frames[0]["local"]
        summary["last_confirmed_local"] = confirmed_frames[-1]["local"]
    return dict(
        schema_version=1,
        date_local=day.isoformat(),
        timezone=str(zone),
        packet_sha256=digest,
        source_root=str(root),
        frames=frames,
        hours=hours,
        groups=groups,
        warnings=warnings,
        coverage=_coverage(packet, root, start, end, hours, warnings),
        summary=summary,
    )
