from __future__ import annotations

import argparse
import json
import os
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Tuple

import pandas as pd

from backtest import run_backtest_for_ticker
from config import CONFIG
from engine import StrategyParams


def _discover_tickers(data_dir: str) -> List[str]:
    if not os.path.isdir(data_dir):
        return []
    return sorted(
        f.replace('.csv', '')
        for f in os.listdir(data_dir)
        if f.endswith('.csv') and f != 'failed_tickers.csv'
    )


def _load_payload(path: str) -> Dict:
    with open(path, 'r', encoding='utf-8') as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError('optimized params payload must be a JSON object')
    return payload


def _iter_ticker_payloads(payload: Dict) -> Iterable[Tuple[str, Dict]]:
    raw = payload.get('tickers') if isinstance(payload.get('tickers'), dict) else payload
    if not isinstance(raw, dict):
        return []

    pairs: List[Tuple[str, Dict]] = []
    for ticker, entry in raw.items():
        if ticker in {'generated_at_utc', 'metadata'}:
            continue
        if not isinstance(entry, dict):
            continue
        params = entry.get('params') if isinstance(entry.get('params'), dict) else entry.get('parameters')
        if not isinstance(params, dict):
            params = entry
        pairs.append((str(ticker), params))
    return pairs


def _build_strategy_params(raw: Dict) -> StrategyParams:
    return StrategyParams(
        window_profile=int(raw['window_profile']),
        price_tolerance=float(raw['price_tolerance']),
        lvn_threshold=float(raw['lvn_threshold']),
        bin_step=float(raw.get('bin_step', CONFIG.strategy.bin_step)),
        min_profile_levels=int(raw.get('min_profile_levels', CONFIG.strategy.min_profile_levels)),
        rsi_period=int(raw.get('rsi_period', CONFIG.strategy.rsi_period)),
        rsi_long_max=float(raw.get('rsi_long_max', CONFIG.strategy.rsi_long_max)),
        rsi_short_min=float(raw.get('rsi_short_min', CONFIG.strategy.rsi_short_min)),
    )


def _run_single_ticker(data_dir: str, ticker: str, params: Dict) -> Dict:
    try:
        strategy_params = _build_strategy_params(params)
        trades_df = run_backtest_for_ticker(
            data_dir=data_dir,
            ticker=ticker,
            params=strategy_params,
            investimento_per_trade=CONFIG.strategy.investimento_per_trade,
            commissione_apertura=CONFIG.strategy.commissione_apertura,
            commissione_chiusura=CONFIG.strategy.commissione_chiusura,
        )
        trade_count = int(len(trades_df))
        total_pnl = round(float(trades_df['realized_pnl'].sum()), 2) if trade_count else 0.0
        wins = int((trades_df['realized_pnl'] > 0).sum()) if trade_count else 0
        win_rate = round((wins / trade_count) * 100.0, 2) if trade_count else 0.0
        status = 'success' if trade_count else 'no_trades'
        return {
            'ticker': ticker,
            'status': status,
            'trade_count': trade_count,
            'total_pnl': total_pnl,
            'win_rate': win_rate,
            'error': '',
        }
    except Exception:
        return {
            'ticker': ticker,
            'status': 'error',
            'trade_count': 0,
            'total_pnl': 0.0,
            'win_rate': 0.0,
            'error': traceback.format_exc(limit=20),
        }


def _run_batch(data_dir: str, ticker_params: List[Tuple[str, Dict]], parallel: bool, max_workers: int) -> List[Dict]:
    results: List[Dict] = []
    if not parallel:
        for ticker, params in ticker_params:
            results.append(_run_single_ticker(data_dir, ticker, params))
        return results

    workers = max(1, min(max_workers, len(ticker_params)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_run_single_ticker, data_dir, ticker, params): ticker
            for ticker, params in ticker_params
        }
        for future in as_completed(futures):
            results.append(future.result())
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description='Run backtest for all tickers with optimized params')
    parser.add_argument('--optimized-params', default='optimized_params.json')
    parser.add_argument('--data-dir', default='.')
    parser.add_argument('--output-dir', default=os.path.join('output', 'production'))
    parser.add_argument('--parallel', action='store_true')
    parser.add_argument('--max-workers', type=int, default=4)
    args = parser.parse_args()

    started_at = datetime.now(timezone.utc)
    os.makedirs(args.output_dir, exist_ok=True)

    payload = _load_payload(args.optimized_params)
    ticker_params = _iter_ticker_payloads(payload)

    if not ticker_params:
        discovered = _discover_tickers(args.data_dir)
        ticker_params = [
            (
                ticker,
                {
                    'window_profile': CONFIG.strategy.window_profile,
                    'price_tolerance': CONFIG.strategy.price_tolerance,
                    'lvn_threshold': CONFIG.strategy.lvn_threshold,
                },
            )
            for ticker in discovered
        ]

    if not ticker_params:
        raise ValueError('No ticker parameters available for execution')

    results = _run_batch(
        data_dir=args.data_dir,
        ticker_params=sorted(ticker_params, key=lambda item: item[0]),
        parallel=args.parallel,
        max_workers=args.max_workers,
    )

    ticker_df = pd.DataFrame(results)
    ticker_df = ticker_df.sort_values(by=['total_pnl', 'trade_count', 'ticker'], ascending=[False, False, True]).reset_index(drop=True)
    ticker_df.to_csv(os.path.join(args.output_dir, 'ticker_results.csv'), index=False)

    ended_at = datetime.now(timezone.utc)
    success_count = int((ticker_df['status'] == 'success').sum())
    no_trades_count = int((ticker_df['status'] == 'no_trades').sum())
    error_count = int((ticker_df['status'] == 'error').sum())
    total_trades = int(ticker_df['trade_count'].sum())
    total_pnl = round(float(ticker_df['total_pnl'].sum()), 2)

    summary_df = pd.DataFrame(
        [
            {
                'started_at_utc': started_at.isoformat(),
                'ended_at_utc': ended_at.isoformat(),
                'execution_seconds': round((ended_at - started_at).total_seconds(), 2),
                'total_tickers': int(len(ticker_df)),
                'successful_tickers': success_count,
                'no_trades_tickers': no_trades_count,
                'failed_tickers': error_count,
                'total_trades': total_trades,
                'total_pnl': total_pnl,
                'parallel_mode': bool(args.parallel),
                'max_workers': int(max(1, args.max_workers)),
            }
        ]
    )
    summary_df.to_csv(os.path.join(args.output_dir, 'batch_summary.csv'), index=False)

    print(f"Backtest completato su {len(ticker_df)} ticker. P&L totale: {total_pnl:.2f} EUR")
    if error_count:
        print(f"Ticker in errore: {error_count}")


if __name__ == '__main__':
    main()
