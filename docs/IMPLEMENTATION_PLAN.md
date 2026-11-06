# BirdWatcherPi — Implementation Plan

Status: Proposed plan v0.1. No application implementation, installation, camera-control changes, GitHub publication, or unattended monitoring is performed by this document.

Source of truth: [SPECIFICATION.md](SPECIFICATION.md), draft v0.1. Where this plan proposes an implementation detail not fixed in that specification, it is provisional and must be validated. All tasks below remain unchecked; the existence of the specification and this plan does not satisfy a runtime acceptance gate.

## 1. Delivery strategy

Deliver a useful motion-triggered camera first, then add local bird/species identification without putting model inference on the capture path. Finish with recovery testing and an explicitly approved unattended installation.

Use small, reviewable vertical slices. For production behavior: write one focused failing test, run it and confirm the expected failure, implement the minimum behavior, rerun it and the regression suite, then refactor. Do not write all tests and all implementation in separate bulk phases. Use real temporary files and SQLite in storage tests; fake only the physical camera, clock, model boundary, and externally induced failures where necessary.

Work on a feature branch once implementation starts. Keep source/config examples/tests/docs in Git; keep photos, local calibration/config, model weights, data/index, environment files, credentials, and virtual environments outside tracked content. Publishing to GitHub is a separate explicit step with remote read-back verification.

### Critical path

P0 foundation → P1 camera/calibration → P2 motion and capture → P3 durable storage/status → P4 field tuning → P7 integrated verification → P8 unattended deployment.

P5 model feasibility can run alongside P2/P3 after its own runtime checks; P6 analysis integration depends on both P3 and a successful P5 decision. The first complete release additionally requires P6 and the identification portion of P7. A motion-only MVP is a useful interim deliverable, not completion of the full specification.

No calendar estimate is promised before camera focus and AI runtime feasibility are tested. Field evaluation depends on actual bird arrivals and the owner's help with perch distances, calibration review, and image labels.

## 2. P0 — Repository, contracts, and reproducible foundation

Dependencies: specification available. No physical camera required for most work.

### Tasks

- [ ] Recheck repository status, available Python interpreters, architecture, OS, free space, camera ownership, and existing tooling. Do not overwrite unrelated changes.
- [ ] Establish a feature branch and safe .gitignore before producing samples or environment files. Inspect the existing repository license; do not replace it.
- [ ] Create pyproject.toml, src/birdwatcher, and unit/integration/fixture directories. Choose a minimal isolated development environment after verifying dependency compatibility. No system-Python replacement.
- [ ] Add the CLI entry point and version/help behavior as the first tested slice.
- [ ] Implement versioned TOML parsing and validation: positive timings, valid resolution/rate, storage constraints, focus-control modes, inference settings, and two calibrated regions. Example regions must be clearly disabled/unconfigured until calibration.
- [ ] Standardize normalized rectangles as x/y/width/height and reject zero area or out-of-bounds coordinates. Document conversion and clipping rules for image crops.
- [ ] Define minimal interfaces for camera frames, UTC/monotonic clock, trigger signals, event IDs, persistent storage, detector, and classifier. Grow interfaces from exercised slices rather than creating unused abstractions.
- [ ] Define frame identity, capture timestamp, negotiated settings, event JSON schema, analysis states, and authoritative manual-correction representation.
- [ ] Add local quality checks for tests, linting/formatting, config examples, and accidental tracked secrets/data. Freeze a compatible environment once exercised.

### Exit evidence

- [ ] A fresh virtual environment installs the project and runs the CLI help and test suite.
- [ ] Tests reject invalid ROIs, unsafe data locations, invalid limits, and unsupported config versions with actionable messages.
- [ ] A documented config example parses but cannot silently start unattended capture with guessed feeder regions.
- [ ] Development setup, actual interpreter/dependency versions, and repeatable check commands are recorded.

Deliverables: package skeleton, configuration layer, CLI baseline, test harness, ignore rules, initial SETUP.md.

