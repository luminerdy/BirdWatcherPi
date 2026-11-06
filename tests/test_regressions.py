"""Regression checks for capture failure paths."""

import pytest


def test_frame_after_failed_start_is_a_controlled_storage_error(tmp_path):
    from birdwatcher.config import StorageConfig
    from birdwatcher.events import EventAction, Frame
    from birdwatcher.storage import EventStore, StorageError

    store = EventStore(StorageConfig(tmp_path / "events", max_bytes=1, min_free_bytes=0))
    frame = Frame(1, "2020-01-01T00:00:00+00:00", 1.0, b"jpeg")
    with pytest.raises(StorageError):
        store.apply(EventAction("start", "event", frame))
    with pytest.raises(StorageError, match="not active"):
        store.apply(EventAction("frame", "event", frame))


def test_snapshot_refuses_any_git_checkout_even_when_package_installed_elsewhere(tmp_path):
    from birdwatcher.camera import CameraError, validate_output

    checkout = tmp_path / "another-checkout"
    (checkout / ".git").mkdir(parents=True)
    with pytest.raises(CameraError, match="outside"):
        validate_output(checkout / "photo.jpg")


def test_private_config_cannot_put_capture_data_in_another_git_checkout(tmp_path):
    from birdwatcher.config import ConfigError, load_config

    checkout = tmp_path / "another-checkout"
    (checkout / ".git").mkdir(parents=True)
    settings = tmp_path / "settings.toml"
    settings.write_text('[storage]\ndata_dir = "' + str(checkout / "captures") + '"\n')
    with pytest.raises(ConfigError, match="outside"):
        load_config(settings)


def test_manual_focus_is_rejected_rather_than_silently_ignored(tmp_path):
    from birdwatcher.config import ConfigError, load_config

    settings = tmp_path / "settings.toml"
    settings.write_text("[camera]\nfocus_auto = false\nfocus_absolute = 100\n")
    with pytest.raises(ConfigError, match="not implemented"):
        load_config(settings)
