"""MOG2 change detection; no bird identity inference."""

import cv2
import numpy as np

from .config import MotionConfig


class MotionDetector:
    def __init__(self, config: MotionConfig):
        self.config = config
        self.reset()

    def reset(self):
        self._background = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=16, detectShadows=True
        )
        self._counts = {r.name: 0 for r in self.config.regions}
        self._seen = 0
        self.suppressed = 0

    def update(self, frame: np.ndarray) -> tuple[str, ...]:
        if frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
            raise ValueError("Expected a uint8 BGR frame")
        height, width = frame.shape[:2]
        target = min(width, self.config.analysis_width)
        image = cv2.resize(frame, (target, max(1, round(height * target / width))))
        image = cv2.GaussianBlur(image, (5, 5), 0)
        mask = self._background.apply(image)
        mask = np.uint8(mask == 255) * 255  # MOG2 shadows (127) are not motion.
        self._seen += 1
        broad = np.count_nonzero(mask) / mask.size >= self.config.lighting_threshold
        if self._seen <= 5 or broad:
            self._counts = dict.fromkeys(self._counts, 0)
            if broad:
                self.suppressed += 1
            return ()
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        h, w = mask.shape
        active = []
        for r in self.config.regions:
            if not r.enabled:
                continue
            x, y = int(r.x * w), int(r.y * h)
            crop = mask[
                y : max(y + 1, int((r.y + r.height) * h)), x : max(x + 1, int((r.x + r.width) * w))
            ]
            changed = crop.size and np.count_nonzero(crop) / crop.size >= self.config.min_area
            self._counts[r.name] = self._counts[r.name] + 1 if changed else 0
            if self._counts[r.name] >= self.config.persistence:
                active.append(r.name)
        return tuple(active)
