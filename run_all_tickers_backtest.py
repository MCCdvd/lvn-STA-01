from __future__ import annotations

import argparse
import json
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import pandas as pd

from backtest import build_summaries, run_backtest_for_ticker
from config import CONFIG
from engine import StrategyParams


@dataclass
class TickerRunSpec:
    ticker: str
    params: StrategyParams


@dataclass
class TickerBacktestResult:
    ticker: str
    status: str
    trade_count: int
    total_pnl: float
    win_rate: float
    profit_factor: float
    max_drawdown: float
    error: str
    elapsed_seconds: float


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    return f"{minutes}m {secs}s"


def _format_progress(done: int, total: int, width: int = 20) -> str:
    if total <= 0:
        return "[Progress bar: 0/0]"
    ratio = done / total
    filled = int(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[Progress bar: {done}/{total} {bar} {ratio * 100:.0f}%]"


def _safe_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number):
        return default
    return number


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _iter_ticker_payloads(payload: Any) -> List[Tuple[str, Dict[str, Any]]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("tickers"), dict):
            return [(str(k), v if isinstance(v, dict) else {}) for k, v in payload["tickers"].items()]
        if isinstance(payload.get("tickers"), list):
            rows = []
            for row in payload["tickers"]:
                if isinstance(row, dict) and row.get("ticker"):
                    rows.append((str(row["ticker"]), row))
            return rows
        rows = []
        for key, value in payload.items():
            if isinstance(value, dict):
                rows.append((str(key), value))
        if rows:
            return rows
    if isinstance(payload, list):
        rows = []
        for row in payload:
            if isinstance(row, dict) and row.get("ticker"):
                rows.append((str(row["ticker"]), row))
        return rows
    return []


def _parse_specs(optimized_params_path: str) -> Tuple[List[TickerRunSpec], List[TickerBacktestResult]]:
    payload = _load_json(optimized_params_path)
    specs: List[TickerRunSpec] = []
    invalid: List[TickerBacktestResult] = []

    for raw_ticker, row in _iter_ticker_payloads(payload):
        ticker = raw_ticker.strip().upper()
        if not ticker:
            continue
        source = row.get("params") if isinstance(row.get("params"), dict) else row

        window_profile = source.get("window_profile")
        price_tolerance = source.get("price_tolerance")
        lvn_threshold = source.get("lvn_threshold")

        if window_profile is None or price_tolerance is None or lvn_threshold is None:
            invalid.append(
                TickerBacktestResult(
                    ticker=ticker,
                    status="ERROR",
                    trade_count=0,
                    total_pnl=0.0,
                    win_rate=0.0,
                    profit_factor=0.0,
                    max_drawdown=0.0,
                    error="Missing required optimized params (window_profile, price_tolerance, lvn_threshold)",
                    elapsed_seconds=0.0,
                )
            )
            continue

        params = StrategyParams(
            window_profile=int(window_profile),
            price_tolerance=float(price_tolerance),
            lvn_threshold=float(lvn_threshold),
            bin_step=_safe_float(source.get("bin_step"), CONFIG.strategy.bin_step),
            min_profile_levels=int(source.get("min_profile_levels", CONFIG.strategy.min_profile_levels)),
            rsi_period=int(source.get("rsi_period", CONFIG.strategy.rsi_period)),
            rsi_long_max=_safe_float(source.get("rsi_long_max"), CONFIG.strategy.rsi_long_max),
            rsi_short_min=_safe_float(source.get("rsi_short_min"), CONFIG.strategy.rsi_short_min),
        )
        specs.append(TickerRunSpec(ticker=ticker, params=params))

    deduped: Dict[str, TickerRunSpec] = {}
    for spec in specs:
        deduped[spec.ticker] = spec

    return sorted(deduped.values(), key=lambda item: item.ticker), invalid


