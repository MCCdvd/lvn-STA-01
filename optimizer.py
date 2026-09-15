from __future__ import annotations

import argparse
import itertools
import os
import subprocess
from dataclasses import asdict
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from backtest import build_summaries, run_backtest_df
from config import CONFIG
from engine import StrategyParams, safe_read_csv


def _parse_int_list(raw: str) -> List[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def _parse_float_list(raw: str) -> List[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def _discover_tickers(data_dir: str) -> List[str]:
    if not os.path.isdir(data_dir):
        return []
    return sorted([f.replace(".csv", "") for f in os.listdir(data_dir) if f.endswith(".csv") and f != "failed_tickers.csv"])


def _git_commit_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=os.path.dirname(__file__), text=True).strip()
    except Exception:
        return "unknown"


def _split_dataset(df: pd.DataFrame, train_ratio: float, validation_ratio: float, test_ratio: float) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    total = len(df)
    if total < 30:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    ratio_sum = train_ratio + validation_ratio + test_ratio
    if ratio_sum <= 0:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    train_end = int(total * (train_ratio / ratio_sum))
    val_end = train_end + int(total * (validation_ratio / ratio_sum))
    train_end = max(train_end, 1)
    val_end = max(val_end, train_end + 1)
    val_end = min(val_end, total - 1)

    train_df = df.iloc[:train_end].copy()
    validation_df = df.iloc[train_end:val_end].copy()
    test_df = df.iloc[val_end:].copy()
    return train_df, validation_df, test_df


def _robust_score(metrics: Dict) -> float:
    total_pnl = float(metrics.get("total_pnl", 0.0))
    max_drawdown = float(metrics.get("max_drawdown", 0.0))
    win_rate = float(metrics.get("overall_win_rate", 0.0))
    raw_pf = float(metrics.get("profit_factor", 0.0))
    bounded_pf = 5.0 if np.isinf(raw_pf) else max(0.0, min(raw_pf, 5.0))
    return round(total_pnl - (0.6 * max_drawdown) + (8.0 * bounded_pf) + (0.2 * win_rate), 4)


def _apply_portfolio_capital_constraint(trades_df: pd.DataFrame, initial_capital: float) -> pd.DataFrame:
    if trades_df.empty:
        return trades_df.copy()

    work = trades_df.copy().reset_index(drop=True)
    work["__trade_id"] = work.index
    work["entry_date"] = pd.to_datetime(work["entry_date"], errors="coerce")
    work["exit_date"] = pd.to_datetime(work["exit_date"], errors="coerce")
    work = work.dropna(subset=["entry_date", "exit_date"]).sort_values(["entry_date", "exit_date", "__trade_id"]).reset_index(drop=True)
    if work.empty:
        return trades_df.iloc[0:0].copy()

    cash = float(initial_capital)
    open_positions: List[Dict] = []
    accepted_ids: List[int] = []

    for row in work.itertuples(index=False):
        entry_dt = row.entry_date
        still_open: List[Dict] = []
        for pos in open_positions:
            if pos["exit_date"] <= entry_dt:
                cash += pos["reserved_notional"] + pos["realized_pnl"]
            else:
                still_open.append(pos)
        open_positions = still_open

        reserved_notional = float(getattr(row, "entry_notional", float(row.entry_price) * float(row.quantity)))
        if reserved_notional <= 0:
            continue
        if cash < reserved_notional:
            continue

        cash -= reserved_notional
        open_positions.append({"exit_date": row.exit_date, "reserved_notional": reserved_notional, "realized_pnl": float(row.realized_pnl)})
        accepted_ids.append(int(row.__trade_id))

    constrained = trades_df.copy().reset_index(drop=True)
    constrained = constrained[constrained.index.isin(accepted_ids)].copy()
    return constrained.reset_index(drop=True)


def _score_ticker_combos(ticker: str, train_df: pd.DataFrame, validation_df: pd.DataFrame, combos: List[tuple]) -> pd.DataFrame:
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
        train_trades_df = run_backtest_df(
            df=train_df,
            ticker=ticker,
            params=params,
            investimento_per_trade=CONFIG.strategy.investimento_per_trade,
            commissione_apertura=CONFIG.strategy.commissione_apertura,
            commissione_chiusura=CONFIG.strategy.commissione_chiusura,
        )
        validation_trades_df = run_backtest_df(
            df=validation_df,
            ticker=ticker,
            params=params,
            investimento_per_trade=CONFIG.strategy.investimento_per_trade,
            commissione_apertura=CONFIG.strategy.commissione_apertura,
            commissione_chiusura=CONFIG.strategy.commissione_chiusura,
        )
        _, validation_summary_global_df = build_summaries(validation_trades_df)
        validation_metrics = validation_summary_global_df.iloc[0].to_dict()
        rows.append(
            {
                "ticker": ticker,
                "window_profile": window_profile,
                "price_tolerance": price_tolerance,
                "lvn_threshold": lvn_threshold,
                "train_trade_count": len(train_trades_df),
                "validation_trade_count": len(validation_trades_df),
                "validation_total_pnl": validation_metrics["total_pnl"],
                "validation_overall_win_rate": validation_metrics["overall_win_rate"],
                "validation_profit_factor": validation_metrics["profit_factor"],
                "validation_max_drawdown": validation_metrics["max_drawdown"],
                "validation_score": _robust_score(validation_metrics),
            }
        )
    return pd.DataFrame(rows)


def _run_baseline_test_set(data_dir: str, tickers: List[str], params: StrategyParams) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    all_test_trades: List[pd.DataFrame] = []
    split_rows: List[Dict] = []
    for ticker in tickers:
        df = safe_read_csv(os.path.join(data_dir, f"{ticker}.csv"))
        if df is None or df.empty:
            continue
        train_df, validation_df, test_df = _split_dataset(
            df,
            CONFIG.grid.train_ratio,
            CONFIG.grid.validation_ratio,
            CONFIG.grid.test_ratio,
        )
        if test_df.empty:
            continue
        split_rows.append({"ticker": ticker, "rows_total": len(df), "rows_train": len(train_df), "rows_validation": len(validation_df), "rows_test": len(test_df)})
        trades = run_backtest_df(
            df=test_df,
            ticker=ticker,
            params=params,
            investimento_per_trade=CONFIG.strategy.investimento_per_trade,
            commissione_apertura=CONFIG.strategy.commissione_apertura,
            commissione_chiusura=CONFIG.strategy.commissione_chiusura,
        )
        if not trades.empty:
            all_test_trades.append(trades)
    if not all_test_trades:
        empty_trades = pd.DataFrame(
            columns=["ticker", "direction", "entry_date", "exit_date", "entry_price", "entry_notional", "exit_price", "quantity", "realized_pnl", "return_pct", "exit_reason"]
        )
        return empty_trades, empty_trades.copy(), pd.DataFrame(split_rows)

    unconstrained = pd.concat(all_test_trades, ignore_index=True)
    constrained = _apply_portfolio_capital_constraint(unconstrained, CONFIG.strategy.portfolio_initial_capital)
    return unconstrained, constrained, pd.DataFrame(split_rows)


def _save_baseline(output_dir: str, params: StrategyParams, unconstrained_trades_df: pd.DataFrame, constrained_trades_df: pd.DataFrame) -> pd.DataFrame:
    baseline_dir = os.path.join(output_dir, "baseline_global")
    os.makedirs(baseline_dir, exist_ok=True)
    summary_by_ticker_df, summary_global_df = build_summaries(constrained_trades_df, initial_capital=CONFIG.strategy.portfolio_initial_capital)
    unconstrained_trades_df.to_csv(os.path.join(baseline_dir, "trades_unconstrained.csv"), index=False)
    constrained_trades_df.to_csv(os.path.join(baseline_dir, "trades.csv"), index=False)
    summary_by_ticker_df.to_csv(os.path.join(baseline_dir, "summary_by_ticker.csv"), index=False)
    summary_global_df.to_csv(os.path.join(baseline_dir, "summary_global.csv"), index=False)
    pd.DataFrame([asdict(params)]).to_csv(os.path.join(baseline_dir, "params.csv"), index=False)
    return summary_global_df


def _run_final_test_for_ticker(ticker: str, test_df: pd.DataFrame, best_params_row: Dict) -> pd.DataFrame:
    best_params = StrategyParams(
        window_profile=int(best_params_row["window_profile"]),
        price_tolerance=float(best_params_row["price_tolerance"]),
        lvn_threshold=float(best_params_row["lvn_threshold"]),
        bin_step=CONFIG.strategy.bin_step,
        min_profile_levels=CONFIG.strategy.min_profile_levels,
        rsi_period=CONFIG.strategy.rsi_period,
        rsi_long_max=CONFIG.strategy.rsi_long_max,
        rsi_short_min=CONFIG.strategy.rsi_short_min,
    )
    return run_backtest_df(
        df=test_df,
        ticker=ticker,
        params=best_params,
        investimento_per_trade=CONFIG.strategy.investimento_per_trade,
        commissione_apertura=CONFIG.strategy.commissione_apertura,
        commissione_chiusura=CONFIG.strategy.commissione_chiusura,
    )


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
    baseline_unconstrained, baseline_constrained, split_info_df = _run_baseline_test_set(args.data_dir, tickers, baseline_params)
    baseline_global_df = _save_baseline(args.output_dir, baseline_params, baseline_unconstrained, baseline_constrained)

    per_ticker_root = os.path.join(args.output_dir, "per_ticker")
    os.makedirs(per_ticker_root, exist_ok=True)

    best_params_rows: List[Dict] = []
    best_test_trades_frames: List[pd.DataFrame] = []

    for ticker in tickers:
        df = safe_read_csv(os.path.join(args.data_dir, f"{ticker}.csv"))
        if df is None or df.empty:
            continue
        train_df, validation_df, test_df = _split_dataset(
            df,
            CONFIG.grid.train_ratio,
            CONFIG.grid.validation_ratio,
            CONFIG.grid.test_ratio,
        )
        if train_df.empty or validation_df.empty or test_df.empty:
            continue

        ticker_results = _score_ticker_combos(ticker, train_df, validation_df, combos)
        ticker_results = ticker_results.sort_values(
            by=["validation_score", "validation_total_pnl", "validation_profit_factor", "validation_max_drawdown"],
            ascending=[False, False, False, True],
        ).reset_index(drop=True)

        ticker_dir = os.path.join(per_ticker_root, ticker)
        os.makedirs(ticker_dir, exist_ok=True)
        ticker_results.to_csv(os.path.join(ticker_dir, "results.csv"), index=False)
        ticker_results.head(max(args.top_n, 1)).to_csv(os.path.join(ticker_dir, "ranking.csv"), index=False)
        if ticker_results.empty:
            continue

        best = ticker_results.iloc[0].to_dict()
        best_test_trades = _run_final_test_for_ticker(ticker, test_df, best)
        _, best_test_summary_global = build_summaries(best_test_trades)
        best["test_trade_count"] = len(best_test_trades)
        best["test_total_pnl"] = float(best_test_summary_global.iloc[0]["total_pnl"])
        best["test_overall_win_rate"] = float(best_test_summary_global.iloc[0]["overall_win_rate"])
        best["test_profit_factor"] = float(best_test_summary_global.iloc[0]["profit_factor"])
        best["test_max_drawdown"] = float(best_test_summary_global.iloc[0]["max_drawdown"])
        pd.DataFrame([best]).to_csv(os.path.join(ticker_dir, "best_params.csv"), index=False)
        best_params_rows.append(best)

        if not best_test_trades.empty:
            best_test_trades_frames.append(best_test_trades)

    best_global_dir = os.path.join(args.output_dir, "per_ticker_best_global")
    os.makedirs(best_global_dir, exist_ok=True)
    best_params_df = pd.DataFrame(best_params_rows)
    best_params_df.to_csv(os.path.join(best_global_dir, "best_params_all_tickers.csv"), index=False)

    if best_test_trades_frames:
        per_ticker_best_unconstrained = pd.concat(best_test_trades_frames, ignore_index=True)
    else:
        per_ticker_best_unconstrained = pd.DataFrame(
            columns=["ticker", "direction", "entry_date", "exit_date", "entry_price", "entry_notional", "exit_price", "quantity", "realized_pnl", "return_pct", "exit_reason"]
        )

    per_ticker_best_constrained = _apply_portfolio_capital_constraint(per_ticker_best_unconstrained, CONFIG.strategy.portfolio_initial_capital)
    per_ticker_best_unconstrained.to_csv(os.path.join(best_global_dir, "trades_unconstrained.csv"), index=False)
    per_ticker_best_constrained.to_csv(os.path.join(best_global_dir, "trades.csv"), index=False)
    per_ticker_summary_by_ticker, per_ticker_summary_global = build_summaries(
        per_ticker_best_constrained, initial_capital=CONFIG.strategy.portfolio_initial_capital
    )
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
                "max_drawdown_pct": baseline_row["max_drawdown_pct"],
            },
            {
                "scenario": "per_ticker_best_global",
                "total_trades": optimized_row["total_trades"],
                "total_pnl": optimized_row["total_pnl"],
                "overall_win_rate": optimized_row["overall_win_rate"],
                "profit_factor": optimized_row["profit_factor"],
                "max_drawdown": optimized_row["max_drawdown"],
                "max_drawdown_pct": optimized_row["max_drawdown_pct"],
            },
            {
                "scenario": "delta_optimized_minus_baseline",
                "total_trades": float(optimized_row["total_trades"]) - float(baseline_row["total_trades"]),
                "total_pnl": float(optimized_row["total_pnl"]) - float(baseline_row["total_pnl"]),
                "overall_win_rate": float(optimized_row["overall_win_rate"]) - float(baseline_row["overall_win_rate"]),
                "profit_factor": float(optimized_row["profit_factor"]) - float(baseline_row["profit_factor"]),
                "max_drawdown": float(optimized_row["max_drawdown"]) - float(baseline_row["max_drawdown"]),
                "max_drawdown_pct": float(optimized_row["max_drawdown_pct"]) - float(baseline_row["max_drawdown_pct"]),
            },
        ]
    )
    comparison.to_csv(os.path.join(args.output_dir, "comparison_baseline_vs_per_ticker.csv"), index=False)

    run_metadata = pd.DataFrame(
        [
            {
                "data_dir": os.path.abspath(args.data_dir),
                "output_dir": os.path.abspath(args.output_dir),
                "ticker_count": len(tickers),
                "combo_count": len(combos),
                "train_ratio": CONFIG.grid.train_ratio,
                "validation_ratio": CONFIG.grid.validation_ratio,
                "test_ratio": CONFIG.grid.test_ratio,
                "portfolio_initial_capital": CONFIG.strategy.portfolio_initial_capital,
                "execution_model": "signal_on_close_execute_next_bar_open_or_close",
                "selection_metric": "validation_score_composite",
                "git_commit": _git_commit_hash(),
            }
        ]
    )
    run_metadata.to_csv(os.path.join(args.output_dir, "run_metadata.csv"), index=False)
    split_info_df.to_csv(os.path.join(args.output_dir, "split_info_by_ticker.csv"), index=False)
    print(f"Ottimizzazione completata. Output: {args.output_dir}")


if __name__ == "__main__":
    main()
