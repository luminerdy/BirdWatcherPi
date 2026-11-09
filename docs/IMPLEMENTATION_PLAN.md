# BirdWatcherPi — Implementation Plan

Status: Plan v0.3, aligned with [SPECIFICATION.md](SPECIFICATION.md) v0.3 and the owner's keeper-focused goal. This plan distinguishes implemented source, private deployed automation, and unpassed release gates. Documentation updates do not change the recorder, install services, merge code, or publish private data.

## 1. Product priority and implementation boundary

Collect good bird photographs, not every visit. Missed images and sampled review are acceptable. Preserve selected keepers separately and let approved retention reclaim ordinary history. Species identification and exhaustive coverage are not prerequisites for a useful photo collection.

The public branch contains the capture CLI and optional shadow analyzer. The approved deployment adds private daylight/storage supervisors, sampled review, provenance finalization, and Hermes/Telegram orchestration outside this checkout. A fresh clone does not install those helpers or schedules. The deployed recorder also uses a separately tested storage-pressure fix; source/runtime reconciliation remains a packaging task rather than a completed merge.

Architecture and editable Mermaid sources: [ARCHITECTURE.md](ARCHITECTURE.md).

## 2. Current evidence and operating decisions

- [x] Persistent USB capture, validated regions, motion/prebuffered bursts, bounded writing, filesystem manifests/recovery/retention, diagnostics, and health are implemented.
- [x] Private feeder framing/region approval and reversible focus comparison were exercised; an integrated calibration command is not implemented.
- [x] Pinned local NanoDet and a separate bounded durable shadow-analysis queue are implemented on the PR #2 branch. Latest documentation check: **139 repository tests passed locally**; this is not remote CI or a field-accuracy result.
- [x] Approved private recurring daylight capture and evening review/digest jobs are installed and were enabled when inspected. A job's scheduled state does not prove a live recorder, successful next launch, or message delivery.
- [x] Guarded USB migration was verified with matching file sets, sizes, and SHA-256 hashes, while preserving the internal backup. Wrong/absent-volume protection and a lower saved-photo rate were exercised; a short replay is not a full live-camera soak.
- [x] Private collector, scheduler/monitor, and finalizer are implemented and independently reviewed. Latest documentation check: **182 private review tests passed locally** (41 collector, 30 scheduler, 111 finalizer).
- [x] A real sampled review packet was produced with source-preservation checks. This demonstrates the packet path, not exhaustive review or a delivered digest.
- [ ] PR #2 approval/merge, reusable packaged orchestration, species validation, and full hardware reliability evidence remain separate work.

The deployment requests 15 camera frames/second and saves at three photos/second. Raw policy is 14 days / 40 GiB with a 2-GiB free-space reserve; the package example remains 14 days / 5 GiB. Current automatic review uses at most six sheets / 120 shortlisted frames, inspects up to three full-resolution originals/crops, and selects at most three keeper photos. The finalizer itself has a five-keeper ceiling. These are bounded operating budgets, not guarantees that every frame is inspected.

## 3. Delivery sequence

### P0 — Reproducible foundation and contracts

Implemented: package/CLI, isolated tested dependencies, configuration and rectangle validation, privacy-aware ignore rules, fake-camera/clock/replay tests, and local quality checks.

Remaining:
- [ ] Formal configuration schema versioning and supported migrations.
- [ ] Recheck fresh-environment installation and supported runtime combinations for each release.
- [ ] Keep frame identity, UTC receipt time, errors, and model provenance explicit; do not claim sensor-exposure timestamps or universal platform support.

### P1 — Camera, composition, and calibration

Implemented: one persistent camera owner, negotiated capture diagnostics, snapshots, warm-up/reconnect behavior, and a privately approved priority-feeder setup.

Remaining:
- [ ] A reusable focus/ROI calibration command with safe restoration on cancellation.
- [ ] Additional optical/glare/exposure improvements only when actual keeper quality warrants them.

Only approved regions need be enabled. Two possible feeder regions do not require two sharp focal planes or a second camera. Keep calibration images and deployment geometry private.

### P2 — Motion-triggered photographs

Implemented: approved-region MOG2 change detection, bounded JPEG prebuffer, burst/event lifecycle, producer/writer separation, and visible overload/missed-save counters.

Remaining:
- [ ] Automatic quality ranking, if it improves keeper selection over bounded visual review.
- [ ] Optional stationary-bird presence scans only after capacity and behavior are validated.

Motion is not bird confirmation. Never place neural inference on the camera's critical path or use model scores to discard photos without a separately approved policy.

### P3 — Storage, retention, and provenance

Implemented: readable filesystem events/manifests, crash-recovery safeguards, managed-retention limits, health snapshots, and a separate durable SQLite shadow queue. Do not imply a complete species/event database or migration framework exists.

Private deployment adds expected-volume checks, preserved migration backup, separately tested storage-pressure improvements, and a keeper archive outside raw cleanup.

Remaining:
- [ ] Reconcile the recorder's tested storage-pressure fix into reviewed public source without silently replacing deployed environments.
- [ ] Reusable packaging/documentation for volume guards, backup/restore, and rollback.
- [ ] More physical media/power-loss and sustained live-camera evidence; synthetic/replay/process-kill tests are not equivalent.

