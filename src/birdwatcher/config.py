"""Strict, offline capture configuration."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Region:
    name: str
    x: float
    y: float
    width: float
    height: float
    enabled: bool = True


@dataclass(frozen=True)
class CameraConfig:
    device: str = "auto"
    width: int = 1920
    height: int = 1080
    fps: int = 15
    warmup_frames: int = 30
    read_timeout: float = 5.0
    focus_auto: bool = True
    focus_absolute: int | None = None


@dataclass(frozen=True)
class MotionConfig:
    analysis_width: int = 640
    min_area: float = 0.01
    persistence: int = 3
    regions: tuple[Region, ...] = ()
    lighting_threshold: float = 0.85


@dataclass(frozen=True)
class CaptureConfig:
    sample_fps: float = 5.0
    pre_seconds: float = 1.0
    post_seconds: float = 2.0
    quiet_seconds: float = 5.0
    max_event_seconds: float = 30.0
    cooldown_seconds: float = 3.0
    repeat_seconds: float = 5.0
    max_bursts: int = 6
    max_buffer_bytes: int = 33554432


@dataclass(frozen=True)
class StorageConfig:
    data_dir: Path = field(default_factory=lambda: Path.home() / "birdwatcher-data")
    max_bytes: int = 5368709120
    min_free_bytes: int = 2147483648
    retention_days: int = 14


@dataclass(frozen=True)
class AppConfig:
    camera: CameraConfig = field(default_factory=CameraConfig)
    motion: MotionConfig = field(default_factory=MotionConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)


def _build(cls, values):
    import math
    from typing import get_type_hints

    if not isinstance(values, dict):
        raise ConfigError("Expected a TOML table")
    hints = get_type_hints(cls)
    if values.keys() - hints.keys():
        raise ConfigError("Unknown configuration key")
    args = dict(values)
    for name, value in args.items():
        expected = hints[name]
        if cls is MotionConfig and name == "regions":
            if not isinstance(value, list):
                raise ConfigError("regions must be an array")
            args[name] = tuple(_build(Region, item) for item in value)
        elif expected is Path:
            if not isinstance(value, str):
                raise ConfigError("data_dir must be a string")
            args[name] = Path(value).expanduser().resolve()
        elif expected is float:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ConfigError(f"{name} must be a finite number")
        elif expected == int | None:
            if value is not None and type(value) is not int:
                raise ConfigError(f"{name} must be an integer")
        elif type(value) is not expected:
            raise ConfigError(f"{name} has invalid type")
    try:
        return cls(**args)
    except TypeError as exc:
        raise ConfigError("Missing configuration fields") from exc


def _validate(config):
    import re

    c, m, b, s = config.camera, config.motion, config.capture, config.storage
    if c.device != "auto" and not re.fullmatch(
        r"/dev/(?:video[0-9]+|v4l/by-(?:id|path)/[^/]+)", c.device
    ):
        raise ConfigError("Invalid capture device")
    for value in (
        c.width,
        c.height,
        c.fps,
        c.read_timeout,
        m.analysis_width,
        m.persistence,
        b.sample_fps,
        b.post_seconds,
        b.quiet_seconds,
        b.max_event_seconds,
        b.repeat_seconds,
        b.max_bursts,
        b.max_buffer_bytes,
        s.max_bytes,
        s.retention_days,
    ):
        if value <= 0:
            raise ConfigError("Limits and timing must be positive")
    if min(c.warmup_frames, b.pre_seconds, b.cooldown_seconds, s.min_free_bytes) < 0:
        raise ConfigError("Negative limit")
    if not (0 < m.min_area <= 1 and 0 < m.lighting_threshold <= 1):
        raise ConfigError("Motion thresholds must be in (0, 1]")
    if b.post_seconds > b.max_event_seconds or b.repeat_seconds < b.post_seconds:
        raise ConfigError("Invalid burst timing")
    if c.focus_absolute is not None and (c.focus_absolute < 0 or c.focus_auto):
        raise ConfigError("Manual focus requires focus_auto=false and a nonnegative value")
    if not c.focus_auto or c.focus_absolute is not None:
        raise ConfigError("Focus control changes are not implemented in this milestone")
    names = set()
    for r in m.regions:
        if not r.name or r.name in names:
            raise ConfigError("Region names must be nonempty and unique")
        names.add(r.name)
        if not (
            0 <= r.x < 1
            and 0 <= r.y < 1
            and 0 < r.width <= 1
            and 0 < r.height <= 1
            and r.x + r.width <= 1
            and r.y + r.height <= 1
        ):
            raise ConfigError("Region rectangle is out of bounds")
    root = Path(__file__).resolve().parents[2]
    data = s.data_dir.expanduser().resolve()
    if (
        data == root
        or data.is_relative_to(root)
        or root.is_relative_to(data)
        or any((parent / ".git").exists() for parent in (data, *data.parents))
    ):
        raise ConfigError("data_dir must be outside and not an ancestor of checkout")


def load_config(path: Path | None = None) -> AppConfig:
    try:
        values = {} if path is None else tomllib.loads(Path(path).read_text())
        classes = {
            "camera": CameraConfig,
            "motion": MotionConfig,
            "capture": CaptureConfig,
            "storage": StorageConfig,
        }
        if values.keys() - classes.keys():
            raise ConfigError("Unknown configuration group")
        result = AppConfig(**{key: _build(classes[key], value) for key, value in values.items()})
        _validate(result)
        return result
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError("Unable to read configuration") from exc


def validate_run(config: AppConfig) -> None:
    _validate(config)
    if not any(r.enabled for r in config.motion.regions):
        raise ConfigError("At least one enabled region is required")
