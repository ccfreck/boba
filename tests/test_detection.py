from boba.security.policy_engine import PolicyEngine
from boba.security.rate_detector import RateDetector


def test_window_threshold_and_bounded_memory() -> None:
    detector = RateDetector()
    assert not detector.observe("R", 3, 60, now=0)
    assert not detector.observe("R", 3, 60, now=1)
    assert not detector.observe("R", 3, 60, now=2)
    assert detector.observe("R", 3, 60, now=3)
    for _ in range(10000):
        detector.observe("R", 3, 60, now=4)
    assert len(detector.windows["R"]) == 4
    assert not detector.observe("R", 3, 60, now=64)


def test_alert_does_not_change_authorization(engine: PolicyEngine) -> None:
    for _ in range(3):
        assert not engine.evaluate("read_file", {"path": "hello.txt"})[0].alerts
    allowed = engine.evaluate("read_file", {"path": "hello.txt"})[0]
    assert allowed.decision == "allow" and allowed.alerts == ["RATE"]
    blocked = engine.evaluate("read_file", {"path": ".env"})[0]
    assert blocked.decision == "block" and blocked.alerts == ["RATE"]
