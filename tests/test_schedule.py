from datetime import datetime
import pytest
from stock_signal.schedule import should_run


@pytest.mark.parametrize('stamp,slot,expected', [
    ('2026-01-06T21:59:59+00:00', 17, False),
    ('2026-01-06T22:00:00+00:00', 17, True), # Winter: KST 07:00.
    ('2026-07-07T21:00:00+00:00', 17, True), # Summer: KST 06:00.
    ('2026-03-06T22:00:00+00:00', 17, True), # Before DST starts.
    ('2026-03-09T21:00:00+00:00', 17, True), # After DST starts.
    ('2026-10-30T21:00:00+00:00', 17, True),
    ('2026-11-02T22:00:00+00:00', 17, True), # After DST ends.
    ('2026-07-07T18:00:00+00:00', 14, False), # Regular day: skip early slot.
    ('2026-11-27T19:00:00+00:00', 14, True), # Black Friday 13:00 close.
    ('2026-11-27T22:00:00+00:00', 17, True), # Early close +4h retry.
    ('2026-09-07T21:00:00+00:00', 17, False), # Labor Day.
    ('2026-09-06T21:00:00+00:00', 17, False), # Sunday.
    ('2026-01-07T05:30:00+00:00', 17, True), # Delayed into next NY date.
])
def test_close_plus_one_hour(stamp, slot, expected):
    assert should_run(datetime.fromisoformat(stamp), f'0 {slot} * * 1-5') is expected

from stock_signal.schedule import scheduled_attempt, complete_for

@pytest.mark.parametrize('stamp,cron,hours,day', [
    ('2026-07-07T00:00:00+00:00', '0 20 * * 1-5', 4, '2026-07-06'),
    ('2026-07-11T04:00:00+00:00', '0 0 * * 2-6', 8, '2026-07-10'),
    ('2026-01-10T05:00:00+00:00', '0 0 * * 2-6', 8, '2026-01-09'),
    ('2026-11-28T02:00:00+00:00', '0 21 * * 1-5', 8, '2026-11-27'),
])
def test_retry_dates_include_friday_dst_and_early_close(stamp, cron, hours, day):
    assert scheduled_attempt(datetime.fromisoformat(stamp), cron) == {'date': day, 'hours': hours}


def test_midnight_holiday_slot_does_not_collect():
    assert scheduled_attempt(datetime.fromisoformat('2026-09-08T04:00:00+00:00'), '0 0 * * 2-6') is None


def test_completion_requires_both_current_and_matching_config():
    state = {'latest': {'date': '2026-09-08'}, 'config': {'v': 1}}
    comparison = {'end': '2026-09-08', 'signal_config': {'v': 1}}
    assert complete_for('2026-09-08', state, comparison, {'v': 1})
    assert not complete_for('2026-09-08', state, comparison, {'v': 2})
    comparison['end'] = '2026-09-04'
    assert not complete_for('2026-09-08', state, comparison, {'v': 1})
