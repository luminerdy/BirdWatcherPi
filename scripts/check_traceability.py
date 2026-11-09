#!/usr/bin/env python3
"""Validate repository-visible traceability mappings, never execute referenced code."""

import argparse
import ast
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from urllib.parse import quote

ID = r"BW-[A-Z]+-\d{3}"
ENUMS = {
    "scope": {"public", "private", "mixed", "future", "policy"},
    "implementation_status": {"implemented", "partial", "planned", "policy", "excluded"},
    "test_status": {"verified", "partial", "unverified", "not_applicable"},
    "field_status": {"validated", "partial", "unvalidated", "not_applicable"},
}
ROW_FIELDS = {
    "id",
    "spec_hash",
    "feature",
    "gap",
    "code",
    "tests",
    "evidence",
    "private_evidence",
    "issues",
    *ENUMS,
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fields(value, expected, label):
    require(isinstance(value, dict), f"{label}: expected object")
    require(set(value) == expected, f"{label}: expected fields {', '.join(sorted(expected))}")


def validate_schema(data):
    fields(
        data,
        {"schema_version", "specification", "spec_sha256", "private_evidence", "requirements"},
        "manifest",
    )
    require(
        isinstance(data["spec_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", data["spec_sha256"]),
        "invalid spec_sha256",
    )
    require(
        type(data["schema_version"]) is int and data["schema_version"] == 1,
        "schema_version must be 1",
    )
    require(isinstance(data["specification"], str), "specification must be a string")
    require(isinstance(data["private_evidence"], list), "private_evidence must be a list")
    require(
        isinstance(data["requirements"], list) and bool(data["requirements"]),
        "requirements must be a nonempty list",
    )
    for row in data["requirements"]:
        fields(row, ROW_FIELDS, "requirement row")
        for name, choices in ENUMS.items():
            require(
                isinstance(row[name], str) and row[name] in choices, f"{row['id']}: invalid {name}"
            )
        require(isinstance(row["id"], str) and re.fullmatch(ID, row["id"]), "invalid id")
        require(
            isinstance(row["spec_hash"], str) and re.fullmatch(r"[0-9a-f]{64}", row["spec_hash"]),
            "invalid spec_hash",
        )
        require(
            isinstance(row["feature"], str) and bool(row["feature"].strip()),
            "feature must be nonempty text",
        )
        require(isinstance(row["gap"], str), "gap must be text")
        for name in ("code", "tests", "evidence", "private_evidence"):
            require(
                isinstance(row[name], list)
                and all(isinstance(ref, str) and bool(ref.strip()) for ref in row[name]),
                f"{name} must be a list of nonempty strings",
            )
        require(
            isinstance(row["issues"], list)
            and all(type(issue) is int and issue > 0 for issue in row["issues"]),
            "issues must be a list of positive integers",
        )


def specification_rows(text):
    """Read one-line explicit requirements; prose is not inferred as normative."""
    rows = {}
    section = None
    fence = None
    annotation = re.compile(
        rf'^(?:(?:[-+*]|\d+[.)])\s+)?<a id="([^"]+)"></a> '
        rf"\*\*({ID})\*\* — (.+)$"
    )
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        marker = re.match(r"^(`{3,}|~{3,})", stripped)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token[0]
            elif token[0] == fence:
                fence = None
            continue
        if fence:
            continue
        heading = re.match(r"^##\s+(\d+)\.", line)
        if heading:
            section = int(heading[1])
        match = annotation.fullmatch(line.lstrip())
        if match:
            anchor, ident, exact_text = match.groups()
            require(anchor == ident.lower(), f"line {number}: mismatched anchor for {ident}")
            require(ident not in rows, f"line {number}: duplicate specification ID {ident}")
            rows[ident] = hashlib.sha256(exact_text.encode("utf-8")).hexdigest()
        elif re.search(r"\*\*BW-|<a\s+id=[\"\']bw-", stripped):
            raise ValueError(f"line {number}: malformed requirement annotation")
        elif section is not None and 2 <= section <= 9:
            require(
                not re.match(r"^(?:[-+*]|\d+[.)])\s+", stripped),
                f"line {number}: unregistered requirement list item",
            )
    return rows


def validate_specification(root, data):
    spec_bytes = repository_path(root, data["specification"]).read_bytes()
    require(
        hashlib.sha256(spec_bytes).hexdigest() == data["spec_sha256"],
        "spec_sha256 drift: explicitly review the specification and update the canonical "
        "manifest; --write never refreshes specification or row hashes",
    )
    spec = specification_rows(spec_bytes.decode("utf-8"))
    mapped = {}
    for row in data["requirements"]:
        require(row["id"] not in mapped, f"duplicate manifest ID {row['id']}")
        mapped[row["id"]] = row
    missing = sorted(set(spec) - set(mapped))
    unknown = sorted(set(mapped) - set(spec))
    require(not missing and not unknown, f"mapping mismatch: missing={missing}; unknown={unknown}")
    for ident, digest in spec.items():
        require(mapped[ident]["spec_hash"] == digest, f"{ident}: spec_hash drift")


def repository_path(root, reference, *, must_exist=True):
    """Reject traversal and external targets before reading any referenced content."""
    require(isinstance(reference, str) and bool(reference), "empty repository path")
    parts = reference.split("/")
    require(
        not any(part in {"", ".", ".."} for part in parts)
        and not any(char in reference for char in "\\\\:#\x00\n\r"),
        f"invalid repository path (escape or malformed): {reference!r}",
    )
    path = root / reference
    require(path.resolve().is_relative_to(root), f"path escape: {reference}")
    if must_exist:
        require(path.is_file(), f"missing repository file: {reference}")
    return path


def markdown_anchors(text):
    anchors = set()
    counts = Counter()
    fence = None
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker[1][0]
            fence = token if fence is None else (None if fence == token else fence)
            continue
        if fence:
            continue
        anchors.update(re.findall(r"<a\s+(?:id|name)=[\"\']([^\"\']+)[\"\']", line))
        match = re.match(r"^ {0,3}#{1,6}\s+(.+?)(?:\s+#+)?\s*$", line)
        if match:
            heading = re.sub(r"<[^>]+>", "", match[1]).lower()
            slug = re.sub(r"[^\w\- ]", "", heading).replace(" ", "-")
            candidate = slug
            while candidate in anchors:
                counts[slug] += 1
                candidate = f"{slug}-{counts[slug]}"
            anchors.add(candidate)
    return anchors


def evidence_reference(root, reference):
    path_text, separator, anchor = reference.partition("#")
    path = repository_path(root, path_text)
    require(path.suffix.lower() == ".md", f"evidence must be Markdown: {reference}")
    if separator:
        require(
            bool(anchor) and anchor in markdown_anchors(path.read_text(encoding="utf-8")),
            f"missing evidence anchor: {reference}",
        )


def python_reference(root, reference, *, test=False):
    parts = reference.split("::")
    path = repository_path(root, parts[0])
    if len(parts) == 1:
        require(not test, f"tests require a pytest symbol: {reference}")
        return
    require(path.suffix == ".py", f"symbols require a Python file: {reference}")
    names = parts[1:] if test else parts[1].split(".")
    require(
        (test or len(parts) == 2) and all(re.fullmatch(r"[A-Za-z_]\w*", name) for name in names),
        f"malformed symbol: {reference}",
    )
    if test:
        require(
            (path.name.startswith("test_") or path.name.endswith("_test.py"))
            and len(names) in {1, 2}
            and names[-1].startswith("test_")
            and (len(names) == 1 or names[0].startswith("Test")),
            f"not a pytest test symbol: {reference}",
        )
    node = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for index, name in enumerate(names):
        matches = [
            child
            for child in node.body
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and child.name == name
        ]
        require(bool(matches), f"missing Python symbol: {reference}")
        node = matches[0]
        if index < len(names) - 1:
            require(isinstance(node, ast.ClassDef), f"symbol parent is not a class: {reference}")
    if test:
        require(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)),
            f"test symbol is not a function: {reference}",
        )


