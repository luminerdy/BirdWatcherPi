# BirdWatcherPi — Product and Engineering Specification

Status: Specification v0.3 — keeper-focused photography with approved private daylight/review automation. This separates the public package, deployed operational helpers, and future work; it does not declare all release gates passed. See [TODO.md](TODO.md), [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), and [ARCHITECTURE.md](ARCHITECTURE.md).

## 1. Purpose

Build a Python application that watches a bird feeder with one USB camera and collects good bird photographs automatically. The owner prioritizes sharp, well-exposed keepers and useful variety, not an exhaustive visitor census. Missed images, sampled review, and expiry of ordinary capture history are acceptable. Species identification is a future enhancement, not a prerequisite for useful photographs.

Capture, storage, and NanoDet inference run locally without cloud inference. The approved private workflow additionally uses an external solar ephemeris, a vision-capable AI provider for selected review images, and Telegram delivery. It is not an entirely offline workflow: automatic starts require a validated daylight window, and external review/delivery require their services. Never silently substitute cloud processing for a failed local detector.

Project: BirdWatcherPi. An optional general region may be configured privately to improve species suggestions. Regional information is a hint, never a hard species filter. Do not publish the deployment location, street address, or precise coordinates.

## 2. Requirements and assumptions

### Confirmed by the owner

- Raspberry Pi 5 with 8 GB RAM; one USB camera positioned at a window.
- Python implementation; photographs triggered by movement or bird presence.
- Bird detection is useful for prioritizing review; validated species identification remains desired future work.
- Approved recurring operation begins near sunrise and stops conservatively before sunset; never record after dark.
- Approved bounded evening review selects good originals for a separate keeper archive and a private digest.
- Routine raw history may expire under configured age/quota rules. This is not permission to erase keepers, backups, or unrelated data.
- One camera for the initial release; no new hardware required before testing.

### Target hardware and compatibility checks

- Initial camera target: Logitech HD Pro Webcam C920 or compatible USB camera.
- Verify 1920 × 1080 MJPEG capture, actual frame rate, and available focus controls on the deployment hardware.
- Discover the capture endpoint at setup time; do not publish device identifiers or assume a fixed device number.
- Verify the chosen Python version, dependency/model compatibility, and available storage in a private deployment report.

### Assumptions requiring physical validation

- Verify actual perch distances and focus planes privately; do not publish deployment geometry or infer optical quality from an overview.
- Multiple regions may fit in a view, but acceptable focus at multiple distances is not guaranteed. A single approved priority feeder is sufficient for the keeper goal.
- The window may introduce reflection or glare. Do not assume the observed overview proves bird-level image quality.
- Initial operation is daylight/adequate-light capture. No guaranteed night vision, species accuracy, or real-time inference rate.

## 3. Scope

### Initial capture milestone

Camera setup and test capture; two adjustable feeder regions; motion-triggered buffered image bursts; event metadata; local storage; health/status commands; recovery and bounded resource use.

### Keeper-focused operational milestone

Combine daylight motion capture, rolling raw storage, sampled local bird-candidate analysis, bounded visual review, provenance-verified keeper copies, and a private dated digest. The approved deployment implements these through separate private helpers; the public package does not install them. Scheduled/enabled is not proof of a live recorder or successful delivery.

### Later identification and packaged-release milestone

Package reusable deployment/review tooling and add a validated local species classifier, ranked suggestions, correction/reanalysis interfaces, and field-tested recovery. These are separate from collecting useful keeper photographs and are not claimed complete.

### Explicitly excluded initially

Two-camera support, audio recognition, a web dashboard, live streaming, public remote access, individual-bird recognition, sex/age estimation, and model training remain excluded. The approved private AI-assisted review and Telegram digest are in deployed scope, but are not bundled integrations in a fresh clone. No public photo publication or per-frame cloud inference is authorized.

## 4. Operating pipeline

    Approved daylight supervisor → USB camera — one persistent owner
        ├── downscaled frames → approved-region motion analysis
        ├── bounded full-resolution JPEG prebuffer and burst writer
        └── rolling raw originals + manifests on private storage
                  └── after cutoff and capture idle: sampled local NanoDet
                        → candidate/control sheets + hashed review packet
                        → bounded AI-assisted visual review
                        → verified keeper originals + observations + prepared receipt
                        → private dated Telegram digest

The separate optional shadow CLI has its own durable analysis queue. It is not the private nightly collector. A specialized species classifier, automated quality ranking, and stationary-bird scans remain future work. See the Mermaid diagrams and component map in [ARCHITECTURE.md](ARCHITECTURE.md).

