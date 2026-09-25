from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

import pandas as pd

from src.backtest.engine import run_backtest_for_ticker
from src.data.loader import load_ticker_data
from src.engine.metrics import summarize_trades
from src.engine.signals import StrategyParams


@dataclass(frozen=True)
class WalkForwardResult:
    windows: pd.DataFrame


def _candidate_params(base: StrategyParams) -> list[StrategyParams]:
    windows = sorted({max(5, base.window_profile - 2), base.window_profile, base.window_profile + 2})
    tolerances = sorted({round(base.price_tolerance * 0.8, 4), base.price_tolerance, round(base.price_tolerance * 1.2, 4)})
    thresholds = sorted({round(base.lvn_threshold * 0.8, 4), base.lvn_threshold, round(base.lvn_threshold * 1.2, 4)})
    candidates: list[StrategyParams] = []
    for window_profile in windows:
        for price_tolerance in tolerances:
            for lvn_threshold in thresholds:
                candidates.append(
                    StrategyParams(
                        window_profile=window_profile,
                        price_tolerance=price_tolerance,
                        lvn_threshold=lvn_threshold,
                        bin_step=base.bin_step,
                        min_profile_levels=base.min_profile_levels,
                        rsi_period=base.rsi_period,
                        rsi_long_max=base.rsi_long_max,
                        rsi_short_min=base.rsi_short_min,
                    )
                )
    return candidates


def _best_train_params(
    train_df: pd.DataFrame,
    ticker: str,
    base_params: StrategyParams,
    investimento_per_trade: float,
    commissione_apertura: float,
    commissione_chiusura: float,
) -> StrategyParams:
    best_params = base_params
    best_score = float("-inf")
    best_profit_factor = float("-inf")
    with tempfile.TemporaryDirectory(prefix="lvn_wf_train_") as tmp_dir:
        temp_dir = Path(tmp_dir)
        train_df.to_csv(temp_dir / f"{ticker}.csv", index=False)
        for candidate in _candidate_params(base_params):
            trades = run_backtest_for_ticker(temp_dir, ticker, candidate, investimento_per_trade, commissione_apertura, commissione_chiusura)
            _, summary = summarize_trades(trades)
            row = summary.iloc[0]
            score = float(row.get("total_pnl", 0.0))
            pf = float(row.get("profit_factor", 0.0))
            if score > best_score or (score == best_score and pf > best_profit_factor):
                best_score = score
                best_profit_factor = pf
                best_params = candidate
    return best_params


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
    df = load_ticker_data(data_dir, ticker)
    rows: list[dict[str, float | int | str]] = []
    start = 0
    while start + train_size + test_size <= len(df):
        chunk = df.iloc[start : start + train_size + test_size].copy()
        train_chunk = chunk.iloc[:train_size].copy()
        test_chunk = chunk.iloc[train_size:].copy()
        best_params = _best_train_params(
            train_chunk,
            ticker,
            params,
            investimento_per_trade,
            commissione_apertura,
            commissione_chiusura,
        )
        with tempfile.TemporaryDirectory(prefix="lvn_wf_test_") as tmp_dir:
            temp_dir = Path(tmp_dir)
            test_chunk.to_csv(temp_dir / f"{ticker}.csv", index=False)
            trades = run_backtest_for_ticker(temp_dir, ticker, best_params, investimento_per_trade, commissione_apertura, commissione_chiusura)
        _, summary = summarize_trades(trades)
        row = summary.iloc[0].to_dict()
        row["window_start"] = start
        row["window_end"] = start + train_size + test_size
        row["best_window_profile"] = best_params.window_profile
        row["best_price_tolerance"] = best_params.price_tolerance
        row["best_lvn_threshold"] = best_params.lvn_threshold
        rows.append(row)
        start += test_size
    return WalkForwardResult(windows=pd.DataFrame(rows))
