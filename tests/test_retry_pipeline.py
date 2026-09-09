import json
import pytest
from stock_signal import app, comparison
from stock_signal.errors import DataPending
from stock_signal.report import failed


@pytest.mark.parametrize('status,final,expected', [
    ({'ok': True, 'comparison_pending': True}, False, False),
    ({'ok': True, 'comparison_pending': True}, True, True),
    ({'ok': False, 'signal_pending': True}, False, False),
    ({'ok': False, 'signal_pending': True}, True, True),
    ({'ok': True, 'comparison_ok': False}, False, True),
    ({'ok': False}, False, True),
    ({'ok': True, 'comparison_ok': True}, True, False),
])
def test_report(status, final, expected):
    assert failed(status, final) is expected


@pytest.mark.parametrize('already_done', [False, True])
def test_retry_skips_current_signal_and_preserves_comparison(tmp_path, monkeypatch, already_done):
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    monkeypatch.setattr('sys.argv', ['app'])
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    (tmp_path / 'data').mkdir()
    config = {'history_start': '2000-01-01'}
    app.atomic_json(tmp_path / 'config.json', config)
    app.atomic_json(tmp_path / 'data/state.json', {'latest': {'date': '2026-09-08'}, 'config': config})
    original = {'end': '2026-09-08' if already_done else '2026-09-04', 'signal_config': config}
    app.atomic_json(tmp_path / 'data/comparison.json', original)
    monkeypatch.setattr(app, 'trading_calendar', lambda *a: (None, None, '2026-09-08', None))
    monkeypatch.setattr(app, 'refresh', lambda *a: pytest.fail('Current signal must not be fetched'))
    calls = []
    def refresh(*args):
        calls.append(True)
        raise DataPending('Missing latest ETF close: QQQ 2026-09-08')
    monkeypatch.setattr(comparison, 'refresh', refresh)
    monkeypatch.setattr(app, 'build', lambda status: None)
    assert app.main() == 0
    assert len(calls) == (0 if already_done else 1)
    assert app.read_json(tmp_path / 'data/comparison.json') == original
    status = app.read_json(tmp_path / 'work/status.json')
    assert status['ok']
    assert status.get('comparison_pending', False) is (not already_done)
