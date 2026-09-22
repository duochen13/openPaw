"""Issue #42: sub-100-word per-stock TLDR generated from computed data."""

from portfolio_analysis.render import _TLDR_MAX_WORDS, _tldr_text


def _regime(alphas, slopes, betas):
    return {
        "windows": {
            "250": {
                "alpha_annualized": alphas,
                "alpha_slope": slopes,
                "beta": betas,
            }
        }
    }


def _move(date, kind="move", facts=None, evidence_status="missing"):
    return {
        "date": date,
        "kind": kind,
        "facts": facts or [],
        "evidence_status": evidence_status,
        "return": 0.05,
        "z": 2.6,
        "beta": 1.1,
        "idiosyncratic_component": 0.04,
    }


def _full_regime():
    alphas = [-0.12 + 0.001 * i for i in range(60)]
    slopes = [0.001] * 60
    betas = [1.30 - 0.004 * i for i in range(60)]
    return _regime(alphas, slopes, betas)


def test_tldr_hard_word_cap():
    # Pathological input: many moves, many facts, long labels.
    facts = [
        {"label": f"8-K filing number {i} with a very long descriptive label", "date": "2024-04-25"}
        for i in range(30)
    ]
    moves = [_move(f"2024-04-{25 - (i % 5):02d}", facts=facts) for i in range(50)]
    text = _tldr_text(factor={"beta": 2.5}, regime=_full_regime(), moves=moves, benchmark="QQQ")
    words = text.split()
    assert len(words) <= _TLDR_MAX_WORDS
    assert _TLDR_MAX_WORDS == 100


def test_tldr_honest_when_no_events_collected():
    moves = [_move("2024-04-25"), _move("2024-04-24")]
    text = _tldr_text(factor={"beta": 1.1}, regime=_full_regime(), moves=moves, benchmark="QQQ")
    assert "unidentified" in text
    assert len(text.split()) <= _TLDR_MAX_WORDS


def test_tldr_honest_when_no_unusual_moves():
    text = _tldr_text(factor={"beta": 1.1}, regime=_full_regime(), moves=[], benchmark="QQQ")
    assert "No unusual moves were flagged" in text


def test_tldr_interpretation_labeled_not_presented_as_fact():
    text = _tldr_text(factor={"beta": 1.1}, regime=_full_regime(), moves=[], benchmark="QQQ")
    assert "Interpretation:" in text


def test_tldr_covers_alpha_direction_and_beta_trend():
    text = _tldr_text(factor={"beta": 1.06}, regime=_full_regime(), moves=[], benchmark="QQQ")
    # alpha negative + positive slope -> improving
    assert "improving" in text
    # beta fell from 1.30 -> 1.06 over the window
    assert "down from 1.30" in text
    assert "vs QQQ" in text


def test_tldr_beta_bucket_wording():
    low = _tldr_text(factor={"beta": 0.3}, regime=_regime([], [], []), moves=[], benchmark="QQQ")
    assert "barely tracks the benchmark" in low
    high = _tldr_text(factor={"beta": 1.8}, regime=_regime([], [], []), moves=[], benchmark="QQQ")
    assert "amplifies market moves" in high


def test_tldr_degrades_gracefully_on_short_history():
    text = _tldr_text(factor=None, regime=_regime([], [], []), moves=[], benchmark="QQQ")
    assert "unavailable" in text
    assert len(text.split()) <= _TLDR_MAX_WORDS


def test_tldr_driver_buckets_count_earnings_and_filings():
    facts = [
        {"label": "Quarterly earnings reported", "date": "2024-04-25"},
        {"label": "8-K current report", "date": "2024-04-25"},
    ]
    moves = [_move("2024-04-25", facts=facts), _move("2024-04-24")]
    text = _tldr_text(factor={"beta": 1.1}, regime=_full_regime(), moves=moves, benchmark="QQQ")
    assert "Earnings reports lined up with 1 of 2 unusual moves" in text
    assert "sec filings lined up with 1 of 2 unusual moves" in text


def test_tldr_incoming_catalysts_honest_about_gap():
    text = _tldr_text(factor={"beta": 1.1}, regime=_full_regime(), moves=[], benchmark="QQQ")
    assert "No upcoming catalyst dates are available" in text
