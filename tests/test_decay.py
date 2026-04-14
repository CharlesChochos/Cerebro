"""
Phase 2 Tests — Confidence decay module.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from processing.decay import compute_decay, HALF_LIFE_HOURS


class TestComputeDecay:
    def test_no_decay_at_zero_hours(self):
        assert compute_decay(0.9, 0) == 0.9

    def test_no_decay_negative_hours(self):
        assert compute_decay(0.9, -5) == 0.9

    def test_half_life_halves_confidence(self):
        result = compute_decay(1.0, HALF_LIFE_HOURS)
        assert abs(result - 0.5) < 0.01

    def test_two_half_lives_quarters_confidence(self):
        result = compute_decay(1.0, HALF_LIFE_HOURS * 2)
        assert abs(result - 0.25) < 0.01

    def test_never_goes_below_minimum(self):
        result = compute_decay(0.5, 10000)  # Very long time
        assert result >= 0.01

    def test_partial_decay(self):
        """After 24 hours (half of the 48h half-life), should be ~70.7% of original."""
        result = compute_decay(1.0, 24.0)
        assert 0.69 < result < 0.72

    def test_low_initial_confidence(self):
        result = compute_decay(0.1, HALF_LIFE_HOURS)
        assert abs(result - 0.05) < 0.01

    def test_result_is_rounded(self):
        result = compute_decay(0.87654321, 12.0)
        # Should be rounded to 4 decimal places
        assert result == round(result, 4)
