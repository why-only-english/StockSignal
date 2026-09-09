import pytest

from stock_signal.app import align_prices, supplement_vix


def sources():
    primary = {f'2026-09-{i:02d}': 15.0 + i / 10 for i in range(1, 8)}
    fallback = {**primary, '2026-09-08': 15.72, '2026-09-09': 16.0}
    return primary, fallback


def test_recent_tail_only_and_no_future_value():
    primary, fallback = sources()
    merged, added = supplement_vix(primary, fallback, '2026-09-08')
    assert merged['2026-09-08'] == 15.72
    assert added == ['2026-09-08']
    assert '2026-09-09' not in merged
    assert '2026-09-08' not in primary


def test_disagreement_rejected():
    primary, fallback = sources()
    fallback['2026-09-07'] += 1
    with pytest.raises(ValueError, match='agree'):
        supplement_vix(primary, fallback, '2026-09-08')


def test_both_sources_delayed():
    primary, fallback = sources()
    fallback.pop('2026-09-08')
    with pytest.raises(ValueError, match='unavailable'):
        supplement_vix(primary, fallback, '2026-09-08')


def test_history_gap_still_rejected():
    primary, fallback = sources()
    primary.pop('2026-09-02')
    merged, _ = supplement_vix(primary, fallback, '2026-09-08')
    assert '2026-09-02' not in merged
    with pytest.raises(ValueError, match='Missing VIX'):
        align_prices({'2026-09-02': 100}, merged, ['2026-09-02'], '2026-09-02')


def test_stale_primary_rejected():
    primary, fallback = sources()
    with pytest.raises(ValueError, match='stale'):
        supplement_vix(primary, fallback, '2026-09-20')


def test_invalid_fallback_rejected():
    primary, fallback = sources()
    fallback['2026-09-08'] = float('nan')
    with pytest.raises(ValueError, match='Invalid'):
        supplement_vix(primary, fallback, '2026-09-08')
