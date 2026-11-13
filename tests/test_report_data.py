"""Synthetic metadata only: these fixtures are not real bird observations."""

import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from birdwatcher import report_data


def fixture_packet(tmp_path, *, day="2026-11-10", zone="America/Chicago", times=()):
    root = tmp_path / "synthetic-source"
    root.mkdir()
    folder = tmp_path / "metadata"
    folder.mkdir()
    inventory = []
    for i, utc in enumerate(times):
        local = datetime.fromisoformat(utc).astimezone(ZoneInfo(zone)).isoformat()
        inventory.append(
            dict(
                event_key=f"{day}/synthetic-event/event.json",
                event_id="synthetic-event",
                frame_id=i,
                source_path=str(root / day / "synthetic-event" / "originals" / f"{i}.jpg"),
                utc=utc,
                local=local,
                input_status="retained",
            )
        )
    packet = dict(
        schema_version=1,
        date_local=day,
        timezone=zone,
        source_root=str(root),
        inventory_path=str(folder / "inventory.json"),
        results_path=str(folder / "results.json"),
        shortlist=[],
        recording_coverage=dict(sessions=[], errors=[]),
    )
    return root, folder / "packet.json", packet, inventory, []


def save(case):
    root, path, packet, inventory, results = case
    path.write_text(json.dumps(packet))
    (path.parent / "inventory.json").write_text(json.dumps(inventory))
    (path.parent / "results.json").write_text(json.dumps(results))
    return report_data.load_report(path, source_root=root)


def test_normalization_uses_all_inventory_not_shortlist(tmp_path):
    case = fixture_packet(
        tmp_path,
        times=(
            "2026-11-10T14:00:02+00:00",
            "2026-11-10T14:00:01+00:00",
            "2026-11-10T15:00:00+00:00",
            "2026-11-10T16:00:00+00:00",
        ),
    )
    case[4].extend(
        [
            dict(
                case[3][0],
                status="bird_candidate",
                detections=[dict(score=0.7)],
                score=0.7,
                source_sha256="a" * 64,
            ),
            dict(case[3][1], status="unknown", detections=[], score=None, source_sha256="b" * 64),
            dict(
                case[3][2],
                status="unknown",
                detections=[],
                score=None,
                source_sha256=None,
                error=dict(code="synthetic_failure"),
            ),
        ]
    )
    view = save(case)
    assert [f["analysis_status"] for f in view["frames"]] == [
        "unknown",
        "bird_candidate",
        "analysis_failed",
        "not_analyzed",
    ]
    assert [f["id"] for f in view["frames"]] == ["F000001", "F000002", "F000003", "F000004"]
    assert view["summary"]["inventory_frames"] == 4
    assert view["summary"]["analyzed_frames"] == 2
    assert view["summary"]["candidate_frames"] == 1
    assert view["summary"]["analysis_errors"] == 1
    assert view["hours"][8]["analyzed_frames"] == 2
    assert view["frames"][1]["source_sha256"] == "a" * 64
    assert not any(f["confirmed"] for f in view["frames"])


