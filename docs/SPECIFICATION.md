# BirdWatcherPi — Product and Engineering Specification

Status: Draft v0.2 — full target specification with daylight-only operation clarified. This is not a claim that every requirement is implemented or validated; see [TODO.md](TODO.md) for the current delivered subset and remaining work.

## 1. Purpose

Build a Python application that watches a backyard bird feeder with one USB camera, captures useful close-up bird photographs automatically, and attempts to identify the species without interrupting capture. It must keep working locally without a cloud service or Internet connection after installation and model download.

Project: BirdWatcherPi. An optional general region may be configured privately to improve species suggestions. Regional information is a hint, never a hard species filter. Do not publish the deployment location, street address, or precise coordinates.

## 2. Requirements and assumptions

### Confirmed by the owner

- Raspberry Pi 5 with 8 GB RAM; one USB camera positioned at a window.
- Python implementation; photographs triggered by movement or bird presence.
- Bird detection and species identification are desired.
- One camera for the initial release; no new hardware required before testing.

### Target hardware and compatibility checks

- Initial camera target: Logitech HD Pro Webcam C920 or compatible USB camera.
- Verify 1920 × 1080 MJPEG capture, actual frame rate, and available focus controls on the deployment hardware.
- Discover the capture endpoint at setup time; do not publish device identifiers or assume a fixed device number.
- Verify the chosen Python version, dependency/model compatibility, and available storage in a private deployment report.

### Assumptions requiring physical validation

- The owner's description is interpreted as a near feeding spot 4–6 INCHES away and a farther spot approximately 12 inches away. Confirm units and measure from the lens.
- Both spots can be included in the same camera view; acceptable focus at both distances is NOT established.
- The window may introduce reflection or glare. Do not assume the observed overview proves bird-level image quality.
- Initial operation is daylight/adequate-light capture. No guaranteed night vision, species accuracy, or real-time inference rate.

## 3. Scope

### Initial capture milestone

Camera setup and test capture; two adjustable feeder regions; motion-triggered buffered image bursts; event metadata; local storage; health/status commands; recovery and bounded resource use.

### First complete release

Add a local bird detector and local species classifier, an asynchronous analysis queue, ranked identification candidates, unknown handling, user corrections, automatic startup, and a field-tested operating configuration.

### Explicitly excluded initially

Two-camera support, audio recognition, cloud inference, automatic Telegram delivery, a web dashboard, live streaming, remote network access, individual-bird recognition, sex/age estimation, and model training. Notifications and a gallery can be separate later features. No automatic publication of photographs.

## 4. Operating pipeline

    USB camera — one persistent owner
        ├── downscaled frames → region motion analysis
        ├── bounded full-resolution JPEG rolling buffer
        └── event capture → originals + metadata → durable analysis queue
                                                   ├── bird detection and crops
                                                   ├── species classification
                                                   └── identification metadata

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

- Two user-calibrated regions: near_feeder and far_feeder; coordinates normalized to [0,1]. Setup validates nonzero in-bounds rectangles and generates an annotated preview.
- Initial analysis width: 640 pixels; target motion analysis: 8 frames/second.
- Initial trigger: foreground occupies at least 1% of a region in three consecutive analyzed frames. Thresholds are region-configurable and must be tuned with real footage.
- Ignore motion outside the regions. Reset/warm up background after camera reconnection, focus changes, or major exposure changes.
- Suppress near-whole-frame lighting transients with configurable area/change checks. Log suppression decisions.
- A bird arriving before warm-up or remaining motionless can escape motion-only triggering. In the complete release, run a low-frequency presence scan, initially every two seconds, when detector capacity permits. Presence scans are best-effort, never block capture, and must report skipped scans.

### Event lifecycle and image selection

State machine: WARMUP → IDLE → ACTIVE → COOLDOWN; ERROR/RECONNECT can interrupt any state.

- Keep a bounded one-second pre-trigger JPEG buffer, sampled at up to five frames/second.
- On trigger, persist available pre-trigger frames and up to ten post-trigger frames over two seconds at a five-frame/second target. Record actual timestamps and missing frames; do not duplicate frames to meet counts.
- Motion/presence in either region opens a single event. Store all triggering region IDs rather than creating duplicate simultaneous events.
- Initial event quiet timeout: five seconds; maximum duration: 30 seconds. During a longer event allow additional bursts no more often than every five seconds.
- Cooldown: three seconds after event closure. Renewed activity after cooldown starts a new event.
- Rank burst images for sharpness and usable exposure; retain originals and mark a best-image candidate. Do not modify or overwrite original photographs with annotations.
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
- Preserve unconfirmed motion events initially to inspect false negatives. A later user-enabled pruning policy may change that.
- Location/season may rerank suggestions only if backed by a documented source. Retain raw results and never exclude an unexpected species solely for being unusual locally. No online occurrence lookup is required for the initial release.
- Manual corrections are authoritative annotations stored separately from model outputs. Reanalysis must not overwrite them.