The capture process must not wait for neural inference. Only one worker process performs model inference initially. A disabled, failed, or overloaded model must not stop photographs.

### Camera acquisition

- Start with a requested stream of 1920 × 1080, MJPEG, 15 frames/second. These are tuning defaults, not verified sustained throughput.
- Keep the stream open; do not reopen the camera for each photograph or change resolution per event.
- Prefer a stable /dev/v4l/by-id device path if available. /dev/video0 is only a setup fallback; reject non-capture endpoints.
- Log requested and actual negotiated format, dimensions, and frame rate. Report degraded mode explicitly; never silently upscale or call upscaled images full-resolution captures.
- Expose automatic/manual focus and exposure configuration. Discover valid controls/ranges rather than assuming all cameras support them.
- Discard startup warm-up frames. Detect stale/no-frame conditions and reconnect with capped exponential backoff.
- Release the camera cleanly on shutdown. Provide a documented stop-service-then-test procedure to avoid camera ownership conflicts.

### Focus and composition calibration — first implementation gate

1. Place a detailed stationary object at each expected perch position.
2. Take samples with autofocus, then a manual focus sweep across supported settings.
3. Compare feather-sized texture, sharpness, reflections, and exposure at both spots.
4. Select focus mode and priority region. Store the chosen calibration outside source control if it reveals the private view.
5. If the near spot cannot focus sharply, adjust camera/perch distance and repeat. Do not promise a software or digital-zoom fix for optical focus.
6. User reviews the samples before unattended operation is enabled.

### Motion triggering

Use OpenCV MOG2 background subtraction on downscaled frames, with blur, shadow handling, morphological cleanup, and minimum foreground area. This detects change, not bird identity.

- Support configurable near_feeder and far_feeder regions, with coordinates normalized to [0,1]. Only approved regions need be enabled; the current private setup prioritizes one feeder. Config validation rejects invalid rectangles; the reviewed annotated preview is a private setup workflow, not a bundled calibration command.
- Initial analysis width: 640 pixels; target motion analysis: 8 frames/second.
- Initial trigger: foreground occupies at least 1% of a region in three consecutive analyzed frames. Thresholds are region-configurable and must be tuned with real footage.
- Ignore motion outside the regions. Reset/warm up background after camera reconnection, focus changes, or major exposure changes.
- Suppress near-whole-frame lighting transients with configurable area/change checks. Log suppression decisions.
- A bird arriving before warm-up or remaining motionless can escape motion-only triggering. In the complete release, run a low-frequency presence scan, initially every two seconds, when detector capacity permits. Presence scans are best-effort, never block capture, and must report skipped scans.

### Event lifecycle and image selection

State machine: WARMUP → IDLE → ACTIVE → COOLDOWN; ERROR/RECONNECT can interrupt any state.

- Keep a bounded one-second pre-trigger JPEG buffer, sampled at up to five frames/second.
- On trigger, persist available pre-trigger frames and bounded post-trigger bursts at the configured saved-photo rate. Five frames/second is a package tuning default, not a requirement; the deployed configuration saves at three frames/second while acquisition requests 15 frames/second. Record actual timestamps and missed saves; never duplicate frames to meet counts.
- Motion/presence in either region opens a single event. Store all triggering region IDs rather than creating duplicate simultaneous events.
- Initial event quiet timeout: five seconds; maximum duration: 30 seconds. During a longer event allow additional bursts no more often than every five seconds.
- Cooldown: three seconds after event closure. Renewed activity after cooldown starts a new event.
- Choose keepers for sharpness, usable exposure, pose, and variety during bounded visual review. Automatic sharpness/exposure ranking is future work, not an implemented capture feature. Do not modify or overwrite original photographs with annotations.
- A configured maximum burst count per event prevents unlimited saves. Log every rate-limit decision.
- Long continuous presence produces linked event segments, not a claim of separate bird visits. Event counts are not individual-bird counts.

## 5. Bird detection and species identification

### Model-selection gate

Do not lock a model family or model runtime before an on-device compatibility and performance experiment. Evaluate a lightweight bird-capable detector plus bird-specific classifier; Birder is a candidate framework, not a selected dependency.

For each candidate record source, version, checksum, license for code AND weights, label set, input transform, supported ARM64/runtime/Python combinations, model size, peak memory, and measured inference latency. Verify relevant local species are covered. Prefer a compatible isolated virtual environment over modifying system Python. Do not assume Python 3.13 wheel support.

### Behavior