@pytest.mark.parametrize(
    "corruption",
    [
        "root",
        "schema",
        "event_key",
        "event_id",
        "frame_bool",
        "path",
        "naive",
        "local_offset",
        "wrong_day",
        "duplicate_inventory",
        "duplicate_result",
        "orphan_result",
        "result_source",
        "result_time",
        "nan",
        "infinite_box",
        "hash",
        "status",
        "box_status",
        "score",
        "metadata_escape",
        "metadata_symlink",
        "source_symlink",
        "duplicate_json",
        "oversize",
        "rows",
    ],
)
def test_rejects_unsafe_or_ambiguous_metadata(tmp_path, corruption, monkeypatch):
    case = fixture_packet(tmp_path, times=("2026-11-10T14:00:00+00:00",))
    root, path, packet, inventory, results = case
    results.append(
        dict(
            inventory[0],
            status="bird_candidate",
            detections=[dict(score=0.7)],
            score=0.7,
            source_sha256="a" * 64,
        )
    )
    row = inventory[0]
    if corruption == "root":
        packet["source_root"] = str(tmp_path)
    if corruption == "schema":
        packet["schema_version"] = True
    if corruption == "event_key":
        row["event_key"] = "../escape/event.json"
    if corruption == "event_id":
        row["event_id"] = "other"
    if corruption == "frame_bool":
        row["frame_id"] = True
    if corruption == "path":
        row["source_path"] += "/../0.jpg"
    if corruption == "naive":
        row["utc"] = "2026-11-10T14:00:00"
    if corruption == "local_offset":
        row["local"] = "2026-11-10T14:00:00+00:00"
    if corruption == "wrong_day":
        row["utc"] = "2026-11-11T14:00:00+00:00"
    if corruption == "duplicate_inventory":
        inventory.append(dict(row))
    if corruption == "duplicate_result":
        results.append(dict(results[0]))
    if corruption == "orphan_result":
        results[0]["frame_id"] = 99
        results[0]["source_path"] = str(
            root / packet["date_local"] / "synthetic-event" / "originals" / "99.jpg"
        )
    if corruption == "result_source":
        results[0]["source_path"] += "x"
    if corruption == "result_time":
        results[0]["utc"] = "2026-11-10T14:00:01+00:00"
    if corruption == "nan":
        results[0]["score"] = float("nan")
    if corruption == "infinite_box":
        results[0]["detections"][0]["bbox"] = [0, 0, float("inf"), 1]
    if corruption == "hash":
        results[0]["source_sha256"] = "not-a-digest"
    if corruption == "status":
        results[0]["status"] = "confirmed"
    if corruption == "box_status":
        results[0]["status"] = "unknown"
    if corruption == "score":
        results[0]["score"] = 0.1
    if corruption == "metadata_escape":
        packet["inventory_path"] = str(path.parent / ".." / "inventory.json")
    if corruption == "metadata_symlink":
        (path.parent / "alias.json").symlink_to(path.parent / "inventory.json")
        packet["inventory_path"] = str(path.parent / "alias.json")
    if corruption == "source_symlink":
        (root / packet["date_local"]).symlink_to(tmp_path, target_is_directory=True)
    if corruption == "oversize":
        monkeypatch.setattr(report_data, "MAX_JSON_BYTES", 10, raising=False)
    if corruption == "rows":
        monkeypatch.setattr(report_data, "MAX_ROWS", 0, raising=False)
    if corruption == "duplicate_json":
        save(case)
        path.write_text('{"schema_version":1,' + path.read_text()[1:])
        with pytest.raises(ValueError):
            report_data.load_report(path, source_root=root)
    else:
        message = "Orphan result" if corruption == "orphan_result" else None
        with pytest.raises(ValueError, match=message):
            save(case)


def reviewed_case(tmp_path, *, day="2026-11-10", times=("2026-11-10T14:00:00+00:00",)):
    case = fixture_packet(tmp_path, day=day, times=times)
    for i, row in enumerate(case[3]):
        result = dict(row, status="unknown", detections=[], score=None, source_sha256="a" * 64)
        case[4].append(result)
        case[2]["shortlist"].append(dict(result, index=i + 1, kind="control"))
    save(case)
    receipt = dict(
        status="prepared",
        date_local=day,
        timezone=case[2]["timezone"],
        packet_sha256=hashlib.sha256(case[1].read_bytes()).hexdigest(),
        confirmed_indices=list(range(1, len(times) + 1)),
        best_indices=[1],
        observations=[
            dict(row, index=i + 1, timezone=case[2]["timezone"])
            for i, row in enumerate(case[2]["shortlist"])
        ],
    )
    return case, receipt


def read_receipt(case, receipt, **kwargs):
    path = case[1].parent / "receipt.json"
    path.write_text(json.dumps(receipt))
    return report_data.load_report(case[1], source_root=case[0], receipt_path=path, **kwargs)


