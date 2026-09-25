from __future__ import annotations

import os
import tempfile
import unittest

import pandas as pd

from backtest import run_backtest_for_ticker
from engine import StrategyParams


class RunBacktestForTickerTests(unittest.TestCase):
    def test_ignores_legacy_progress_kwargs(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            ticker = "A2A"
            pd.DataFrame(
                {
                    "Date": pd.date_range("2024-01-01", periods=8, freq="D"),
                    "Close": [10.0, 10.2, 10.1, 10.3, 10.0, 10.4, 10.2, 10.5],
                    "Volume": [100, 120, 110, 130, 90, 150, 140, 160],
                }
            ).to_csv(os.path.join(data_dir, f"{ticker}.csv"), index=False)

            params = StrategyParams(
                window_profile=3,
                price_tolerance=0.1,
                lvn_threshold=0.5,
                bin_step=0.05,
                min_profile_levels=2,
                rsi_period=2,
                rsi_long_max=35.0,
                rsi_short_min=65.0,
            )

            trades_df = run_backtest_for_ticker(
                data_dir=data_dir,
                ticker=ticker,
                params=params,
                investimento_per_trade=10_000.0,
                commissione_apertura=10.0,
                commissione_chiusura=10.0,
                progress_display=object(),
                progress_update_interval=0.0,
                enable_progress=True,
            )

            self.assertIsInstance(trades_df, pd.DataFrame)


if __name__ == "__main__":
    unittest.main()
