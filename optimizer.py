from __future__ import annotations

import argparse
import itertools
import os
import time
from dataclasses import asdict
from typing import Dict, List, Optional, Tuple

import pandas as pd

from backtest import build_summaries, run_backtest_for_ticker
from config import CONFIG
from engine import StrategyParams
from progress import ProgressDisplay, RunMetrics


def _parse_int_list(raw: str) -> List[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def _parse_float_list(raw: str) -> List[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def _discover_tickers(data_dir: str) -> List[str]:
    if not os.path.isdir(data_dir):
        return []
    return sorted([f.replace(".csv", "") for f in os.listdir(data_dir) if f.endswith(".csv") and f != "failed_tickers.csv"])


def _run_global_with_shared_params(
    data_dir: str,
    tickers: List[str],
    params: StrategyParams,
    progress_display: Optional[ProgressDisplay] = None,
    processed_units: int = 0,
) -> Tuple[pd.DataFrame, int]:
    all_trades: List[pd.DataFrame] = []
    for ticker in tickers:
        trades = run_backtest_for_ticker(
            data_dir=data_dir,
            ticker=ticker,
            params=params,
            investimento_per_trade=CONFIG.strategy.investimento_per_trade,
            commissione_apertura=CONFIG.strategy.commissione_apertura,
            commissione_chiusura=CONFIG.strategy.commissione_chiusura,
        )
        summary_row = _summary_row_for_trades(trades)
        processed_units += 1
        if progress_display is not None:
            progress_display.update(
                processed_units=processed_units,
                current_ticker=ticker,
                metrics=RunMetrics(
                    trades_found=int(len(trades)),
                    total_pnl=float(summary_row["total_pnl"]),
                    win_rate=float(summary_row["overall_win_rate"]),
                    max_drawdown=float(summary_row["max_drawdown"]),
                ),
                context="Baseline shared parameters",
            )
        if not trades.empty:
            all_trades.append(trades)
    if not all_trades:
        empty = pd.DataFrame(columns=["ticker", "direction", "entry_date", "exit_date", "entry_price", "exit_price", "quantity", "realized_pnl", "return_pct", "exit_reason"])
        return empty, processed_units
    return pd.concat(all_trades, ignore_index=True), processed_units


def _save_baseline(output_dir: str, params: StrategyParams, trades_df: pd.DataFrame) -> pd.DataFrame:
    baseline_dir = os.path.join(output_dir, "baseline_global")
    os.makedirs(baseline_dir, exist_ok=True)
    summary_by_ticker_df, summary_global_df = build_summaries(trades_df)
    trades_df.to_csv(os.path.join(baseline_dir, "trades.csv"), index=False)
    summary_by_ticker_df.to_csv(os.path.join(baseline_dir, "summary_by_ticker.csv"), index=False)
    summary_global_df.to_csv(os.path.join(baseline_dir, "summary_global.csv"), index=False)
    pd.DataFrame([asdict(params)]).to_csv(os.path.join(baseline_dir, "params.csv"), index=False)
    return summary_global_df


def _summary_row_for_trades(trades_df: pd.DataFrame) -> Dict[str, float]:
    _, summary_global_df = build_summaries(trades_df)
    if summary_global_df.empty:
        return {
            "total_trades": 0.0,
            "total_pnl": 0.0,
            "overall_win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
        }
    return summary_global_df.iloc[0].to_dict()


def _score_ticker_combos(
    data_dir: str,
    ticker: str,
    combos: List[tuple],
    progress_display: Optional[ProgressDisplay] = None,
    processed_units: int = 0,
) -> Tuple[pd.DataFrame, int]:
    rows: List[Dict] = []
    for window_profile, price_tolerance, lvn_threshold in combos:
        params = StrategyParams(
            window_profile=window_profile,
            price_tolerance=price_tolerance,
            lvn_threshold=lvn_threshold,
            bin_step=CONFIG.strategy.bin_step,
            min_profile_levels=CONFIG.strategy.min_profile_levels,
            rsi_period=CONFIG.strategy.rsi_period,
            rsi_long_max=CONFIG.strategy.rsi_long_max,
            rsi_short_min=CONFIG.strategy.rsi_short_min,
        )
        trades_df = run_backtest_for_ticker(
            data_dir=data_dir,
            ticker=ticker,
            params=params,
            investimento_per_trade=CONFIG.strategy.investimento_per_trade,
            commissione_apertura=CONFIG.strategy.commissione_apertura,
            commissione_chiusura=CONFIG.strategy.commissione_chiusura,
        )
        metrics = _summary_row_for_trades(trades_df)
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
        processed_units += 1
        if progress_display is not None:
            progress_display.update(
                processed_units=processed_units,
                current_ticker=ticker,
                metrics=RunMetrics(
                    trades_found=int(metrics["trade_count"]),
                    total_pnl=float(metrics["total_pnl"]),
                    win_rate=float(metrics["overall_win_rate"]),
                    max_drawdown=float(metrics["max_drawdown"]),
                ),
                context=f"Grid search (window={window_profile}, tolerance={price_tolerance}, lvn={lvn_threshold})",
            )
    return pd.DataFrame(rows), processed_units


def main() -> None:
    parser = argparse.ArgumentParser(description="Single ticker optimizer + baseline comparison")
    parser.add_argument("--data-dir", default=CONFIG.runtime.data_dir)
    parser.add_argument("--output-dir", default=CONFIG.runtime.output_dir)
    parser.add_argument("--tickers", nargs="*", default=None)
    parser.add_argument("--window-profiles", default=",".join(map(str, CONFIG.grid.window_profiles)))
    parser.add_argument("--price-tolerances", default=",".join(map(str, CONFIG.grid.price_tolerances)))
    parser.add_argument("--lvn-thresholds", default=",".join(map(str, CONFIG.grid.lvn_thresholds)))
    parser.add_argument("--top-n", type=int, default=CONFIG.grid.top_n)
    args = parser.parse_args()

    tickers = args.tickers if args.tickers else _discover_tickers(args.data_dir)
    if not tickers:
        raise ValueError(f"Nessun ticker CSV trovato in {args.data_dir}")

    os.makedirs(args.output_dir, exist_ok=True)
    combos = list(
        itertools.product(
            _parse_int_list(args.window_profiles),
            _parse_float_list(args.price_tolerances),
            _parse_float_list(args.lvn_thresholds),
        )
    )
    if not combos:
        raise ValueError("Nessuna combinazione parametri disponibile")

    total_progress_units = len(tickers) + (len(tickers) * len(combos)) + len(tickers)
    progress_display = ProgressDisplay(
        title="LVN Trading Strategy - Optimization Progress",
        total_units=total_progress_units,
        unit_label="runs",
        update_interval_seconds=CONFIG.progress.update_interval_seconds,
        bar_width=CONFIG.progress.bar_width,
        enabled=CONFIG.progress.enabled,
    )
    processed_units = 0
    started_at = time.monotonic()

    baseline_params = StrategyParams(
        window_profile=CONFIG.strategy.window_profile,
        price_tolerance=CONFIG.strategy.price_tolerance,
        lvn_threshold=CONFIG.strategy.lvn_threshold,
        bin_step=CONFIG.strategy.bin_step,
        min_profile_levels=CONFIG.strategy.min_profile_levels,
        rsi_period=CONFIG.strategy.rsi_period,
        rsi_long_max=CONFIG.strategy.rsi_long_max,
        rsi_short_min=CONFIG.strategy.rsi_short_min,
    )
    baseline_trades, processed_units = _run_global_with_shared_params(
        args.data_dir,
        tickers,
        baseline_params,
        progress_display=progress_display,
        processed_units=processed_units,
    )
    baseline_global_df = _save_baseline(args.output_dir, baseline_params, baseline_trades)

    per_ticker_root = os.path.join(args.output_dir, "per_ticker")
    os.makedirs(per_ticker_root, exist_ok=True)

    best_params_rows: List[Dict] = []
    best_trades_frames: List[pd.DataFrame] = []

    for ticker in tickers:
        ticker_results, processed_units = _score_ticker_combos(
            args.data_dir,
            ticker,
            combos,
            progress_display=progress_display,
            processed_units=processed_units,
        )
        ticker_results = ticker_results.sort_values(
            by=["profit_factor", "total_pnl", "max_drawdown", "trade_count"],
            ascending=[False, False, True, False],
        ).reset_index(drop=True)

        ticker_dir = os.path.join(per_ticker_root, ticker)
        os.makedirs(ticker_dir, exist_ok=True)
        ticker_results.to_csv(os.path.join(ticker_dir, "results.csv"), index=False)
        ticker_results.head(max(args.top_n, 1)).to_csv(os.path.join(ticker_dir, "ranking.csv"), index=False)

        best = ticker_results.iloc[0].to_dict()
        pd.DataFrame([best]).to_csv(os.path.join(ticker_dir, "best_params.csv"), index=False)
        best_params_rows.append(best)

        best_params = StrategyParams(
            window_profile=int(best["window_profile"]),
            price_tolerance=float(best["price_tolerance"]),
            lvn_threshold=float(best["lvn_threshold"]),
            bin_step=CONFIG.strategy.bin_step,
            min_profile_levels=CONFIG.strategy.min_profile_levels,
            rsi_period=CONFIG.strategy.rsi_period,
            rsi_long_max=CONFIG.strategy.rsi_long_max,
            rsi_short_min=CONFIG.strategy.rsi_short_min,
        )
        best_trades = run_backtest_for_ticker(
            data_dir=args.data_dir,
            ticker=ticker,
            params=best_params,
            investimento_per_trade=CONFIG.strategy.investimento_per_trade,
            commissione_apertura=CONFIG.strategy.commissione_apertura,
            commissione_chiusura=CONFIG.strategy.commissione_chiusura,
        )
        processed_units += 1
        best_summary_row = _summary_row_for_trades(best_trades)
        progress_display.record_ticker_result(ticker, int(len(best_trades)), float(best_summary_row["total_pnl"]))
        progress_display.update(
            processed_units=processed_units,
            current_ticker=ticker,
            metrics=RunMetrics(
                trades_found=int(len(best_trades)),
                total_pnl=float(best_summary_row["total_pnl"]),
                win_rate=float(best_summary_row["overall_win_rate"]),
                max_drawdown=float(best_summary_row["max_drawdown"]),
            ),
            context="Best parameters validation",
            force=processed_units == total_progress_units,
        )
        if not best_trades.empty:
            best_trades_frames.append(best_trades)

    best_global_dir = os.path.join(args.output_dir, "per_ticker_best_global")
    os.makedirs(best_global_dir, exist_ok=True)
    best_params_df = pd.DataFrame(best_params_rows)
    best_params_df.to_csv(os.path.join(best_global_dir, "best_params_all_tickers.csv"), index=False)

    if best_trades_frames:
        per_ticker_best_trades = pd.concat(best_trades_frames, ignore_index=True)
    else:
        per_ticker_best_trades = pd.DataFrame(columns=["ticker", "direction", "entry_date", "exit_date", "entry_price", "exit_price", "quantity", "realized_pnl", "return_pct", "exit_reason"])
    per_ticker_best_trades.to_csv(os.path.join(best_global_dir, "trades.csv"), index=False)
    per_ticker_summary_by_ticker, per_ticker_summary_global = build_summaries(per_ticker_best_trades)
    per_ticker_summary_by_ticker.to_csv(os.path.join(best_global_dir, "summary_by_ticker.csv"), index=False)
    per_ticker_summary_global.to_csv(os.path.join(best_global_dir, "summary_global.csv"), index=False)

    baseline_row = baseline_global_df.iloc[0]
    optimized_row = per_ticker_summary_global.iloc[0]
    comparison = pd.DataFrame(
        [
            {
                "scenario": "baseline_global",
                "total_trades": baseline_row["total_trades"],
                "total_pnl": baseline_row["total_pnl"],
                "overall_win_rate": baseline_row["overall_win_rate"],
                "profit_factor": baseline_row["profit_factor"],
                "max_drawdown": baseline_row["max_drawdown"],
            },
            {
                "scenario": "per_ticker_best_global",
                "total_trades": optimized_row["total_trades"],
                "total_pnl": optimized_row["total_pnl"],
                "overall_win_rate": optimized_row["overall_win_rate"],
                "profit_factor": optimized_row["profit_factor"],
                "max_drawdown": optimized_row["max_drawdown"],
            },
            {
                "scenario": "delta_optimized_minus_baseline",
                "total_trades": float(optimized_row["total_trades"]) - float(baseline_row["total_trades"]),
                "total_pnl": float(optimized_row["total_pnl"]) - float(baseline_row["total_pnl"]),
                "overall_win_rate": float(optimized_row["overall_win_rate"]) - float(baseline_row["overall_win_rate"]),
                "profit_factor": float(optimized_row["profit_factor"]) - float(baseline_row["profit_factor"]),
                "max_drawdown": float(optimized_row["max_drawdown"]) - float(baseline_row["max_drawdown"]),
            },
        ]
    )
    comparison.to_csv(os.path.join(args.output_dir, "comparison_baseline_vs_per_ticker.csv"), index=False)
    progress_display.print_summary(total_time_seconds=time.monotonic() - started_at)
    print(f"Ottimizzazione completata. Output: {args.output_dir}")


if __name__ == "__main__":
    main()
