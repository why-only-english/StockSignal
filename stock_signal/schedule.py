"""Select the one scheduled slot that matches the market's actual close + 1h."""
from datetime import datetime, timedelta, timezone
import os
from zoneinfo import ZoneInfo

import exchange_calendars as xc

NY = ZoneInfo('America/New_York')
SLOTS = {'0 14 * * 1-5': 14, '0 17 * * 1-5': 17}


def should_run(now, schedule):
    if schedule not in SLOTS:
        raise ValueError('Unknown scheduled event')
    if now.tzinfo is None:
        raise ValueError('Timezone-aware time is required')
    today = now.astimezone(NY).date()
    cal = xc.get_calendar('XNYS', start=today - timedelta(days=10), end=today + timedelta(days=10))
    # Allow delayed jobs across midnight, but never run before the due time.
    for date in (today, today - timedelta(days=1)):
        if not cal.is_session(str(date)):
            continue
        due = cal.session_close(str(date)).to_pydatetime() + timedelta(hours=1)
        if due.astimezone(NY).hour != SLOTS[schedule]:
            continue
        if due <= now < due + timedelta(hours=12):
            return True
    return False


def main():
    run = (os.environ.get('EVENT_NAME') == 'workflow_dispatch' or
           should_run(datetime.now(timezone.utc), os.environ.get('SCHEDULE', '')))
    value = 'true' if run else 'false'
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write(f'run={value}\n')
    print('Run collection: ' + value)


if __name__ == '__main__':
    main()