- Analyze best candidate frames after capture, detect bird bounding boxes, and classify each usable crop with surrounding context.
- Support multiple birds in one image. Store one detection/identification record per bird; do not force one species per event.
- Preserve uncropped originals, crop coordinates, and links from crops to source frames.
- Record detector scores and classifier scores separately. Model scores are not calibrated probabilities or guarantees.
- Keep up to three species candidates, including common/scientific names when supported, raw scores, model/label-map versions, and inference timestamp.
- Emit a species label only when configurable score, top-candidate margin, crop size/quality, and cross-frame agreement checks pass. Initial thresholds are provisional until validated with labeled feeder images.
- Require agreement from at least two usable frames where available; do not silently treat a single-frame result as multi-frame confirmation.
- Otherwise use unknown_bird, no_bird_detected, or analysis_failed as distinct states. A detector miss is not proof that no bird was present.
- Preserve originals during analysis/review, but allow ordinary raw history to expire under the approved retention policy. Model scores do not authorize immediate suppression/deletion. Any future recognition-based rejection policy needs separate approval and validation.
- Location/season may rerank suggestions only if backed by a documented source. Retain raw results and never exclude an unexpected species solely for being unusual locally. No online occurrence lookup is required for the initial release.
- Manual corrections are authoritative annotations stored separately from model outputs. Reanalysis must not overwrite them.

### Queue and overload policy

Persist pending work in SQLite after event files are committed. Use pending/running/completed/failed states, retry limits, and recovery of interrupted jobs. Initial inference backlog cap: 100 events. At cap, continue saving captures, mark additional events analysis_deferred, and increment a visible counter; defer opportunistic presence scans first. Provide an explicit reanalysis command. No unbounded in-memory queues.

## 6. Data and retention