def _run_single_ticker(spec: TickerRunSpec, data_dir: str, output_dir: str) -> TickerBacktestResult:
    started = time.perf_counter()
    data_file = os.path.join(data_dir, f"{spec.ticker}.csv")
    if not os.path.isfile(data_file):
        raise FileNotFoundError(f"No data file found: {data_file}")

    trades_df = run_backtest_for_ticker(
        data_dir=data_dir,
        ticker=spec.ticker,
        params=spec.params,
        investimento_per_trade=CONFIG.strategy.investimento_per_trade,
        commissione_apertura=CONFIG.strategy.commissione_apertura,
        commissione_chiusura=CONFIG.strategy.commissione_chiusura,
    )
    summary_by_ticker_df, _ = build_summaries(trades_df)

    ticker_dir = os.path.join(output_dir, "tickers", spec.ticker)
    os.makedirs(ticker_dir, exist_ok=True)
    trades_df.to_csv(os.path.join(ticker_dir, "trades.csv"), index=False)
    summary_by_ticker_df.to_csv(os.path.join(ticker_dir, "summary_by_ticker.csv"), index=False)

    with open(os.path.join(ticker_dir, "params_used.json"), "w", encoding="utf-8") as handle:
        json.dump(
            {
                "ticker": spec.ticker,
                "window_profile": spec.params.window_profile,
                "price_tolerance": spec.params.price_tolerance,
                "lvn_threshold": spec.params.lvn_threshold,
                "bin_step": spec.params.bin_step,
                "min_profile_levels": spec.params.min_profile_levels,
                "rsi_period": spec.params.rsi_period,
                "rsi_long_max": spec.params.rsi_long_max,
                "rsi_short_min": spec.params.rsi_short_min,
            },
            handle,
            indent=2,
        )

    if summary_by_ticker_df.empty:
        trade_count = 0
        total_pnl = 0.0
        win_rate = 0.0
        profit_factor = 0.0
        max_drawdown = 0.0
    else:
        row = summary_by_ticker_df.iloc[0]
        trade_count = int(row["trade_count"])
        total_pnl = round(float(row["total_pnl"]), 2)
        win_rate = round(float(row["win_rate"]), 2)
        profit_factor = float(row["profit_factor"])
        max_drawdown = round(float(row["max_drawdown"]), 2)

    return TickerBacktestResult(
        ticker=spec.ticker,
        status="DONE",
        trade_count=trade_count,
        total_pnl=total_pnl,
        win_rate=win_rate,
        profit_factor=profit_factor,
        max_drawdown=max_drawdown,
        error="",
        elapsed_seconds=time.perf_counter() - started,
    )


def _execute_all(specs: List[TickerRunSpec], data_dir: str, output_dir: str, parallel: bool) -> List[TickerBacktestResult]:
    results: List[TickerBacktestResult] = []
    total = len(specs)

    if parallel and total > 1:
        workers = min(total, os.cpu_count() or 1)
        with ProcessPoolExecutor(max_workers=workers) as executor:
            future_map = {executor.submit(_run_single_ticker, spec, data_dir, output_dir): spec for spec in specs}
            done = 0
            for future in as_completed(future_map):
                spec = future_map[future]
                done += 1
                try:
                    result = future.result()
                    print(
                        f"✅ Backtest {result.ticker} ({done}/{total})... DONE - "
                        f"{result.trade_count} trades, €{result.total_pnl:.2f} P&L, {result.win_rate:.2f}% win rate"
                    )
                except Exception as exc:  # noqa: BLE001
                    result = TickerBacktestResult(
                        ticker=spec.ticker,
                        status="ERROR",
                        trade_count=0,
                        total_pnl=0.0,
                        win_rate=0.0,
                        profit_factor=0.0,
                        max_drawdown=0.0,
                        error=str(exc),
                        elapsed_seconds=0.0,
                    )
                    print(f"⚠️  Backtest {result.ticker} ({done}/{total})... ERROR - {result.error}")
                print(_format_progress(done, total))
                results.append(result)
    else:
        for idx, spec in enumerate(specs, start=1):
            try:
                result = _run_single_ticker(spec, data_dir, output_dir)
                print(
                    f"✅ Backtest {result.ticker} ({idx}/{total})... DONE - "
                    f"{result.trade_count} trades, €{result.total_pnl:.2f} P&L, {result.win_rate:.2f}% win rate"
                )
            except Exception as exc:  # noqa: BLE001
                result = TickerBacktestResult(
                    ticker=spec.ticker,
                    status="ERROR",
                    trade_count=0,
                    total_pnl=0.0,
                    win_rate=0.0,
                    profit_factor=0.0,
                    max_drawdown=0.0,
                    error=str(exc),
                    elapsed_seconds=0.0,
                )
                print(f"⚠️  Backtest {result.ticker} ({idx}/{total})... ERROR - {result.error}")
            print(_format_progress(idx, total))
            results.append(result)

    return sorted(results, key=lambda item: item.ticker)


