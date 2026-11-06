"""Command-line interface. All operational output stays on the local machine."""

import argparse
from pathlib import Path

from . import __version__


def parser():
    root = argparse.ArgumentParser(description="Local bird-feeder photo capture")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--config", type=Path, help="Private TOML configuration")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check camera and capture prerequisites")
    snapshot = commands.add_parser("snapshot", help="Take a private test photo")
    snapshot.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run", help="Run motion-triggered capture in the foreground")
    run.add_argument("--duration", type=float, help="Stop after this many seconds")
    commands.add_parser("status", help="Read the last local health report")
    events = commands.add_parser("events", help="List locally saved events")
    events.add_argument("--limit", type=int, default=20)
    analyze = commands.add_parser(
        "analyze",
        help="Shadow bird analysis of saved events; never filters photos",
        description="Optional shadow analysis: record bird candidates without modifying captures",
    )
    analyze.add_argument(
        "--model", type=Path, required=True, help="Private pinned NanoDet ONNX model"
    )
    analyze.add_argument(
        "--analysis-dir", type=Path, help="Private results/queue directory outside capture data"
    )
    analyze.add_argument(
        "--threshold", type=float, default=0.25, help="Provisional model score threshold"
    )
    analyze.add_argument("--frames-per-event", type=int, default=3)
    analyze.add_argument("--limit", type=int, default=20, help="Maximum events per analysis pass")
    analyze.add_argument(
        "--watch-seconds",
        type=float,
        default=0,
        help="Watch for a bounded time; zero runs one pass",
    )
    analyze.add_argument(
        "--full-frame", action="store_true", help="Use full images instead of configured regions"
    )
    return root


def main(argv=None):
    import json
    import math
    import os

    from .camera import Camera, CameraError, validate_output
    from .config import ConfigError, load_config, validate_run

    root = parser()
    args = root.parse_args(argv)
    if args.command == "run" and args.duration is not None:
        if not math.isfinite(args.duration) or args.duration <= 0:
            root.error("duration must be a finite positive number")
    if args.command == "events" and not 1 <= args.limit <= 1000:
        root.error("limit must be between 1 and 1000")
    if args.command == "analyze":
        if not math.isfinite(args.threshold) or not 0 < args.threshold <= 1:
            root.error("threshold must be finite and in (0, 1]")
        if not 1 <= args.frames_per_event <= 10:
            root.error("frames-per-event must be between 1 and 10")
        if not 1 <= args.limit <= 100:
            root.error("limit must be between 1 and 100")
        if not math.isfinite(args.watch_seconds) or not 0 <= args.watch_seconds <= 3600:
            root.error("watch-seconds must be between 0 and 3600")
    os.umask(0o077)
    try:
        config = load_config(args.config)
        if args.command == "analyze" and not args.full_frame:
            validate_run(config)
        if args.command == "doctor":
            with Camera(config.camera) as camera:
                camera.read()
                result = {"camera_available": True, "capture": camera.settings}
            result["configured_regions"] = sum(r.enabled for r in config.motion.regions)
            result["species_identification"] = "not_implemented"
            print(json.dumps(result, indent=2))
        elif args.command == "snapshot":
            output = validate_output(args.output)
            with Camera(config.camera) as camera:
                jpeg = camera.read()
                settings = camera.settings.copy()
            output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Exclusive creation prevents accidental replacement of private files.
            with output.open("xb") as file:
                file.write(jpeg)
                file.flush()
                os.fsync(file.fileno())
            print(json.dumps({"saved": True, "bytes": len(jpeg), "capture": settings}, indent=2))
        elif args.command in ("events", "status"):
            data = config.storage.data_dir
            if args.command == "events":
                results = []
                if data.exists():
                    for path in sorted(data.glob("*/*/event.json"), reverse=True):
                        if (
                            path.is_symlink()
                            or path.parent.is_symlink()
                            or path.parent.parent.is_symlink()
                        ):
                            continue
                        try:
                            item = json.loads(path.read_text())
                            if isinstance(item, dict) and isinstance(item.get("started_utc"), str):
                                results.append(item)
                        except (ValueError, OSError):
                            continue
                results.sort(key=lambda item: item["started_utc"], reverse=True)
                print(json.dumps(results[: args.limit], indent=2))
            else:
                health = data / "health.json"
                result = (
                    json.loads(health.read_text()) if health.is_file() else {"state": "not_started"}
                )
                print(json.dumps(result, indent=2))
        elif args.command == "analyze":
            result = run_shadow_analysis(args, config)
            print(json.dumps(result, indent=2))
            return 1 if result["totals"].get("failed", 0) else 0
        elif args.command == "run":
            validate_run(config)
            from .runner import run_capture

            result = run_capture(config, duration=args.duration)
            print(json.dumps(result, indent=2))
            return (
                1 if result.get("storage_errors", 0) or not result.get("frames_received", 0) else 0
            )
        return 0
    except KeyboardInterrupt:
        return 130
    except (ConfigError, CameraError, ValueError) as error:
        root.exit(2, f"Error: {error}\n")
    except OSError:
        root.exit(2, "Error: local I/O failed; check storage, permissions, and camera access\n")


def run_shadow_analysis(args, config):
    """Separate, optional analysis process: never acquires a camera or edits photos."""
    import os
    import time

    from .analysis import AnalysisError, Analyzer
    from .bird_detector import BirdDetector, DetectorError

    regions = () if args.full_frame else tuple(r for r in config.motion.regions if r.enabled)
    analysis_dir = args.analysis_dir or config.storage.data_dir.with_name(
        config.storage.data_dir.name + "-analysis"
    )
    try:
        os.nice(10)
    except (AttributeError, OSError):
        pass
    try:
        detector = BirdDetector(args.model, threshold=args.threshold)
        started = time.monotonic()
        deadline = started + args.watch_seconds
        totals = {}
        passes = 0
        with Analyzer(
            config.storage.data_dir,
            analysis_dir,
            detector,
            regions=regions,
            frames_per_event=args.frames_per_event,
        ) as analyzer:
            while True:
                result = analyzer.run(limit=args.limit)
                passes += 1
                for key, value in result.items():
                    if type(value) is int:
                        totals[key] = totals.get(key, 0) + value
                remaining = deadline - time.monotonic()
                if not args.watch_seconds or remaining <= 0:
                    break
                time.sleep(min(2.0, remaining))
        return {
            "mode": "shadow",
            "filtering_enabled": False,
            "passes": passes,
            "totals": totals,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "model": detector.model_info,
        }
    except (AnalysisError, DetectorError):
        raise ValueError(
            "Shadow analysis failed; check the model and private analysis data"
        ) from None
