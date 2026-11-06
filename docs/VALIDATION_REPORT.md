# Capture milestone validation

Scope: early, foreground-only motion-capture implementation. This report is sanitized: no deployment location, personal paths, device serials, timestamps, private settings, or captured images are included.

## Hardware evidence

A live Logitech C920 stream negotiated **1920 × 1080, MJPEG, 15 fps**. Diagnostics and snapshot commands exercised that camera adapter. Focus and exposure controls were not changed.

A supervised 15-second smoke session using an explicitly temporary **full-frame test region**, not a calibrated feeder region, reported:

- 188 received frames.
- One motion-triggered event.
- 13 saved JPEG files; every saved image decoded successfully at 1920 × 1080.
- Zero reconnects, invalid decoded frames, dropped saves, or storage-write errors in that session.
- A complete event manifest and identification status `not_configured`.

This verifies a short live capture path, **not bird presence, species identification, long-term reliability, or a calibrated feeder configuration**. Private samples remain outside the checkout. Subsequent storage fixes are covered by dedicated regression tests and an independent review of the staged source.

## Packaging evidence

An application wheel was built and installed into a separate clean virtual environment with the pinned runtime dependencies. The installed executable returned its version and command help successfully. The tested interpreter was Python 3.13 on Linux ARM64; declared support for other Python versions is not validation of those versions.

## Repeatable checks

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
git diff --cached --check
```

Tests use isolated temporary directories and explicitly synthetic/replayed frames where applicable. They cover configuration validation, camera parsing/ownership/timeouts, event timing/prebuffers, bounded writer behavior, local storage safety/recovery, and CLI/integration behavior. The initial capture milestone passed **89 tests**, Ruff lint/format checks, and staged whitespace checks. Future revisions must rerun these commands rather than inherit this result.

Independent reviews found storage-recovery defects despite the initial passing suite: recovered events incorrectly prevented quota pruning, interrupted frame commits could strand payloads, and journal overhead could block constrained recovery. These were fixed with regression coverage for quota boundaries and real subprocess termination before/after JPEG and manifest renames. Final independent review exported the staged source to an isolated checkout, passed all 89 tests, and reported no remaining blocking correctness or security findings. This establishes tested process-termination recovery, not a physical power-loss guarantee.

## Still pending

- User-reviewed focus quality at both actual perch distances and calibrated feeder regions.
- Measured bird-arrival capture yield and nuisance-trigger rate.
- Best-image quality ranking and configurable local-date partitions.
- Durable analysis index/queue, local bird/species models, and identification evaluation.
- Physical unplug/replug testing, approved unattended service/reboot testing, and a 24-hour soak.

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for full acceptance gates. No service is installed or enabled by this milestone, and no private photo is published.
