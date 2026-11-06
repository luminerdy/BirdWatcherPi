# Setup — early capture milestone

This is an experimental, foreground-only capture application. Species identification, a durable AI queue/index, automatic focus calibration, and an installed background service are not provided by this milestone. Keep any private settings and photos outside the checkout.

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

Omit `--duration` only for an intentionally started foreground session; press Ctrl-C to stop. No systemd service is installed or enabled. Capture does not upload images or contact a model service. Motion events are not confirmed birds and event counts are not bird counts.

See [OPERATIONS.md](OPERATIONS.md) for limitations and recovery. Run from the checkout's virtual environment, not an unrelated interpreter.
