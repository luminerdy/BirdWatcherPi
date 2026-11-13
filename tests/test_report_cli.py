"""Report CLI tests use synthetic paths and never open a camera."""

import json
import sys
import types

import pytest

from birdwatcher import cli


def test_report_cli_dispatches_without_camera(tmp_path, monkeypatch, capsys):
    calls = []

    def build_report(packet_path, output_dir, **kwargs):
        calls.append((packet_path, output_dir, kwargs))
        return {"date_local": "2030-01-01", "index_path": str(output_dir / "index.html")}

    monkeypatch.setitem(
        sys.modules, "birdwatcher.report_export", types.SimpleNamespace(build_report=build_report)
    )

    def no_camera(*args, **kwargs):
        pytest.fail("Report command must not acquire a camera")

    monkeypatch.setattr("birdwatcher.camera.Camera", no_camera)
    packet = tmp_path / "packet.json"
    output = tmp_path / "private-report"
    source = tmp_path / "raw"
    receipt = tmp_path / "reviewed.json"
    comparison = tmp_path / "previous-packet.json"
    assert (
        cli.main(
            [
                "report",
                "--packet",
                str(packet),
                "--output-dir",
                str(output),
                "--source-root",
                str(source),
                "--receipt",
                str(receipt),
                "--compare-with",
                str(comparison),
                "--visit-gap-seconds",
                "90",
                "--no-portable",
            ]
        )
        == 0
    )
    assert calls == [
        (
            packet,
            output,
            {
                "source_root": source,
                "receipt_path": receipt,
                "comparison_packets": (comparison,),
                "visit_gap_seconds": 90,
                "portable": False,
            },
        )
    ]
    assert json.loads(capsys.readouterr().out)["date_local"] == "2030-01-01"
    assert not source.exists()
    assert not output.exists()


@pytest.mark.parametrize("gap", ["0", "-1", "3601"])
def test_report_cli_rejects_invalid_group_gap_before_export(tmp_path, monkeypatch, gap):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid arguments must fail before export")

    monkeypatch.setitem(
        sys.modules, "birdwatcher.report_export", types.SimpleNamespace(build_report=forbidden)
    )
    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "report",
                "--packet",
                str(tmp_path / "packet.json"),
                "--output-dir",
                str(tmp_path / "out"),
                "--visit-gap-seconds",
                gap,
            ]
        )
    assert error.value.code == 2
    assert not (tmp_path / "out").exists()
