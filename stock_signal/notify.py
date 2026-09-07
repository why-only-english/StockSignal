"""Private SMTP notifications; recipient addresses never enter persisted state."""
from email.message import EmailMessage
from html import escape
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


def message(sender, events, test=False):
    mail = EmailMessage()
    mail['From'] = sender
    mail['To'] = 'undisclosed-recipients:;'
    mail['Subject'] = ('[테스트] ' if test else '') + f"[Stock Signal] 신호 변경 · {events[-1][1]['date']}"
    notice = '테스트 메일입니다. 아래는 과거 신호 변경 예시이며, 오늘 발생한 변경이나 매매 지시가 아닙니다.'
    lines = ([notice, ''] if test else []) + ['종가 기준 전략 신호가 변경됐습니다.', '']
    cards = []
    for before, after in events:
        lines.extend([
            f"미국 종가 기준일: {after['date']}",
            f"시장: {MARKETS[before['market']]} → {MARKETS[after['market']]}",
            f"목표 비중: {TARGETS[before['target']]} → {TARGETS[after['target']]}",
            f"판단 지표: 250일선 대비 {after['distance']:+.2%}, "
            f"VIX10 {after['vix10']:.2f}, 고점 대비 낙폭 {after['drawdown']:.2%}",
            '종가 확인 후 다음 거래일에 적용하는 신호입니다.', '',
        ])
        color = '#9c4037' if after['target'] == 'CASH' else '#17634e'
        changed = []
        if before['market'] != after['market']:
            changed.append('시장 상태 변경')
        if before['target'] != after['target']:
            changed.append('목표 비중 변경')
        cells = []
        for label, value in (
            ('250일선 대비', f"{after['distance']:+.2%}"),
            ('VIX 10일 평균', f"{after['vix10']:.2f}"),
            ('고점 대비 낙폭', f"{after['drawdown']:.2%}"),
        ):
            cells.append(f'<td width="33%" valign="top" style="padding:14px 6px;text-align:center;">'
                         f'<div style="font-size:11px;color:#64716a;line-height:1.6;">{label}</div>'
                         f'<div style="font-size:20px;font-weight:700;color:#20372c;margin-top:5px;">{value}</div></td>')
        cards.append(f'''
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:24px;border-top:1px solid #dce3dd;">
<tr><td style="padding:20px 0 12px;font-size:12px;color:#64716a;line-height:1.8;">미국 종가 기준일 · <strong style="color:#20372c;">{escape(after['date'])}</strong><br>{' · '.join(changed)}</td></tr>
<tr><td><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td width="46%" valign="top" style="padding:16px 10px;background:#f3f4f0;border-radius:6px;">
<div style="font-size:11px;color:#64716a;letter-spacing:1px;">변경 전</div>
<div style="font-size:14px;color:#526259;margin:12px 0 5px;">{MARKETS[before['market']]} 시장</div>
<div style="font-size:18px;font-weight:700;color:#526259;line-height:1.6;">{TARGETS[before['target']]}</div></td>
<td width="8%" align="center" style="font-size:20px;color:#819087;">→</td>
<td width="46%" valign="top" style="padding:16px 10px;background:#edf5ef;border-top:3px solid {color};border-radius:6px;">
<div style="font-size:11px;color:{color};letter-spacing:1px;">변경 후</div>
<div style="font-size:14px;color:{color};margin:12px 0 5px;">{MARKETS[after['market']]} 시장</div>
<div style="font-size:18px;font-weight:700;color:{color};line-height:1.6;">{TARGETS[after['target']]}</div></td>
</tr></table></td></tr>
<tr><td style="padding-top:14px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-bottom:1px solid #dce3dd;">{''.join(['<tr>', *cells, '</tr>'])}</table></td></tr>
</table>''')
    lines.append('https://stocksignal-psi.vercel.app/')
    mail.set_content('\n'.join(lines))
    banner = (f'<div style="padding:12px 14px;margin:20px 0;background:#fff3d9;border-left:3px solid #b77a1b;font-size:12px;line-height:1.8;color:#73501b;"><strong>테스트 발송</strong><br>{notice}</div>' if test else '')
    html = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f2f3ee;font-family:Arial,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;color:#20372c;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{'테스트 · 과거 변경 예시' if test else '시장과 목표 비중의 변경 내용을 확인하세요.'}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f2f3ee;"><tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#ffffff;border-top:4px solid #17634e;">
