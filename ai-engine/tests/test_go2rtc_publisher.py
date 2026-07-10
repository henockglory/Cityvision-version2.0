"""Go2rtcPublisher sizing."""

from citevision_ai.ingest.go2rtc_publisher import Go2rtcPublisher


def test_publisher_scales_down_wide_frames():
    pub = Go2rtcPublisher("cam-test", 1920, 1080, 25.0)
    assert pub._out_w <= 1280
    assert pub._out_h > 0
