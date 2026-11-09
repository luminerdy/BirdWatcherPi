# BirdWatcherPi

A local-first Python bird-feeder camera project for Raspberry Pi: collect good bird photographs without delaying capture. Prioritize sharp, well-exposed keepers and variety, not an exhaustive visitor census.

> **Project status: experimental capture + shadow analysis, with approved private keeper automation.** This branch provides motion photography and optional separate-process local bird-candidate analysis. The deployed setup adds daylight scheduling, guarded USB storage, sampled evening visual review, a separate keeper archive, and a private Telegram digest through helpers outside this checkout. A fresh clone installs none of those private jobs. Recognition accuracy, validated species classification, automatic quality ranking/calibration, and a fully validated portable deployment remain incomplete.

## Start here

See [SETUP.md](docs/SETUP.md) for the tested environment, installation, camera checks, and a supervised capture session. See [OPERATIONS.md](docs/OPERATIONS.md) for storage, shutdown, recovery, and current limitations.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install -e . --no-deps
.venv/bin/birdwatcher doctor
```

The example configuration deliberately has no enabled feeder regions. Keep your calibrated settings and photographs outside this repository. Nothing installs or enables an unattended service.

## Product goals and release boundary

- Watch one USB camera with two configurable feeder regions.
- Detect movement near the feeder instead of reacting to the whole scene.
- Save full-resolution photo bursts with a short pre-trigger buffer to help capture arrivals.
- Prioritize sampled saved images with local bird-candidate analysis; validated species classification is later work.
- Preserve original photographs and use **unknown bird** when evidence is insufficient.
- Support multiple birds in a frame and retain manual identification corrections.
- Keep rolling raw photographs/events under configurable retention, with selected keeper originals archived separately.
- Recover from camera disconnects and report storage, camera, and analysis health.
- Support approved daylight automation; private Hermes supervision exists, while a portable packaged installer/systemd alternative remains future work.

These goals include both implemented and future features; they are not a completed-release checklist. Missing images and sampled review are accepted. The status and architecture distinguish public package behavior from private deployment and later species/correction features.

## Target hardware

- Raspberry Pi 5 with 8 GB RAM.
- One USB camera; the initial target is a Logitech C920 or compatible camera.
- Adequate local storage and a camera position with a clear view of the feeder.

The first setup task is **focus calibration**. Very close perches must be tested at their actual distances. Two regions in the same picture do not guarantee both will be sharply focused. Requested capture settings start at 1920 × 1080 MJPEG; the application must report what the camera actually negotiates.

Core photography and NanoDet run locally without a second camera or per-frame cloud inference. The approved private workflow uses an external solar ephemeris, selected-image AI review, and Telegram; do not describe the entire deployment as offline.

## Architecture

See [Architecture and how it works](docs/ARCHITECTURE.md) for the **Mermaid system diagram**, **daily lifecycle sequence**, component map, and operational outline. Editable sources: [system diagram](docs/ARCHITECTURE.mmd) and [daily lifecycle](docs/DAILY_LIFECYCLE.mmd).

- **Daylight capture:** one USB camera stream, approved-region motion detection, a short pre-trigger buffer, and a bounded full-resolution writer.
- **Rolling storage:** raw JPEGs, event manifests and health; configured managed-history cleanup is separate from the keeper archive.
- **Evening review:** sampled local bird-candidate analysis plus no-candidate controls, followed by bounded AI-assisted visual confirmation.
- **Keepers and delivery:** verified original copies, idempotent observations, and one private digest per new review packet.

The core capture and optional shadow-analysis components are in this repository. The approved deployed workflow adds **private daylight/review/Hermes orchestration outside the checkout**; a fresh clone does not install those helpers, schedules or credentials. The architecture document makes that implementation boundary and the external AI/Telegram data boundary explicit.

Capture must not wait for identification. A specialized species classifier and a lightweight stationary-bird presence scan remain future work.

The initial shadow-mode detector is a pinned OpenCV Zoo NanoDet model, exercised locally through OpenCV DNN. It has produced both correct bird boxes and false positives; scores are not guarantees. This is not a calibrated filtering policy or a species-model selection. See the [model decision](docs/MODEL_DECISION.md) and [shadow-analysis guide](docs/SHADOW_ANALYSIS.md).

## Project documents

- [Architecture and how it works](docs/ARCHITECTURE.md) — Mermaid system/lifecycle diagrams, deployed-vs-packaged scope, privacy boundaries, and operating outline.
- [Product and engineering specification](docs/SPECIFICATION.md) — stable requirement IDs, scope, behavior, reliability, and acceptance criteria.
- [Requirement-to-feature traceability](docs/TRACEABILITY.md) — implementation/test/field status, exact source/test references, evidence, issue gaps, and reverse indexes; [machine-readable registry](docs/traceability.json).
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md) — ordered work packages, dependencies, tests, and release gates.
- [Current status and prioritized to-do list](docs/TODO.md) — completed building blocks, merged source, and remaining work tracked in issues #3–#8.
- [Capture validation report](docs/VALIDATION_REPORT.md) — sanitized live-test evidence and remaining acceptance gaps.
- [Bird-presence model decision](docs/MODEL_DECISION.md) — pinned provenance, actual feasibility measurements, and uncertainty.
- [Shadow analysis](docs/SHADOW_ANALYSIS.md) — optional local analysis without changing or filtering photographs.
- [Shadow integration validation](docs/SHADOW_VALIDATION.md) — real execution, private candidate review, and validation boundaries.

The specification defines the intended result. The plan describes how to reach it. Neither document is evidence that the application has been built or benchmarked.

## Roadmap

Implemented building blocks are not the same as a fully validated release:

- [x] **Capture baseline:** Python package/CLI, validated regions, persistent capture, buffered photo bursts, bounded writing, storage safeguards, recovery tests, and health.
- [x] **Private setup workflow:** region review and reversible feeding-plane focus experiments; an integrated calibration UI remains pending.
- [x] **Shadow analysis delivered through PR #2:** pinned local model, durable bounded analysis queue, uncertainty/provenance, and 139 capture/shadow baseline tests; now merged into main. A separate traceability test suite checks the requirement registry.
- [x] **Private daylight/review automation:** owner-approved schedules, solar/storage guards, sampled candidate/control packets, verified keeper finalization, and change-gated digest preparation; 182 private review tests passed locally.
- [x] **Private rolling storage:** verified USB migration with preserved backup; selected keeper archive stays outside raw cleanup.
- [x] **PR #2 merged into main** with owner approval. Merging source does not authorize filtering, change the running recorder, or replace private schedules.
- [ ] **P1 / #4 and #6:** improve confirmation, keeper quality/variety, and optional non-destructive close-ups.
- [ ] **P1 / #8:** reconcile the deployed storage-pressure fix into reviewed public source, package reusable guards/review integration, and complete physical recovery/soak/rollback evidence.
- [ ] **P2 / #3 and #5:** optional comparison photos and a reusable photo-observation report, not an exhaustive census.
- [ ] **P2 / #7:** select and validate a species classifier after detection/crop quality is established.

See [TODO.md](docs/TODO.md) for acceptance boundaries and remaining technical gaps. **Do not record after dark**, including during reliability tests. Private schedules already exist; this roadmap and a fresh clone do not install, enable, or change them. Scheduled/enabled does not prove camera liveness or digest delivery.

A reliable motion-triggered photo recorder is the first useful milestone. Species identification is a later milestone, not a prerequisite for saving pictures.

## Installation and usage

The current CLI provides `doctor`, `snapshot`, `run`, `status`, `events`, and optional `analyze`. Use an isolated virtual environment and the documented commands in [SETUP.md](docs/SETUP.md). Runtime and development version snapshots are supplied in `requirements.txt` and `requirements-dev.txt`. Analysis requires a separately obtained, hash-verified model; no model download happens at capture startup.

Automatic calibration/focus control, correction/reanalysis, validated species models, and a portable unattended installer remain future package work. The current camera adapter preserves existing focus/exposure controls and does not download models. Event folders currently use UTC dates; configurable local date partitioning remains pending.

## Privacy and repository hygiene

This public repository is for source code, generic configuration examples, tests, and sanitized documentation—not deployment data.

**Do not commit:**

- Passwords, access tokens, API keys, private keys, or credential files.
- Names, personal email addresses, deployment locations, precise coordinates, network addresses, or device identifiers.
- Personal filesystem paths, private configuration, calibration views, captured photos/video/audio, logs, databases, or event metadata.
- Model weights, local virtual environments, or private evaluation datasets.

Keep operational data outside the checkout. Any optional region/timezone configuration stays private. Selected-image review and private Telegram delivery are already approved in the deployed workflow; additional uploads/public sharing require separate operator approval.

The included `.gitignore` is a safeguard, not a security boundary: review staged changes and commit metadata before publishing. Avoid attaching private diagnostics or photos to public issues.

## Development approach

Implement small vertical slices with tests first: observe the expected failing test, implement the behavior, run the regression suite, then refactor. Keep hardware-dependent checks separate from repeatable unit/integration tests.

Check the requirement registry and generated matrix with `python3 scripts/check_traceability.py --check`. After explicitly reviewing registry/spec changes, regenerate the view with `python3 scripts/check_traceability.py --write`; generation does not automatically approve new requirements, refresh their fingerprints, run mapped tests, or pass field gates. See [TRACEABILITY.md](docs/TRACEABILITY.md).

Numerical targets in the specification are proposed acceptance criteria, not established results. Field reports must distinguish passed, failed, and pending checks. Model evaluation must report abstentions and detector misses as well as successful classifications.

## Initial non-goals

Multiple cameras, audio identification, a web dashboard, live streaming, individual-bird recognition, public photo publication, and per-frame cloud inference remain out of scope. The approved private AI-assisted review and Telegram digest are deployed integrations, not bundled fresh-clone capabilities.

## License

Application code retains the [MIT license](LICENSE). The bundled NanoDet decoder is separately licensed under Apache-2.0, with its license and notices in `third_party/nanodet/`. Package metadata describes the combined distribution as `MIT AND Apache-2.0`; that does not replace the application's MIT license. Optional model weights have their own preserved license and are not bundled. Legal attribution notices are not deployment data and must remain intact.
