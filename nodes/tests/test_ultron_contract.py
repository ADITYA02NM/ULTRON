"""The shared node contract must stay in step with the risk engine.

If someone changes a threshold in one place and not the other, the dashboard and
the shelf indicator start disagreeing about what RED means while both insist
they are right. These tests make that drift a build failure.
"""

from __future__ import annotations

import pytest

import risk_engine
from ultron import BAND_THRESHOLDS, RISK_WEIGHTS, band_for_score


def test_risk_engine_uses_the_shared_weights():
    assert risk_engine.RISK_WEIGHTS == RISK_WEIGHTS


def test_risk_engine_uses_the_shared_thresholds():
    assert risk_engine.BAND_THRESHOLDS == BAND_THRESHOLDS


def test_risk_engine_uses_the_shared_band_function():
    assert risk_engine.band_for_score is band_for_score


def test_weights_total_one():
    assert sum(RISK_WEIGHTS.values()) == pytest.approx(1.0)


def test_thresholds_are_descending_and_end_at_zero():
    thresholds = [t for t, _ in BAND_THRESHOLDS]
    assert thresholds == sorted(thresholds, reverse=True)
    assert thresholds[-1] == 0


def test_every_band_is_reachable():
    assert {name for _, name in BAND_THRESHOLDS} == {
        band_for_score(t) for t, _ in BAND_THRESHOLDS
    }
