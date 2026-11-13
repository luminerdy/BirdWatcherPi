# BirdWatcherPi — Current status and next work

Current tracker, aligned with [SPECIFICATION.md](SPECIFICATION.md) v0.5, [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), and [ARCHITECTURE.md](ARCHITECTURE.md). The goal is **good keeper photographs, not an exhaustive visitor census**. Missed images, sampled review, and expiry of ordinary capture history are accepted.

## Current recovery blockers

**Production capture is manually paused and not restored.** Actual recorder startup still fails with `EIO` replacing production `health.json`; persisted `capturing` is stale. Isolated temporary-file/replayed-writer successes after limited NTFS repair and a replacement driver do not pass production recovery. Historical accomplishments below remain evidence only within their original scope.

- [ ] **P0 / #8:** resolve production filesystem writes, then verify approved supervised daylight recorder startup, saved-JPEG readback, and restart before resuming capture. Preserve originals, keepers, backups, and unknown files.
- [ ] **P0 / #8:** investigate the fixed solar-cache temporary-filename startup failure; concurrent writers remain a hypothesis, not a proven cause.
- [ ] **P1 / #5:** fix private report-helper import-resolution binding, unrelated-artifact adoption/deletion, and historical-receipt symlink gaps; rerun adversarial checks before activation. Automatic report generation and delivery must remain disabled.
- [ ] **P1 / #5:** complete and verify interrupted exporter performance work; partial edits are not a successful export or performance result.

