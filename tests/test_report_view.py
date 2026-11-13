"""Synthetic-only tests for the offline report surface."""

import copy
import json
import shutil
import subprocess
from html.parser import HTMLParser

import pytest


def fixture():
    return {
        "date_local": "2026-01-02",
        "timezone": "America/Chicago",
        "mode": "portable",
        "source_root": "/private/captures",
        "frames": [
            {
                "id": "F000001",
                "local": "2026-01-02T07:05:00-06:00",
                "utc": "2026-01-02T13:05:00+00:00",
                "analysis_status": "unknown",
                "source_path": "/private/captures/secret.jpg",
                "available": False,
            }
        ],
    }


def test_serialization_escapes_html_and_strips_private_fields_without_mutation():
    view = fixture()
    attack = "</script><img src=x onerror=alert(1)>&\u2028\u2029"
    view["title"] = attack
    view["frames"][0]["export_note"] = attack
    view["frames"][0]["original_url"] = "javascript:alert(1)"
    view["frames"][0]["thumbnail_url"] = "https://example.invalid/photo.jpg"
    view["warnings"] = ["Missing /home/user/private/photo.jpg and C:\\Private\\photo.jpg"]
    before = copy.deepcopy(view)
    html = render(view)
    doc = Document(html)
    data = next(text for attrs, text in doc.scripts if attrs.get("id") == "report-data")
    payload = json.loads(data)
    assert payload["title"] == attack
    assert "<" not in data and ">" not in data and "&" not in data
    assert "\u2028" not in data and "\u2029" not in data
    assert "/private/captures" not in html and "/home/user" not in html
    assert "C:\\Private" not in html
    assert "source_path" not in data and "source_root" not in data
    assert payload["frames"][0]["original_url"] is None
    assert payload["frames"][0]["thumbnail_url"] is None
    assert "<img src=x" not in html
    assert view == before


def test_gallery_has_distinct_states_filters_pagination_and_inspector():
    view = fixture()
    view["frames"] = [
        dict(view["frames"][0], id=f"F{i:06}", analysis_status=status, confirmed=i == 1)
        for i, status in enumerate(
            ["bird_candidate", "bird_candidate", "unknown", "not_analyzed", "analysis_failed"]
        )
    ]
    html = render(view)
    doc = Document(html)
    ids = {attrs.get("id") for _, attrs in doc.tags}
    assert {
        "status-filter",
        "hour-filter",
        "gallery",
        "previous-page",
        "next-page",
        "inspector",
        "zoom-in",
        "zoom-out",
        "open-original",
        "download-original",
    } <= ids
    for label in (
        "Confirmed photograph",
        "Provisional candidate",
        "Sampled · no boxes / unknown",
        "Unsampled",
        "Analysis failed",
        "Image unavailable",
    ):
        assert label in html
    assert "5 inventory frames" in html
    assert "1 confirmed photographs" in html
    assert "All frame records" in html
    assert "<dialog" in html
    assert "textContent" in html
    assert "innerHTML" not in html
    assert "addEventListener" in html


def test_activity_and_limits_remain_explicit():
    view = fixture()
    view.update(
        warnings=["Synthetic sampling warning"],
        gallery_limit_note="Synthetic byte limit",
        coverage={"note": "Synthetic coarse coverage", "estimated_seconds": None},
        hours=[
            {
                "key": "2026-01-02T07:00:00-06:00",
                "label": "07:00 -06:00",
                "inventory_frames": 7,
                "analyzed_frames": 3,
                "candidate_frames": 2,
                "confirmed_frames": 1,
                "session_seconds": None,
            }
        ],
        comparison=[
            {
                "date_local": "2026-01-01",
                "inventory_frames": 10,
                "candidate_frames": 2,
                "confirmed_frames": 1,
            }
        ],
        exported={"embedded_originals": 1, "omitted_originals": 5},
    )
    html = render(view)
    for text in (
        "Synthetic sampling warning",
        "Synthetic byte limit",
        "Synthetic coarse coverage",
        "Hourly activity",
        "07:00 -06:00",
        "Session bounds",
        "not verified continuous coverage",
        "UTC-based",
        "not unique visits",
        "2026-01-01",
        "embedded_originals",
        "omitted_originals",
    ):
        assert text in html
    assert "<table" in html
    assert "No confirmed photographs" in html


