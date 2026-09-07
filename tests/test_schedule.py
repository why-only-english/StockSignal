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
    ('2026-11-27T22:00:00+00:00', 17, False), # No second collection.
    ('2026-09-07T21:00:00+00:00', 17, False), # Labor Day.
    ('2026-09-06T21:00:00+00:00', 17, False), # Sunday.
    ('2026-01-07T05:30:00+00:00', 17, True), # Delayed into next NY date.
])
def test_close_plus_one_hour(stamp, slot, expected):
    assert should_run(datetime.fromisoformat(stamp), f'0 {slot} * * 1-5') is expected