def test_receipt_confirms_even_no_box_control_and_groups_utc_observations(tmp_path):
    case, receipt = reviewed_case(
        tmp_path,
        times=(
            "2026-11-10T14:00:00+00:00",
            "2026-11-10T14:01:00+00:00",
            "2026-11-10T14:02:01+00:00",
        ),
    )
    view = read_receipt(case, receipt)
    assert view["summary"]["confirmed_frames"] == 3
    assert view["summary"]["candidate_frames"] == 0
    assert view["summary"]["apparent_groups"] == 2
    assert view["summary"]["first_confirmed_local"] == "2026-11-10T08:00:00-06:00"
    assert view["summary"]["last_confirmed_local"] == "2026-11-10T08:02:01-06:00"
    assert [f["shortlist_index"] for f in view["frames"]] == [1, 2, 3]
    assert [f["keeper"] for f in view["frames"]] == [True, False, False]
    assert view["hours"][8]["confirmed_frames"] == 3
    assert view["groups"][0]["frame_ids"] == ["F000001", "F000002"]
    assert any("delivered" in w for w in view["warnings"])


@pytest.mark.parametrize(
    "field",
    [
        "packet_sha256",
        "status",
        "date_local",
        "timezone",
        "source_path",
        "source_sha256",
        "utc",
        "local",
        "event_id",
        "index",
        "duplicate",
        "missing",
        "best",
        "confirmed_bool",
    ],
)
def test_receipt_provenance_must_match_original_shortlist(tmp_path, field):
    case, receipt = reviewed_case(tmp_path)
    if field in ("packet_sha256", "status", "date_local", "timezone"):
        receipt[field] = "invalid"
    elif field == "duplicate":
        receipt["observations"].append(dict(receipt["observations"][0]))
    elif field == "missing":
        receipt["observations"] = []
    elif field == "best":
        receipt["best_indices"] = [2]
    elif field == "confirmed_bool":
        receipt["confirmed_indices"] = [True]
    else:
        receipt["observations"][0][field] = "invalid"
    with pytest.raises(ValueError):
        read_receipt(case, receipt)


@pytest.mark.parametrize("change", ["hash", "source", "time", "duplicate", "unknown", "index"])
def test_shortlist_is_a_validated_result_subset(tmp_path, change):
    case, _ = reviewed_case(tmp_path)
    row = case[2]["shortlist"][0]
    if change == "hash":
        row["source_sha256"] = "b" * 64
    if change == "source":
        row["source_path"] += "x"
    if change == "time":
        row["utc"] = "2026-11-10T14:00:01+00:00"
    if change == "duplicate":
        case[2]["shortlist"].append(dict(row))
    if change == "unknown":
        row["frame_id"] = 99
    if change == "index":
        row["index"] = True
    with pytest.raises(ValueError):
        save(case)


@pytest.mark.parametrize("gap", [True, 0, -1, 3601, float("nan"), float("inf"), "60"])
def test_visit_gap_is_finite_numeric_one_to_3600(tmp_path, gap):
    case = fixture_packet(tmp_path)
    save(case)
    with pytest.raises(ValueError):
        report_data.load_report(case[1], source_root=case[0], visit_gap_seconds=gap)


def test_validated_keeper_archive_path_is_internal_metadata_only(tmp_path):
    case, receipt = reviewed_case(tmp_path)
    archive = case[1].parent / ("best-1-" + "a" * 64 + ".jpg")
    receipt["observations"][0]["durable_copy"] = str(archive)
    view = read_receipt(case, receipt)
    assert view["frames"][0]["durable_copy"] == str(archive)
    assert not archive.exists()  # Normalization never reads or requires images.
    receipt["observations"][0]["durable_copy"] = str(case[1].parent / "elsewhere.jpg")
    with pytest.raises(ValueError):
        read_receipt(case, receipt)
    receipt["observations"][0]["durable_copy"] = str(archive)
    archive.symlink_to(case[1])
    with pytest.raises(ValueError):
        read_receipt(case, receipt)