## 3. P1 — Persistent camera access and focus calibration

Dependencies: P0. Requires live camera access; coordinate with any other camera owner.

### Tasks

- [ ] Implement a fake-camera snapshot test and the real Linux capture adapter. Compare available capture mechanisms briefly; select the simplest that demonstrates persistent streaming, actual format reporting, and reliable release.
- [ ] Discover the stable camera device path and supported formats/controls. Default requests: 1920 × 1080 MJPEG at 15 fps, subject to actual negotiation.
- [ ] Implement warm-up, one persistent camera owner, frame timestamps/IDs, stale-frame detection, and explicit degraded-format reporting. Do not duplicate frames to meet a rate target.
- [ ] Implement doctor and snapshot commands. A camera lock must prevent the service and calibration/snapshot tools from competing.
- [ ] Add calibration capture with automatic focus and a supported manual sweep. Preserve original control values; restore them on error/cancellation and apply a chosen persistent setting only after review.
- [ ] Generate a private annotated ROI preview plus unmodified test photos. Confirm near/far distances with the owner, including whether the near distance really is 4–6 inches.
- [ ] Have the owner compare the expected bird/perch locations at both distances, including glare and exposure, then choose focus mode and any priority region.

### Exit evidence and stop condition

- [ ] Real sample JPEGs have verified dimensions and capture settings; camera ownership and release are exercised.
- [ ] Samples from both intended perch positions receive approval, or a documented single-priority/degraded compromise is accepted.
- [ ] Calibration settings/regions are valid and stored outside Git.
- [ ] If focus is unacceptable, stop physical deployment and adjust placement/perch distance. Continue isolated software tests if useful, but do not call unattended capture ready.

Deliverables: camera.py, calibration.py, doctor/snapshot/calibrate commands, focus/ROI decision record, private samples.

## 4. P2 — End-to-end motion-triggered photo events

Dependencies: P0; a real field demonstration also requires P1 approval.

Build each slice through frame input → trigger/event behavior → saved photo or observable event output. Do not stop with a detector that only prints motion scores.

### Tasks

- [ ] Build repeatable frame-sequence fixtures for a feeder arrival, outside-region motion, quiet scene, lighting transition, and two simultaneous active regions. Synthetic fixtures test logic, not real bird-detection accuracy.
- [ ] Add downscaling and per-region MOG2 analysis, shadow handling, blur/cleanup, foreground thresholds, and three-frame persistence.
- [ ] Implement warm-up/reset behavior and configurable broad-light-change suppression, with counters for suppressed triggers.
- [ ] Implement the event state machine with an injected monotonic clock: WARMUP, IDLE, ACTIVE, COOLDOWN, and camera-error/reconnect handling.
- [ ] Implement a one-second, five-sample/second JPEG prebuffer, bounded by both frame count and bytes. Never retain an unbounded full-resolution decoded-frame history.
- [ ] Persist pre-trigger frames and up to ten unique post-trigger frames across two seconds at the proposed rate. Preserve original resolution and actual timestamps.
- [ ] Implement shared events across two regions, five-second quiet timeout, 30-second event segmentation, five-second minimum repeat-burst interval, three-second cooldown, and a configurable per-event burst cap.
- [ ] Mark the best photo using documented sharpness/exposure heuristics without changing originals. Treat image-quality scores as heuristics, not proof of a correct species result.
- [ ] Bound capture-to-writer work by count and byte budget. When overloaded, keep acquisition responsive, record missed saves, and mark affected events incomplete; never silently invent saved frames.

### Exit evidence

- [ ] A replayed arrival creates an event with available preceding imagery, unique frame IDs, region IDs, and usable image files.
- [ ] Tests cover exact timing boundaries, overlapping regions, burst caps, cooldown, segmentation, warm-up, and reset after discontinuity.
- [ ] A controlled live trigger produces a viewable full-resolution burst; no AI model is required.

Deliverables: motion.py, events.py, capture.py, runnable foreground capture path and regression fixtures.

