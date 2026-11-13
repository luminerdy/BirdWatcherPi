# Private daily photographs and activity report

The report is an **offline private gallery plus a sampled-activity view**, separate from the three-photo digest. It does not start a camera, run a new detector, identify individuals, publish photographs, or install a web server.

## What you can inspect

- The complete retained-photo **inventory recorded in the selected packet**, not only the keeper selection. Inventory records do not guarantee that an original still exists at report-build time.
- All saved local-model result records, with provisional candidates distinguished from no-box/unknown results, unsampled frames, failures, and packet-matched visual confirmations.
- Local-hour activity, first/last confirmed photographed presence, and approximate groups of adjacent confirmed photo observations.
- Coarse recording-session bounds and gaps, sampling/error notes, and comparison summaries from other completed packets.

These are photo observations and activity proxies, **not a count of unique birds, exact arrivals/departures, or measured feeding duration**. A model proposal is not confirmation; unknown/unsampled is not absence. Grouping uses a configurable time gap and does not establish that the same bird stayed or returned. The report deliberately keeps source availability, analysis status, and visual confirmation separate.

## Build from a completed packet

From an installed, reviewed package:

```sh
birdwatcher --config "$HOME/.config/birdwatcher/config.toml" report \
  --packet "$HOME/private-review/2030-01-01/packet.json" \
  --receipt "$HOME/private-review-confirmations/2030-01-01/reviewed.json" \
  --output-dir "$HOME/private-reports/2030-01-01"
```

The date/paths above are synthetic examples, not a deployment location or real sighting. `--source-root DIR` can explicitly select the expected capture root instead of the configuration value. It must match the packet. Omit `--receipt` to create a clearly unconfirmed review view; that does not mean no birds were present.

Other options:

- Repeat `--compare-with PACKET` for sampled-activity comparisons. Missing visual-review evidence must not be presented as zero confirmed activity.
- `--visit-gap-seconds 60` controls the photo-group heuristic; the accepted range is 1–3600 seconds. The name is convenient CLI terminology, not a validated visit counter.
- `--no-portable` skips the bounded attachment while retaining the on-device report.

Run `birdwatcher report --help` for the command contract. Output must be outside the archive, packet/receipt inputs, and Git checkouts. Report generation must not rewrite source JPEGs, manifests, packets, receipts, observation logs, or keeper archives.

## Two views, with explicit limits

### On-device gallery

Open the generated `index.html` on the machine holding the photo archive. Filters and pagination let you explore candidate, confirmed, unknown, unsampled, and unavailable records by local hour. Retained originals open at their original resolution; lazy image loading avoids eagerly copying/decoding the full archive. A later raw-retention deletion can make an unarchived original unavailable. Verified archived keeper evidence remains separate.

### Portable offline attachment

The generated portable HTML can be downloaded and opened in a browser without a network connection. It embeds bounded previews and a selection of full-resolution originals, prioritizing keeper/confirmed/candidate images. An original-opening action is shown only when its bytes are embedded; other records identify the photo so the operator can retrieve it from the on-device archive before expiry.

The attachment is **not a copy of every original**. It has a strict 44,000,000-byte delivery ceiling and separate image budgets. Embedded, unavailable, and omitted counts must be visible. No raw host paths, outside-file links, external fonts, CDN scripts, or web requests belong in the portable view. A browser is required for interactive filtering/zoom; a chat application's static document preview may not run those controls.

## Evidence, time and comparisons

- A confirmation is accepted only from a prepared receipt matching the exact packet fingerprint and original source identity/hash/time/index. Prepared still does not prove message delivery.
- Local days/hours follow the packet's IANA timezone; repeated or missing daylight-saving hours must not be silently merged into a fixed 24-hour assumption.
- Overlapping valid session intervals are unioned. Launch/exit bounds include warmup/shutdown and are not proof of continuous per-frame monitoring; absent coverage remains unknown.
- More candidate frames can reflect motion triggering, sampling effort, lighting or false positives. Do not turn a raw candidate histogram into a verified feeding-rate claim or infer normal behavior from sparse days.
- Historical packet counts describe the collection snapshot. Missing/changed/undecodable images at export are labelled separately rather than silently replaced or counted as negative evidence.

## Deployment boundary

The public command builds reports on demand. The approved private deployment additionally uses a source-verified runtime and a bounded bridge to generate the report alongside the existing evening digest. That private integration and its paths/settings are not installed by cloning this repository. The initial real report and subsequent automation must be tested separately from unit fixtures; source reconciliation is not a completed hardware soak or reboot validation.

Report exports are private derived artifacts, not keeper archives or public-repository content. The approved private bridge keeps a hash-backed ownership registry and reclaims registered, unchanged exports older than 14 local calendar days. Modified, unrecognized, aliased or unrelated files are preserved for operator review; keeper archives and raw captures are outside this cleanup root. The on-demand public command does not install that private housekeeping policy. Per-report budgets alone do not imply unlimited storage or retention. See [SPECIFICATION.md](SPECIFICATION.md), [TRACEABILITY.md](TRACEABILITY.md), and [OPERATIONS.md](OPERATIONS.md) for the broader contracts and remaining gates.
