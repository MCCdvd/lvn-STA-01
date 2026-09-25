from __future__ import annotations

import itertools
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from src.backtest.engine import run_backtest_for_ticker, run_backtest_for_universe
from src.engine.metrics import summarize_trades
from src.engine.signals import StrategyParams


def parse_int_list(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def parse_float_list(raw: str) -> list[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def score_ticker_combos(
    data_dir: Path,
    ticker: str,
    combos: list[tuple[int, float, float]],
    base_params: StrategyParams,
    investimento_per_trade: float,
    commissione_apertura: float,
    commissione_chiusura: float,
) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for window_profile, price_tolerance, lvn_threshold in combos:
        params = StrategyParams(
            window_profile=window_profile,
            price_tolerance=price_tolerance,
            lvn_threshold=lvn_threshold,
            bin_step=base_params.bin_step,
            min_profile_levels=base_params.min_profile_levels,
            rsi_period=base_params.rsi_period,
            rsi_long_max=base_params.rsi_long_max,
            rsi_short_min=base_params.rsi_short_min,
        )
        trades_df = run_backtest_for_ticker(
            data_dir,
            ticker,
            params,
            investimento_per_trade,
            commissione_apertura,
            commissione_chiusura,
        )
        _, summary_global_df = summarize_trades(trades_df)
        metrics = summary_global_df.iloc[0].to_dict()
        metrics.update(
            {
                "ticker": ticker,
                "window_profile": window_profile,
                "price_tolerance": price_tolerance,
                "lvn_threshold": lvn_threshold,
                "trade_count": len(trades_df),
            }
        )
        rows.append(metrics)
    return pd.DataFrame(rows)


def run_grid_search(
    data_dir: Path,
    output_dir: Path,
    tickers: list[str],
    base_params: StrategyParams,
    window_profiles: list[int],
    price_tolerances: list[float],
    lvn_thresholds: list[float],
    top_n: int,
    investimento_per_trade: float,
    commissione_apertura: float,
    commissione_chiusura: float,
) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    combos = list(itertools.product(window_profiles, price_tolerances, lvn_thresholds))
    if not combos:
        raise ValueError("No parameter combinations available")

    baseline = run_backtest_for_universe(data_dir, tickers, base_params, investimento_per_trade, commissione_apertura, commissione_chiusura)
    baseline_dir = output_dir / "baseline_global"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    baseline.to_csv(baseline_dir / "trades.csv", index=False)
    baseline_by_ticker, baseline_global = summarize_trades(baseline)
    baseline_by_ticker.to_csv(baseline_dir / "summary_by_ticker.csv", index=False)
    baseline_global.to_csv(baseline_dir / "summary_global.csv", index=False)
    pd.DataFrame([asdict(base_params)]).to_csv(baseline_dir / "params.csv", index=False)

    per_ticker_root = output_dir / "per_ticker"
    per_ticker_root.mkdir(parents=True, exist_ok=True)
    best_params_rows: list[dict[str, float | int | str]] = []
    best_trades_frames: list[pd.DataFrame] = []

    for ticker in tickers:
        scored = score_ticker_combos(
            data_dir,
            ticker,
            combos,
            base_params,
            investimento_per_trade,
            commissione_apertura,
            commissione_chiusura,
        )
        scored = scored.sort_values(
            by=["profit_factor", "total_pnl", "max_drawdown", "trade_count"],
            ascending=[False, False, True, False],
        ).reset_index(drop=True)
        if scored.empty:
            continue
        ticker_dir = per_ticker_root / ticker
        ticker_dir.mkdir(parents=True, exist_ok=True)
        scored.to_csv(ticker_dir / "results.csv", index=False)
        scored.head(max(top_n, 1)).to_csv(ticker_dir / "ranking.csv", index=False)
        best = scored.iloc[0].to_dict()
        best_params_rows.append(best)
        pd.DataFrame([best]).to_csv(ticker_dir / "best_params.csv", index=False)

        best_params = StrategyParams(
            window_profile=int(best["window_profile"]),
            price_tolerance=float(best["price_tolerance"]),
            lvn_threshold=float(best["lvn_threshold"]),
            bin_step=base_params.bin_step,
            min_profile_levels=base_params.min_profile_levels,
            rsi_period=base_params.rsi_period,
            rsi_long_max=base_params.rsi_long_max,
            rsi_short_min=base_params.rsi_short_min,
        )
        best_trades = run_backtest_for_ticker(
            data_dir,
            ticker,
            best_params,
            investimento_per_trade,
            commissione_apertura,
            commissione_chiusura,
        )
        if not best_trades.empty:
            best_trades_frames.append(best_trades)

    best_global_dir = output_dir / "per_ticker_best"
    best_global_legacy_dir = output_dir / "per_ticker_best_global"
    best_global_dir.mkdir(parents=True, exist_ok=True)
    best_global_legacy_dir.mkdir(parents=True, exist_ok=True)
    best_params_df = pd.DataFrame(best_params_rows)
    best_params_df.to_csv(best_global_dir / "params.csv", index=False)
    best_params_df.to_csv(best_global_legacy_dir / "best_params_all_tickers.csv", index=False)

    per_ticker_best = pd.concat(best_trades_frames, ignore_index=True) if best_trades_frames else pd.DataFrame()
    per_ticker_best.to_csv(best_global_dir / "trades.csv", index=False)
    per_ticker_best.to_csv(best_global_legacy_dir / "trades.csv", index=False)
    best_by_ticker, best_global = summarize_trades(per_ticker_best)
    best_by_ticker.to_csv(best_global_dir / "summary_by_ticker.csv", index=False)
    best_global.to_csv(best_global_dir / "summary_global.csv", index=False)
    best_by_ticker.to_csv(best_global_legacy_dir / "summary_by_ticker.csv", index=False)
    best_global.to_csv(best_global_legacy_dir / "summary_global.csv", index=False)

    comparison = pd.DataFrame(
        [
            {"scenario": "baseline_global", **baseline_global.iloc[0].to_dict()},
            {"scenario": "per_ticker_best", **best_global.iloc[0].to_dict()},
        ]
    )
    comparison.to_csv(output_dir / "comparison_baseline_vs_per_ticker.csv", index=False)
    return pd.DataFrame(best_params_rows)