## 5. P3 — Durable events, retention, and health

Dependencies: P2's event contract; storage primitives may be developed alongside P2.

### Tasks

- [ ] Implement date/event directory allocation, collision-resistant IDs, atomic image/JSON writes, UTC filenames, and privately configured local folder/display dates. Do not publish deployment timestamps or timezone settings.
- [ ] Add a versioned SQLite index and job schema; migrations must preserve data and create index backups before modifying an existing schema.
- [ ] Define the filesystem/SQLite handoff: create a committed event manifest first, then index/enqueue idempotently. Startup reconciles committed manifests missing from the index and marks interrupted writes incomplete.
- [ ] Add a bounded durable analysis queue with pending/running/completed/failed states, retry limits, stale-job recovery, a 100-event backlog cap, and analysis_deferred handling. Queue execution can use a fake model until P6.
- [ ] Coordinate retention with active captures and worker leases: do not delete an event while it is being written/read. Deleting a retained-out event must remove/cancel its jobs and index references safely. Pinned events remain protected.
- [ ] Implement 14-day/5-GiB proposed retention and 2-GiB free-space reserve, oldest eligible first, with symlink/path-escape protection. Include temporary/crop/index growth in monitoring.
- [ ] Implement storage_full behavior when eligible pruning cannot restore reserve. Protect existing photos and report suspended writes clearly.
- [ ] Add status and event-list commands, bounded logging, last-frame/event health, and queue/dropped-frame/storage/error counters.
- [ ] Handle SIGTERM, camera loss, capped reconnect backoff, and interrupted-job recovery.

### Exit evidence — capture MVP

- [ ] Real motion events are saved, indexed, listable, and viewable without the running application.
- [ ] Restart during write, full-disk simulation, pinned events, symlink escapes, interrupted jobs, and writer overload tests pass using isolated data, never the owner's photo collection.
- [ ] Killing the analysis worker does not stop capture; a disabled model does not prevent capture startup.
- [ ] SETUP.md and OPERATIONS.md explain foreground operation, safe test capture, paths, cleanup, and recovery.

Deliverables: durable motion-only MVP with local storage, health, and recovery. This milestone is not a species-identification release.

## 6. P4 — Real feeder tuning and labeled evidence

Dependencies: P1 approval and P3 MVP. No unattended service enabled automatically.

### Tasks

- [ ] Run a supervised daylight session; inspect missed/false events, glare, exposure, blur, framing, and idle behavior.
- [ ] Collect a manually reviewed two-hour sample and at least 20 visibly usable arrivals when birds provide them. Preserve privacy; keep raw footage and photos outside Git.
- [ ] Tune one setting at a time and record configuration versions and conditions. Separate tuning samples from later evaluation samples.
- [ ] Measure capture yield, nuisance-only events/hour, daily storage growth, dropped frames, and CPU/memory/temperature under the actual capture configuration.
- [ ] Build a private labeling manifest with event-level grouping and reference species labels only when reasonably established; uncertain reference labels must not become ground truth.

### Exit evidence

- [ ] At least 18 of 20 reviewed usable arrivals captured, and proposed nuisance target assessed against no more than five nuisance-only events/hour during the two-hour sample.
- [ ] Publish measured counts and conditions in a sanitized report, or document failures and tune/retest. Lack of bird visits leaves this gate pending, not passed.
- [ ] Review retention defaults against measured usage and user preferences.

Deliverables: working local capture configuration, private labeled samples, sanitized CAPTURE_VALIDATION.md.

## 7. P5 — On-device model feasibility and selection

Dependencies: P0 environment discovery; private calibration images or suitable licensed test images. Can overlap P2/P3 without owning the camera.

This is an evidence-gathering gate, not permission to declare a model selected from documentation alone. Obtain approval before installing substantial runtimes or downloading large weights. Research official model/runtime documentation at execution time.

### Feasibility questions

