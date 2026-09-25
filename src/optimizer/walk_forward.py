from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

import pandas as pd

from src.backtest.engine import run_backtest_for_ticker
from src.engine.metrics import summarize_trades
from src.engine.signals import StrategyParams


@dataclass(frozen=True)
class WalkForwardResult:
    windows: pd.DataFrame


def run_walk_forward(
    data_dir: Path,
    ticker: str,
    params: StrategyParams,
    investimento_per_trade: float,
    commissione_apertura: float,
    commissione_chiusura: float,
    train_size: int = 252,
    test_size: int = 63,
) -> WalkForwardResult:
    df = pd.read_csv(data_dir / f"{ticker}.csv")
    rows: list[dict[str, float | int | str]] = []
    start = 0
    while start + train_size + test_size <= len(df):
        chunk = df.iloc[start : start + train_size + test_size].copy()
        with tempfile.TemporaryDirectory(prefix="lvn_wf_") as tmp_dir:
            temp_dir = Path(tmp_dir)
            chunk.to_csv(temp_dir / f"{ticker}.csv", index=False)
            trades = run_backtest_for_ticker(temp_dir, ticker, params, investimento_per_trade, commissione_apertura, commissione_chiusura)
        _, summary = summarize_trades(trades)
        row = summary.iloc[0].to_dict()
        row["window_start"] = start
        row["window_end"] = start + train_size + test_size
        rows.append(row)
        start += test_size
    return WalkForwardResult(windows=pd.DataFrame(rows))
