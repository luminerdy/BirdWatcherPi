"""Pure offline report rendering. Only allowlisted presentation data leaves here."""

import json
import re
from html import escape
from urllib.parse import unquote


def _text(value):
    text = str(value) if value is not None else ""
    return re.sub(
        r'(?<![\w<.])(?:[A-Za-z]:[\\/]|/(?![/>]))[^\s<>"\']+',
        "[private path]",
        text,
    )


def _url(value, portable):
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    if re.fullmatch(r"data:image/(?:jpeg|png|webp|gif);base64,[A-Za-z0-9+/=]+", value):
        return value
    decoded = unquote(value)
    # Reject rather than trim: browsers normalize whitespace before resolving URLs.
    if (
        decoded != decoded.strip()
        or decoded.startswith(("/", "\\"))
        or ":" in decoded
        or "\\" in decoded
        or any(ord(c) < 32 for c in decoded)
        or "?" in decoded
        or "#" in decoded
        or (portable and ".." in decoded.split("/"))
    ):
        return None
    return value


def _payload(view):
    portable = view.get("mode", "portable") != "local"
    data: dict = {
        key: _text(view.get(key))
        for key in ("title", "date_local", "timezone", "mode", "gallery_limit_note")
    }
    data["warnings"] = [_text(w) for w in view.get("warnings", [])]
    data["frames"] = []
    for frame in view.get("frames", []):
        row = {
            key: frame.get(key)
            for key in (
                "id",
                "utc",
                "local",
                "frame_id",
                "analysis_status",
                "score",
                "detection_count",
                "shortlisted",
                "shortlist_index",
                "confirmed",
                "keeper",
                "available",
                "export_note",
            )
        }
        row = {key: _text(value) if isinstance(value, str) else value for key, value in row.items()}
        for key in ("thumbnail_url", "original_url"):
            row[key] = _url(frame.get(key), portable)
        data["frames"].append(row)
    return data