def validate_references(root, data):
    registry = set()
    for entry in data["private_evidence"]:
        fields(entry, {"id", "summary", "public_report"}, "private_evidence entry")
        ident = entry["id"]
        require(
            isinstance(ident, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", ident),
            "private evidence id must be a logical label, never a private path",
        )
        require(ident not in registry, f"duplicate private evidence id: {ident}")
        registry.add(ident)
        require(
            isinstance(entry["summary"], str) and bool(entry["summary"].strip()),
            "private evidence summary must be nonempty text",
        )
        require(
            isinstance(entry["public_report"], str) and "#" in entry["public_report"],
            "private evidence public_report must be a string with a public anchor",
        )
        evidence_reference(root, entry["public_report"])
    for row in data["requirements"]:
        ident = row["id"]
        require(set(row["private_evidence"]) <= registry, f"{ident}: unknown private evidence id")
        require(
            row["implementation_status"] not in {"implemented", "partial"}
            or row["scope"] == "policy"
            or bool(row["code"] or row["private_evidence"]),
            f"{ident}: implemented/partial needs code or private evidence unless policy",
        )
        require(
            row["test_status"] != "verified" or bool(row["tests"] or row["private_evidence"]),
            f"{ident}: verified needs tests or private evidence",
        )
        require(
            row["field_status"] != "validated" or bool(row["evidence"]),
            f"{ident}: validated needs public evidence",
        )
        for ref in row["code"]:
            python_reference(root, ref)
        for ref in row["tests"]:
            python_reference(root, ref, test=True)
        for ref in row["evidence"]:
            evidence_reference(root, ref)


def cell(value):
    """Keep public text inside one Markdown table cell."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", r"\|")
        .replace("\r\n", "\n")
        .replace("\n", "<br>")
    )


def reference_link(reference, *, code=False):
    target = reference.split("::")[0] if code else reference
    label = f"`{cell(reference)}`" if code else cell(reference)
    return f"[{label}](../{quote(target, safe='/#')})"


def render(data):
    """Render a deterministic public mapping inventory."""
    lines = [
        "# Traceability",
        "",
        "Generated from `docs/traceability.json`; edit the manifest, not this report.",
        "",
        "Mapping integrity is not fulfillment, semantic coverage, or test execution.",
        "Private evidence not independently checked; this is not a private evidence audit.",
        "Status values are declared claims, not independently established by this validator.",
        "`--write` regenerates this report only; it never refreshes specification or row hashes.",
        "",
    ]
    lines.extend(
        [
            "## Status legend",
            "",
            "- **Implementation:** implemented = the bounded stated feature exists; partial = some clauses are missing; planned = not implemented; policy/excluded = an approval, scope, or engineering-policy decision rather than completed software.",
            "- **Test:** verified = reviewed automated evidence addresses the stated contract; partial = only a subset is covered; unverified = no adequate automated proof; not_applicable = not an executable test claim. Private-only verified evidence remains a reported local result, not reproducible public coverage.",
            "- **Field:** validated = the bounded physical/approval criterion has cited evidence; partial = limited historical evidence; unvalidated = the field gate has not passed; not_applicable = no physical field claim.",
            "- A compound requirement stays partial when any promised clause is missing. Public, private, mixed, future, and policy scopes are distinct. These counts overlap across dimensions and are not a project-completion percentage.",
            "",
            "## Mapping summary",
            "",
            f"Requirements mapped: **{len(data['requirements'])}**",
            "",
        ]
    )
    for label, field in [
        ("implementation", "implementation_status"),
        ("test", "test_status"),
        ("field", "field_status"),
    ]:
        counts = Counter(row[field] for row in data["requirements"])
        lines.append(
            "- " + label + ": " + ", ".join(f"{key}={counts[key]}" for key in sorted(counts))
        )
    lines.extend(
        [
            "",
            "Update the reviewed manifest, then run `python3 scripts/check_traceability.py --write` and `python3 scripts/check_traceability.py --check` from the repository root. Never refresh fingerprints just to silence a failure; review the changed contract and its evidence first.",
            "",
        ]
    )
    rows = sorted(data["requirements"], key=lambda row: row["id"])
    category = None
    for row in rows:
        current = row["id"].split("-")[1]
        if current != category:
            category = current
            lines.extend(
                [
                    f"## {category}",
                    "",
                    "| Requirement | Scope | Implementation | Test | Field | Code | Tests / evidence / private / issues | Gap |",
                    "| --- | --- | --- | --- | --- | --- | --- | --- |",
                ]
            )
        # Report lives in docs/, so links to repository files are relative to docs/.
        spec_link = "../" + data["specification"]
        link = f"[{row['id']}: {cell(row['feature'])}]({spec_link}#{row['id'].lower()})"
        refs = (
            ["Test: " + reference_link(ref, code=True) for ref in row["tests"]]
            + ["Evidence: " + reference_link(ref) for ref in row["evidence"]]
            + ["Private: " + ref for ref in row["private_evidence"]]
            + [f"Issue: #{issue}" for issue in row["issues"]]
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    link,
                    row["scope"],
                    row["implementation_status"],
                    row["test_status"],
                    row["field_status"],
                    "<br>".join(reference_link(ref, code=True) for ref in row["code"]) or "—",
                    "<br>".join(
                        ref if ref.startswith(("Test: ", "Evidence: ")) else cell(ref)
                        for ref in refs
                    )
                    or "—",
                    cell(row["gap"]) or "—",
                ]
            )
            + " |"
        )
    for field in ("code", "tests"):
        lines.extend(["", f"## Reverse index: {field}", ""])
        reverse = {}
        for row in rows:
            for reference in row[field]:
                reverse.setdefault(reference, set()).add(row["id"])
        for reference, ids in sorted(reverse.items()):
            lines.append(f"- `{cell(reference)}` → {', '.join(sorted(ids))}")
    lines.extend(["", "## Private evidence declarations", ""])
    for entry in sorted(data["private_evidence"], key=lambda entry: entry["id"]):
        lines.append(
            f"- {cell(entry['id'])}: {cell(entry['summary'])} — {reference_link(entry['public_report'])}"
        )
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="check generated report (default)")
    mode.add_argument(
        "--write",
        action="store_true",
        help="validate then write report only; never refreshes hashes: review and explicitly "
        "update canonical manifest hashes after specification changes",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        manifest = repository_path(root, "docs/traceability.json")
        target = repository_path(root, "docs/TRACEABILITY.md", must_exist=False)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        validate_schema(data)
        validate_specification(root, data)
        validate_references(root, data)
        report = render(data)
        if args.write:
            require(not target.is_symlink(), "report output alias: symlink")
            require(
                not target.exists() or target.stat().st_nlink == 1, "report output alias: hardlink"
            )
            fd, temporary = tempfile.mkstemp(
                prefix=".traceability-", suffix=".tmp", dir=target.parent
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as output:
                    output.write(report)
                os.replace(temporary, target)
            finally:
                Path(temporary).unlink(missing_ok=True)
        else:
            require(
                target.is_file() and target.read_bytes() == report.encode("utf-8"),
                "stale generated report; run --write",
            )
    except (OSError, UnicodeError, ValueError, SyntaxError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"mapping integrity: {len(data['requirements'])} requirements")
    for label, field in [
        ("implementation", "implementation_status"),
        ("test", "test_status"),
        ("field", "field_status"),
    ]:
        counts = Counter(row[field] for row in data["requirements"])
        print(label + ": " + ", ".join(f"{key}={counts[key]}" for key in sorted(counts)))
    print("private evidence not independently checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