See [OPERATIONS.md](OPERATIONS.md#current-recovery-status) for the recovery boundary.

## Historical delivery status and implementation boundary

- **Public capture baseline:** delivered to main through PR #1; persistent USB capture, diagnostics, validated regions, motion bursts, bounded writing, filesystem recovery/retention, and health.
- **Optional shadow analyzer:** merged into main through PR #2 with owner approval. The capture/shadow baseline passed **139 local tests**, with additional dedicated traceability regressions now part of the repository suite; this is not a remote-CI or detector-accuracy claim.
- **Approved private automation:** recurring daylight capture, evening packet preparation, and change-gated digest jobs are installed and were enabled when inspected. These helpers are outside the checkout; a fresh clone does not install them. Scheduled/enabled is not live-camera or delivery evidence.
- **USB storage:** private guarded-volume migration and full copy verification were completed while preserving the internal backup. The recorder configuration requests three saved photos/second from a requested 15-fps stream; this is not current successful capture. The reviewed pruning-scan fix is now reconciled into source; writer queue/byte and cached storage-full/error health have regression coverage. Live runtime adoption and broader hardware validation are separate.
- **Private sampled review:** collector, scheduler/monitor, and provenance finalizer are implemented and independently reviewed. **182 private review tests passed locally**: 41 collector, 30 scheduler, 111 finalizer. A real packet was produced with source-preservation checks; this is not exhaustive image review or proof of a delivered digest.
- **Selection and retention:** visual review prioritizes sharpness, exposure, pose, and variety. Automatic digest budgets are six sheets / 120 shortlisted frames, up to three full-resolution inspections and three keepers; finalizer maximum is five. Keepers are outside raw cleanup. Deployed raw policy is 14 days / 40 GiB / 2-GiB reserve; package examples use a 5-GiB quota.
- **Recognition remains experimental:** model scores are not calibrated probabilities, candidates are not confirmations, no box/unknown is not absence, and photo observations/segments are not unique birds or visits. A validated species classifier and automatic quality ranking are not implemented.

## Completed building blocks

- [x] Exercised package, CLI, configuration/region validation, and capture/analysis tests.
- [x] Real full-resolution snapshots and bounded motion-triggered event capture.
- [x] Storage recovery/retention and process-interruption regressions; health and overload reporting.
- [x] Private reviewed feeder geometry/focus workflow; no integrated calibration UI claim.
- [x] Pinned local-model provenance/license/runtime feasibility and separate shadow queue delivered through merged PR #2.
- [x] Approved private daylight scheduling with solar/pause/storage guards and an absolute before-sunset deadline.
- [x] Guarded USB copy/verification, preserved backup, and lower-rate write replay.
- [x] Private sampled candidate/control packet creation and bounded visual-review/finalizer workflow.
- [x] Separate verified keeper archive, idempotent photo-observation logging, and prepared receipts.
- [x] Mermaid system/lifecycle diagrams and deployed-versus-packaged component outline.

## Requirement coverage and verification

See [TRACEABILITY.md](TRACEABILITY.md) and its [machine-readable registry](traceability.json). Stable IDs distinguish implemented, partial, planned, policy, and excluded requirements, with separate automated-test and field-evidence statuses. Private-only evidence is not reproducible public test coverage. An integrity pass means the map is complete and its references resolve, not that every feature or release gate is complete.

## Approval and packaging gates

- [x] PR #2 merged into main with owner approval. Source merge does not enable filtering or change private schedules/runtime environments.
- [x] Reconcile the exact reviewed recorder storage-pressure fix into source and add bounded cached writer/storage-health fields.
- [ ] Package reusable daylight/storage/review integration without secrets, private geometry, or personal paths.
- [ ] Complete coordinated reboot/rollback and longer physical recovery/soak evidence. Do not claim a fully validated unattended release from scheduled jobs alone.

## Prioritized work and issue mapping

### P1 — Improve confirmation and keeper quality — issues #4 and #6

Use actual bird photographs and systematic no-candidate controls to assess false candidates/misses, feeder sway, lighting, blur, and small/partial birds. Choose useful sharp photos with variety; optional original-coordinate crops must preserve originals and not invent detail through upscaling. Automatic quality scoring is future work. The existing sampled visual-review path is useful without being exhaustive.

### P0 — Recovery; subsequent portable automation — issue #8

Private daily scheduling is implemented, but capture remains manually paused and production startup fails; scheduling is not recovery proof. The recorder pruning-scan fix is reconciled into source. Remaining work includes reusable deployment/volume guards, runtime adoption verification, recovery and rollback, sustained daylight soak, and coordinated reboot validation. The foreground CLI has no built-in solar guard; never bypass daylight constraints or install a competing recorder.

### P2 — Comparison photographs, not a census — issue #3

Morning/afternoon examples may improve composition and selection when useful. Preserve provenance and sampling/error context. Complete arrival coverage and usual visiting-pattern estimates are not owner requirements; sparse photos do not support them.

### P1 — Approved daily gallery and activity report — issue #5

The owner approved a private browsable daily report alongside the short digest. Its source is implemented locally but unactivated; automatic generation and delivery must remain disabled pending the security fixes above. Public packet/receipt normalization and offline rendering expose the full inventory and model results, not just the three keepers. Validate bounded portable export, original/keeper availability, sampled hourly comparisons, first/last confirmed photographs and UTC-gap photo groups. Keep confirmation separate from candidates and label session bounds, unknown coverage and sampling limits. Groups are not actual visits or unique birds.

- [ ] Verify a real saved-day export in desktop/mobile browsers and source-preservation checks.
- [ ] After security fixes and adversarial verification, verify the source-pinned private daily-generation bridge and bounded attachment integration without assuming activation or delivery.
- [ ] Observe the first scheduled report delivery separately from prepared artifacts.

See [DAILY_REPORT.md](DAILY_REPORT.md). Individual recognition remains a later experimental idea, not this milestone.

### P2 — Future species classifier — issue #7

Validate license/runtime/labels, crop quality, measured resources, and an independent labeled set before accuracy claims. Preserve ranked suggestions, abstention, and authoritative manual corrections. The approved external visual-review provider is not a validated local species classifier.

## Remaining limitations

- Calibrated detection/species accuracy, automatic recognition-based suppression, correction/reanalysis UI, stationary-bird scans, local-date capture partitions, formal config-schema versioning, and an integrated calibration command.
- Portable packaged private orchestration, complete event-database/migration tooling, and automatic quality ranking.
- Full physical power-loss/camera-recovery/soak/reboot evidence. Process-kill and synthetic tests do not establish all hardware outcomes.
- A prepared receipt is not message-delivery proof; uncertain delivery must not be blindly replayed.

## Operating and privacy rules

- **Daylight only**, including tests. Validate the local date/timezone and solar window, stop conservatively before sunset, and fail closed when prerequisites cannot be established. A sunset timer is not a darkness sensor.
- Raw-history age/quota pruning is approved. Review itself must not mutate originals or wipe keeper archives, backups, unrecognized data, or unrelated files. A recognition-based rejection policy needs separate approval.
- Capture/storage/NanoDet are local. Selected review images/context go to the configured AI provider and selected keepers to private Telegram; do not claim all processing is offline or that every frame is uploaded.
- Keep photos, logs, exact sighting times, names/locations, identifiers, credentials, calibration geometry, and deployment configuration outside public Git/issues. Preserve required third-party legal notices.
- Test counts, remote CI, live recorder health, prepared packets, and delivery are separate evidence. A job list or stale health snapshot is not camera liveness.
