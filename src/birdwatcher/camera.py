"""Linux camera adapter: one FFmpeg owner, bounded JPEG parsing and reads.

Device identifiers are used only to open the camera, never in health metadata.
"""

import fcntl
import os
import re
import select
import shutil
import subprocess
import time
from pathlib import Path


class CameraError(RuntimeError):
    """Camera discovery, ownership, or stream failure."""


def discover_device(device="auto", device_root=Path("/dev")):
    if device != "auto":
        path = Path(device)
        if not path.is_absolute() or not path.is_relative_to(device_root) or not path.exists():
            raise CameraError("Configured capture device is unavailable")
        return str(path)
    candidates = sorted((device_root / "v4l" / "by-id").glob("*-video-index0"))
    for path in candidates:
        if path.exists():
            return str(path)
    fallback = device_root / "video0"
    if fallback.exists():
        return str(fallback)
    raise CameraError("No USB capture camera found")


class CameraLock:
    """Per-user exclusive camera ownership for this application."""

    def __init__(self, path=None):
        self.path = path or Path.home() / ".cache" / "birdwatcher" / "camera.lock"
        self.fd = None

    def __enter__(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.__exit__(None, None, None)
            raise CameraError(
                "Camera busy or lock unavailable; stop the capture process first"
            ) from None
        return self

    def __exit__(self, *args):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def extract_jpeg(buffer, max_bytes=16 * 1024 * 1024):
    """Consume one complete MJPEG frame, keeping partial markers between reads."""
    if len(buffer) > max_bytes:
        raise CameraError("Camera frame exceeds buffer limit")
    start = buffer.find(b"\xff\xd8")
    if start < 0:
        tail = buffer[-1:] if buffer[-1:] == b"\xff" else b""
        buffer.clear()
        buffer.extend(tail)
        return None
    if start:
        del buffer[:start]
    end = buffer.find(b"\xff\xd9", 2)
    if end < 0:
        return None
    result = bytes(buffer[: end + 2])
    del buffer[: end + 2]
    return result


def read_stream_frame(process, buffer, timeout):
    deadline = time.monotonic() + timeout
    while True:
        result = extract_jpeg(buffer)
        if result is not None:
            return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CameraError("Camera read timed out")
        readable, _, _ = select.select([process.stdout], [], [], remaining)
        if not readable:
            raise CameraError("Camera read timed out")
        chunk = os.read(process.stdout.fileno(), 65536)
        if not chunk:
            raise CameraError("Camera stream stopped; check connection and requested format")
        buffer.extend(chunk)


def parse_settings(text):
    result = {}
    size = re.search(r"Width/Height\s*:\s*(\d+)/(\d+)", text)
    if size:
        result.update(width=int(size[1]), height=int(size[2]))
    pixel = re.search(r"Pixel Format\s*:\s*'([^']+)'", text)
    if pixel:
        result["pixel_format"] = pixel[1]
    fps = re.search(r"Frames per second\s*:\s*([\d.]+)", text)
    if fps:
        result["fps"] = float(fps[1])
    return result


def validate_output(path):
    resolved = path.expanduser().resolve()
    checkout = Path(__file__).resolve().parents[2]
    if resolved.is_relative_to(checkout) or any(
        (parent / ".git").exists() for parent in (resolved, *resolved.parents)
    ):
        raise CameraError("Save private images outside the repository")
    if path.is_symlink() or resolved.exists():
        raise CameraError("Snapshot output must be a new regular file")
    if resolved.suffix.lower() not in (".jpg", ".jpeg"):
        raise CameraError("Snapshot output must use .jpg or .jpeg")
    return resolved


class Camera:
    def __init__(self, config):
        self.config = config
        self.process = None
        self.lock = CameraLock()
        self.buffer = bytearray()
        self.settings = {}
        self._warmed = False

    def __enter__(self):
        if not shutil.which("ffmpeg"):
            raise CameraError("FFmpeg is required; install the system ffmpeg package")
        device = discover_device(self.config.device)
        self.lock.__enter__()
        args = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "v4l2",
            "-input_format",
            "mjpeg",
            "-framerate",
            str(self.config.fps),
            "-video_size",
            f"{self.config.width}x{self.config.height}",
            "-i",
            device,
            "-an",
            "-c:v",
            "copy",
            "-f",
            "image2pipe",
            "-flush_packets",
            "1",
            "pipe:1",
        ]
        try:
            self.process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
        except OSError:
            self.lock.__exit__(None, None, None)
            raise CameraError("Could not start camera capture") from None
        self._device = device
        return self

    def read(self):
        if self.process is None:
            raise CameraError("Camera is not open")
        if not self._warmed:
            for _ in range(self.config.warmup_frames):
                read_stream_frame(self.process, self.buffer, self.config.read_timeout)
            self._warmed = True
        frame = read_stream_frame(self.process, self.buffer, self.config.read_timeout)
        if not self.settings:
            self._read_settings(frame)
        return frame

    def _read_settings(self, jpeg):
        import cv2
        import numpy as np

        decoded = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None:
            raise CameraError("Camera returned an invalid JPEG")
        self.settings = {"width": decoded.shape[1], "height": decoded.shape[0]}
        if shutil.which("v4l2-ctl"):
            try:
                result = subprocess.run(
                    ["v4l2-ctl", "-d", self._device, "--get-fmt-video", "--get-parm"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if result.returncode == 0:
                    measured = parse_settings(result.stdout)
                    # Decoded image dimensions are authoritative for the saved frames.
                    measured.pop("width", None)
                    measured.pop("height", None)
                    self.settings.update(measured)
            except (OSError, subprocess.TimeoutExpired):
                pass
        self.settings["degraded"] = (
            self.settings["width"] != self.config.width
            or self.settings["height"] != self.config.height
            or ("fps" in self.settings and abs(self.settings["fps"] - self.config.fps) > 0.1)
        )
        self.settings["focus_controls_applied"] = False

    def __exit__(self, *args):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
            if self.process.stdout:
                self.process.stdout.close()
            self.process = None
        self.lock.__exit__(None, None, None)
