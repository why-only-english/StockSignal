"""Four actual-ETF scenarios, with explicitly simplified Korean tax assumptions."""
from collections import defaultdict, deque
from datetime import date, timedelta
import math
import time

SYMBOLS = ('QQQ', 'QLD', 'TQQQ')
SERIES = (*SYMBOLS, 'strategy')
START = '2010-02-11'
weights = {'QQQ': {'QQQ': 1}, 'QLD': {'QLD': 1}, 'TQQQ': {'TQQQ': 1},
           'MIX': {'QQQ': .5, 'QLD': .5}, 'CASH': {}}


def tax(gain):
    return max(gain - 2500000, 0) * .22


class Portfolio:
    def __init__(self,name,initial_fx):
        self.name=name;self.cash=10000000/initial_fx;self.lots={s:deque() for s in SYMBOLS}
        self.gain=defaultdict(float);self.divgross=defaultdict(float);self.paid=defaultdict(float)
        self.target=None;self.turns=0
    def qty(self,s):return sum(x[0] for x in self.lots[s])
    def gross(self,p):return self.cash+sum(self.qty(s)*p[s] for s in SYMBOLS)
    def sell(self,s,qty,p,f,year):
        remaining=qty;gain=0
        while remaining>1e-9 and self.lots[s]:
            n,c=self.lots[s][0];take=min(n,remaining)
            gain+=take*p[s]*f-c*(take/n)
            if take>=n-1e-9:self.lots[s].popleft()
            else:self.lots[s][0]=[n-take,c*(1-take/n)]
            remaining-=take
        assert remaining<1e-5
        self.cash+=qty*p[s];self.gain[year]+=gain
    def invest(self,p,f):
        amount=max(0,self.cash)
        for s,w in weights[self.target].items():
            usd=amount*w
            if usd>1e-8:
                self.lots[s].append([usd/p[s],usd*f]);self.cash-=usd
    def transition(self,target,p,f,y):
        if target!=self.target:
            for s in SYMBOLS:
                q=self.qty(s)
                if q>1e-9:self.sell(s,q,p,f,y)
            self.target=target;self.turns+=1
        self.invest(p,f)
    def pay_tax(self,p,f,y):
        owed=tax(self.gain[y-1])-self.paid[y-1]
        if owed<=1e-6:return
        need=max(0,owed/f-self.cash)
        stock=sum(self.qty(s)*p[s] for s in SYMBOLS)
        if need>0:
            assert need<=stock+1e-5, 'Portfolio insolvent'
            fraction=min(1,need/stock)
            for s in SYMBOLS:
                q=self.qty(s)*fraction
                if q>1e-9:self.sell(s,q,p,f,y)
        self.cash-=owed/f;self.paid[y-1]+=owed
        assert self.cash>=-1e-5
    def net(self,p,f,y):
        unreal=sum(self.qty(s)*p[s]*f-sum(c for n,c in self.lots[s]) for s in SYMBOLS)
        outstanding=sum(max(0,tax(g)-self.paid[yr]) for yr,g in self.gain.items() if yr<y)
        current=max(0,tax(self.gain[y]+unreal)-self.paid[y])
        return self.gross(p)*f-outstanding-current


def simulate(state, frames, fx_source, payment_days=None):
    import pandas as pd
    history = state['history']
    signals = {r['date']: r for r in history}
    dates = [r['date'] for r in history if r['date'] >= START]
    if not dates or dates[0] != START:
        raise ValueError('Actual ETF comparison requires full history from 2010-02-11')
    for symbol in SYMBOLS:
        frame = frames[symbol]
        if not frame.index.is_unique or not set(dates) <= set(frame.index):
            raise ValueError('Missing or duplicate ETF trading sessions: ' + symbol)
        for column in ('Close', 'Dividends'):
            values = frame.loc[dates, column]
            if not all(math.isfinite(v) and (v > 0 if column == 'Close' else v >= 0) for v in values):
                raise ValueError('Invalid ETF prices or dividends')
        if 'Capital Gains' in frame and (frame.loc[dates, 'Capital Gains'] != 0).any():
            raise ValueError('Capital distributions need separate tax treatment')
    if not fx_source.index.is_unique:
        raise ValueError('Duplicate FX dates')
    source = fx_source.dropna().sort_index()
    valid_fx = source[source > 0]
    grid = sorted(set(valid_fx.index) | set(dates))
    fx = valid_fx.reindex(grid).ffill().reindex(dates)
    stamps = pd.Series(valid_fx.index, index=valid_fx.index).reindex(grid).ffill().reindex(dates)
    for day in dates:
        if pd.isna(fx.loc[day]) or (date.fromisoformat(day) - date.fromisoformat(stamps.loc[day])).days > 7:
            raise ValueError('Missing or stale FX data')
    if payment_days is None:
        import exchange_calendars as xc
        # Use the complete May calendar, never the last date of an unfinished download.
        cal = xc.get_calendar('XNYS', start=START, end=dates[-1][:4] + '-12-31')
        payment_days = {s.year: s.strftime('%Y-%m-%d') for s in cal.sessions if s.month == 5}
    portfolios = [Portfolio(s, float(fx.iloc[0])) for s in SERIES]
    previous_dates = [d for d in signals if d < START]
    if not previous_dates:
        raise ValueError('Prior-day signal is required')
    prior = signals[max(previous_dates)]['target']
    daily = []
    for day in dates:
        year = int(day[:4]); rate = float(fx.loc[day])
        prices = {s: float(frames[s].loc[day, 'Close']) for s in SYMBOLS}
        for portfolio in portfolios:
            for symbol in SYMBOLS:
                dividend = portfolio.qty(symbol) * float(frames[symbol].loc[day, 'Dividends'])
                portfolio.cash += dividend * .85
                portfolio.divgross[year] += dividend * rate
            if day == payment_days.get(year):
                portfolio.pay_tax(prices, rate, year)
            target = prior if portfolio.name == 'strategy' else portfolio.name
            portfolio.transition(target, prices, rate, year)
        values = [p.net(prices, rate, year) for p in portfolios]
        if not all(math.isfinite(v) and v > 0 for v in values):
            raise ValueError('Invalid portfolio value')
        daily.append({'date': day, **{key: round(value, 2) for key, value in zip(SERIES, values)}})
        prior = signals[day]['target']
    return {'schema': 1, 'initial_krw': 10000000, 'start': dates[0], 'end': dates[-1],
            'signal_config': state['config'], 'series': list(SERIES), 'daily': daily,
            'dividend_threshold_years': {p.name: [y for y, amount in p.divgross.items() if amount > 20000000]
                                         for p in portfolios},
            'sources': 'Yahoo Finance daily split-adjusted Close, dividends, KRW=X'}


def refresh(state):
    import yfinance as yf
    from .app import ROOT, atomic_json
    end = (date.fromisoformat(state['latest']['date']) + timedelta(days=1)).isoformat()
    frames = {}
    for symbol in (*SYMBOLS, 'KRW=X'):
        for attempt in range(3):
            try:
                frame = yf.Ticker(symbol).history(start='2010-02-01', end=end,
                    auto_adjust=False, actions=True, timeout=40)
                if frame.empty:
                    raise ValueError('No data for ' + symbol)
                frame.index = frame.index.strftime('%Y-%m-%d')
                frames[symbol] = frame
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(5 * (attempt + 1))
    result = simulate(state, frames, frames['KRW=X']['Close'])
    atomic_json(ROOT / 'data/comparison.json', result)
    print(f"Compared four scenarios: {result['start']} to {result['end']}")
