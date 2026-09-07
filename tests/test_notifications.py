import json
from unittest.mock import MagicMock

import pytest

from stock_signal import notify


def row(day, market='bull', target='TQQQ'):
    return dict(date=day, market=market, target=target, distance=.02, vix10=20, drawdown=.05)


def test_market_only_and_allocation_only_changes():
    first = row('2026-09-01', target='MIX')
    market = row('2026-09-02', 'bear', 'MIX')
    target = row('2026-09-03', 'bear', 'CASH')
    assert len(notify.changes([first, market, target], first)) == 2
    assert notify.changes([first, market, target], target) == []


def test_both_changes_are_one_event_and_unchanged_days_silent():
    first = row('2026-09-01')
    last = row('2026-09-03', 'bear', 'CASH')
    events = notify.changes([first, row('2026-09-02'), last], first)
    assert len(events) == 1
    mail = notify.message('sender@example.com', events)
    assert '상승 → 하락' in mail.get_content()
    assert 'TQQQ 100% → 현금 100%' in mail.get_content()
    assert mail['To'] == 'undisclosed-recipients:;'


def test_initialization_delivery_and_rerun(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, 'ROOT', tmp_path)
    (tmp_path / 'data').mkdir()
    for key, value in {'MAIL_USERNAME':'sender@example.com', 'MAIL_PASSWORD':'fake',
                       'MAIL_TO':'one@example.com,two@example.com'}.items():
        monkeypatch.setenv(key, value)
    smtp = MagicMock()
    smtp.return_value.__enter__.return_value.send_message.return_value = {}
    monkeypatch.setattr(notify.smtplib, 'SMTP_SSL', smtp)
    first, last = row('2026-09-01'), row('2026-09-02', 'bear', 'CASH')
    path = tmp_path / 'data/state.json'
    path.write_text(json.dumps({'latest':first, 'history':[first]}))
    notify.run()
    smtp.assert_not_called()
    path.write_text(json.dumps({'latest':last, 'history':[first,last]}))
    notify.run()
    notify.run()
    assert smtp.call_count == 1
    persisted = (tmp_path / 'data/notification.json').read_text()
    assert '@' not in persisted and 'fake' not in persisted


def test_smtp_failure_preserves_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, 'ROOT', tmp_path)
    (tmp_path / 'data').mkdir()
    for key, value in {'MAIL_USERNAME':'sender@example.com', 'MAIL_PASSWORD':'fake',
                       'MAIL_TO':'one@example.com'}.items():
        monkeypatch.setenv(key, value)
    first, last = row('2026-09-01'), row('2026-09-02', 'bear', 'CASH')
    notify.atomic_json(tmp_path / 'data/state.json', {'latest':last,'history':[first,last]})
    checkpoint = tmp_path / 'data/notification.json'
    notify.atomic_json(checkpoint, notify.checkpoint(first))
    monkeypatch.setattr(notify.smtplib, 'SMTP_SSL', MagicMock(side_effect=OSError))
    with pytest.raises(OSError):
        notify.run()
    assert notify.read_json(checkpoint)['date'] == first['date']
