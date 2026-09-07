"""Pure strategy decisions. Only completed, aligned trading sessions enter here."""
from collections import deque
import math


def market_state(close, average, previous, config):
    if close > average * config['bull_multiplier']:
        return 'bull'
    if close < average * config['bear_multiplier']:
        return 'bear'
    return previous


def allocation(market, vix10, drawdown, config):
    if market is None:
        return None
    if market == 'bull':
        if vix10 < config['bull_vix_limit'] and drawdown <= config['drawdown_limit']:
            return 'TQQQ'
        return 'MIX'
    return 'MIX' if vix10 < config['bear_vix_limit'] else 'CASH'


def calculate(rows, config):
    prices = deque(maxlen=max(config['ma_days'], config['high_days']))
    vixes = deque(maxlen=config['vix_days'])
    result = []
    market = None
    prior_target = None
    last_date = ''
    for row in rows:
        if row['date'] <= last_date:
            raise ValueError('Dates must be unique and increasing')
        last_date = row['date']
        close, vix = float(row['close']), float(row['vix'])
        if not all(math.isfinite(v) and v > 0 for v in (close, vix)):
            raise ValueError('Prices must be finite and positive')
        prices.append(close)
        vixes.append(vix)
        if len(prices) < prices.maxlen or len(vixes) < vixes.maxlen:
            continue
        average = sum(list(prices)[-config['ma_days']:]) / config['ma_days']
        high = max(list(prices)[-config['high_days']:])
        vix10 = sum(vixes) / len(vixes)
        dd = (high - close) / high
        market = market_state(close, average, market, config)
        target = allocation(market, vix10, dd, config)
        if target is None:
            continue  # Never invent a first state in the neutral band.
        result.append(dict(date=row['date'], close=close, vix=vix,
                           ma=average, high=high, vix10=vix10,
                           drawdown=dd, distance=close / average - 1,
                           market=market, target=target,
                           changed=prior_target is not None and target != prior_target,
                           initial=prior_target is None))
        prior_target = target
    if not result:
        raise ValueError('Insufficient history to establish a market state')
    return result
