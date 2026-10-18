"""Risk engine — the maths that decides what the operator is told.

These are the checks that matter operationally: the score is the one number the
whole appliance exists to produce, so a wrong weight or an inverted comparison
is a security defect, not a cosmetic one.
"""

from __future__ import annotations

import pytest

from risk_engine import (
    HALF_LIFE_S,
    HYSTERESIS,
    RISK_WEIGHTS,
    Engine,
    band_for_score,
    severity_from_envelope,
)

T = 1_000_000.0


def test_weights_total_one():
    """If the weights drift from 1.0 the score can never reach 100 and every
    PURPLE response in the runbook becomes unreachable."""
    assert sum(RISK_WEIGHTS.values()) == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("score", "band"),
    [(0, "GREEN"), (29.9, "GREEN"), (30, "YELLOW"), (59.9, "YELLOW"),
     (60, "RED"), (84.9, "RED"), (85, "PURPLE"), (100, "PURPLE")],
)
def test_band_thresholds(score, band):
    assert band_for_score(score) == band


def test_idle_engine_scores_zero():
    assert Engine().raw_score(T) == 0.0


def test_a_source_is_worth_its_weight():
    e = Engine()
    e.observe("suricata", 1.0, T)
    assert e.raw_score(T) == pytest.approx(40.0)


def test_contribution_halves_every_half_life():
    e = Engine()
    e.observe("suricata", 1.0, T)
    assert e.raw_score(T + HALF_LIFE_S) == pytest.approx(20.0)
    assert e.raw_score(T + 2 * HALF_LIFE_S) == pytest.approx(10.0)


def test_all_sources_saturate_to_purple():
    e = Engine()
    for source in RISK_WEIGHTS:
        e.observe(source, 1.0, T)
    assert e.raw_score(T) == pytest.approx(100.0)
    assert band_for_score(e.raw_score(T)) == "PURPLE"


def test_a_lone_case_open_must_not_be_green():
    """Regression: the tripwire is the one sensor that cannot be disarmed
    remotely, and a case physically opened is the least ambiguous signal the
    appliance has. At severity 0.9 it scored 27 — BELOW the 30 threshold — so
    the unit could have its own lid prised off while the shelf read GREEN."""
    source, severity = severity_from_envelope("ultron/tripwire/pi3a", {"edge": "open"})
    assert source == "tripwire"

    e = Engine()
    e.observe(source, severity, T)
    score, band, _ = e.step(T)
    assert score == pytest.approx(30.0)
    assert band == "YELLOW"


def test_bands_rise_at_once_but_fall_slowly():
    """Regression: the rise/fall branches were inverted, which made the display
    lag an escalation and drop the moment a score dipped a hair."""
    e = Engine()
    e.observe("tripwire", 1.0, T)
    _, band, _ = e.step(T)
    assert band == "YELLOW"          # a rise is taken immediately

    # A hair inside the hysteresis margin must NOT drop the band.
    _, band, _ = e.step(T + HALF_LIFE_S * 0.05)
    assert band == "YELLOW"

    # Clearly clear of the margin does drop it.
    _, band, _ = e.step(T + 4 * HALF_LIFE_S)
    assert band == "GREEN"


def test_hysteresis_margin_is_actually_used():
    """Guard the constant itself: a zero margin would reintroduce flicker."""
    assert HYSTERESIS > 0
    e = Engine()
    e.observe("tripwire", 1.0, T)
    e.step(T)
    # Decay just past the threshold but inside the margin, and confirm that the
    # raw band really has flipped while the published band has not.
    later = T + HALF_LIFE_S * 0.05
    assert band_for_score(e.raw_score(later)) == "GREEN"
    assert e.step(later)[1] == "YELLOW"


def test_a_milder_event_does_not_erase_a_fresh_serious_one():
    e = Engine()
    e.observe("suricata", 1.0, T)
    e.observe("suricata", 0.2, T + 1.0)
    # Not 8.0 — the serious reading must survive the milder one, and it is
    # measured after a second of decay rather than assumed fresh.
    assert e.raw_score(T + 1.0) == pytest.approx(39.77, abs=0.01)


def test_closing_a_case_is_not_a_detection():
    assert severity_from_envelope("ultron/tripwire/pi3a", {"edge": "close"}) is None


def test_known_endpoints_never_move_the_score():
    assert severity_from_envelope("ultron/lan/aabbccddeeff", {"known": True}) is None


def test_an_unknown_endpoint_is_a_prompt_not_an_alarm():
    source, severity = severity_from_envelope(
        "ultron/lan/aabbccddeeff", {"known": False}
    )
    assert source == "lan"
    assert 0.0 < severity < 0.5


def test_unrelated_topics_are_ignored():
    assert severity_from_envelope("ultron/health/pi4", {"node": "pi4"}) is None


def test_severity_is_clamped():
    e = Engine()
    e.observe("suricata", 5.0, T)
    assert e.raw_score(T) == pytest.approx(40.0)
    e.observe("suricata", -3.0, T + 1.0)
    assert e.raw_score(T + 1.0) <= 40.0