- [ ] Given the actual Pi environment, can a licensed lightweight detector locate a bird from a saved feeder photo with measured memory/latency?
- [ ] Given a usable bird crop, can a bird-specific classifier return a documented label set and ranked scores on this device?
- [ ] Given capture running concurrently, does inference stay within the provisional memory/latency budget without materially degrading capture?

### Tasks

- [ ] Compare a short list of detector/classifier candidates; include Birder only as a candidate. Inspect code and weight licenses separately, label coverage, preprocessing, ARM64 support, and Python/runtime availability.
- [ ] Use an isolated environment; if the current interpreter is unsupported, test a separate compatible environment rather than modifying system Python. Document whether the worker needs a separate runtime/process protocol.
- [ ] Record exact artifacts/checksums, provenance, model sizes, versions, preprocessing, labels, warm/cold inference times, and peak resident memory.
- [ ] Run multiple representative images plus no-bird, tiny/partial bird, blur, and multiple-bird cases. Repeat with capture active when available.
- [ ] Record VALIDATED, PARTIAL, or INVALIDATED for each feasibility question, with real evidence and a decision. Do not promote disposable experiment code into production without tested reimplementation.

### Exit evidence and fallback

- [ ] Selected detector/classifier artifacts run locally with documented licenses and known labels, or AI feasibility is explicitly unresolved.
- [ ] Measure the candidate median ten-second/event analysis target and combined application 2-GiB resident-memory target. Missing a target requires a documented constrained mode or redesign, not a fabricated pass.
- [ ] If AI is not feasible, retain the useful capture MVP and stop claiming completion of species identification. No automatic cloud substitution or new hardware purchase.

Deliverables: MODEL_DECISION.md, benchmark records, artifact manifest; no weights committed to Git.

## 8. P6 — Integrate asynchronous bird/species analysis

Dependencies: P3 durable queue and successful P5 runtime/model decision.

### Tasks

- [ ] Implement detector/classifier adapters from failing behavioral tests, with a single worker process and explicit startup/readiness failures.
- [ ] Read candidate frames, detect each bird, save contextual crops, and keep source-frame/crop-coordinate links. Preserve multiple birds as separate records.
- [ ] Store separate detector/classifier scores, top-three species candidates, common/scientific names where supplied, label/model versions, quality signals, and timestamps.
- [ ] Implement cross-frame comparison using spatial/temporal consistency; do not combine votes from obviously different birds. When association is ambiguous, keep per-detection suggestions and abstain from a combined identity.
- [ ] Implement configurable score/margin/quality/agreement gates and distinct unknown_bird, no_bird_detected, and analysis_failed outcomes. Represent single-frame evidence explicitly.
- [ ] Add correct and reanalyze CLI operations with immutable original model outputs or versioned revisions; never overwrite manual corrections.
- [ ] Add opportunistic two-second presence scans using the same bounded worker scheduling, not a second camera stream. Share a bounded latest-frame snapshot and prioritize saved-event work; log skipped scans.
- [ ] Test queue cap, retries, worker crash/restart, deferred events, failed/corrupt models, duplicate job execution, and concurrent manual edits/analysis.
- [ ] Leave location-based reranking disabled unless a documented source and reproducible method are selected. Any privately configured region is a hint, not a species whitelist; never publish deployment location settings.

### Exit evidence

- [ ] A real captured event receives reviewable local detections, crops, species suggestions or explicit abstention, and complete provenance.
- [ ] Inference failure and backlog saturation leave capture functioning with visible health degradation.
- [ ] Reanalysis preserves the original photos and manual corrections; multiple birds do not collapse into one forced species label.

Deliverables: integrated local analysis pipeline, species/event inspection and correction commands, offline startup verification.

## 9. P7 — Release verification and failure testing

Dependencies: P4 for field evidence; P6 for a complete release. Capture-only verification may proceed earlier.

### Tasks