### Queue and overload policy

Persist pending work in SQLite after event files are committed. Use pending/running/completed/failed states, retry limits, and recovery of interrupted jobs. Initial inference backlog cap: 100 events. At cap, continue saving captures, mark additional events analysis_deferred, and increment a visible counter; defer opportunistic presence scans first. Provide an explicit reanalysis command. No unbounded in-memory queues.

## 6. Data and retention

Default data root: ~/birdwatcher-data, outside the repository.

    YYYY-MM-DD/
      <UTC timestamp>_<unique event ID>/
        originals/*.jpg
        crops/*.jpg
        event.json

- Use collision-resistant IDs, UTC capture timestamps, a privately configured display timezone, and monotonic timing for event intervals. Date folders use the configured local date; filenames carry UTC explicitly. Keep deployment timestamps and event records out of the public repository.
- event.json records schema version, event/segment IDs, region IDs, trigger reason, camera settings, image timestamps/paths, image-quality metrics, detections, species candidates, analysis status/errors, model provenance, and manual corrections.
- Write files through temporary files plus atomic rename. Recover incomplete events at startup; label them incomplete rather than presenting them as intact.
- SQLite indexes events and durable jobs; event files remain readable without the application. Record schema migrations and back up the index before migrations.
- Initial retention defaults: oldest eligible events removed after 14 days OR above 5 GiB managed storage. Keep at least 2 GiB free on the filesystem. Values are configurable.
- Pinning prevents automatic deletion; active events are never deleted. Delete only managed event directories, never arbitrary files or symlink targets. Account for crops, metadata, temporary files, and index overhead in storage monitoring.
- If pruning cannot restore reserve space, suspend new image writes, keep health reporting alive, and clearly report storage_full. Never erase pinned events automatically.
- Keep logs bounded and rotated. No photos, secrets, model binaries, virtual environments, local database, or private calibration views in Git.

## 7. User interface and configuration

Planned CLI contract — these commands are NOT implemented yet:

- birdwatcher doctor: camera/format/controls, model/runtime checks, storage, config validation.
- birdwatcher snapshot: deliberate test capture when the service is stopped, with chosen settings.
- birdwatcher calibrate: create sample images and ROI preview for user review.
- birdwatcher run: foreground capture and queued analysis orchestration.
- birdwatcher status: last frame/event, camera health, queue depth, storage state, inference health.
- birdwatcher events: filter local events by date, species, and analysis state.
- birdwatcher correct: add an identification correction without replacing model results.
- birdwatcher reanalyze: enqueue selected existing events with a selected model version.

TOML configuration groups: camera, motion, regions, capture, detection, classification, storage, logging, location, and runtime. Ship a documented example with calibration-required placeholders, not guessed ROI coordinates. Validate all bounds and writable paths before starting. Version the configuration schema. No GitHub token is needed by the capture service.

## 8. Reliability, privacy, and deployment

- Daylight-only capture: establish the correct local date/timezone and approved daylight window, stop conservatively before sunset, and enforce an absolute deadline independently of relative capture duration. Refuse launch when the window cannot be established or the cutoff has passed. Do not record after dark, including during reliability testing. A sunset-based timer is not a darkness sensor; recurring schedules/service installation still need approval.
- Run under a dedicated unprivileged service account or the existing non-root user, with camera and data-directory access only as necessary.
- Install a systemd service with bounded restart-on-failure behavior. No service is enabled as part of writing this specification.
- Camera capture and local identification must work offline once dependencies/models are installed; startup must not silently download packages or models.
- Expose no network listener by default. No uploads to GitHub, Telegram, or a cloud inference service without a separate user-enabled integration.
- Use a hardware-independent library layer and a small Linux/V4L2 adapter so tests need not own the live camera.
- Publish health counters for dropped frames, reconnect attempts, trigger suppressions, disk failures, queue skips, model failures, and identification latency.
- SIGTERM must close the camera and database, finish or mark interrupted writes, and persist outstanding jobs. Restart must recover safely.
- Pin tested dependencies in a reproducible lock file; document the exact supported Pi OS/architecture/Python environment after testing. Review dependency and model licenses before release. Do not assume the repository license covers third-party weights.

## 9. Acceptance criteria

All numerical values below are engineering targets or proposed release gates, not current measured performance.

### A. Calibration and capture

- User approves a real sample from each intended perch distance, or explicitly chooses one sharp priority region and accepts the other as degraded.
- A negotiated 1920 × 1080 capture is verified from image dimensions; inability is reported rather than hidden.
- A scripted test fixture containing an arrival triggers an event and includes a preceding buffered frame when the buffer was populated.
- Controlled motion outside configured regions does not trigger; inside-region motion meeting thresholds does. Test glare/lighting-change fixtures separately.
- At least 18 of 20 manually marked, visibly usable real feeder arrivals produce an event. Record missed arrivals and false triggers; do not claim this covers all weather/seasons.
- Initial tuning target: no more than five nuisance-only events per hour during a manually reviewed two-hour daylight sample. Report actual conditions and results.

### B. Analysis and uncertainty

- A selected model runs on the actual Pi with an approved license, known labels, and recorded latency/memory. Candidate target: median analysis below ten seconds per event, capture unaffected.
- Evaluate at least 100 locally relevant labeled bird crops where available, with at least 20 examples for each species for which species-specific performance is claimed; do not imply full local coverage from this sample.
- Report top-1 accuracy, precision of accepted labels, abstention rate, per-species results, and detector misses. Tune only on a separate calibration set; keep an untouched evaluation set and avoid putting adjacent frames from one visit in different splits.
- Provisional release gate: at least 90% precision among accepted species labels on that evaluation set. Report sample count and uncertainty; if unmet or data is insufficient, retain experimental suggestions with no verified-accuracy claim. Unknown handling must always work.
- Model unavailable, corrupt frame, multiple birds, unsupported species, disagreement, and low-quality crops have explicit tested outcomes.

### C. Operational reliability

- Complete at least 24 cumulative hours of daylight-only soak testing across multiple sessions, with the camera stopped outside approved daylight windows, without an unhandled crash or unbounded memory/backlog growth. Record CPU, resident memory, temperature, dropped frames, and queue depth.
- Provisional budget: combined application resident memory below 2 GiB in normal operation. Measure rather than infer from board RAM.
- Camera unplug/replug recovers within 60 seconds after the device becomes available, without duplicate event IDs or a busy retry loop.
- Simulated low-disk, pinned-retention, restart-during-write, and inference-crash tests protect existing photographs and expose health failures.
- Reboot starts the enabled service; graceful stop releases the camera. These are tested only after explicit installation, not merely by writing a service file.
- Automated checks verify no credentials or captured photographs are tracked in Git.

## 10. Implementation structure

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

Use pytest with synthetic/replayed frames, fake clocks, a fake camera, temporary storage, and mock model adapters. Test ROI validation, event state transitions, cooldown, prebuffer bounds, burst limits, queue recovery, retention safety, schema handling, and correction preservation before live deployment. Hardware tests remain separate and clearly labeled.

## 11. Delivery sequence and outstanding decisions

1. Calibration gate: confirm distance units; sample both perches; choose camera placement/focus and actual ROI rectangles.
2. Capture MVP: configuration, persistent stream, motion detection, prebuffered bursts, event files, storage limits, CLI, and automated tests.
3. Field tuning: label daylight arrivals/nuisance events, measure capture reliability, choose working thresholds.
4. AI experiment and integration: verify runtime/model licenses and compatibility, benchmark the Pi, add asynchronous detection/classification and explicit uncertainty.
5. Operational release: daylight-only systemd/scheduling installation with approval, recovery tests, cumulative daylight-only soak, documented installation and identification results.

Decisions deliberately left open: exact perch distances, acceptable near/far focus trade-off, ROI geometry, model/weights/runtime selection, calibrated identification thresholds, tested Python environment, and storage values after observing daily usage. This draft proposes defaults; it does not authorize installing dependencies, changing camera controls, enabling a service, or publishing files/photos.

## 12. Primary technical references

These establish available mechanisms, not measured performance on this Pi:

- OpenCV background subtraction tutorial: `https://docs.opencv.org/4.x/d1/dc5/tutorial_background_subtraction.html`
- Birder project and model/inference documentation: `https://birder.gitlab.io/birder/`
- systemd service lifecycle and restart semantics: `https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html`

Implementation must verify hardware capabilities and dynamic properties on the actual deployment. Keep deployment observations and private calibration evidence outside the public repository; publish only sanitized engineering results.
