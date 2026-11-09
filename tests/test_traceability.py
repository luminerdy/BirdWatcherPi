"""Offline contract tests for the traceability CLI; no app imports or hardware."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_traceability.py"


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/SPECIFICATION.md").write_text(
        "# Specification\n\n## 2. Camera\n\n"
        '- <a id="bw-cam-001"></a> **BW-CAM-001** — Capture images.\n',
        encoding="utf-8",
    )
    (tmp_path / "camera.py").write_text("def capture():\n    pass\n", encoding="utf-8")
    (tmp_path / "test_camera.py").write_text(
        "def test_capture():\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "docs/evidence.md").write_text("# Pilot\n", encoding="utf-8")
    data = {
        "schema_version": 1,
        "spec_sha256": hashlib.sha256(
            (tmp_path / "docs/SPECIFICATION.md").read_bytes()
        ).hexdigest(),
        "specification": "docs/SPECIFICATION.md",
        "private_evidence": [],
        "requirements": [
            {
                "id": "BW-CAM-001",
                "spec_hash": hashlib.sha256(b"Capture images.").hexdigest(),
                "feature": "Capture",
                "scope": "public",
                "implementation_status": "implemented",
                "test_status": "verified",
                "field_status": "validated",
                "code": ["camera.py::capture"],
                "tests": ["test_camera.py::test_capture"],
                "evidence": ["docs/evidence.md#pilot"],
                "private_evidence": [],
                "issues": [],
                "gap": "",
            }
        ],
    }
    save(tmp_path, data)
    return tmp_path, data


def save(root, data):
    (root / "docs/traceability.json").write_text(json.dumps(data), encoding="utf-8")


def cli(root, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize("alias", ["symlink", "hardlink"])
def test_write_refuses_output_alias_without_modifying_source(repo, alias):
    root, _ = repo
    source = root / "camera.py"
    before = source.read_bytes()
    output = root / "docs/TRACEABILITY.md"
    if alias == "symlink":
        output.symlink_to(source)
    else:
        import os

        os.link(source, output)
    result = cli(root, "--write")
    assert result.returncode == 1
    assert "alias" in result.stderr
    assert source.read_bytes() == before


def test_write_publishes_by_replacing_report_inode(repo):
    root, _ = repo
    assert cli(root, "--write").returncode == 0
    output = root / "docs/TRACEABILITY.md"
    inode = output.stat().st_ino
    expected = output.read_bytes()
    assert cli(root, "--write").returncode == 0
    assert output.stat().st_ino != inode
    assert output.read_bytes() == expected
    assert not list(output.parent.glob(".traceability-*.tmp"))


def test_report_has_status_legend_summary_and_clickable_references(repo):
    root, _ = repo
    assert cli(root, "--write").returncode == 0
    report = (root / "docs/TRACEABILITY.md").read_text()
    assert "## Status legend" in report
    assert "## Mapping summary" in report
    assert "Requirements mapped: **1**" in report
    assert "implementation: implemented=1" in report
    assert "[`camera.py::capture`](../camera.py)" in report
    assert "[`test_camera.py::test_capture`](../test_camera.py)" in report
    assert "[docs/evidence.md#pilot](../docs/evidence.md#pilot)" in report


def test_cli_writes_deterministic_report_and_checks_it(repo):
    root, _ = repo
    result = cli(root, "--write")
    assert result.returncode == 0, result.stderr
    assert "mapping integrity" in result.stdout
    assert "private evidence not independently checked" in result.stdout
    report = (root / "docs/TRACEABILITY.md").read_text()
    assert "BW-CAM-001" in report
    assert "SPECIFICATION.md#bw-cam-001" in report
    assert "implementation: implemented=1" in result.stdout
    assert "test: verified=1" in result.stdout
    assert "field: validated=1" in result.stdout
    assert cli(root).returncode == 0
    assert cli(root, "--check").returncode == 0
    assert cli(root, "--write").returncode == 0
    assert (root / "docs/TRACEABILITY.md").read_text() == report


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope", "external"),
        ("implementation_status", "done"),
        ("test_status", "passed"),
        ("field_status", "done"),
        ("id", "BW-cam-001"),
        ("spec_hash", "bad"),
        ("feature", ""),
        ("gap", None),
        ("code", "camera.py"),
        ("tests", [3]),
        ("evidence", [None]),
        ("private_evidence", [True]),
        ("issues", [0]),
        ("issues", [-1]),
        ("issues", [True]),
        ("issues", ["7"]),
    ],
)
def test_rejects_malformed_row_without_writing(repo, field, value):
    root, data = repo
    data["requirements"][0][field] = value
    save(root, data)
    result = cli(root, "--write")
    assert result.returncode == 1
    assert field in result.stderr
    assert "Traceback" not in result.stderr
    assert not (root / "docs/TRACEABILITY.md").exists()


@pytest.mark.parametrize(
    "change",
    [
        "version",
        "bool_version",
        "missing_field",
        "extra_field",
        "row_not_object",
        "no_requirements",
        "requirements_object",
        "private_not_list",
        "top_not_object",
        "unknown_top_field",
        "bad_specification",
    ],
)
def test_rejects_malformed_manifest(repo, change):
    root, data = repo
    if change == "version":
        data["schema_version"] = 2
    elif change == "bool_version":
        data["schema_version"] = True
    elif change == "missing_field":
        del data["requirements"][0]["gap"]
    elif change == "extra_field":
        data["requirements"][0]["typo"] = "value"
    elif change == "row_not_object":
        data["requirements"] = [None]
    elif change == "no_requirements":
        data["requirements"] = []
    elif change == "requirements_object":
        data["requirements"] = {}
    elif change == "private_not_list":
        data["private_evidence"] = {}
    elif change == "top_not_object":
        data = []
    elif change == "unknown_top_field":
        data["typo"] = True
    elif change == "bad_specification":
        data["specification"] = 7
    save(root, data)
    result = cli(root, "--write")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "change,expected",
    [
        ("hash", "spec_hash"),
        ("duplicate", "duplicate"),
        ("anchor", "anchor"),
        ("missing_anchor", "annotation"),
        ("bad_id", "annotation"),
        ("unmapped", "mapping"),
        ("unknown", "mapping"),
        ("duplicate_manifest", "duplicate"),
        ("bullet", "unregistered"),
        ("number", "unregistered"),
        ("asterisk", "unregistered"),
        ("plus", "unregistered"),
    ],
)
def test_rejects_spec_drift_and_incomplete_registration(repo, change, expected):
    root, data = repo
    spec = root / "docs/SPECIFICATION.md"
    text = spec.read_text()
    if change == "hash":
        text = text.replace("Capture images.", "Capture different images.")
    elif change == "duplicate":
        text += text.splitlines()[-1] + "\n"
    elif change == "anchor":
        text = text.replace('id="bw-cam-001"', 'id="bw-cam-002"')
    elif change == "missing_anchor":
        text = text.replace('<a id="bw-cam-001"></a> ', "")
    elif change == "bad_id":
        text = text.replace("BW-CAM-001", "BW-CAM-01")
    elif change == "unmapped":
        text += '- <a id="bw-cam-002"></a> **BW-CAM-002** — Another rule.\n'
    elif change == "unknown":
        data["requirements"][0]["id"] = "BW-CAM-099"
    elif change == "duplicate_manifest":
        data["requirements"].append(data["requirements"][0].copy())
    else:
        prefix = {"bullet": "-", "number": "2.", "asterisk": "*", "plus": "+"}[change]
        text += f"{prefix} An unregistered requirement.\n"
    spec.write_text(text)
    data["spec_sha256"] = hashlib.sha256(spec.read_bytes()).hexdigest()
    save(root, data)
    result = cli(root, "--write")
    assert result.returncode == 1
    assert expected in result.stderr
    assert not (root / "docs/TRACEABILITY.md").exists()


@pytest.mark.parametrize("prefix", ["", "- ", "1. ", "2) ", "* ", "+ "])
def test_accepts_annotation_prefixes_and_nonrequirement_context(repo, prefix):
    root, data = repo
    spec = root / "docs/SPECIFICATION.md"
    text = spec.read_text().replace("- <a", prefix + "<a")
    text = text.replace("## 2.", "Introduction without an ID.\n\n## 2.")
    text += "\n## 10. Layout\n- Not a requirement.\n1. A sequence.\n"
    text += "\n## 11. References\n- A reference.\n## 12. Context\n- Context.\n"
    text += "\n```text\n- Example list, not normative.\n```\n"
    spec.write_text(text)
    data["spec_sha256"] = hashlib.sha256(spec.read_bytes()).hexdigest()
    save(root, data)
    assert cli(root, "--write").returncode == 0


@pytest.mark.parametrize("mode", ["--check", "--write"])
def test_whole_spec_hash_rejects_untagged_prose_without_refreshing_manifest(repo, mode):
    root, _ = repo
    manifest = root / "docs/traceability.json"
    original = manifest.read_bytes()
    spec = root / "docs/SPECIFICATION.md"
    spec.write_text(spec.read_text() + "\nThe camera must also record sound.\n")
    result = cli(root, mode)
    assert result.returncode == 1
    assert "spec_sha256" in result.stderr
    assert "review" in result.stderr
    assert manifest.read_bytes() == original
    assert not (root / "docs/TRACEABILITY.md").exists()


def test_write_help_explains_hash_review_boundary(repo):
    root, _ = repo
    result = cli(root, "--help")
    assert result.returncode == 0
    assert "never refreshes" in result.stdout
    assert "review" in result.stdout


@pytest.mark.parametrize(
    "field,ref",
    [
        ("code", "missing.py"),
        ("code", "camera.py::missing"),
        ("code", "camera.py::capture.missing"),
        ("code", "camera.py::capture()"),
        ("code", "../outside.py"),
        ("code", "/etc/passwd"),
        ("code", "https://example.com/app.py"),
        ("code", "docs"),
        ("code", "camera.py#capture"),
        ("code", "./camera.py"),
        ("code", "docs/../camera.py"),
        ("code", "camera.py\\\\capture"),
        ("tests", "test_camera.py"),
        ("tests", "test_camera.py::missing"),
        ("tests", "camera.py::capture"),
        ("tests", "test_camera.py::test_capture[x]"),
        ("evidence", "docs/evidence.md#absent"),
        ("evidence", "missing.md"),
        ("evidence", "camera.py"),
        ("evidence", "docs/evidence.md#"),
    ],
)
def test_rejects_missing_or_unsafe_public_references(repo, field, ref):
    root, data = repo
    data["requirements"][0][field] = [ref]
    save(root, data)
    result = cli(root, "--write")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert not (root / "docs/TRACEABILITY.md").exists()


@pytest.mark.parametrize(
    "target", ["code", "tests", "evidence", "specification", "manifest", "report"]
)
def test_rejects_symlink_escape(repo, target, tmp_path):
    root, data = repo
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.write_text("sentinel", encoding="utf-8")
    rel = {
        "code": "camera.py",
        "tests": "test_camera.py",
        "evidence": "docs/evidence.md",
        "specification": "docs/SPECIFICATION.md",
        "manifest": "docs/traceability.json",
        "report": "docs/TRACEABILITY.md",
    }[target]
    path = root / rel
    path.unlink(missing_ok=True)
    path.symlink_to(outside)
    result = cli(root, "--write")
    assert result.returncode == 1
    assert "escape" in result.stderr
    assert outside.read_text() == "sentinel"


def test_accepts_static_symbols_and_markdown_anchors_without_importing(repo):
    root, data = repo
    (root / "camera.py").write_text(
        'raise RuntimeError("must never import")\n'
        "class Camera:\n    async def capture(self):\n        pass\n"
    )
    (root / "test_camera.py").write_text(
        'raise RuntimeError("must never execute")\n'
        "class TestCamera:\n    def test_capture(self):\n        pass\n"
    )
    (root / "docs/evidence.md").write_text(
        "# Pilot: the **public** report!\n# Pilot: the **public** report!\n"
        '<a id="explicit-pilot"></a>\n'
    )
    row = data["requirements"][0]
    row["code"] = ["camera.py", "camera.py::Camera.capture"]
    row["tests"] = ["test_camera.py::TestCamera::test_capture"]
    row["evidence"] = [
        "docs/evidence.md",
        "docs/evidence.md#explicit-pilot",
        "docs/evidence.md#pilot-the-public-report-1",
    ]
    save(root, data)
    result = cli(root, "--write")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "change,expected",
    [
        ("no_code", "code"),
        ("partial_no_code", "code"),
        ("verified_no_tests", "verified"),
        ("validated_no_evidence", "validated"),
        ("unknown_private", "private"),
        ("private_path", "private"),
        ("duplicate_private", "duplicate"),
        ("private_bad_id", "private"),
        ("private_bad_summary", "summary"),
        ("private_missing_anchor", "anchor"),
        ("private_missing_report", "public_report"),
        ("private_extra", "private"),
        ("private_not_object", "private"),
    ],
)
def test_rejects_unsubstantiated_claims_and_private_registry_errors(repo, change, expected):
    root, data = repo
    row = data["requirements"][0]
    private = {
        "id": "PRIVATE-PILOT",
        "summary": "Private pilot record",
        "public_report": "docs/evidence.md#pilot",
    }
    if change in {"no_code", "partial_no_code"}:
        row["code"] = []
        if change == "partial_no_code":
            row["implementation_status"] = "partial"
    elif change == "verified_no_tests":
        row["tests"] = []
    elif change == "validated_no_evidence":
        row["evidence"] = []
    elif change == "unknown_private":
        row["private_evidence"] = ["UNKNOWN"]
    elif change == "private_path":
        private["id"] = "/outside/private-record.json"
    elif change == "duplicate_private":
        data["private_evidence"] = [private, private]
    elif change == "private_bad_id":
        private["id"] = ""
    elif change == "private_bad_summary":
        private["summary"] = None
    elif change == "private_missing_anchor":
        private["public_report"] = "docs/evidence.md#missing"
    elif change == "private_missing_report":
        del private["public_report"]
    elif change == "private_extra":
        private["real_private_path"] = "/outside/private-record.json"
    elif change == "private_not_object":
        private = None
    if change.startswith("private_"):
        data["private_evidence"] = [private]
    save(root, data)
    result = cli(root, "--write")
    assert result.returncode == 1
    assert expected in result.stderr
    assert "Traceback" not in result.stderr


def test_private_ids_substantiate_mapping_without_opening_private_records(repo):
    root, data = repo
    data["private_evidence"] = [
        {
            "id": "PRIVATE-PILOT",
            "summary": "Private pilot record",
            "public_report": "docs/evidence.md#pilot",
        }
    ]
    row = data["requirements"][0]
    row.update(code=[], tests=[], private_evidence=["PRIVATE-PILOT"])
    save(root, data)
    result = cli(root, "--write")
    assert result.returncode == 0, result.stderr
    report = (root / "docs/TRACEABILITY.md").read_text()
    assert "PRIVATE-PILOT" in report
    assert "Private pilot record" in report


def test_policy_can_be_implemented_without_executable_code(repo):
    root, data = repo
    row = data["requirements"][0]
    row.update(scope="policy", code=[])
    save(root, data)
    assert cli(root, "--write").returncode == 0


def test_report_groups_categories_labels_evidence_and_reverse_indexes(repo):
    root, data = repo
    spec = root / "docs/SPECIFICATION.md"
    spec.write_text(
        spec.read_text() + '<a id="bw-aaa-001"></a> **BW-AAA-001** — Another requirement.\n'
    )
    data["spec_sha256"] = hashlib.sha256(spec.read_bytes()).hexdigest()
    other = data["requirements"][0].copy()
    other.update(
        id="BW-AAA-001",
        feature="Other | feature",
        gap="first\nsecond",
        spec_hash=hashlib.sha256(b"Another requirement.").hexdigest(),
        issues=[42],
    )
    data["requirements"].append(other)
    save(root, data)
    assert cli(root, "--write").returncode == 0
    report = (root / "docs/TRACEABILITY.md").read_text()
    assert report.index("## AAA") < report.index("## CAM")
    assert "Other \\| feature" in report
    assert "first<br>second" in report
    assert "Test:" in report
    assert "Evidence:" in report
    assert "Issue: #42" in report
    assert "## Reverse index: code" in report
    assert "## Reverse index: tests" in report
    assert "`camera.py::capture` → BW-AAA-001, BW-CAM-001" in report
    assert "`test_camera.py::test_capture` → BW-AAA-001, BW-CAM-001" in report
    assert "semantic coverage" in report
    assert "test execution" in report
    assert "private evidence audit" in report


def test_check_rejects_stale_report_without_rewriting(repo):
    root, _ = repo
    assert cli(root, "--write").returncode == 0
    report = root / "docs/TRACEABILITY.md"
    report.write_text(report.read_text() + "edited\n")
    original = report.read_bytes()
    result = cli(root)
    assert result.returncode == 1
    assert "stale generated report" in result.stderr
    assert report.read_bytes() == original


def test_check_compares_exact_report_bytes(repo):
    root, _ = repo
    assert cli(root, "--write").returncode == 0
    report = root / "docs/TRACEABILITY.md"
    report.write_bytes(report.read_bytes().replace(b"\n", b"\r\n"))
    result = cli(root, "--check")
    assert result.returncode == 1
    assert "stale generated report" in result.stderr


def test_missing_manifest_has_controlled_error(repo):
    root, _ = repo
    (root / "docs/traceability.json").unlink()
    result = cli(root, "--write")
    assert result.returncode == 1
    assert "missing repository file" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_modes_are_mutually_exclusive(repo):
    root, _ = repo
    assert cli(root, "--check", "--write").returncode == 2


@pytest.mark.parametrize("suffix", ["  ", " café — 🐦"])
def test_spec_hash_uses_exact_utf8_requirement_text(repo, suffix):
    root, data = repo
    spec = root / "docs/SPECIFICATION.md"
    exact = "Capture images." + suffix
    spec.write_text(spec.read_text().replace("Capture images.", exact), encoding="utf-8")
    data["spec_sha256"] = hashlib.sha256(spec.read_bytes()).hexdigest()
    data["requirements"][0]["spec_hash"] = hashlib.sha256(exact.encode("utf-8")).hexdigest()
    save(root, data)
    result = cli(root, "--write")
    assert result.returncode == 0, result.stderr


def test_private_report_requires_public_anchor(repo):
    root, data = repo
    data["private_evidence"] = [
        {"id": "pilot", "summary": "Pilot", "public_report": "docs/evidence.md"}
    ]
    save(root, data)
    result = cli(root, "--write")
    assert result.returncode == 1
    assert "anchor" in result.stderr


def test_fenced_example_does_not_supply_evidence_anchor(repo):
    root, data = repo
    (root / "docs/evidence.md").write_text('```html\n<a id="fake"></a>\n```\n')
    data["requirements"][0]["evidence"] = ["docs/evidence.md#fake"]
    save(root, data)
    assert cli(root, "--write").returncode == 1


def test_invalid_python_symbol_file_has_controlled_error(repo):
    root, _ = repo
    (root / "camera.py").write_text("def capture(:\n")
    result = cli(root, "--write")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr


def test_default_root_is_script_repository_not_working_directory(repo, tmp_path):
    root, _ = repo
    scripts = root / "scripts"
    scripts.mkdir()
    copied = scripts / "check_traceability.py"
    copied.write_bytes(SCRIPT.read_bytes())
    result = subprocess.run(
        [sys.executable, str(copied), "--write"],
        cwd=tmp_path.parent,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (root / "docs/TRACEABILITY.md").exists()


def test_real_repository_mapping_integrity():
    root = SCRIPT.parents[1]
    if not (root / "docs/traceability.json").is_file():
        pytest.skip("parent-owned canonical traceability manifest not yet available")
    result = cli(root, "--check")
    assert result.returncode == 0, result.stderr


def test_invalid_json_has_controlled_error(repo):
    root, _ = repo
    (root / "docs/traceability.json").write_text("{bad")
    result = cli(root, "--write")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
