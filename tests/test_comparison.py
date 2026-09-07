import pandas as pd
import pytest

from stock_signal.comparison import Portfolio, simulate, tax


def inputs():
    days = ['2010-02-11', '2010-02-12', '2010-02-16']
    frames = {s: pd.DataFrame({'Close': [100., 110., 90.], 'Dividends': [0., 0., 0.]}, index=days)
              for s in ('QQQ', 'QLD', 'TQQQ')}
    state = {'config': {}, 'history': [
        {'date': '2010-02-10', 'target': 'TQQQ'},
        *[{'date': d, 'target': 'CASH'} for d in days]]}
    return state, frames, pd.Series(1000., index=days)


def test_next_session_execution_and_hypothetical_liquidation():
    state, frames, fx = inputs()
    result = simulate(state, frames, fx, {})['daily']
    assert result[0]['strategy'] == 10000000
    assert result[1]['strategy'] == 11000000
    assert result[2]['strategy'] == 11000000  # Cash after prior day's signal.
    assert result[2]['QQQ'] == 9000000  # Earlier hypothetical liquidation did not sell.


def test_missing_etf_day_rejected():
    state, frames, fx = inputs()
    frames['QLD'] = frames['QLD'].iloc[:-1]
    with pytest.raises(ValueError, match='Missing'):
        simulate(state, frames, fx, {})


def test_fx_only_forward_fills_and_rejects_stale():
    state, frames, fx = inputs()
    with pytest.raises(ValueError, match='FX'):
        simulate(state, frames, fx.iloc[1:], {})
    fx = pd.Series([1000.], index=['2010-02-01'])
    with pytest.raises(ValueError, match='FX'):
        simulate(state, frames, fx, {})


def test_dividends_net_reinvested_once():
    state, frames, fx = inputs()
    for frame in frames.values():
        frame['Close'] = 100.
        frame['Dividends'] = [0., 10., 0.]
    daily = simulate(state, frames, fx, {})['daily']
    assert daily[-1]['QQQ'] == 10850000


def test_fifo_realized_gain_uses_krw_cost():
    portfolio = Portfolio('QQQ', 1000.)
    prices = {'QQQ': 100., 'QLD': 100., 'TQQQ': 100.}
    portfolio.transition('QQQ', prices, 1000., 2020)
    portfolio.sell('QQQ', 50., prices, 1200., 2020)
    assert portfolio.gain[2020] == pytest.approx(1000000.)
    assert portfolio.qty('QQQ') == pytest.approx(50.)


def test_paid_tax_not_deducted_twice_and_sale_funds_payment():
    portfolio = Portfolio('QQQ', 1000.)
    prices = {'QQQ': 100., 'QLD': 100., 'TQQQ': 100.}
    portfolio.transition('QQQ', prices, 1000., 2020)
    portfolio.gain[2020] = 12500000.
    before = portfolio.net(prices, 1000., 2021)
    portfolio.pay_tax(prices, 1000., 2021)
    assert portfolio.paid[2020] == 2200000.
    assert portfolio.qty('QQQ') == pytest.approx(78.)
    assert portfolio.net(prices, 1000., 2021) == pytest.approx(before)
    portfolio.pay_tax(prices, 1000., 2021)
    assert portfolio.qty('QQQ') == pytest.approx(78.)


def test_annual_loss_offsets_and_deduction():
    assert tax(3000000 - 1000000) == 0
    assert tax(12500000) == 2200000
    assert tax(-1000000) == 0


def test_unchanged_mix_does_not_rebalance():
    portfolio = Portfolio('strategy', 1000.)
    prices = {'QQQ': 100., 'QLD': 100., 'TQQQ': 100.}
    portfolio.transition('MIX', prices, 1000., 2020)
    prices['QLD'] = 200.
    portfolio.transition('MIX', prices, 1000., 2020)
    assert portfolio.qty('QQQ') == portfolio.qty('QLD') == 50.
    assert portfolio.gain[2020] == 0