def session(case, start, end, **updates):
    return dict(
        launch_utc=start,
        finished_utc=end,
        data_root=str(case[0]),
        matches_source_root=True,
        date_local=case[2]["date_local"],
        **updates,
    )


def test_session_union_is_clipped_and_hourly_not_continuous_coverage(tmp_path):
    case = fixture_packet(tmp_path)
    case[2]["recording_coverage"]["sessions"] = [
        session(case, "2026-11-10T05:00:00+00:00", "2026-11-10T07:30:00+00:00"),
        session(case, "2026-11-10T07:00:00+00:00", "2026-11-10T08:00:00+00:00"),
        session(case, "2026-11-11T05:30:00+00:00", "2026-11-11T07:00:00+00:00"),
    ]
    view = save(case)
    assert view["coverage"]["estimated_seconds"] == 9000.0
    assert view["coverage"]["sessions"] == [
        dict(start_utc="2026-11-10T06:00:00+00:00", end_utc="2026-11-10T08:00:00+00:00"),
        dict(start_utc="2026-11-11T05:30:00+00:00", end_utc="2026-11-11T06:00:00+00:00"),
    ]
    assert view["hours"][0]["session_seconds"] == 3600.0
    assert view["hours"][1]["session_seconds"] == 3600.0
    assert view["hours"][2]["session_seconds"] == 0.0
    assert view["hours"][-1]["session_seconds"] == 1800.0
    assert view["coverage"]["gaps"] == [
        dict(start_utc="2026-11-10T08:00:00+00:00", end_utc="2026-11-11T05:30:00+00:00")
    ]
    assert "continuous" in view["coverage"]["note"]
    assert "warm" in view["coverage"]["note"]


@pytest.mark.parametrize(
    "problem",
    [
        "missing",
        "wrong_root",
        "false_match",
        "unfinished",
        "reverse",
        "malformed",
        "errors",
        "wrong_day",
    ],
)
def test_incomplete_coverage_never_claims_monitored_day(tmp_path, problem):
    case = fixture_packet(tmp_path)
    row = session(case, "2026-11-10T06:00:00+00:00", "2026-11-11T06:00:00+00:00")
    case[2]["recording_coverage"]["sessions"] = [row]
    if problem == "missing":
        case[2].pop("recording_coverage")
    if problem == "wrong_root":
        row["data_root"] = str(tmp_path)
    if problem == "false_match":
        row["matches_source_root"] = False
    if problem == "unfinished":
        row["finished_utc"] = None
    if problem == "reverse":
        row["finished_utc"] = "2026-11-09T06:00:00+00:00"
    if problem == "malformed":
        row["launch_utc"] = "not-a-time"
    if problem == "errors":
        case[2]["recording_coverage"]["errors"] = [dict(detail="synthetic")]
    if problem == "wrong_day":
        row["date_local"] = "2026-11-09"
    view = save(case)
    assert view["coverage"]["estimated_seconds"] is None
    assert all(hour["session_seconds"] is None for hour in view["hours"])
    assert any("coverage" in warning.lower() for warning in view["warnings"])


@pytest.mark.parametrize("day,count", [("2026-03-08", 23), ("2026-11-01", 25)])
def test_dst_days_have_real_hours_and_session_totals(tmp_path, day, count):
    case = fixture_packet(tmp_path, day=day)
    zone = ZoneInfo("America/Chicago")
    from datetime import timedelta, timezone

    start = datetime.fromisoformat(day).replace(tzinfo=zone)
    end = start + timedelta(days=1)
    case[2]["recording_coverage"]["sessions"] = [
        session(
            case,
            start.astimezone(timezone.utc).isoformat(),
            end.astimezone(timezone.utc).isoformat(),
        )
    ]
    view = save(case)
    assert len(view["hours"]) == count
    assert len({h["key"] for h in view["hours"]}) == count
    assert view["coverage"]["estimated_seconds"] == count * 3600.0
    if count == 25:
        assert view["hours"][1]["key"].endswith("01:00:00-05:00")
        assert view["hours"][2]["key"].endswith("01:00:00-06:00")
    else:
        assert not any("T02:" in h["key"] for h in view["hours"])


