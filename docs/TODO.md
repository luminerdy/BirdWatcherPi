# BirdWatcherPi — Current status and next work

This is the current project tracker. The detailed [implementation plan](IMPLEMENTATION_PLAN.md) describes the full target; an implemented component does not mean every release gate has passed.

## Delivery status

- **Capture baseline:** delivered to `main` through PR #1. Persistent USB capture, diagnostics/snapshots, validated regions, buffered motion bursts, bounded writing, event manifests, retention safeguards, recovery, and health reporting are implemented.
- **Optional shadow analyzer:** submitted in **draft PR #2**, not merged as part of this documentation update. The reviewed source has **139 passing local tests** and independent review approval. It records provisional bird candidates using a pinned, verified local model and a bounded durable queue; it never suppresses or deletes photos.
- **Private field setup:** feeder geometry has been reviewed, a reversible middle-plane focus comparison was exercised, and finite capture sessions with clean automatic stops were verified. Capture configuration, focus samples, observations, and coverage logs remain private.
- **Recognition remains experimental:** real birds and feeder/seed false candidates have both been observed. Model scores are not calibrated probabilities. Unknown results are not empty-feeder assertions, and motion events/boxes are not individual-bird counts.
- **No permanent deployment:** no automatic boot service or daily schedule is installed. One-off session approval is not permanent-operation approval.

## Completed building blocks

- [x] Exercised Python package, CLI, configuration validation, and automated tests.
- [x] Real full-resolution camera snapshots and supervised motion-burst capture.
- [x] Bounded buffers/writer, original JPEG preservation, event lifecycle, and capture health.
- [x] Filesystem recovery/retention tests, including process-interruption and quota-boundary regressions.
- [x] Private region preview/approval workflow and reversible focus experiments; no claim that an integrated calibration UI exists.
- [x] Pinned-model runtime/license feasibility, immutable-buffer loading, and uncertainty-preserving shadow analysis on the PR #2 branch.
- [x] Private prototype sighting and recording-coverage logs; a reusable visit-report CLI is still pending.

## Immediate approval gate

- [ ] Approve and merge PR #2 when desired. Merging source does **not** enable filtering, start a recorder, install a service, or publish private data.

## Prioritized implementation and validation backlog

### P1 — Collect morning/daylight comparison data — issue #3

This is the highest-value next operational step. Compare reviewed morning and afternoon observations over multiple daylight sessions. Keep session approval, a before-dark cutoff, original-frame provenance, coverage windows, and labeled positives/controls. Do not infer a usual visiting pattern from one day or treat recorder-off gaps as bird absence.

### P1 — Validate bird confirmation — issue #4

Use real birds, seeds/hardware, feeder sway, and difficult lighting from the private labeled set. Evaluate held-out examples, preserve unknown/failed states, and test any geometry/temporal rules before adopting a filtering policy. Keep every original during validation; automatic suppression/deletion needs separate approval.

### P1 — Build the local visit-time report — issue #5

Group confirmed observations by the privately configured local timezone, alongside UTC provenance and monitoring coverage. Keep provisional candidates separate. Distinguish first/last photographed presence from actual arrival/departure, mark approximate snapshot times, and avoid counting burst frames or linked segments as distinct visits.

### P2 — Choose representative photos and close-ups — issue #6

Rank useful images for sharpness, exposure, and blur in the bird/feeding plane. Create contextual original-coordinate crops without changing originals, inventing detail through upscaling, or treating a sharpness score as bird confirmation.

### P2 — Add species identification — issue #7

First validate bird detection and crop quality. Then select a licensed, pinned, Pi-compatible classifier, measure actual latency/memory, retain ranked suggestions and unknown outcomes, and evaluate an independent labeled set. Manual corrections must not be overwritten.

### P2 — Daylight scheduling and recovery — issue #8

Add approved daylight-only startup/stop automation with correct date/timezone, validated sunrise/sunset, and an absolute deadline independent of relative duration. Fail closed if the window cannot be established. Test camera disconnect/restart, low disk, model failure, queue bounds, and rollback. Complete longer reliability testing across daylight sessions with the camera off overnight.

## Still outside the completed scope

- Calibrated detection accuracy, independent missed-arrival recall, and a verified filtering threshold.
- Automatic photo suppression/deletion, species recognition, manual correction UI, and best-photo ranking.
- Capture-internal analysis integration, stationary-bird presence scans, and local-date capture partitions.
- Formal configuration-schema versioning and an integrated focus/region calibration command.
- Fully validated recovery on physical hardware, cumulative daylight reliability gates, and approved permanent deployment.

## Operating and privacy rules

- **Daylight only.** Choose conservative before-sunset stops, recompute remaining time after delays/calibration, and distinguish a sunset timer from a darkness sensor. Do not record after dark, including during reliability testing.
- Preserve private photographs and logs outside Git. No passwords, tokens, personal identifiers, locations, device serials, exact sighting times, deployment geometry, or private configuration in public issues/docs.
- Keep required third-party license/attribution notices; those are not deployment identifiers.
- Report local tests and remote CI separately. Passing tests or a model benchmark does not establish field accuracy or authorize unattended capture.