Retain original bytes during review. Age/quota pruning of eligible raw events is approved; deleting keepers, backups, unknown files, or unrelated photos is not.

### P4 — Keeper quality and field evidence — issues #3, #4, #6

- [x] Supervised field sessions, real bird photographs, and sampled local-analysis/visual review have been exercised.
- [ ] Improve sharpness, exposure, framing, pose variety, and representative selection using real keeper results.
- [ ] Evaluate detector positives and no-candidate controls against feeder hardware, sway, glare, small birds, and difficult lighting.
- [ ] Separate tuning samples from held-out evaluation and keep uncertain labels out of ground truth.
- [ ] Measure storage growth, writer pressure, and missed saves; optimize for useful photos rather than an exhaustive visitor log.

The former 18-of-20-arrivals and nuisance-rate studies are optional diagnostic benchmarks, not keeper-workflow release blockers or evidence of a complete census. Do not infer usual visit patterns from sparse photographs.

### P5 — Local model feasibility and species work — issue #7

- [x] A pinned, licensed NanoDet model runs locally with measured latency/memory and known preprocessing/labels.
- [ ] Choose a species classifier only after crop quality, license, labels, runtime compatibility, and useful local performance are established.
- [ ] Preserve unknown/failed states, separate detector/classifier scores, and immutable human corrections.
- [ ] Before any validated species-accuracy claim, use independent event-grouped labels and report sample sizes, accepted-label precision, abstention, and misses.

No automatic cloud substitution, large runtime installation, or new hardware purchase follows from this plan. The already approved selected-image AI review is a separate external boundary, not a local species model.

### P6 — Bounded evening review, keepers, and digest

Private implementation exists and its 182 tests pass locally. Preserve the existing contract:

1. Wait until cutoff and recorder idle; require the existing capture-data lock and one bounded worker.
2. Sample retained frames, run local NanoDet, and include systematic no-candidate controls.
3. Publish hashed packet, contact sheets, source mapping, errors, and scope atomically.
4. Wake the visual-review agent only for a new stable completed packet; inspect all listed sheets and a bounded number of originals.
5. Bind explicit reviewed/confirmed/best indices to the packet hash; verify source bytes before copying keepers and appending complete idempotent observations.
6. Read the exact prepared receipt, then return one dated private digest with verified attachment paths and honest review/error scope.

Remaining:
- [ ] Package reusable helpers/integration instructions without publishing private settings or credentials.
- [ ] Verify delivery separately when needed: prepared is not delivered, and uncertain delivery must not cause blind duplicate sends.
- [ ] Improve selection quality without changing review into unbounded processing or an exhaustive census.

### P7 — Reliability and release verification — issue #8

- [x] Repeatable capture/analysis and private review regression suites pass as recorded above.
- [ ] Accumulate 24 cumulative daylight-only soak hours with CPU/memory/temperature, queue/writer/storage health, and event-integrity evidence.
- [ ] Complete physical camera disconnect/reconnect, low-disk/volume-removal, clock/timezone, restart, and power-loss validation within approved scope.
- [ ] Keep failures visible and mark gates passed/failed/pending using actual evidence, not implemented code alone.
- [ ] Keep repository tests, private helper tests, remote CI, packet preparation, and delivery evidence distinct.

Species-release validation remains separate from keeper-workflow usefulness. Never record overnight to satisfy a soak target.

### P8 — Approved automation and portable handoff — issue #8

- [x] Private daily arming/daylight supervision and change-gated evening review jobs are installed with owner approval.
- [x] The daylight supervisor validates date/timezone/solar window, pause/storage prerequisites, and a conservative absolute stop deadline.
- [ ] Make deployment reusable from reviewed source; do not imply cloning this repository installs private helpers or credentials.
- [ ] Validate reboot/startup and rollback with coordination. A running schedule is not proof of reboot recovery.
- [ ] If adding a systemd alternative, prevent competing camera owners and do not silently install it beside the current scheduler.

The foreground run CLI does not enforce a solar window itself. Core local capture/model inference does not require cloud inference; valid ephemeris is required for automatic daylight starts, while selected-image AI review and Telegram require their external services.

## 4. Next work and acceptance traceability

Priority is keeper quality and safe repeatable operation. Issues #4/#6 concern confirmation and representative photos; #8 still covers packaging/recovery/soak gaps despite privately deployed scheduling. #3 can supply comparison examples without promising complete coverage. #5 is an optional observation/coverage report, not an exhaustive visitor log; the private finalizer already provides provenance-backed photo observations. #7 remains future species work.

- Specification §§1–4: product priority, composition, camera and motion → P1/P2/P4.
- §5: local-model uncertainty and later species validation → P5/P6.
- §6: rolling raw history, keeper separation, hashes, receipts → P3/P6.
- §§7–8: available versus future CLI, privacy, deployment boundaries → P0/P7/P8.
- §9A: calibration/capture evidence → P1/P2/P4; optional coverage studies are not census requirements.
- §9B: later model/accuracy claims → P5/P7.
- §9C: bounded review, verified keepers and honest delivery → P6.
- §9D: recovery, soak, restart and secret/data protection → P3/P7/P8.

Use tested vertical slices: observe a focused failing regression, implement the minimum change, rerun affected/regression suites, then refactor. Keep hardware-independent fixtures separate from live-camera evidence. A documentation refresh is not a passed implementation gate.
