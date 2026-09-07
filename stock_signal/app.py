"""Run: python -m stock_signal.app [--build-only]. All paths are project relative."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import sys
import time
import urllib.request

from .engine import calculate

ROOT = Path(__file__).resolve().parents[1]
CBOE = 'https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(temp, path)


def trading_calendar(now, start):
    import exchange_calendars as xc
    import pandas as pd
    end = (now + timedelta(days=400)).date().isoformat()
    cal = xc.get_calendar('XNYS', start=start, end=end)
    sessions = cal.sessions
    closed = [s for s in sessions if cal.session_close(s) <= pd.Timestamp(now)]
    expected = closed[-1].strftime('%Y-%m-%d')
    future = []
    for s in sessions:
        if s.strftime('%Y-%m-%d') >= (now - timedelta(days=10)).date().isoformat():
            future.append({'date': s.strftime('%Y-%m-%d'),
                           'close': cal.session_close(s).isoformat(),
                           'open': cal.session_open(s).isoformat()})
    return cal, sessions, expected, future


def fetch_prices(config, expected):
    import yfinance as yf
    end = (datetime.fromisoformat(expected) + timedelta(days=1)).date().isoformat()
    ndx = yf.Ticker(config['symbol']).history(start=config['history_start'], end=end,
        interval='1d', auto_adjust=False, actions=False, raise_errors=True, timeout=30)
    if ndx.empty:
        raise ValueError('NDX source returned no data')
    ndx_map = {}
    for stamp, row in ndx.iterrows():
        day = stamp.strftime('%Y-%m-%d')
        if day in ndx_map:
            raise ValueError('Duplicate NDX session')
        ndx_map[day] = float(row['Close'])
    request = urllib.request.Request(CBOE, headers={'User-Agent': 'StockSignal/1.0 personal dashboard'})
    with urllib.request.urlopen(request, timeout=40) as response:
        raw = response.read().decode('utf-8-sig')
    vix_map = {}
    for row in csv.DictReader(io.StringIO(raw)):
        day = datetime.strptime(row['DATE'], '%m/%d/%Y').date().isoformat()
        if day in vix_map:
            raise ValueError('Duplicate VIX session')
        vix_map[day] = float(row['CLOSE'])
    return ndx_map, vix_map


def align_prices(ndx, vix, session_dates, expected):
    # Reject gaps, rather than silently turn a 250-session window into a longer one.
    rows = []
    for day in session_dates:
        if day > expected:
            break
        if day not in ndx or day not in vix:
            raise ValueError(f'Missing matching NDX/VIX close for {day}')
        rows.append({'date': day, 'close': ndx[day], 'vix': vix[day]})
    if not rows or rows[-1]['date'] != expected:
        raise ValueError(f'Latest completed trading session {expected} is unavailable')
    return rows


def refresh(config, now):
    cal, sessions, expected, calendar = trading_calendar(now, config['history_start'])
    prices = None
    for attempt in range(3):
        try:
            ndx, vix = fetch_prices(config, expected)
            dates = [s.strftime('%Y-%m-%d') for s in sessions]
            prices = align_prices(ndx, vix, dates, expected)
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
    signals = calculate(prices, config)
    latest = signals[-1].copy()
    next_day = cal.next_session(latest['date'])
    latest['effective_date'] = next_day.strftime('%Y-%m-%d')
    # Full replay from fixed inception repairs missed runs and preserves hysteresis.
    state = {'schema': 1, 'config': config, 'latest': latest,
             'history': signals, 'source_start': prices[0]['date'],
             'expected_date': expected, 'calendar': calendar,
             'sources': {'ndx': 'Yahoo Finance / yfinance / ^NDX Close (unadjusted)', 'vix': CBOE}}
    atomic_json(ROOT / 'data/state.json', state)
    print(f"Verified {len(prices)} sessions; {latest['date']}: {latest['market']} / {latest['target']}")


def build(status):
    state_path = ROOT / 'data/state.json'
    state = read_json(state_path) if state_path.exists() else None
    # Embed data: the same HTML works with file:// and GitHub Pages without a server.
    if state:
        state = dict(state)
        state['history'] = [r for r in state['history'] if r['changed'] or r['initial']]
    comparison_path = ROOT / 'data/comparison.json'
    comparison = read_json(comparison_path) if comparison_path.exists() else None
    payload = json.dumps({'state': state, 'status': status, 'comparison': comparison}, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    template = (ROOT / 'web/template.html').read_text(encoding='utf-8')
    output = ROOT / 'site'
    output.mkdir(exist_ok=True)
    (output / 'index.html').write_text(template.replace('__SIGNAL_DATA__', payload), encoding='utf-8')
    (output / '.nojekyll').touch()
    print(f'Built {output / "index.html"}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-only', action='store_true', help='Render saved data without network requests')
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    status = {'checked_at': now.isoformat(), 'ok': True, 'error': None}
    exit_code = 0
    if args.build_only:
        saved = ROOT / 'work/status.json'
        status = read_json(saved) if saved.exists() else {'checked_at': None, 'ok': None, 'error': None}
    else:
        try:
            refresh(read_json(ROOT / 'config.json'), now)
        except Exception as error:
            status.update(ok=False, error=f'{type(error).__name__}: {error}')
            print(f'Update failed; retaining last verified state. {status["error"]}', file=sys.stderr)
            exit_code = 1
        if status['ok']:
            try:
                from .comparison import refresh as refresh_comparison
                refresh_comparison(read_json(ROOT / 'data/state.json'))
                status['comparison_ok'] = True
            except Exception as error:
                status['comparison_ok'] = False
                print(f'Comparison refresh failed; retaining previous comparison: {type(error).__name__}', file=sys.stderr)
        atomic_json(ROOT / 'work/status.json', status)
    build(status)
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