def _save_batch_outputs(output_dir: str, results: List[TickerBacktestResult], elapsed_seconds: float) -> None:
    rows = [
        {
            "ticker": result.ticker,
            "status": result.status,
            "trade_count": result.trade_count,
            "total_pnl": result.total_pnl,
            "win_rate": result.win_rate,
            "profit_factor": result.profit_factor,
            "max_drawdown": result.max_drawdown,
            "error": result.error,
            "elapsed_seconds": round(result.elapsed_seconds, 4),
        }
        for result in results
    ]
    result_df = pd.DataFrame(rows)
    result_df.to_csv(os.path.join(output_dir, "ticker_results.csv"), index=False)

    success_df = result_df[result_df["status"] == "DONE"].copy()
    if success_df.empty:
        aggregate = {
            "total_tickers_processed": len(results),
            "success_count": 0,
            "failed_count": len(results),
            "execution_seconds": round(elapsed_seconds, 2),
            "total_trades": 0,
            "total_pnl": 0.0,
            "average_win_rate": 0.0,
            "average_profit_factor": 0.0,
            "total_max_drawdown": 0.0,
        }
    else:
        finite_profit_factor = success_df["profit_factor"].replace([float("inf"), float("-inf")], pd.NA).dropna()
        aggregate = {
            "total_tickers_processed": len(results),
            "success_count": int(len(success_df)),
            "failed_count": int(len(results) - len(success_df)),
            "execution_seconds": round(elapsed_seconds, 2),
            "total_trades": int(success_df["trade_count"].sum()),
            "total_pnl": round(float(success_df["total_pnl"].sum()), 2),
            "average_win_rate": round(float(success_df["win_rate"].mean()), 2),
            "average_profit_factor": round(float(finite_profit_factor.mean()), 2) if not finite_profit_factor.empty else 0.0,
            "total_max_drawdown": round(float(success_df["max_drawdown"].sum()), 2),
        }
    pd.DataFrame([aggregate]).to_csv(os.path.join(output_dir, "batch_summary.csv"), index=False)


def _print_final_summary(output_dir: str, results: List[TickerBacktestResult], elapsed_seconds: float) -> None:
    success = [item for item in results if item.status == "DONE"]
    failed = [item for item in results if item.status != "DONE"]

    total_trades = sum(item.trade_count for item in success)
    total_pnl = round(sum(item.total_pnl for item in success), 2)
    average_win_rate = round((sum(item.win_rate for item in success) / len(success)), 2) if success else 0.0

    finite_pf = [item.profit_factor for item in success if not math.isinf(item.profit_factor)]
    average_profit_factor = round(sum(finite_pf) / len(finite_pf), 2) if finite_pf else 0.0
    total_max_drawdown = round(sum(item.max_drawdown for item in success), 2)

    ranked = sorted(success, key=lambda item: item.total_pnl, reverse=True)
    top = ranked[:5]
    bottom = sorted(success, key=lambda item: item.total_pnl)[:2]

    print("\n📊 BATCH BACKTEST SUMMARY")
    print("═════════════════════════")
    print(f"Total tickers processed: {len(results)}")
    print(f"Successfully completed: {len(success)}")
    print(f"Failed: {len(failed)}")
    print(f"Execution time: {_format_duration(elapsed_seconds)}")

    print("\n💰 AGGREGATE RESULTS")
    print(f"Total trades: {total_trades}")
    print(f"Total P&L: €{total_pnl:,.2f}")
    print(f"Average win rate: {average_win_rate:.2f}%")
    print(f"Average profit factor: {average_profit_factor:.2f}")
    print(f"Total max drawdown: €{total_max_drawdown:,.2f}")

    print("\n🏆 TOP 5 TICKERS")
    for index, result in enumerate(top, start=1):
        print(f"{index}. {result.ticker}: €{result.total_pnl:,.2f} ({result.trade_count} trades)")

    if bottom:
        print("\n❌ BOTTOM 2 TICKERS")
        for index, result in enumerate(bottom, start=1):
            print(f"{index}. {result.ticker}: €{result.total_pnl:,.2f} ({result.trade_count} trades)")

    if failed:
        print("\n⚠️ FAILED TICKERS")
        for result in failed:
            print(f"- {result.ticker}: {result.error}")

    print(f"\n📁 Results saved in: {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run backtest for all tickers using optimized parameters")
    parser.add_argument("--optimized-params", required=True, help="Path to optimized params JSON")
    parser.add_argument("--data-dir", default=".", help="Directory containing <TICKER>.csv data files")
    parser.add_argument("--output-dir", required=True, help="Directory where batch outputs will be written")
    parser.add_argument("--parallel", action="store_true", help="Execute tickers in parallel")
    args = parser.parse_args()

    started = time.perf_counter()
    os.makedirs(args.output_dir, exist_ok=True)

    specs, invalid = _parse_specs(args.optimized_params)
    if not specs and not invalid:
        raise ValueError(f"No ticker configurations found in optimized params file: {args.optimized_params}")

    print("🚀 Starting batch backtest for all tickers...")
    if invalid:
        for item in invalid:
            print(f"⚠️  Backtest {item.ticker}... ERROR - {item.error}")

    results = invalid + _execute_all(specs, args.data_dir, args.output_dir, args.parallel)
    elapsed_seconds = time.perf_counter() - started

    _save_batch_outputs(args.output_dir, results, elapsed_seconds)
    _print_final_summary(args.output_dir, results, elapsed_seconds)


if __name__ == "__main__":
    main()