def _json(data):
    return (
        json.dumps(data, ensure_ascii=True, allow_nan=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def _h(value):
    return escape(_text(value), quote=True)


_LABELS = {
    "bird_candidate": "Provisional candidate",
    "unknown": "Sampled · no boxes / unknown",
    "not_analyzed": "Unsampled",
    "analysis_failed": "Analysis failed",
}


def _badge(frame):
    return (
        "Confirmed photograph"
        if frame.get("confirmed")
        else _LABELS.get(frame.get("analysis_status"), "Sampled · no boxes / unknown")
    )


def _card(frame):
    photo_id = _h(frame.get("id"))
    url = frame.get("thumbnail_url") or frame.get("original_url")
    image = (
        f'<img src="{escape(url, quote=True)}" alt="Photograph {photo_id}" loading="lazy" decoding="async">'
        if url
        else '<span class="placeholder">On-Pi original / request photo ID</span>'
    )
    unavailable = (
        '<span class="badge unavailable">Image unavailable</span>'
        if not frame.get("available")
        else ""
    )
    return (
        f'<article class="photo"><button class="preview" data-photo-id="{photo_id}" '
        f'aria-label="Inspect photograph {photo_id}">{image}</button><div class="photo-body">'
        f'<div class="photo-title"><strong>{photo_id}</strong>'
        f"<time>{_h(frame.get('local'))}</time></div>"
        f'<span class="badge">{_h(_badge(frame))}</span>{unavailable}'
        f'<p class="note">{_h(frame.get("export_note"))}</p></div></article>'
    )


def _table(headers, rows):
    body = []
    for row in rows:
        cells = [f'<th scope="row">{_h(row[0])}</th>'] if row else []
        cells.extend(f"<td>{_h(value)}</td>" for value in row[1:])
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<div class="table-scroll" tabindex="0" role="region" aria-label="Scrollable data table">'
        "<table><thead><tr>"
        + "".join(f'<th scope="col">{_h(h)}</th>' for h in headers)
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>"
    )


_CSS = r"""
:root{color-scheme:light;--paper:#f5f3ed;--panel:#fffef9;--ink:#252d28;--muted:#596158;--line:#d6d9cd;--forest:#244c38;--soft:#e7eddf;--amber:#735417}
*{box-sizing:border-box}body{overflow-wrap:anywhere;margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 'Trebuchet MS',Arial,sans-serif}a{color:var(--forest)}button,select{font:inherit}button,a,select{touch-action:manipulation}button,select,.action{min-height:44px}button{cursor:pointer}button:disabled{cursor:default;opacity:.45}button,.action,select{border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--ink);padding:9px 14px}button:hover:not(:disabled),.action:hover{border-color:var(--forest);background:var(--soft)}:focus-visible{outline:3px solid var(--forest);outline-offset:4px}.skip-link{position:absolute;left:16px;top:-100px;background:var(--panel);padding:12px;z-index:5}.skip-link:focus{top:12px}.shell{max-width:1460px;margin:auto;padding:0 clamp(18px,4vw,60px)}header{padding:28px 0 22px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:20px;align-items:center}.brand{font-weight:bold;letter-spacing:.04em}.edition{color:var(--muted);font-size:.85rem}h1,h2,h3,p{margin-top:0}h1{font:normal clamp(30px,4vw,44px)/1.15 Georgia,serif;letter-spacing:-.025em;margin-bottom:12px}h2{font:normal 27px/1.2 Georgia,serif;margin-bottom:10px}h3{font-size:1rem}main{padding:30px 0 56px}.date-line,.eyebrow{color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.09em}.intro{margin-bottom:25px}.intro p{margin-bottom:8px}.counts{color:var(--forest);font-weight:bold;font-variant-numeric:tabular-nums}.workspace{display:grid;grid-template-columns:minmax(0,1fr) 310px;gap:34px;align-items:start}.toolbar{display:flex;flex-wrap:wrap;gap:12px;align-items:end;padding:16px 0;border-block:1px solid var(--line);margin:18px 0}.toolbar label{display:grid;gap:5px;font-size:.85rem;font-weight:bold}.toolbar select{max-width:100%}.results{font-size:.9rem;color:var(--muted);margin-bottom:16px}.gallery{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.photo{min-width:0;background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden}.preview{padding:0;border:0;border-radius:0;width:100%;display:flex;align-items:center;justify-content:center;aspect-ratio:4/3;background:#e7e7dd;overflow:hidden}.preview img{display:block;width:100%;height:100%;object-fit:cover}.placeholder{color:var(--muted);padding:20px;font-size:.85rem}.photo-body{padding:14px}.photo-title{display:flex;flex-direction:column;gap:3px}.photo-title strong{font-size:.95rem}.photo-title time{font-size:.72rem;overflow-wrap:anywhere;color:var(--muted)}.badge{display:inline-block;font-size:.72rem;padding:3px 7px;background:var(--soft);border-radius:4px;margin:10px 4px 0 0}.unavailable{background:#eee6d4;color:#604918}.note{font-size:.8rem;color:var(--muted);margin:8px 0 0;overflow-wrap:anywhere}.pagination{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:24px 0}.sidebar{border-left:1px solid var(--line);padding-left:25px}.sidebar section{padding:0 0 24px;margin-bottom:24px;border-bottom:1px solid var(--line)}.sidebar p,.sidebar li,.sidebar dd,.sidebar dt{font-size:.85rem}.sidebar ul{padding-left:18px}.sidebar li{margin-bottom:10px;overflow-wrap:anywhere}.sidebar dl{margin:12px 0}.sidebar dt{color:var(--muted)}.sidebar dd{margin:0 0 12px;overflow-wrap:anywhere}.empty{padding:42px 22px;border:1px dashed var(--line);text-align:center;color:var(--muted)}.section{margin-top:42px;padding-top:28px;border-top:1px solid var(--line)}.table-scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.85rem;font-variant-numeric:tabular-nums;text-align:left}th,td{padding:11px 14px;border-bottom:1px solid var(--line);white-space:nowrap}th{font-weight:600}thead{color:var(--muted)}.bars{display:flex;gap:6px;height:110px;align-items:end;margin:20px 0 8px}.hour-bar{flex:1;display:flex;gap:1px;align-items:end;height:100%;min-width:4px}.hour-bar i{flex:1;min-height:0;background:#b7bfb2}.hour-bar i.candidate{background:#9a7940}.hour-bar i.confirmed{background:var(--forest)}.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:.8rem;color:var(--muted)}.legend span:before{content:'';display:inline-block;width:9px;height:9px;margin-right:6px;background:#b7bfb2}.legend .candidate:before{background:#9a7940}.legend .confirmed:before{background:var(--forest)}dialog{border:1px solid var(--line);border-radius:10px;padding:0;background:var(--panel);color:var(--ink);width:min(1100px,96vw);max-height:94vh}dialog::backdrop{background:#17251ce0}.dialog-head{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--line);gap:12px}.dialog-head h2{margin:0;font-size:24px}.image-stage{background:#1d2521;height:min(60vh,650px);overflow:auto;display:flex;align-items:flex-start;justify-content:flex-start}.image-stage img{display:block;max-width:100%;max-height:100%;object-fit:contain;margin:auto;flex-shrink:0}.inspector-body{padding:18px 20px}.inspect-tools{display:flex;gap:10px;flex-wrap:wrap}.action{text-decoration:none;display:inline-flex;align-items:center}[hidden]{display:none!important}footer{padding:22px 0;border-top:1px solid var(--line);font-size:.8rem;color:var(--muted)}noscript p{padding:15px;background:#eee6d4}
@media(min-width:1250px){.gallery{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:1050px){.workspace{grid-template-columns:minmax(0,1fr) 260px;gap:22px}.gallery{grid-template-columns:repeat(2,minmax(0,1fr))}.sidebar{padding-left:20px}}@media(max-width:760px){.workspace{display:block}.sidebar{margin-top:34px;border-left:0;padding-left:0;display:grid;grid-template-columns:1fr 1fr;gap:22px}.gallery{grid-template-columns:repeat(2,minmax(0,1fr))}.edition{max-width:150px;text-align:right}.toolbar{gap:10px}.toolbar label{flex:1;min-width:130px}}@media(max-width:440px){.gallery{grid-template-columns:1fr}.sidebar{display:block}.photo-title{flex-direction:row;justify-content:space-between;gap:12px}.photo-title time{max-width:60%}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}@media print{.toolbar,.pagination,dialog{display:none}.workspace{display:block}.sidebar{border:0}.photo{break-inside:avoid}body{font-size:12pt}}
"""

_JS = r"""
'use strict';
function hourKey(frame) { const t=frame.local || ''; const offset=t.match(/(?:Z|[+-]\d{2}:\d{2})$/); return t.slice(0,13)+(offset ? offset[0] : ''); }
function selectFrames(frames,status,hour) {
  return frames.filter(f=>(!status || (status==='confirmed' ? f.confirmed : status==='unavailable' ? !f.available : f.analysis_status===status)) && (!hour || hourKey(f)===hour));
}
function pageFrames(frames,page,size) { return frames.slice((page-1)*size,page*size); }
function frameLabel(f) { return f.confirmed ? 'Confirmed photograph' : ({bird_candidate:'Provisional candidate',unknown:'Sampled · no boxes / unknown',not_analyzed:'Unsampled',analysis_failed:'Analysis failed'}[f.analysis_status] || 'Sampled · no boxes / unknown'); }
// DOM binding
const model=JSON.parse(document.getElementById('report-data').textContent);
const $=id=>document.getElementById(id);
let page=1; const pageSize=24;
let focusedPhoto=null; let zoom=1;
function node(tag,className,text) { const n=document.createElement(tag); if(className)n.className=className; if(text!==undefined)n.textContent=text; return n; }
function pictureFailure(img) { img.hidden=true; const p=node('span','placeholder','Image unavailable · request photo ID'); img.after(p); }
function card(f) {
  const article=node('article','photo'),button=node('button','preview');
  button.type='button';button.setAttribute('aria-label','Inspect photograph '+f.id);
  const url=f.thumbnail_url || f.original_url;
  if(url) { const img=node('img');img.src=url;img.alt='Photograph '+f.id;img.loading='lazy';img.decoding='async';img.addEventListener('error',()=>pictureFailure(img),{once:true});button.append(img); }
  else button.append(node('span','placeholder','On-Pi original / request photo ID'));
  button.addEventListener('click',()=>inspect(f,button));article.append(button);
  const body=node('div','photo-body'),title=node('div','photo-title');
  title.append(node('strong','',f.id),node('time','',f.local || 'Time unavailable'));body.append(title,node('span','badge',frameLabel(f)));
  if(!f.available)body.append(node('span','badge unavailable','Image unavailable'));
  if(f.export_note)body.append(node('p','note',f.export_note));article.append(body);return article;
}
function update() {
  const matches=selectFrames(model.frames,$('status-filter').value,$('hour-filter').value);
  const pages=Math.max(1,Math.ceil(matches.length/pageSize));page=Math.min(page,pages);
  const gallery=$('gallery');gallery.replaceChildren();
  for(const frame of pageFrames(matches,page,pageSize))gallery.append(card(frame));
  $('empty-results').hidden=matches.length!==0;
  $('result-count').textContent=matches.length ? `${matches.length} of ${model.frames.length} frame records · showing ${(page-1)*pageSize+1}–${Math.min(page*pageSize,matches.length)}` : (model.frames.length ? 'No matching frame records. Try another filter.' : 'No frame records');
  $('page-count').textContent=`Page ${page} of ${pages}`;
  $('previous-page').disabled=page===1;$('next-page').disabled=page===pages;
}
function setZoom(value) {
  zoom=Math.max(1,Math.min(4,value));const img=$('inspect-image');
  img.style.maxWidth=zoom===1 ? '100%' : 'none';img.style.maxHeight=zoom===1 ? '100%' : 'none';
  img.style.width=zoom===1 ? '' : `${zoom*100}%`;
  $('zoom-level').textContent=Math.round(zoom*100)+'%';
  $('zoom-out').disabled=zoom===1;$('zoom-in').disabled=zoom===4;
}
function inspect(f,trigger) {
  focusedPhoto=trigger;$('inspect-title').textContent=f.id+' · '+frameLabel(f);
  $('inspect-details').textContent=`Local: ${f.local || 'unavailable'} · UTC: ${f.utc || 'unavailable'} · Score: ${f.score ?? 'not available'} · Candidate boxes: ${f.detection_count ?? 'not available'}${f.keeper ? ' · Keeper photograph' : ''}. Boxes and scores are provisional, not species or individual identification.`;
  $('inspect-note').textContent=f.export_note || '';
  const url=f.original_url || f.thumbnail_url, img=$('inspect-image');img.hidden=!url;
  if(url){img.src=url;img.alt='Photograph '+f.id;}else img.removeAttribute('src');
  $('inspect-unavailable').hidden=!!url;
  for(const id of ['open-original','download-original']) {const a=$(id);a.hidden=!f.original_url;if(f.original_url)a.href=f.original_url;else a.removeAttribute('href');}
  $('download-original').download=f.id+'.jpg';
  $('zoom-in').hidden=!url;$('zoom-out').hidden=!url;setZoom(1);
  $('inspector').showModal();
}
for(const id of ['status-filter','hour-filter'])$(id).addEventListener('change',()=>{page=1;update();});
$('reset-filters').addEventListener('click',()=>{$('status-filter').value='';$('hour-filter').value='';page=1;update();});
$('previous-page').addEventListener('click',()=>{page--;update();});
$('next-page').addEventListener('click',()=>{page++;update();});
$('close-inspector').addEventListener('click',()=>$('inspector').close());
$('inspector').addEventListener('close',()=>{if(focusedPhoto)focusedPhoto.focus();});
$('zoom-in').addEventListener('click',()=>setZoom(zoom+.5));$('zoom-out').addEventListener('click',()=>setZoom(zoom-.5));
$('inspect-image').addEventListener('error',()=>{$('inspect-image').hidden=true;$('inspect-unavailable').hidden=false;});
$('controls').hidden=false;update();
"""


def render_report(view):
    """Return a complete HTML document, without I/O or mutation of ``view``."""
    data = _payload(view)
    frames = data["frames"]
    confirmed = [f for f in frames if f.get("confirmed")]
    candidates = sum(f.get("analysis_status") == "bird_candidate" for f in frames)
    analyzed = sum(f.get("analysis_status") in ("bird_candidate", "unknown") for f in frames)
    first = next((f.get("local") for f in confirmed), None)
    last = next((f.get("local") for f in reversed(confirmed)), None)
    coverage = view.get("coverage") or {}
    unsampled = sum(f.get("analysis_status") == "not_analyzed" for f in frames)
    failures = sum(f.get("analysis_status") == "analysis_failed" for f in frames)
    estimate = coverage.get("estimated_seconds")
    coverage_details = (
        f"{len(coverage.get('sessions') or [])} coarse session bounds · "
        f"{len(coverage.get('gaps') or [])} reported coverage gaps. "
        f"Estimated session-bound seconds: {_h(estimate) if estimate is not None else 'Unknown'}."
    )
    hours = view.get("hours") or []
    options = "".join(
        f'<option value="{_h(key)}">{_h(label)}</option>'
        for key, label in [
            ("", "All statuses"),
            ("confirmed", "Confirmed photograph"),
            *_LABELS.items(),
            ("unavailable", "Image unavailable"),
        ]
    )
    hour_options = {}
    for f in frames:
        local = f.get("local") or ""
        if len(local) >= 19:
            match = re.search(r"(?:Z|[+-]\d{2}:\d{2})$", local)
            offset = match.group() if match else ""
            key = local[:13] + offset
            hour_options[key] = local[11:13] + ":00 " + offset
    hour_select = "".join(
        f'<option value="{_h(k)}">{_h(v)}</option>' for k, v in sorted(hour_options.items())
    )
    warning_list = "".join(f"<li>{_h(w)}</li>" for w in data["warnings"])
    exported = view.get("exported") or {}
    export_details = "".join(
        f"<dt>{_h(k)}</dt><dd>{_h(v)}</dd>"
        for k, v in exported.items()
        if isinstance(v, (str, int, float))
    )
    max_count = max(
        [1]
        + [h.get("analyzed_frames", 0) or 0 for h in hours]
        + [h.get("candidate_frames", 0) or 0 for h in hours]
        + [h.get("confirmed_frames", 0) or 0 for h in hours]
    )
    bars = ""
    for h in hours:
        bars += (
            '<div class="hour-bar">'
            + "".join(
                f'<i class="{style}" style="height:{max(0, min(100, (h.get(key, 0) or 0) / max_count * 100)):.2f}%"></i>'
                for key, style in [
                    ("analyzed_frames", ""),
                    ("candidate_frames", "candidate"),
                    ("confirmed_frames", "confirmed"),
                ]
            )
            + "</div>"
        )
    activity = _table(
        [
            "Local hour",
            "Inventory",
            "Analyzed",
            "Candidates",
            "Confirmed",
            "Session bounds (seconds)",
        ],
        [
            [
                h.get("label"),
                h.get("inventory_frames", 0),
                h.get("analyzed_frames", 0),
                h.get("candidate_frames", 0),
                h.get("confirmed_frames", 0),
                h.get("session_seconds") if h.get("session_seconds") is not None else "Unknown",
            ]
            for h in hours
        ],
    )
    comparison = view.get("comparison") or []
    comparison_rows = []
    for day in comparison:
        totals = day.get("summary", day)
        comparison_rows.append(
            [
                day.get("date_local"),
                totals.get("inventory_frames", "Unknown"),
                totals.get("analyzed_frames", "Unknown"),
                totals.get("candidate_frames", "Unknown"),
                totals.get("confirmed_frames", "Unknown"),
            ]
        )
    comparison_html = (
        _table(["Date", "Inventory", "Analyzed", "Candidates", "Confirmed"], comparison_rows)
        if comparison_rows
        else '<p class="note">No comparison days supplied.</p>'
    )
    title = data["title"] or "Daily field notes"
    cards = "".join(_card(f) for f in frames[:24])
    empty = " hidden" if frames else ""
    absence = (
        "No confirmed photographs" if not confirmed else f"{len(confirmed)} confirmed photographs"
    )
    groups = view.get("groups") or []
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; connect-src 'none'; img-src data: file: 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; object-src 'none'">
<title>{_h(title)} · BirdWatcher</title><style>{_CSS}</style></head><body>
<a class="skip-link" href="#explore">Skip to photographs</a><div class="shell">
<header><span class="brand">BirdWatcher / Field journal</span><span class="edition">Offline daily report<br>{_h(data["mode"] or "metadata")} edition</span></header>
<main id="explore"><div class="intro"><p class="date-line">{_h(data["date_local"] or "Date unavailable")} · {_h(data["timezone"] or "Timezone unavailable")}</p><h1>{_h(title)}</h1>
<p class="counts">{len(frames)} inventory frames · {analyzed} analyzed · {candidates} provisional candidates · {len(confirmed)} confirmed photographs</p>
<p class="note">{unsampled} unsampled · {failures} analysis failures. All frame records, not just the shortlist. Model boxes are provisional; confirmation means photographic presence, not a distinct bird.</p></div>
<div class="workspace"><section aria-labelledby="gallery-title"><h2 id="gallery-title">Explore photographs</h2>
<div id="controls" class="toolbar" hidden><label for="status-filter">Observation status<select id="status-filter">{options}</select></label>
<label for="hour-filter">Local hour<select id="hour-filter"><option value="">All hours</option>{hour_select}</select></label><button id="reset-filters" type="button">Reset filters</button></div>
<p id="result-count" class="results" role="status" aria-live="polite">{"No frame records" if not frames else f"{len(frames)} frame records · first {min(24, len(frames))} shown"}</p>
<div id="gallery" class="gallery">{cards}</div><div id="empty-results" class="empty"{empty}>No frame records match this selection.</div>
<nav class="pagination" aria-label="Gallery pages"><button id="previous-page" type="button" disabled>Previous</button><span id="page-count">Page 1</span><button id="next-page" type="button" disabled>Next</button></nav>
<noscript><p>JavaScript is disabled. Only the first 24 records are shown; enable JavaScript for all records, filtering, and inspection.</p></noscript></section>
<aside class="sidebar" aria-label="Report context"><section><p class="eyebrow">Photographic evidence</p><h2>What is confirmed</h2><p>{absence}</p><dl><dt>First confirmed (local)</dt><dd>{_h(first or "Not established")}</dd><dt>Last confirmed (local)</dt><dd>{_h(last or "Not established")}</dd></dl><p>Unconfirmed records and no-box results are not evidence of bird absence.</p><p>{len(groups)} estimated UTC-based activity groups, not unique visits or distinct birds. Grouping uses a time-gap heuristic, not continuous observation.</p></section>
<section><p class="eyebrow">Scope &amp; limitations</p><h2>Read with context</h2><p>{_h(coverage.get("note") or "Recording coverage is unknown.")}</p><p>{coverage_details}</p><p>Session bounds include warmup and shutdown; not verified continuous coverage. Coverage gaps do not establish bird absence.</p><p>{_h(data["gallery_limit_note"] or "Image availability is separate from historical observations. Local sources may expire under raw retention.")}</p><ul>{warning_list}</ul><dl>{export_details}</dl></section></aside></div>
<section class="section" aria-labelledby="activity-title"><p class="eyebrow">Secondary activity monitor</p><h2 id="activity-title">Hourly activity</h2><p class="note">Frame counts by local hour and UTC offset; repeated daylight-saving hours remain separate. Session bounds are coarse, not continuous coverage.</p>
<div class="bars" aria-hidden="true">{bars}</div><div class="legend"><span>Analyzed</span><span class="candidate">Provisional candidates</span><span class="confirmed">Confirmed photographs</span></div>{activity}</section>
<section class="section" aria-labelledby="comparison-title"><h2 id="comparison-title">Day comparison</h2><p class="note">Observation counts only. Sampling and recording scope can differ between days.</p>{comparison_html}</section></main>
<footer>BirdWatcher · Local-first photographic records. No species, identities, feeding durations, or absence inferred.</footer></div>
<dialog id="inspector" aria-labelledby="inspect-title"><div class="dialog-head"><h2 id="inspect-title">Photograph inspection</h2><button id="close-inspector" type="button" autofocus>Close</button></div><div class="image-stage"><img id="inspect-image" alt="" hidden><p id="inspect-unavailable" class="placeholder">Image unavailable · On-Pi original / request photo ID</p></div><div class="inspector-body"><p id="inspect-details"></p><p id="inspect-note" class="note"></p><div class="inspect-tools"><button id="zoom-out" type="button" aria-label="Zoom out">−</button><output id="zoom-level" aria-live="polite">100%</output><button id="zoom-in" type="button" aria-label="Zoom in">+</button><a id="open-original" class="action" target="_blank" rel="noopener noreferrer" hidden>Open original</a><a id="download-original" class="action" download hidden>Download original</a></div></div></dialog>
<script id="report-data" type="application/json">{_json(data)}</script><script>{_JS}</script></body></html>'''
