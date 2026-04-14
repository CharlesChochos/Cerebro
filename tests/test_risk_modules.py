"""
Unit tests for risk scoring, velocity, alerts, and prediction scorecard.
"""
import pytest


class TestRiskScoring:
    def test_compute_decay_zero_hours(self):
        from detection.risk import compute_decay
        assert compute_decay(0) == 1.0

    def test_compute_decay_half_life(self):
        from detection.risk import compute_decay
        result = compute_decay(48)  # default half-life is 48h
        assert result == pytest.approx(0.5, abs=0.01)

    def test_compute_decay_negative(self):
        from detection.risk import compute_decay
        assert compute_decay(-5) == 1.0

    def test_compute_decay_double_half_life(self):
        from detection.risk import compute_decay
        result = compute_decay(96)  # 2 half-lives
        assert result == pytest.approx(0.25, abs=0.01)

    def test_classify_trend_spike(self):
        from detection.risk import classify_trend
        assert classify_trend(30, 10) == "spike"

    def test_classify_trend_rising(self):
        from detection.risk import classify_trend
        assert classify_trend(20, 10) == "rising"

    def test_classify_trend_falling(self):
        from detection.risk import classify_trend
        assert classify_trend(3, 10) == "falling"

    def test_classify_trend_stable(self):
        from detection.risk import classify_trend
        assert classify_trend(10, 10) == "stable"

    def test_classify_trend_zero_baseline(self):
        from detection.risk import classify_trend
        assert classify_trend(5, 0) == "stable"

    def test_weights_sum_to_one(self):
        from detection.risk import WEIGHTS
        total = sum(WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=0.001)


class TestVelocity:
    def test_periods_defined(self):
        from detection.velocity import PERIODS
        assert "1h" in PERIODS
        assert "6h" in PERIODS
        assert "24h" in PERIODS

    def test_period_fractions(self):
        from detection.velocity import PERIODS
        assert PERIODS["24h"] == 1.0
        assert PERIODS["1h"] == pytest.approx(1/24, abs=0.001)


class TestAlerts:
    def test_fire_alert_basic(self):
        """Test that fire_alert constructs the right data."""
        # This needs a DB, so just test the module imports cleanly
        from detection.alerts import fire_alert, check_cooldown, run_alert_evaluation
        assert callable(fire_alert)
        assert callable(check_cooldown)
        assert callable(run_alert_evaluation)


class TestPredictions:
    def test_timeframe_hours(self):
        from detection.predictions import TIMEFRAME_HOURS
        assert TIMEFRAME_HOURS["24h"] == 24
        assert TIMEFRAME_HOURS["7d"] == 168
        assert TIMEFRAME_HOURS["30d"] == 720

    def test_compute_calibration_imports(self):
        from detection.predictions import compute_calibration, compute_scorecard, compute_surprise_index
        assert callable(compute_calibration)
        assert callable(compute_scorecard)
        assert callable(compute_surprise_index)