def test_confirmed_groups_cross_dst_fold_in_utc_not_wall_clock(tmp_path):
    case, receipt = reviewed_case(
        tmp_path, day="2026-11-01", times=("2026-11-01T06:59:45+00:00", "2026-11-01T07:00:15+00:00")
    )
    view = read_receipt(case, receipt)
    assert view["summary"]["apparent_groups"] == 1
    assert view["hours"][1]["confirmed_frames"] == 1
    assert view["hours"][2]["confirmed_frames"] == 1
    assert read_receipt(case, receipt, visit_gap_seconds=29)["summary"]["apparent_groups"] == 2


@pytest.mark.parametrize(
    "problem",
    [
        "missing_day",
        "timezone",
        "day_type",
        "shortlist_type",
        "shortlist_bool_frame",
        "shortlist_bad_key",
        "error_type",
        "error_empty",
        "score_bool",
        "receipt_bool_frame",
        "reviewed_subset",
        "receipt_best_duplicate",
    ],
)
def test_malformed_metadata_fails_closed_with_value_error(tmp_path, problem):
    case, receipt = reviewed_case(tmp_path)
    packet = case[2]
    if problem == "missing_day":
        packet.pop("date_local")
    if problem == "timezone":
        packet["timezone"] = "Synthetic/NoSuchTimezone"
    if problem == "day_type":
        packet["date_local"] = None
    if problem == "shortlist_type":
        packet["shortlist"] = {}
    if problem == "shortlist_bool_frame":
        packet["shortlist"][0]["frame_id"] = False
    if problem == "shortlist_bad_key":
        packet["shortlist"][0]["event_key"] = []
    if problem == "error_type":
        case[4][0]["error"] = "invalid"
    if problem == "error_empty":
        case[4][0]["error"] = {}
    if problem == "score_bool":
        case[4][0]["score"] = False
    if problem == "receipt_bool_frame":
        receipt["observations"][0]["frame_id"] = False
    if problem == "reviewed_subset":
        receipt["reviewed_indices"] = []
    if problem == "receipt_best_duplicate":
        receipt["best_indices"] = [1, 1]
    with pytest.raises(ValueError):
        save(case)
        receipt["packet_sha256"] = hashlib.sha256(case[1].read_bytes()).hexdigest()
        read_receipt(case, receipt)


def test_metadata_parent_symlink_swap_is_rejected_at_open(tmp_path, monkeypatch):
    case = fixture_packet(tmp_path)
    save(case)
    checked = report_data._path
    swapped = False

    def swap_after_check(value):
        nonlocal swapped
        result = checked(value)
        if result.name == "inventory.json" and not swapped:
            swapped = True
            original = result.parent
            moved = original.with_name("synthetic-moved-metadata")
            original.rename(moved)
            original.symlink_to(moved, target_is_directory=True)
        return result

    monkeypatch.setattr(report_data, "_path", swap_after_check)
    with pytest.raises((ValueError, OSError)):
        report_data._read(case[1].parent / "inventory.json")
    assert swapped


def test_empty_packet_has_unknown_coverage_not_absence(tmp_path):
    case = fixture_packet(tmp_path)
    view = save(case)
    assert view["schema_version"] == 1
    assert view["frames"] == []
    assert len(view["hours"]) == 24
    assert view["coverage"]["estimated_seconds"] is None
    assert view["summary"] == dict(
        inventory_frames=0,
        analyzed_frames=0,
        candidate_frames=0,
        confirmed_frames=0,
        apparent_groups=0,
        first_confirmed_local=None,
        last_confirmed_local=None,
        analysis_errors=0,
    )
    assert view["packet_sha256"] == hashlib.sha256(case[1].read_bytes()).hexdigest()
    assert any("receipt" in warning.lower() for warning in view["warnings"])
