# BirdWatcherPi

A local-first Python bird-feeder camera project for Raspberry Pi: capture close-up photographs when activity occurs, then attempt bird and species identification without delaying the next photograph.

> **Project status: experimental capture + shadow analysis.** Motion-triggered photography is available, with optional separate-process bird-candidate analysis of saved events and a bounded durable analysis queue. Shadow analysis never filters/deletes captures and does not prove a bird is present or absent. Species identification, automatic calibration, a capture-internal AI worker, and background-service installation remain future work. Field detection accuracy is not established.

## Start here

See [SETUP.md](docs/SETUP.md) for the tested environment, installation, camera checks, and a supervised capture session. See [OPERATIONS.md](docs/OPERATIONS.md) for storage, shutdown, recovery, and current limitations.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install -e . --no-deps
.venv/bin/birdwatcher doctor
```

The example configuration deliberately has no enabled feeder regions. Keep your calibrated settings and photographs outside this repository. Nothing installs or enables an unattended service.

## What the project will do

- Watch one USB camera with two configurable feeder regions.
- Detect movement near the feeder instead of reacting to the whole scene.
- Save full-resolution photo bursts with a short pre-trigger buffer to help capture arrivals.
- Analyze saved images asynchronously to locate birds and suggest species.
- Preserve original photographs and use **unknown bird** when evidence is insufficient.
- Support multiple birds in a frame and retain manual identification corrections.
- Store photographs and event records locally, with configurable retention limits.
- Recover from camera disconnects and report storage, camera, and analysis health.
- Eventually support approved automatic startup through systemd.

This list describes the complete project goal. The status above and operating documentation distinguish the current capture milestone from future identification and deployment features.

## Target hardware

- Raspberry Pi 5 with 8 GB RAM.
- One USB camera; the initial target is a Logitech C920 or compatible camera.
- Adequate local storage and a camera position with a clear view of the feeder.

The first setup task is **focus calibration**. Very close perches must be tested at their actual distances. Two regions in the same picture do not guarantee both will be sharply focused. Requested capture settings start at 1920 × 1080 MJPEG; the application must report what the camera actually negotiates.

No extra hardware purchase, second camera, or cloud service is assumed for the initial release.

## Proposed architecture

```text
USB camera — one persistent owner
    |
    +--> downscaled frames --> feeder-region motion analysis
    |
    +--> bounded pre-trigger buffer
                    |
                    v
             photo burst + event record
                    |
                    v
             bounded, durable work queue
                    |
                    v
          local bird detection and species suggestions
```

Capture must continue if identification is slow, disabled, or unavailable. A proposed lightweight presence scan may supplement motion detection when inference capacity permits.

The initial shadow-mode detector is a pinned OpenCV Zoo NanoDet model, exercised locally through OpenCV DNN. It has produced both correct bird boxes and false positives; scores are not guarantees. This is not a calibrated filtering policy or a species-model selection. See the [model decision](docs/MODEL_DECISION.md) and [shadow-analysis guide](docs/SHADOW_ANALYSIS.md).

## Project documents

- [Product and engineering specification](docs/SPECIFICATION.md) — scope, behavior, data handling, reliability, and acceptance criteria.
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md) — ordered work packages, dependencies, tests, and release gates.
- [Capture validation report](docs/VALIDATION_REPORT.md) — sanitized live-test evidence and remaining acceptance gaps.
- [Bird-presence model decision](docs/MODEL_DECISION.md) — pinned provenance, actual feasibility measurements, and uncertainty.
- [Shadow analysis](docs/SHADOW_ANALYSIS.md) — optional local analysis without changing or filtering photographs.
- [Shadow integration validation](docs/SHADOW_VALIDATION.md) — real execution, private candidate review, and validation boundaries.

The specification defines the intended result. The plan describes how to reach it. Neither document is evidence that the application has been built or benchmarked.

## Roadmap

- [ ] **Foundation:** package structure, configuration validation, CLI, and tests.
- [ ] **Camera calibration:** persistent capture, focus review, and feeder regions.
- [x] **Capture MVP:** motion-triggered buffered photo bursts.
- [ ] **Storage and recovery:** durable events, bounded queues, retention, and health.
- [ ] **Field tuning:** measure missed arrivals and nuisance triggers.
- [x] **Bird-presence feasibility:** exercise a pinned local detector and verify its license; deployment accuracy remains unvalidated.
- [ ] **Species feasibility:** select and test a species classifier.
- [ ] **Analysis integration:** background identification, uncertainty, and corrections.
- [ ] **Release verification:** failure testing, evaluation, and a 24-hour soak.
- [ ] **Approved deployment:** automatic startup and operating/rollback instructions.

A reliable motion-triggered photo recorder is the first useful milestone. Species identification is a later milestone, not a prerequisite for saving pictures.

## Installation and usage

The current CLI provides `doctor`, `snapshot`, `run`, `status`, `events`, and optional `analyze`. Use an isolated virtual environment and the documented commands in [SETUP.md](docs/SETUP.md). Runtime and development version snapshots are supplied in `requirements.txt` and `requirements-dev.txt`. Analysis requires a separately obtained, hash-verified model; no model download happens at capture startup.

Automatic calibration/focus control, correction/reanalysis, species models, and unattended deployment remain future work. The current camera adapter preserves existing focus/exposure controls and does not download models. Event folders currently use UTC dates; configurable local date partitioning remains pending.

## Privacy and repository hygiene

This public repository is for source code, generic configuration examples, tests, and sanitized documentation—not deployment data.

**Do not commit:**

- Passwords, access tokens, API keys, private keys, or credential files.
- Names, personal email addresses, deployment locations, precise coordinates, network addresses, or device identifiers.
- Personal filesystem paths, private configuration, calibration views, captured photos/video/audio, logs, databases, or event metadata.
- Model weights, local virtual environments, or private evaluation datasets.

Keep operational data outside the checkout. Any optional region/timezone configuration stays private. Network uploads and public photo sharing are out of scope unless separately enabled by the operator.

The included `.gitignore` is a safeguard, not a security boundary: review staged changes and commit metadata before publishing. Avoid attaching private diagnostics or photos to public issues.

## Development approach

Implement small vertical slices with tests first: observe the expected failing test, implement the behavior, run the regression suite, then refactor. Keep hardware-dependent checks separate from repeatable unit/integration tests.

Numerical targets in the specification are proposed acceptance criteria, not established results. Field reports must distinguish passed, failed, and pending checks. Model evaluation must report abstentions and detector misses as well as successful classifications.

## Initial non-goals

Multiple cameras, audio identification, a web dashboard, live streaming, individual-bird recognition, cloud inference, and automatic messaging are not included in the first release.

## License

Application code retains the [MIT license](LICENSE). The bundled NanoDet decoder is separately licensed under Apache-2.0, with its license and notices in `third_party/nanodet/`. Package metadata describes the combined distribution as `MIT AND Apache-2.0`; that does not replace the application's MIT license. Optional model weights have their own preserved license and are not bundled. Legal attribution notices are not deployment data and must remain intact.
