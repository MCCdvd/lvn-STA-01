from __future__ import annotations

import pandas as pd

from src.engine.metrics import summarize_trades


def test_summarize_trades_adds_advanced_metrics():
    trades = pd.DataFrame(
        [
            {"ticker": "AAA", "exit_date": "2024-01-01", "realized_pnl": 100.0, "return_pct": 1.0},
            {"ticker": "AAA", "exit_date": "2024-01-02", "realized_pnl": -50.0, "return_pct": -0.5},
        ]
    )
    by_ticker, global_summary = summarize_trades(trades)
    assert "sharpe" in by_ticker.columns
    assert "sortino" in by_ticker.columns
    assert "calmar" in global_summary.columns
