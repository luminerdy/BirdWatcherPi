# Setup — early capture milestone

> **Recovery checkpoint: do not resume production capture from this guide.** Capture is manually paused; actual recorder startup still fails with `EIO` replacing production `health.json`, despite successful isolated temporary-file/replay tests. Stale `capturing` health is not liveness. Keep capture stopped until approved supervised daylight startup, saved-JPEG readback, and restart checks pass. The camera/run commands below are generic setup procedures, not recovery evidence or authorization to bypass the pause. See [current recovery status](OPERATIONS.md#current-recovery-status).

Gallery/report source is implemented locally but unactivated. Automatic report generation and delivery must remain disabled pending private-helper security fixes and verification; exporter performance edits are incomplete and unverified. A fresh installation does not restore private helpers, schedules, credentials, archives, or a healthy production filesystem.

The public package provides experimental foreground capture with optional separate-process shadow bird analysis. It does not install species identification, automatic focus calibration, or a background service. The approved deployed setup has separate private daylight/storage/review helpers and schedules; this guide does not install or alter them. See [ARCHITECTURE.md](ARCHITECTURE.md) for that boundary. The shadow analyzer has its own durable work queue but never filters capture or changes the camera. Keep private settings and photos outside the checkout. See [SHADOW_ANALYSIS.md](SHADOW_ANALYSIS.md) for the optional model/analyzer and [DAILY_REPORT.md](DAILY_REPORT.md) for private offline packet/receipt gallery and activity reporting.

## Environment

Initial compatibility target: Linux ARM64, Raspberry Pi 5, Python 3.13, FFmpeg with V4L2 support, and a USB camera capable of MJPEG. The package declares Python 3.11 or newer; other versions/platforms require their own verification. The camera adapter is Linux-specific.

System prerequisites are `ffmpeg` and optionally `v4l-utils` for reporting negotiated capture settings. If absent on a Debian-derived system, review and run `sudo apt install ffmpeg v4l-utils python3-venv` yourself. Do not replace system Python.

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install -e . --no-deps
.venv/bin/birdwatcher --help
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
```

Dependency files pin the exercised environment's versions, not signed artifacts or universal platform support. No neural models are downloaded.

## Check the camera and take a private photograph

```sh
.venv/bin/birdwatcher doctor
.venv/bin/birdwatcher snapshot --output "$HOME/birdwatcher-data/setup-snapshot.jpg"
```

Choose a new output filename on each snapshot; overwriting is refused. The camera is opened briefly by `doctor` and `snapshot`; stop another capture process first. Device serials and paths are not included in the diagnostic JSON. The adapter requests MJPEG and reports actual decoded dimensions plus negotiated format/rate when `v4l2-ctl` is available.

Focus/exposure controls are **not changed** by this milestone. Review test images from the actual perch distances. Automatic focus sweeps and an annotated region-selection UI remain future tasks; use existing camera settings until those tools are added. Do not interpret a sharp feeder overview as proof that a bird at every distance will be sharp.

## Private configuration

```sh
mkdir -p "$HOME/.config/birdwatcher"
chmod 700 "$HOME/.config/birdwatcher"
cp config/config.example.toml "$HOME/.config/birdwatcher/config.toml"
chmod 600 "$HOME/.config/birdwatcher/config.toml"
```

Edit that private copy. Each region uses normalized `x`, `y`, `width`, and `height` values in the range zero to one. The full rectangle must fit inside the image. Replace the full-frame placeholders with feeder-specific rectangles and enable only the regions you have reviewed. The included example intentionally refuses capture because both regions are disabled.

`storage.data_dir` must be outside the repository and must not be a directory containing the repository. Keep it dedicated to application data. Do not use a shared photo collection. Default storage limits are configurable; review them before longer sessions.

## Supervised capture

```sh
.venv/bin/birdwatcher --config "$HOME/.config/birdwatcher/config.toml" run --duration 60
.venv/bin/birdwatcher --config "$HOME/.config/birdwatcher/config.toml" status
.venv/bin/birdwatcher --config "$HOME/.config/birdwatcher/config.toml" events --limit 5
```

The foreground CLI does not enforce a solar window. Start supervised runs only within an established daylight window and choose a duration that ends conservatively before sunset; omit `--duration` only with deliberate manual supervision and a before-dark stop. Press Ctrl-C to stop. This guide installs/enables no systemd service or private scheduler. Capture itself does not upload images or contact a model service; approved private visual review/Telegram are separate integrations. Motion events are not confirmed birds and event counts are not bird counts.

See [OPERATIONS.md](OPERATIONS.md) for limitations and recovery. Run from the checkout's virtual environment, not an unrelated interpreter.