Package example data root: ~/birdwatcher-data, outside the repository; this is not the live deployment path. The deployed recorder uses a guarded private USB photo volume and preserves a separate pre-migration backup. Never infer the active archive from an old health file or a default path.

    YYYY-MM-DD/
      <UTC timestamp>_<unique event ID>/
        originals/*.jpg
        crops/*.jpg
        event.json

- Use collision-resistant IDs, UTC capture timestamps, a privately configured display timezone, and monotonic timing for event intervals. Current capture date folders use UTC; nightly review filters by the privately configured local day. Local-date capture partitioning remains future work. Filenames carry UTC explicitly. Keep deployment timestamps and event records out of the public repository.
- The target event schema includes identity/regions, capture settings, UTC receipt times/source paths, errors, quality metrics, detections, species suggestions, model provenance, and manual corrections. Capture manifests currently provide capture/storage fields; shadow analysis uses separate results. Quality ranking, species fields, and correction interfaces must not be assumed implemented.
- Write files through temporary files plus atomic rename. Recover incomplete events at startup; label them incomplete rather than presenting them as intact.
- Event manifests remain readable without a database or running application. The optional shadow analyzer has a durable SQLite queue; a complete event/species index and migration/backup framework are future work, not current capture dependencies.
- Package retention defaults: oldest eligible events removed after 14 days OR above 5 GiB managed storage, with at least 2 GiB free. The deployed configuration uses 14 days / 40 GiB with the same 2-GiB reserve. Values are configurable and do not guarantee every frame remains available until review.
- Keeper originals live outside the raw-retention root. The finalizer verifies source-byte hashes before copying selected originals. The automatic digest currently inspects up to three originals/crops and selects at most three keepers; the finalizer itself permits at most five. No selection is required when no usable bird photo is confirmed.
- Record packet fingerprint, explicit reviewed/confirmed/best source indices, sampling scope, errors, and observation provenance. A prepared review receipt is not evidence of Telegram delivery. Avoid duplicate reports; uncertain delivery must not trigger blind replay.
- Pinning prevents automatic deletion; active events are never deleted. Delete only managed event directories, never arbitrary files or symlink targets. Account for crops, metadata, temporary files, and index overhead in storage monitoring.
- If pruning cannot restore reserve space, suspend new image writes, keep health reporting alive, and clearly report storage_full. Never erase pinned events automatically.
- Keep logs bounded and rotated. No photos, secrets, model binaries, virtual environments, local database, or private calibration views in Git.

## 7. User interface and configuration

Available package CLI: doctor, snapshot, run, status, events, and optional analyze. These do not install private daylight/review jobs. In particular, run is foreground capture and does not itself enforce a solar cutoff. Operator-managed sessions must remain within approved daylight.

The following is the broader target contract; calibrate, correct, reanalyze, species filtering, and capture-internal analysis remain future work:

- birdwatcher doctor: camera/format/controls, model/runtime checks, storage, config validation.
- birdwatcher snapshot: deliberate test capture when the service is stopped, with chosen settings.
- birdwatcher calibrate: create sample images and ROI preview for user review.
- birdwatcher run: foreground motion capture; any capture-internal queued analysis orchestration is future work.
- birdwatcher status: last frame/event, camera health, queue depth, storage state, inference health.
- birdwatcher events: filter local events by date, species, and analysis state.
- birdwatcher correct: add an identification correction without replacing model results.
- birdwatcher reanalyze: enqueue selected existing events with a selected model version.

TOML configuration groups: camera, motion, regions, capture, detection, classification, storage, logging, location, and runtime. Ship a documented example with calibration-required placeholders, not guessed ROI coordinates. Validate all bounds and writable paths before starting. Version the configuration schema. No GitHub token is needed by the capture service.

## 8. Reliability, privacy, and deployment

- Daylight-only capture: establish the correct local date/timezone and approved daylight window, stop conservatively before sunset, and enforce an absolute deadline independently of relative capture duration. Refuse launch when the window cannot be established or the cutoff has passed. Do not record after dark, including during reliability testing. A sunset-based timer is not a darkness sensor. Recurring capture/review has owner approval and is installed privately; new services, changed integrations, or broader behavior still need approval.
- Run under a dedicated unprivileged service account or the existing non-root user, with camera and data-directory access only as necessary.
- Use one explicitly approved scheduler/supervisor, not competing camera owners. The current deployment uses private Hermes jobs and separate immutable runtime environments, not a bundled systemd installer. A reusable systemd alternative and reboot/rollback validation remain future work. Documentation changes install or enable nothing.
- Core camera capture and local NanoDet must not require cloud inference or silently download dependencies/models. Daylight supervision must refuse launch if it cannot validate the current solar window. External visual review and Telegram delivery may fail independently and must not fabricate results or block the recorder.
- Expose no network listener by default. No uploads to GitHub, Telegram, or a cloud inference service without a separate user-enabled integration.
- Use a hardware-independent library layer and a small Linux/V4L2 adapter so tests need not own the live camera.
- Publish health counters for dropped frames, reconnect attempts, trigger suppressions, disk failures, queue skips, model failures, and identification latency.
- SIGTERM must close the camera and database, finish or mark interrupted writes, and persist outstanding jobs. Restart must recover safely.
- Pin tested dependencies in a reproducible lock file; document the exact supported Pi OS/architecture/Python environment after testing. Review dependency and model licenses before release. Do not assume the repository license covers third-party weights.

## 9. Acceptance criteria

Numerical values below are engineering targets or proposed gates, not measured performance unless explicitly evidenced. Keeper-workflow acceptance is separate from later species-classifier release claims. Coverage/yield benchmarks are optional diagnostic studies, not an owner requirement for exhaustive monitoring.

### A. Calibration and capture

- User approves a real sample from each intended perch distance, or explicitly chooses one sharp priority region and accepts the other as degraded.
- A negotiated 1920 × 1080 capture is verified from image dimensions; inability is reported rather than hidden.
- A scripted test fixture containing an arrival triggers an event and includes a preceding buffered frame when the buffer was populated.
- Controlled motion outside configured regions does not trigger; inside-region motion meeting thresholds does. Test glare/lighting-change fixtures separately.
- Optional coverage benchmark: assess capture yield against 18 of 20 manually marked usable arrivals when such a study is worthwhile. Missing this benchmark does not invalidate a useful keeper collection; report limitations rather than claim an exhaustive census.
- Initial tuning target: no more than five nuisance-only events per hour during a manually reviewed two-hour daylight sample. Report actual conditions and results.

### B. Analysis and uncertainty

- A selected model runs on the actual Pi with an approved license, known labels, and recorded latency/memory. Candidate target: median analysis below ten seconds per event, capture unaffected.
- Evaluate at least 100 locally relevant labeled bird crops where available, with at least 20 examples for each species for which species-specific performance is claimed; do not imply full local coverage from this sample.
- Report top-1 accuracy, precision of accepted labels, abstention rate, per-species results, and detector misses. Tune only on a separate calibration set; keep an untouched evaluation set and avoid putting adjacent frames from one visit in different splits.
- Provisional release gate: at least 90% precision among accepted species labels on that evaluation set. Report sample count and uncertainty; if unmet or data is insufficient, retain experimental suggestions with no verified-accuracy claim. Unknown handling must always work.
- Model unavailable, corrupt frame, multiple birds, unsupported species, disagreement, and low-quality crops have explicit tested outcomes.

### C. Keeper review and delivery

- Review only saved photos after the recorder is idle; require the capture-data lock and bounded worker/runtime budgets.
- Include representative local-model samples and no-candidate controls, then visually inspect the listed contact sheets. Distinguish local inference, thumbnail review, and full-resolution inspection counts. Sampling is acceptable; claiming every frame was reviewed is not.
- Preserve verified selected original bytes outside managed raw cleanup. Decisions must match the packet hash and valid source indices; failed validation must not mutate originals or append invalid observations.
- Make observation logging idempotent, keep uncertain cases separate, and never count frames/boxes as distinct birds. Report review errors and recording gaps without claiming absence.
- Prepare one dated private digest per new packet, with keeper attachments when available. Read the exact prepared receipt; distinguish preparation from delivery acknowledgement and do not blindly resend.

### D. Operational reliability

- Complete at least 24 cumulative hours of daylight-only soak testing across multiple sessions, with the camera stopped outside approved daylight windows, without an unhandled crash or unbounded memory/backlog growth. Record CPU, resident memory, temperature, dropped frames, and queue depth.
- Provisional budget: combined application resident memory below 2 GiB in normal operation. Measure rather than infer from board RAM.
- Camera unplug/replug recovers within 60 seconds after the device becomes available, without duplicate event IDs or a busy retry loop.
- Simulated low-disk, pinned-retention, restart-during-write, and inference-crash tests protect existing photographs and expose health failures.
- Coordinated reboot testing must verify the approved scheduler/supervisor restarts the intended daylight workflow; graceful stop releases the camera. Installed/enabled jobs or a service file alone do not establish reboot recovery. Do not install a competing recorder or reboot without coordination.
- Automated checks verify no credentials or captured photographs are tracked in Git.

## 10. Target implementation structure

    pyproject.toml
    src/birdwatcher/
      cli.py
      config.py
      camera.py
      calibration.py
      motion.py
      events.py
      capture.py
      storage.py
      queue.py
      detection.py
      classification.py
      health.py
      main.py
    config/config.example.toml
    deploy/birdwatcher.service
    tests/unit/
    tests/integration/
    tests/fixtures/
    docs/SPECIFICATION.md
    docs/SETUP.md
    docs/OPERATIONS.md

This is an aspirational module layout, not a directory inventory. Current implemented modules and private helper boundaries are mapped in [ARCHITECTURE.md](ARCHITECTURE.md).

Use pytest with synthetic/replayed frames, fake clocks, a fake camera, temporary storage, and mock model adapters. Test ROI validation, event state transitions, cooldown, prebuffer bounds, burst limits, queue recovery, retention safety, schema handling, and correction preservation before live deployment. Hardware tests remain separate and clearly labeled.

## 11. Delivery sequence and outstanding decisions

The following is the dependency order, not a claim that current work starts from zero. See the implementation plan for completed versus pending steps.

1. Calibration gate: privately verify focus/framing and approve at least one priority feeder region.
2. Capture MVP: configuration, persistent stream, motion detection, prebuffered bursts, event files, storage limits, CLI, and automated tests.
3. Field tuning: label daylight arrivals/nuisance events, measure capture reliability, choose working thresholds.
4. AI experiment and integration: verify runtime/model licenses and compatibility, benchmark the Pi, add asynchronous detection/classification and explicit uncertainty.
5. Operational handoff: retain approved private daylight/review automation while packaging reusable integration and gathering recovery/rollback/cumulative daylight-only soak evidence. Later species validation remains a separate release.

Already decided privately: one priority feeder region with sway allowance, the exercised focus choice, a pinned local NanoDet detector, tested isolated runtimes, guarded USB storage, three saved photos/second, recurring daylight operation, sampled evening review, separate keepers, and rolling raw retention. These are deployment decisions, not portable package defaults.

Still open: validated species model/thresholds, automatic image-quality ranking, reusable calibration/review/deployment tooling, source/runtime reconciliation of the deployed storage-pressure fix, and longer physical recovery/soak evidence. The approved keeper workflow does not authorize new integrations, destructive cleanup, public photographs, or unannounced installation/reboots.

## 12. Primary technical references

These establish available mechanisms, not measured performance on this Pi:

- OpenCV background subtraction tutorial: `https://docs.opencv.org/4.x/d1/dc5/tutorial_background_subtraction.html`
- Birder project and model/inference documentation: `https://birder.gitlab.io/birder/`
- systemd service lifecycle and restart semantics: `https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html`

Implementation must verify hardware capabilities and dynamic properties on the actual deployment. Keep deployment observations and private calibration evidence outside the public repository; publish only sanitized engineering results.
