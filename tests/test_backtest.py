from __future__ import annotations

import pandas as pd

from src.backtest import engine as backtest_engine
from src.backtest.engine import run_backtest_for_ticker
from src.engine.signals import StrategyParams


def test_backtest_returns_dataframe_with_expected_columns(tmp_path):
    ticker = "AAA"
    pd.DataFrame(
        {
            "Date": pd.date_range("2024-01-01", periods=40, freq="D"),
            "Close": [10 + (i % 5) * 0.1 for i in range(40)],
            "Volume": [100 + i for i in range(40)],
        }
    ).to_csv(tmp_path / f"{ticker}.csv", index=False)

    params = StrategyParams(25, 0.2, 0.9, 0.05, 5, 14, 70.0, 30.0)
    trades = run_backtest_for_ticker(tmp_path, ticker, params, 10_000.0, 10.0, 10.0)
    expected = {"ticker", "direction", "entry_date", "exit_date", "entry_price", "exit_price", "quantity", "realized_pnl", "return_pct", "exit_reason"}
    assert expected.issubset(set(trades.columns))


def test_backtest_does_not_reenter_on_same_bar_after_close(tmp_path, monkeypatch):
    ticker = "AAA"
    prices = [10.0] * 25 + [10.0, 9.5, 9.6, 9.7, 9.8]
    pd.DataFrame(
        {
            "Date": pd.date_range("2024-01-01", periods=len(prices), freq="D"),
            "Close": prices,
            "Volume": [100 + i for i in range(len(prices))],
        }
    ).to_csv(tmp_path / f"{ticker}.csv", index=False)

    def fake_signal_for_index(df, idx, params):  # noqa: ANN001
        if idx == 25:
            return "LONG", 10.0, "entry", 30.0
        if idx == 26:
            return "SHORT", 9.5, "opposite", 70.0
        return "WAIT", None, "wait", 50.0

    monkeypatch.setattr(backtest_engine, "signal_for_index", fake_signal_for_index)
    params = StrategyParams(25, 0.2, 0.9, 0.05, 5, 14, 70.0, 30.0)
    trades = run_backtest_for_ticker(tmp_path, ticker, params, 10_000.0, 10.0, 10.0)
    assert len(trades) == 1
