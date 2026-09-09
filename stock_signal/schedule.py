"""Select close +1/+4/+8 hour slots using the exchange calendar."""
from datetime import datetime, timedelta, timezone
import os
from zoneinfo import ZoneInfo
import exchange_calendars as xc

NY = ZoneInfo('America/New_York')
SLOTS = {'0 14 * * 1-5': 14, '0 17 * * 1-5': 17,
         '0 20 * * 1-5': 20, '0 21 * * 1-5': 21, '0 0 * * 2-6': 0}


def scheduled_attempt(now, schedule):
    if schedule not in SLOTS:
        raise ValueError('Unknown scheduled event')
    if now.tzinfo is None:
        raise ValueError('Timezone-aware time is required')
    today = now.astimezone(NY).date()
    cal = xc.get_calendar('XNYS', start=today - timedelta(days=10), end=today + timedelta(days=10))
    for day in (today, today - timedelta(days=1)):
        if not cal.is_session(str(day)):
            continue
        close = cal.session_close(str(day)).to_pydatetime()
        for hours in (1, 4, 8):
            due = close + timedelta(hours=hours)
            if due.astimezone(NY).hour == SLOTS[schedule] and due <= now < due + timedelta(hours=12):
                return {'date': str(day), 'hours': hours}
    return None


def should_run(now, schedule):
    return scheduled_attempt(now, schedule) is not None


def complete_for(day, state, comparison, config):
    return (state is not None and comparison is not None
            and state.get('latest', {}).get('date') == day and state.get('config') == config
            and comparison.get('end') == day and comparison.get('signal_config') == config)


def main():
    from .app import ROOT, read_json
    manual = os.environ.get('EVENT_NAME') == 'workflow_dispatch'
    attempt = None if manual else scheduled_attempt(datetime.now(timezone.utc), os.environ.get('SCHEDULE', ''))
    run = manual or attempt is not None
    if attempt:
        def saved(name):
            path = ROOT / 'data' / name
            return read_json(path) if path.exists() else None
        run = not complete_for(attempt['date'], saved('state.json'), saved('comparison.json'), read_json(ROOT / 'config.json'))
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write(f"run={str(run).lower()}\nfinal={str(bool(attempt and attempt['hours'] == 8)).lower()}\n")
    print(f'Run collection: {run}; attempt: {attempt or "manual"}')


if __name__ == '__main__':
    main()
