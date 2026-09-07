import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from stock_signal.engine import allocation, calculate, market_state
from stock_signal import app

C = json.loads((Path(__file__).resolve().parents[1] / 'config.json').read_text())


@pytest.mark.parametrize('close,prior,expected', [
    (101, 'bear', 'bear'), (101.001, 'bear', 'bull'),
    (95, 'bull', 'bull'), (94.999, 'bull', 'bear'),
    (100, None, None), (100, 'bear', 'bear'), (100, 'bull', 'bull')])
def test_hysteresis_boundaries(close, prior, expected):
    assert market_state(close, 100, prior, C) == expected


@pytest.mark.parametrize('market,vix,dd,target', [
    ('bull', 27.99, .09, 'TQQQ'), ('bull', 28, .09, 'MIX'),
    ('bull', 20, .090001, 'MIX'), ('bear', 17.99, .2, 'MIX'),
    ('bear', 18, 0, 'CASH'), (None, 10, 0, None)])
def test_allocations(market, vix, dd, target):
    assert allocation(market, vix, dd, C) == target


def test_no_invented_initial_state_and_vix_can_change_target():
    c = dict(C, ma_days=3, high_days=3, vix_days=2)
    rows = [dict(date=f'2026-01-{i:02}', close=p, vix=v)
            for i, (p, v) in enumerate([(100, 10), (100, 10), (100, 10),
                                       (110, 10), (110, 50)], 1)]
    result = calculate(rows, c)
    assert result[0]['date'] == '2026-01-04'
    assert result[0]['initial'] and not result[0]['changed']
    assert result[-1]['market'] == 'bull'
    assert result[-1]['target'] == 'MIX' and result[-1]['changed']
    assert result == calculate(rows, c)  # Replay is deterministic.


def test_future_prices_cannot_change_previous_signals():
    c = dict(C, ma_days=3, high_days=3, vix_days=2)
    rows = [dict(date=f'2026-01-{i:02}', close=100+i*5, vix=10) for i in range(1, 9)]
    assert calculate(rows, c) == calculate(rows + [dict(date='2026-01-09', close=1, vix=80)], c)[:-1]


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), 0, -1])
def test_reject_bad_prices(bad):
    with pytest.raises(ValueError):
        calculate([dict(date='2026-01-01', close=bad, vix=10)], C)


def test_missing_session_not_silently_skipped():
    with pytest.raises(ValueError, match='2026-01-02'):
        app.align_prices({'2026-01-02': 100}, {}, ['2026-01-02'], '2026-01-02')


def test_holiday_and_early_close_calendar():
    # Labor Day Monday: previous Friday remains the latest completed session.
    cal, _, expected, _ = app.trading_calendar(datetime(2026, 9, 7, 23, tzinfo=timezone.utc), '2026-01-01')
    assert expected == '2026-09-04'
    assert cal.next_session(expected).strftime('%Y-%m-%d') == '2026-09-08'
    assert cal.session_close('2026-11-27').hour == 18  # 13:00 New York.


def test_failure_preserves_state_and_builds_error(tmp_path, monkeypatch):
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    (tmp_path / 'data').mkdir()
    (tmp_path / 'web').mkdir()
    (tmp_path / 'config.json').write_text(json.dumps(C))
    (tmp_path / 'web/template.html').write_text('__SIGNAL_DATA__')
    saved = {'latest': {'date': '2026-09-04'}, 'history': []}
    app.atomic_json(tmp_path / 'data/state.json', saved)
    before = (tmp_path / 'data/state.json').read_bytes()
    def fail(*args):
        raise ValueError('simulated source outage')
    monkeypatch.setattr(app, 'refresh', fail)
    monkeypatch.setattr('sys.argv', ['app'])
    assert app.main() == 1
    assert (tmp_path / 'data/state.json').read_bytes() == before
    payload = json.loads((tmp_path / 'site/index.html').read_text(encoding='utf-8'))
    assert payload['status']['ok'] is False
    assert payload['state']['latest']['date'] == '2026-09-04'