- [ ] Run unit/integration suites, lint/config checks, fresh-environment installation, and tracked-secret/data scans. Exercise documented commands rather than assuming help text proves they work.
- [ ] Partition private labels by event/visit grouping into calibration and untouched evaluation sets; do not split neighboring frames from one visit across them.
- [ ] Evaluate at least 100 labeled local bird crops where available. Require at least 20 examples for each species with a species-specific performance claim; otherwise explicitly withhold that claim.
- [ ] Report top-1 accuracy, accepted-label precision, abstention, detector misses, per-species counts/results, and uncertainty. The provisional accepted-label precision gate is 90%; insufficient evidence or failure keeps species suggestions experimental.
- [ ] Preserve out-of-set/unknown samples and test uncertainty behavior; reference labels must be credible and independent of the model being evaluated.
- [ ] Exercise camera unplug/replug, restart during write, disk reserve exhaustion, pin protection, writer/queue saturation, inference crash, clock jumps, and timezone transitions. Recovery target: within 60 seconds after camera availability returns.
- [ ] Run a recorded 24-hour soak with capture and selected analysis active; monitor memory, queue depth, dropped frames, CPU, temperature, logs, disk, and event integrity.
- [ ] Summarize every specification acceptance item as passed/failed/pending with evidence paths. No release gate is passed solely because its code exists.

### Exit evidence

- [ ] VALIDATION_REPORT.md contains actual commands, environment, results, failures, and evidence locations.
- [ ] No unhandled crash or unbounded growth during the soak; any performance or accuracy deviations have an explicit scope decision.
- [ ] The capture-only and complete-release readiness decisions are separate and truthful.

## 10. P8 — Approved unattended deployment and handoff

Dependencies: appropriate P7 readiness gate, owner approval for service installation and reboot testing.

### Tasks

- [ ] Review the final config, privacy behavior, storage policy, selected environment/models, and known limitations with the owner.
- [ ] Install a least-privilege systemd unit using absolute executable/config/data paths, proper camera access, bounded restart behavior, and clean shutdown. Do not run the application as root.
- [ ] Stop foreground capture before service startup; verify a single camera owner and no unexpected network listener.
- [ ] Verify enabled service state, health, camera release after stop, restart recovery, and reboot startup through real read-backs. A reboot requires coordination, not an unannounced command.
- [ ] Document start/stop/status, viewing photos, corrections/reanalysis, retention pinning, backup/restore, updating, and rollback to the previous known-good environment/config.
- [ ] If publication is approved, push only reviewed source/docs/tests/config examples, then read back the exact remote branch/commit and any CI results before claiming publication or CI success.

Deliverables: operating service, SETUP.md, OPERATIONS.md, release notes, validated rollback procedure. Notifications/dashboard remain out of scope.

## 11. Acceptance traceability

- Specification §2 assumptions and §4 focus gate → P1, with explicit owner review.
- §4 camera format/ownership/recovery → P1, P3, P7, P8.
- §4 motion, timing, prebuffer, bursts, segmentation → P2, P4, P7.
- §5 model/license/runtime selection → P5; detections/uncertainty/multiple birds/corrections → P6, P7.
- §5 durable queue/overload and §6 atomic storage/retention → P3, P6, P7.
- §6 timestamps/schema/provenance → P0, P3, P6, P7.
- §7 CLI/config → P0 through P3, P6; exercised in P7.
- §8 offline operation/security/health/shutdown → P0, P3, P6 through P8.
- §9A capture acceptance → P1, P2, P4, P7.
- §9B AI evaluation and uncertainty acceptance → P5 through P7.
- §9C soak/recovery/storage/reboot/credential checks → P3, P7, P8.
- §10 implementation structure/testing and §11 sequence → this entire plan; create modules only as exercised slices need them.

## 12. First implementation session

Start with P0's CLI/config test harness and P1's safe doctor/snapshot path. The first user-visible output should be a verified test photograph plus a clear focus/ROI calibration procedure, not an untested AI installation. Request the perch-distance confirmation when physical calibration becomes necessary; it does not block isolated configuration or event tests.

Plan completion means the document and its traceability are checked. Implementation completion requires actual evidence for every applicable release gate above.
