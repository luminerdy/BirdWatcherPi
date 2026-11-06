from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def detector(tmp_path, monkeypatch):
    import hashlib

    import birdwatcher.bird_detector as module

    payload = b"fixture"
    path = tmp_path / "model"
    path.write_bytes(payload)
    monkeypatch.setattr(module, "MODEL_SIZE", len(payload))
    monkeypatch.setattr(module, "MODEL_SHA256", hashlib.sha256(payload).hexdigest())

    class Engine:
        predictions = np.array([[0, 104, 416, 312, 0.8, 14], [1, 1, 20, 20, 0.9, 0]])

        def infer(self, image):
            self.image = image.copy()
            return self.predictions

    engine = Engine()

    def factory(*, model_buffer, **kwargs):
        assert isinstance(model_buffer, bytes)
        assert model_buffer == payload
        return engine

    return module.BirdDetector(path, engine_factory=factory), engine


def test_geometry_color_no_mutation_and_only_birds(detector):
    d, engine = detector
    image = np.zeros((100, 200, 3), np.uint8)
    image[:] = [10, 20, 30]
    before = image.copy()
    result = d.analyze(image)
    assert result["status"] == "bird_candidate"
    assert result["detections"] == [
        dict(class_id=14, label="bird", score=0.8, box=[0, 0, 200, 100], region="full_frame")
    ]
    assert engine.image.shape == (416, 416, 3)
    assert engine.image[200, 200].tolist() == [30, 20, 10]
    assert np.array_equal(image, before)
    assert d.model_info["preprocess_version"]
    assert "path" not in str(d.model_info)


def test_rois_unknown_and_bad_image(detector):
    from birdwatcher.bird_detector import DetectorError
    from birdwatcher.config import Region

    d, engine = detector
    image = np.zeros((100, 200, 3), np.uint8)
    engine.predictions = np.array([[0, 0, 416, 416, 0.8, 14]])
    r = Region("feeder", 0.25, 0.25, 0.5, 0.5)
    assert d.analyze(image, (r,))["detections"][0]["box"] == [50, 25, 150, 75]
    assert d.analyze(image, (Region("off", 0, 0, 1, 1, False),))["status"] == "unknown"
    engine.predictions = np.array([[0, 0, 416, 416, 0.9, 0]])
    assert d.analyze(image)["status"] == "unknown"
    with pytest.raises(ValueError):
        d.analyze(image, (Region("bad", 0.9, 0, 0.2, 1),))
    with pytest.raises(DetectorError):
        d.analyze(np.zeros((1, 2)))


def test_official_decoder_and_cpu_mocknet(monkeypatch):
    import cv2

    from birdwatcher._vendor.nanodet import NanoDet

    class Net:
        def setPreferableBackend(self, value):
            assert value == cv2.dnn.DNN_BACKEND_OPENCV

        def setPreferableTarget(self, value):
            assert value == cv2.dnn.DNN_TARGET_CPU

        def setInput(self, blob):
            assert blob.shape == (1, 3, 416, 416)

        def getUnconnectedOutLayersNames(self):
            return ["outputs"]

        def forward(self, names):
            result = []
            for stride in (8, 16, 32, 64):
                n = (416 // stride) ** 2
                scores = np.zeros((1, n, 80), np.float32)
                if stride == 8:
                    scores[0, 100, 14] = 0.9
                    scores[0, 200, 14] = 0.8
                result.extend([scores, np.zeros((1, n, 32), np.float32)])
            return result

    monkeypatch.setattr(cv2.dnn, "readNetFromONNX", lambda buffer: Net())
    engine = NanoDet(
        b"unused", backend_id=cv2.dnn.DNN_BACKEND_OPENCV, target_id=cv2.dnn.DNN_TARGET_CPU
    )
    output = engine.infer(np.zeros((416, 416, 3), np.uint8))
    assert output.shape == (2, 6)
    assert output[:, 5].tolist() == [14, 14]
    assert np.allclose(output[:, 4], [0.9, 0.8])


def test_verified_model_buffer_survives_path_replacement(tmp_path, monkeypatch):
    import hashlib

    import cv2

    import birdwatcher.bird_detector as module

    original = b"verified original ONNX fixture"
    replacement = b"unverified replacement fixture"
    path = tmp_path / "model.onnx"
    path.write_bytes(original)
    monkeypatch.setattr(module, "MODEL_SIZE", len(original))
    monkeypatch.setattr(module, "MODEL_SHA256", hashlib.sha256(original).hexdigest())

    def replace_path(threads):
        assert threads == 1
        other = tmp_path / "replacement.onnx"
        other.write_bytes(replacement)
        other.replace(path)

    monkeypatch.setattr(cv2, "setNumThreads", replace_path)
    loaded = []

    class Net:
        def setPreferableBackend(self, value):
            pass

        def setPreferableTarget(self, value):
            pass

    def load_model(source):
        loaded.append(source)
        return Net()

    monkeypatch.setattr(cv2.dnn, "readNet", load_model)
    monkeypatch.setattr(cv2.dnn, "readNetFromONNX", load_model)
    detector = module.BirdDetector(path)
    assert path.read_bytes() == replacement
    assert len(loaded) == 1
    source = loaded[0]
    loaded_bytes = Path(source).read_bytes() if isinstance(source, str) else bytes(source)
    assert loaded_bytes == original
    assert isinstance(source, np.ndarray)
    assert source.dtype == np.uint8
    assert not source.flags.writeable
    assert isinstance(source.base, bytes)
    with pytest.raises(ValueError):
        source.setflags(write=True)
    assert detector.model_info["sha256"] == hashlib.sha256(loaded_bytes).hexdigest()


@pytest.mark.parametrize("oversized", [False, True])
def test_model_read_is_bounded_and_rejects_trailing_bytes(tmp_path, monkeypatch, oversized):
    import hashlib
    import io

    import birdwatcher.bird_detector as module

    original = b"verified fixture"
    payload = original + (b"extra bytes" if oversized else b"")
    reads = []

    class ModelFile(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            assert 0 <= size <= len(original) + 1
            return super().read(size)

    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: ModelFile(payload))
    monkeypatch.setattr(module, "MODEL_SIZE", len(original))
    monkeypatch.setattr(module, "MODEL_SHA256", hashlib.sha256(original).hexdigest())
    loaded = []

    def factory(*, model_buffer, **kwargs):
        loaded.append(model_buffer)

    path = tmp_path / "model.onnx"
    if oversized:
        with pytest.raises(module.DetectorError, match="integrity"):
            module.BirdDetector(path, engine_factory=factory)
        assert not loaded
    else:
        module.BirdDetector(path, engine_factory=factory)
        assert loaded == [original]
    assert reads == [len(original) + 1]


def test_model_integrity_before_engine(tmp_path):
    from birdwatcher.bird_detector import BirdDetector, DetectorError

    model = tmp_path / "bad.onnx"
    model.write_bytes(b"bad")
    called = []
    with pytest.raises(DetectorError, match="integrity"):
        BirdDetector(model, engine_factory=lambda **kw: called.append(kw))
    assert not called


@pytest.mark.parametrize("threshold", [0, 1.1, float("nan"), True])
def test_threshold_validation(threshold):
    from birdwatcher.bird_detector import BirdDetector

    with pytest.raises(ValueError):
        BirdDetector(Path("unused"), threshold)
