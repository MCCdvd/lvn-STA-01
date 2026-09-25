from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.loader import load_ticker_data
from src.engine.position import PositionState, close_trade, open_position
from src.engine.signals import StrategyParams, signal_for_index
from src.utils.constants import TRADE_COLUMNS


def _update_position(
    position: PositionState,
    df: pd.DataFrame,
    idx: int,
    date_str: str,
    current_price: float,
    params: StrategyParams,
    commissione_chiusura: float,
) -> dict[str, str | float | int] | None:
    if not position.tp1_hit:
        if position.direction == "LONG" and current_price <= position.entry_price * 0.97:
            return close_trade(position, date_str, current_price, "Hard stop exit", commissione_chiusura)
        if position.direction == "SHORT" and current_price >= position.entry_price * 1.03:
            return close_trade(position, date_str, current_price, "Hard stop exit", commissione_chiusura)

        signal, _, _, _ = signal_for_index(df, idx, params)
        opposite_signal = "SHORT" if position.direction == "LONG" else "LONG"
        if signal == opposite_signal:
            return close_trade(position, date_str, current_price, "Opposite LVN exit", commissione_chiusura)
    else:
        if position.direction == "LONG":
            position.current_stop = max(position.current_stop, current_price * 0.98)
            if current_price <= position.current_stop:
                return close_trade(position, date_str, current_price, "Trailing stop exit", commissione_chiusura)
        else:
            if position.current_stop == 0.0:
                position.current_stop = current_price * 1.02
            position.current_stop = min(position.current_stop, current_price * 1.02)
            if current_price >= position.current_stop:
                return close_trade(position, date_str, current_price, "Trailing stop exit", commissione_chiusura)
    return None


def run_backtest_for_ticker(
    data_dir: Path,
    ticker: str,
    params: StrategyParams,
    investimento_per_trade: float,
    commissione_apertura: float,
    commissione_chiusura: float,
) -> pd.DataFrame:
    df = load_ticker_data(data_dir, ticker)
    if len(df) < params.window_profile + 1:
        return pd.DataFrame(columns=TRADE_COLUMNS)

    trades: list[dict[str, str | float | int]] = []
    position: PositionState | None = None

    for idx in range(params.window_profile, len(df)):
        row = df.iloc[idx]
        date_str = str(pd.to_datetime(row["Date"]).date())
        close_price = float(row["Close"])
        signal, _, _, _ = signal_for_index(df, idx, params)
        closed_this_bar = False

        if position is not None:
            closed_trade = _update_position(position, df, idx, date_str, close_price, params, commissione_chiusura)
            if closed_trade is not None:
                trades.append(closed_trade)
                position = None
                closed_this_bar = True

        if position is None and (not closed_this_bar) and signal in {"LONG", "SHORT"}:
            position = open_position(ticker, signal, date_str, close_price, investimento_per_trade, commissione_apertura)

    if position is not None:
        last_row = df.iloc[-1]
        trades.append(close_trade(position, str(pd.to_datetime(last_row["Date"]).date()), float(last_row["Close"]), "End of data", commissione_chiusura))

    return pd.DataFrame(trades, columns=TRADE_COLUMNS)


def run_backtest_for_universe(
    data_dir: Path,
    tickers: list[str],
    params: StrategyParams,
    investimento_per_trade: float,
    commissione_apertura: float,
    commissione_chiusura: float,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for ticker in tickers:
        trades = run_backtest_for_ticker(data_dir, ticker, params, investimento_per_trade, commissione_apertura, commissione_chiusura)
        if not trades.empty:
            frames.append(trades)
    if not frames:
        return pd.DataFrame(columns=TRADE_COLUMNS)
    return pd.concat(frames, ignore_index=True)