def test_javascript_syntax_and_filter_pagination_behavior(tmp_path):
    assert shutil.which("node"), "Node is required to verify the offline script"
    html = render(fixture())
    script = next(text for attrs, text in Document(html).scripts if not attrs.get("type"))
    path = tmp_path / "report.js"
    path.write_text(script)
    result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    helpers = script.split("// DOM binding")[0]
    checks = """
const assert = require('node:assert/strict');
const frames = [
{id:'A', local:'2026-11-01T01:10:00-05:00', analysis_status:'bird_candidate',confirmed:true},
{id:'B', local:'2026-11-01T01:20:00-06:00', analysis_status:'bird_candidate'},
{id:'C', local:'2026-11-01T02:20:00-06:00', analysis_status:'not_analyzed'}];
assert.deepEqual(selectFrames(frames,'confirmed','').map(f=>f.id),['A']);
assert.deepEqual(selectFrames(frames,'bird_candidate','').map(f=>f.id),['A','B']);
assert.deepEqual(selectFrames(frames,'','2026-11-01T01-06:00').map(f=>f.id),['B']);
assert.deepEqual(pageFrames(frames,2,2).map(f=>f.id),['C']);
assert.deepEqual(pageFrames([],1,24),[]);
assert.equal(hourKey({local:'2026-01-02T07:05:00.123456-06:00'}),'2026-01-02T07-06:00');
"""
    path.write_text(helpers + checks)
    result = subprocess.run(["node", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def render(view):
    from birdwatcher.report_view import render_report

    return render_report(view)


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.scripts = []
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if tag == "script":
            self.current = [attrs, ""]

    def handle_data(self, text):
        if self.current is not None:
            self.current[1] += text

    def handle_endtag(self, tag):
        if tag == "script" and self.current is not None:
            self.scripts.append(self.current)
            self.current = None


def test_privacy_redacts_arbitrary_paths_in_public_notes():
    view = fixture()
    view["warnings"] = ["Missing /capture-data/secret.jpg and /secrets.jpg"]
    view["frames"][0]["export_note"] = "Read error at /volume/birds/photo.jpg"
    html = render(view)
    assert "/capture-data" not in html
    assert "/secrets.jpg" not in html
    assert "/volume/birds" not in html


def test_urls_are_available_only_when_safe_for_export_mode():
    view = fixture()
    frame = view["frames"][0]
    for bad in (
        "//host/a.jpg",
        "/etc/passwd",
        "file:///home/user/a.jpg",
        "data:image/svg+xml;base64,AAA=",
        "%2f%2fhost/a.jpg",
        "javascript:alert(1)",
        "../captures/a.jpg",
    ):
        frame["original_url"] = bad
        doc = Document(render(view))
        payload = json.loads(next(t for a, t in doc.scripts if a.get("id") == "report-data"))
        assert payload["frames"][0]["original_url"] is None, bad
    view["mode"] = "local"
    frame.update(
        original_url="../captures/a%20b.jpg",
        thumbnail_url="data:image/png;base64,AA==",
        available=True,
    )
    html = render(view)
    doc = Document(html)
    payload = json.loads(next(t for a, t in doc.scripts if a.get("id") == "report-data"))
    assert payload["frames"][0]["original_url"] == "../captures/a%20b.jpg"
    assert any(t == "img" and a.get("src") == "data:image/png;base64,AA==" for t, a in doc.tags)


@pytest.mark.parametrize("mode", ["portable", "local"])
@pytest.mark.parametrize(
    "url",
    [
        " ../private/synthetic.jpg",
        " /private/synthetic.jpg",
        " //host/private/synthetic.jpg",
        "%20../private/synthetic.jpg",
        "%20/private/synthetic.jpg",
        "%20//host/private/synthetic.jpg",
        "images/synthetic.jpg ",
        "images/synthetic.jpg%20",
        "\t../private/synthetic.jpg",
        "%09../private/synthetic.jpg",
        "images/syn\nthetic.jpg",
        "images/syn%0dthetic.jpg",
        "\x00../private/synthetic.jpg",
        "%00../private/synthetic.jpg",
        "\x1f../private/synthetic.jpg",
        "%1f../private/synthetic.jpg",
    ],
)
def test_url_boundary_whitespace_and_controls_never_reach_html(mode, url):
    view = fixture()
    view["mode"] = mode
    view["frames"][0].update(original_url=url, thumbnail_url=url)
    html = render(view)
    doc = Document(html)
    payload = json.loads(next(t for a, t in doc.scripts if a.get("id") == "report-data"))
    assert payload["frames"][0]["original_url"] is None
    assert payload["frames"][0]["thumbnail_url"] is None
    assert not any(t == "img" and a.get("src") for t, a in doc.tags)
    assert "private/synthetic.jpg" not in html
    assert "/private/captures" not in html


@pytest.mark.parametrize(
    "url",
    [
        "/private/synthetic.jpg",
        "//host/private/synthetic.jpg",
        "%2fprivate/synthetic.jpg",
        "%2f%2fhost/private/synthetic.jpg",
        "../private/synthetic.jpg",
        "%2e%2e/private/synthetic.jpg",
        "images/%2E%2e/private/synthetic.jpg",
        "..%2fprivate/synthetic.jpg",
        "..\\private\\synthetic.jpg",
        "file:///private/synthetic.jpg",
    ],
)
def test_portable_rejects_absolute_and_normalized_traversal_urls(url):
    view = fixture()
    view["frames"][0].update(original_url=url, thumbnail_url=url)
    html = render(view)
    payload = json.loads(next(t for a, t in Document(html).scripts if a.get("id") == "report-data"))
    assert payload["frames"][0]["original_url"] is None
    assert payload["frames"][0]["thumbnail_url"] is None
    assert "private/synthetic.jpg" not in html


@pytest.mark.parametrize(
    "mode,url",
    [
        ("local", "../raw%20archive/a%20%22quoted%22.jpg"),
        ("portable", "images/a%20%22quoted%22.jpg"),
        ("portable", "data:image/png;base64,AA=="),
        ("local", "data:image/png;base64,AA=="),
    ],
)
def test_safe_relative_and_data_image_urls_are_preserved(mode, url):
    view = fixture()
    view["mode"] = mode
    view["frames"][0].update(original_url=url, thumbnail_url=url)
    doc = Document(render(view))
    payload = json.loads(next(t for a, t in doc.scripts if a.get("id") == "report-data"))
    assert payload["frames"][0]["original_url"] == url
    assert payload["frames"][0]["thumbnail_url"] == url
    assert any(t == "img" and a.get("src") == url for t, a in doc.tags)


def test_all_metadata_survives_but_initial_dom_is_bounded():
    view = fixture()
    view["frames"] = [dict(view["frames"][0], id=f"F{i:06}") for i in range(100)]
    doc = Document(render(view))
    payload = json.loads(next(t for a, t in doc.scripts if a.get("id") == "report-data"))
    assert len(payload["frames"]) == 100
    assert sum(t == "article" for t, a in doc.tags) == 24


def test_coverage_sessions_gaps_and_failure_counts_are_disclosed():
    view = fixture()
    view["frames"][0]["analysis_status"] = "analysis_failed"
    view["coverage"] = {
        "estimated_seconds": 120.0,
        "sessions": [{"start_utc": "synthetic"}],
        "gaps": [{"start_utc": "synthetic-gap"}],
    }
    html = render(view)
    assert "120.0" in html
    assert "1 coarse session bounds" in html
    assert "1 reported coverage gaps" in html
    assert "1 analysis failures" in html
    assert "0 unsampled" in html


@pytest.mark.parametrize("width", [390, 1440])
def test_chromium_controls_inspector_and_responsive_layout(tmp_path, width):
    chromium = shutil.which("chromium")
    if not chromium:
        pytest.skip("Chromium not installed")
    view = fixture()
    image = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN/8AAAAASUVORK5CYII="
    )
    view["frames"] = [
        dict(
            view["frames"][0],
            id=f"F{i:06}",
            confirmed=i == 0,
            thumbnail_url=image,
            original_url=image if i == 0 else None,
            available=i == 0,
            analysis_status="unknown" if i < 20 else "not_analyzed",
        )
        for i in range(30)
    ]
    view["title"] = '<img src=x onerror="document.body.dataset.injected=1">'
    checks = r"""
<script>
try {
  const check=(value,message)=>{if(!value)throw new Error(message);};
  const change=(id,value)=>{document.getElementById(id).value=value;document.getElementById(id).dispatchEvent(new Event('change'));};
  check(document.querySelectorAll('.photo').length===24,'Initial page bound');
  document.getElementById('next-page').click();
  check(document.querySelectorAll('.photo').length===6,'Next page');
  document.getElementById('previous-page').click();
  change('status-filter','confirmed');
  check(document.querySelectorAll('.photo').length===1,'Confirmed filtering');
  document.querySelector('.preview').click();
  check(document.getElementById('inspector').open,'Inspector opens');
  check(!document.getElementById('open-original').hidden,'Original enabled');
  document.getElementById('zoom-in').click();
  check(document.getElementById('zoom-level').textContent==='150%','Zoom works');
  document.getElementById('close-inspector').click();
  change('status-filter','not_analyzed');
  check(document.querySelectorAll('.photo').length===10,'Unsampled filtering');
  document.querySelector('.preview').click();
  check(document.getElementById('open-original').hidden,'Missing original hidden');
  check(!document.getElementById('open-original').hasAttribute('href'),'Missing original no href');
  document.getElementById('close-inspector').click();
  document.getElementById('reset-filters').click();
  check(document.querySelectorAll('.photo').length===24,'Reset filters');
  change('status-filter','analysis_failed');
  check(!document.getElementById('empty-results').hidden,'Empty filtered state');
  check(document.body.dataset.injected===undefined,'XSS blocked');
  check(document.documentElement.scrollWidth<=window.innerWidth,'No page horizontal overflow '+document.documentElement.scrollWidth+'/'+window.innerWidth+' h1 '+document.querySelector('h1').scrollWidth+': '+Array.from(document.querySelectorAll('body *')).filter(e=>e.getBoundingClientRect().right>window.innerWidth).map(e=>e.tagName+'.'+e.className).slice(0,10).join(','));
  document.body.dataset.testResult='passed';
} catch(error) { document.body.dataset.testResult='FAILED '+error.message; }
</script>
"""
    path = tmp_path / "synthetic-report.html"
    path.write_text(render(view).replace("</body>", checks + "</body>"))
    result = subprocess.run(
        [
            chromium,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-background-networking",
            "--no-first-run",
            f"--user-data-dir={tmp_path / 'profile'}",
            f"--window-size={width},900",
            "--dump-dom",
            path.as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    doc = Document(result.stdout)
    assert next(a for t, a in doc.tags if t == "body").get("data-test-result") == "passed"


def test_chromium_portable_whitespace_cannot_activate_outside_file_links(tmp_path):
    chromium = shutil.which("chromium")
    if not chromium:
        pytest.skip("Chromium not installed")
    report = tmp_path / "report"
    report.mkdir()
    private = tmp_path / "private"
    private.mkdir()
    outside = private / "synthetic.jpg"
    outside.write_bytes(b"synthetic private original")
    view = fixture()
    view["frames"][0].update(
        original_url=" ../private/synthetic.jpg", thumbnail_url=" ../private/synthetic.jpg"
    )
    checks = r"""
<script>
try {
  const check=(value,message)=>{if(!value)throw new Error(message);};
  const outside=new URL('../private/synthetic.jpg',location.href).href;
  check(new URL(' ../private/synthetic.jpg',location.href).href===outside,
        'Browser reproduces leading-space traversal normalization');
  check(new URL(' /private/synthetic.jpg',location.href).href==='file:///private/synthetic.jpg',
        'Browser trims absolute URL');
  check(new URL(' //host/private/synthetic.jpg',location.href).href==='file://host/private/synthetic.jpg',
        'Browser trims protocol-relative URL');
  check(new URL('%2e%2e/private/synthetic.jpg',location.href).href===outside,
        'Browser normalizes encoded dot segments');
  check(!document.querySelector('.photo img[src]'),'No outside gallery image');
  document.querySelector('.preview').click();
  check(!document.getElementById('inspect-image').hasAttribute('src'),'No outside inspector image');
  for(const id of ['open-original','download-original']) {
    const link=document.getElementById(id);
    check(link.hidden && !link.hasAttribute('href'),'No active outside link: '+id);
  }
  document.body.dataset.testResult='passed';
} catch(error) { document.body.dataset.testResult='FAILED '+error.message; }
</script>
"""
    html = render(view)
    path = report / "synthetic-report.html"
    path.write_text(html.replace("</body>", checks + "</body>"))
    result = subprocess.run(
        [
            chromium,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-background-networking",
            "--no-first-run",
            f"--user-data-dir={tmp_path / 'profile'}",
            "--dump-dom",
            path.as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    doc = Document(result.stdout)
    assert next(a for t, a in doc.tags if t == "body").get("data-test-result") == "passed"
    assert "private/synthetic.jpg" not in html
    assert "/private/captures" not in html


def test_empty_complete_accessible_offline_document():
    html = render({})
    doc = Document(html)
    assert html.startswith("<!doctype html>")
    assert '<html lang="en">' in html
    assert "No frame records" in html
    assert "No confirmed photographs" in html
    assert "not evidence of bird absence" in html
    assert any(
        t == "meta"
        and a.get("http-equiv") == "Content-Security-Policy"
        and "connect-src 'none'" in a["content"]
        for t, a in doc.tags
    )
    assert not any("src" in a for t, a in doc.tags if t == "script")
    assert 'aria-live="polite"' in html
    assert "<main" in html
    assert "skip-link" in html
    assert "https://" not in html
    assert "http://" not in html
