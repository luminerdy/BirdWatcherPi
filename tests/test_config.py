from pathlib import Path

import pytest


def test_validate_run_checks_direct_config_and_external_tmp_data(tmp_path):
    from dataclasses import replace

    from birdwatcher.config import (
        AppConfig,
        ConfigError,
        MotionConfig,
        Region,
        StorageConfig,
        validate_run,
    )

    valid = AppConfig(
        motion=MotionConfig(regions=(Region("feeder", 0, 0, 1, 1),)),
        storage=StorageConfig(tmp_path / "captures", min_free_bytes=0),
    )
    validate_run(valid)
    with pytest.raises(ConfigError):
        validate_run(replace(valid, motion=MotionConfig(regions=(Region("bad", 0, 0, 2, 1),))))


def test_toml_validates_types_bounds_paths_and_unknowns(tmp_path):
    from birdwatcher.config import ConfigError, load_config, validate_run

    p = tmp_path / "settings.toml"
    p.write_text(
        '[camera]\ndevice="/dev/video2"\n[motion]\n[[motion.regions]]\nname="feeder"\nx=0.1\ny=0.2\nwidth=0.3\nheight=0.4\n'
    )
    config = load_config(p)
    validate_run(config)
    assert config.motion.regions[0].name == "feeder"
    for invalid in (
        "[camera]\nwidth=true",
        "[camera]\nwidth=0",
        '[camera]\ndevice="echo unsafe"',
        "[motion]\nmin_area=2",
        "[capture]\nrepeat_seconds=0",
        "[storage]\nmax_bytes=-1",
        "[wrong]\nx=1",
        '[motion]\n[[motion.regions]]\nname="x"\nx=0.9\ny=0.0\nwidth=0.2\nheight=1.0',
    ):
        p.write_text(invalid)
        with pytest.raises(ConfigError):
            load_config(p)
    root = Path(__file__).resolve().parents[1]
    for unsafe in (root, root / "captures", root.parent):
        p.write_text("[storage]\ndata_dir=" + repr(str(unsafe)))
        with pytest.raises(ConfigError, match="outside"):
            load_config(p)


def test_defaults_require_calibration():
    from birdwatcher.config import ConfigError, load_config, validate_run

    config = load_config()
    assert config.camera.width == 1920
    assert config.storage.data_dir == Path.home() / "birdwatcher-data"
    with pytest.raises(ConfigError, match="region"):
        validate_run(config)
