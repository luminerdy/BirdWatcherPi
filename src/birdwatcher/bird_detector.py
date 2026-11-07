"""Offline, pinned NanoDet bird candidates; never a manual confirmation."""

import hashlib
import math
from pathlib import Path

MODEL_SHA256 = "4b82da9944b88577175ee23a459dce2e26e6e4be573def65b1055dc2d9720186"
MODEL_SIZE = 3800954
REVISION = "48b10fa505aeb51fbd127fc60a5c660040e823b7"


class DetectorError(RuntimeError):
    pass


class BirdDetector:
    def __init__(self, model_path: Path, threshold: float = 0.25, *, engine_factory=None):
        if (
            type(threshold) not in (int, float)
            or not math.isfinite(threshold)
            or not 0 < threshold <= 1
        ):
            raise ValueError("threshold must be in (0, 1]")
        self.threshold = float(threshold)
        try:
            with Path(model_path).open("rb") as model_file:
                payload = model_file.read(MODEL_SIZE + 1)
            if len(payload) != MODEL_SIZE or hashlib.sha256(payload).hexdigest() != MODEL_SHA256:
                raise DetectorError("Model integrity check failed")
        except OSError as exc:
            raise DetectorError("Model integrity check failed") from exc
        import cv2

        cv2.setNumThreads(1)
        cv2.ocl.setUseOpenCL(False)
        if engine_factory is None:
            from ._vendor.nanodet import NanoDet

            engine_factory = NanoDet
        try:
            self.engine = engine_factory(
                model_buffer=payload,
                prob_threshold=self.threshold,
                iou_threshold=0.6,
                backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
                target_id=cv2.dnn.DNN_TARGET_CPU,
            )
        except Exception as exc:
            raise DetectorError("Model load failed") from exc

    @property
    def model_info(self):
        return dict(
            name="NanoDet-m-plus-1.5x_416",
            revision=REVISION,
            sha256=MODEL_SHA256,
            threshold=self.threshold,
            preprocess_version="zoo-rgb-letterbox-416-v1",
        )

    def analyze(self, image, regions=()):
        import cv2
        import numpy as np

        if (
            not isinstance(image, np.ndarray)
            or image.dtype != np.uint8
            or image.ndim != 3
            or image.shape[2] != 3
            or min(image.shape[:2]) <= 0
        ):
            raise DetectorError("Expected nonempty uint8 BGR image")
        h, w = image.shape[:2]
        crops = []
        names = set()
        for r in regions:
            if (
                not r.name
                or r.name in names
                or not (
                    0 <= r.x < 1
                    and 0 <= r.y < 1
                    and 0 < r.width <= 1
                    and 0 < r.height <= 1
                    and r.x + r.width <= 1
                    and r.y + r.height <= 1
                )
            ):
                raise ValueError("Invalid region")
            names.add(r.name)
            if r.enabled:
                crops.append(
                    (
                        r.name,
                        round(r.x * w),
                        round(r.y * h),
                        round((r.x + r.width) * w),
                        round((r.y + r.height) * h),
                    )
                )
        if not regions:
            crops.append(("full_frame", 0, 0, w, h))
        detections = []
        for name, x, y, x2, y2 in crops:
            ch, cw = y2 - y, x2 - x
            if min(ch, cw) <= 0:
                raise ValueError("Region has no pixels")
            rgb = cv2.cvtColor(image[y:y2, x:x2], cv2.COLOR_BGR2RGB)
            nh, nw = (
                (416, max(1, int(416 * cw / ch))) if ch > cw else (max(1, int(416 * ch / cw)), 416)
            )
            top, left = (416 - nh) // 2, (416 - nw) // 2
            resized = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
            padded = cv2.copyMakeBorder(
                resized, top, 416 - nh - top, left, 416 - nw - left, cv2.BORDER_CONSTANT, value=0
            )
            try:
                predictions = self.engine.infer(padded)
            except Exception as exc:
                raise DetectorError("Inference failed") from exc
            for prediction in predictions:
                a, b, c, d, score, class_id = map(float, prediction)
                if (
                    class_id != 14
                    or score < self.threshold
                    or not all(math.isfinite(v) for v in (a, b, c, d, score))
                ):
                    continue
                box = [
                    max(x, min(x2, (a - left) * cw / nw + x)),
                    max(y, min(y2, (b - top) * ch / nh + y)),
                    max(x, min(x2, (c - left) * cw / nw + x)),
                    max(y, min(y2, (d - top) * ch / nh + y)),
                ]
                if box[2] > box[0] and box[3] > box[1]:
                    detections.append(
                        dict(class_id=14, label="bird", score=score, box=box, region=name)
                    )
        return dict(status="bird_candidate" if detections else "unknown", detections=detections)
