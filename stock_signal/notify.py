"""Private SMTP notifications; recipient addresses never enter persisted state."""
from email.message import EmailMessage
import os
import re
import smtplib
import ssl
import sys

from .app import ROOT, atomic_json, read_json

MARKETS = {'bull': '상승', 'bear': '하락'}
TARGETS = {'TQQQ': 'TQQQ 100%', 'MIX': 'QQQ 50% + QLD 50%', 'CASH': '현금 100%'}


def checkpoint(row):
    return {key: row[key] for key in ('date', 'market', 'target')}


def changes(history, previous):
    events = []
    for row in history:
        if row['date'] <= previous['date']:
            continue
        if (row['market'], row['target']) != (previous['market'], previous['target']):
            events.append((previous, row))
        previous = row
    return events


def message(sender, events):
    mail = EmailMessage()
    mail['From'] = sender
    mail['To'] = 'undisclosed-recipients:;'
    mail['Subject'] = f"[Stock Signal] 신호 변경 · {events[-1][1]['date']}"
    lines = ['종가 기준 전략 신호가 변경됐습니다.', '']
    for before, after in events:
        lines.extend([
            f"미국 종가 기준일: {after['date']}",
            f"시장: {MARKETS[before['market']]} → {MARKETS[after['market']]}",
            f"목표 비중: {TARGETS[before['target']]} → {TARGETS[after['target']]}",
            f"판단 지표: 250일선 대비 {after['distance']:+.2%}, "
            f"VIX10 {after['vix10']:.2f}, 고점 대비 낙폭 {after['drawdown']:.2%}",
            '종가 확인 후 다음 거래일에 적용하는 신호입니다.', '',
        ])
    lines.append('https://stocksignal-psi.vercel.app/')
    mail.set_content('\n'.join(lines))
    return mail


def run():
    keys = ('MAIL_USERNAME', 'MAIL_PASSWORD', 'MAIL_TO')
    values = [os.environ.get(key, '').strip() for key in keys]
    if not any(values):
        print('Email notifications disabled: secrets not configured')
        return
    if not all(values):
        raise ValueError('Incomplete mail secrets')
    sender, password, raw_recipients = values
    recipients = list(dict.fromkeys(re.split(r'[,;\s]+', raw_recipients)))
    if any(not re.fullmatch(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+', address)
           for address in [sender, *recipients]):
        raise ValueError('Invalid mail address configuration')
    state = read_json(ROOT / 'data/state.json')
    path = ROOT / 'data/notification.json'
    latest = state['latest']
    if not path.exists():
        atomic_json(path, checkpoint(latest))
        print('Email baseline initialized; no historical email sent')
        return
    previous = read_json(path)
    if latest['date'] < previous['date']:
        raise ValueError('Signal older than notification checkpoint')
    events = changes(state['history'], previous)
    if events:
        host = os.environ.get('MAIL_HOST') or 'smtp.gmail.com'
        port = int(os.environ.get('MAIL_PORT') or '465')
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as smtp:
            smtp.login(sender, password)
            refused = smtp.send_message(message(sender, events), from_addr=sender, to_addrs=recipients)
            if refused:
                raise RuntimeError('Some recipients were refused')
        print('Signal notification accepted by SMTP server')
    else:
        print('No new market or allocation change; no email sent')
    atomic_json(path, checkpoint(latest))


if __name__ == '__main__':
    try:
        run()
    except Exception:
        # SMTP errors may contain private recipient addresses. Never print them.
        print('Email notification failed; check mail settings and provider. Checkpoint unchanged.', file=sys.stderr)
        sys.exit(1)
