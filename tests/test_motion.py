import numpy as np

from birdwatcher.config import MotionConfig, Region


def test_motion_persistence_regions_lighting_and_reset():
    from birdwatcher.motion import MotionDetector

    detector = MotionDetector(
        MotionConfig(analysis_width=160, persistence=3, regions=(Region("feeder", 0, 0, 0.5, 1),))
    )
    blank = np.zeros((120, 160, 3), np.uint8)
    for _ in range(40):
        assert detector.update(blank) == ()
    outside = blank.copy()
    outside[30:70, 110:150] = 255
    for _ in range(4):
        assert detector.update(outside) == ()
    inside = blank.copy()
    inside[30:70, 20:60] = 255
    assert detector.update(inside) == ()
    assert detector.update(inside) == ()
    assert detector.update(inside) == ("feeder",)
    assert detector.update(np.full_like(blank, 255)) == ()
    detector.reset()
    assert detector.update(inside) == ()