<tr><td style="padding:28px 22px;">
<div style="font-family:Georgia,serif;font-size:28px;letter-spacing:-1px;color:#20372c;">Stock Signal<span style="color:#17634e;">.</span></div>
<div style="margin-top:24px;font-size:11px;font-weight:700;letter-spacing:2px;color:#17634e;">SIGNAL UPDATE</div>
<h1 style="font-size:25px;line-height:1.5;font-weight:700;margin:8px 0;">{'신호 알림 미리보기' if test else '투자 신호가 변경됐습니다'}</h1>
<p style="margin:0;font-size:13px;line-height:1.9;color:#64716a;">종가 기준 시장 상태와 목표 비중을 확인하세요.</p>
{banner}{''.join(cards)}
<p style="font-size:12px;line-height:1.9;color:#64716a;margin:22px 0;">종가 확인 후 <strong style="color:#20372c;">다음 거래일에 적용</strong>하는 신호입니다.<br>실제 보유 비중과 주문 체결을 추적하거나 자동으로 매매하지 않습니다.</p>
<table role="presentation" cellpadding="0" cellspacing="0"><tr><td bgcolor="#17634e" style="border-radius:5px;"><a href="https://stocksignal-psi.vercel.app/" style="display:inline-block;padding:14px 22px;font-size:14px;font-weight:700;color:#ffffff;text-decoration:none;">대시보드 확인하기 →</a></td></tr></table>
<p style="border-top:1px solid #dce3dd;padding-top:18px;margin:26px 0 0;font-size:11px;line-height:1.9;color:#7a857e;">Stock Signal · 등록한 수신 주소로 보내는 알림입니다.</p>
</td></tr></table></td></tr></table></body></html>'''
    mail.add_alternative(html, subtype='html')
    return mail


def run(test=False):
    keys = ('MAIL_USERNAME', 'MAIL_PASSWORD', 'MAIL_TO')
    values = [os.environ.get(key, '').strip() for key in keys]
    if not any(values):
        if test:
            raise ValueError('Mail secrets required for test')
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
    if test:
        history = state['history']
        events = changes(history, history[0])[-1:]
        if not events:
            raise ValueError('No historical change available for test')
    elif not path.exists():
        atomic_json(path, checkpoint(latest))
        print('Email baseline initialized; no historical email sent')
        return
    else:
        previous = read_json(path)
        if latest['date'] < previous['date']:
            raise ValueError('Signal older than notification checkpoint')
        events = changes(state['history'], previous)
    if events:
        host = os.environ.get('MAIL_HOST') or 'smtp.gmail.com'
        port = int(os.environ.get('MAIL_PORT') or '465')
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as smtp:
            smtp.login(sender, password)
            mail = message(sender, events, test=test)
            refused = smtp.send_message(mail, from_addr=sender, to_addrs=recipients)
            if refused:
                raise RuntimeError('Some recipients were refused')
        print('Signal notification accepted by SMTP server')
    else:
        print('No new market or allocation change; no email sent')
    if not test:
        atomic_json(path, checkpoint(latest))


if __name__ == '__main__':
    try:
        run(test='--test' in sys.argv)
    except Exception:
        # SMTP errors may contain private recipient addresses. Never print them.
        print('Email notification failed; check mail settings and provider. Checkpoint unchanged.', file=sys.stderr)
        sys.exit(1)
