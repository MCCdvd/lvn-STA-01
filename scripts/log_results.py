from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import pandas as pd


DAILY_RUN_TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS daily_backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_timestamp_utc TEXT NOT NULL,
    execution_seconds REAL NOT NULL,
    total_tickers INTEGER NOT NULL,
    successful_tickers INTEGER NOT NULL,
    no_trades_tickers INTEGER NOT NULL,
    failed_tickers INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    total_pnl REAL NOT NULL,
    created_at_utc TEXT NOT NULL
);
'''

DAILY_TICKER_TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS daily_backtest_tickers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    status TEXT NOT NULL,
    trade_count INTEGER NOT NULL,
    total_pnl REAL NOT NULL,
    win_rate REAL NOT NULL,
    error_message TEXT,
    FOREIGN KEY(run_id) REFERENCES daily_backtest_runs(id)
);
'''

MONTHLY_RUN_TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS monthly_optimization_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_timestamp_utc TEXT NOT NULL,
    total_tickers INTEGER NOT NULL,
    total_pnl REAL NOT NULL,
    previous_total_pnl REAL,
    pnl_delta REAL,
    parameters_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
'''

MONTHLY_TICKER_TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS monthly_optimization_tickers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    rank_position INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    window_profile INTEGER NOT NULL,
    price_tolerance REAL NOT NULL,
    lvn_threshold REAL NOT NULL,
    trade_count INTEGER,
    total_pnl REAL,
    win_rate REAL,
    FOREIGN KEY(run_id) REFERENCES monthly_optimization_runs(id)
);
'''


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute('PRAGMA journal_mode = WAL;')
    conn.execute('PRAGMA foreign_keys = ON;')
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(DAILY_RUN_TABLE_SQL)
    conn.execute(DAILY_TICKER_TABLE_SQL)
    conn.execute(MONTHLY_RUN_TABLE_SQL)
    conn.execute(MONTHLY_TICKER_TABLE_SQL)


def _load_json(path: Path) -> Dict:
    with path.open('r', encoding='utf-8') as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f'Invalid JSON payload in {path}')
    return payload


def _latest_monthly_total_pnl(conn: sqlite3.Connection) -> float | None:
    row = conn.execute(
        'SELECT total_pnl FROM monthly_optimization_runs ORDER BY id DESC LIMIT 1'
    ).fetchone()
    return None if row is None else float(row[0])


def _to_nullable_int(value) -> int | None:
    if pd.isna(value):
        return None
    return int(value)


def _to_nullable_float(value) -> float | None:
    if pd.isna(value):
        return None
    return float(value)


def _to_int_default(value, default: int = 0) -> int:
    return default if pd.isna(value) else int(value)


def _to_float_default(value, default: float = 0.0) -> float:
    return default if pd.isna(value) else float(value)


def log_daily(conn: sqlite3.Connection, summary_csv: Path, ticker_csv: Path) -> Dict:
    summary_df = pd.read_csv(summary_csv)
    ticker_df = pd.read_csv(ticker_csv)

    if summary_df.empty:
        raise ValueError('Daily summary CSV is empty')

    row = summary_df.iloc[0]
    run_timestamp = str(row.get('ended_at_utc') or datetime.now(timezone.utc).isoformat())
    created_at = datetime.now(timezone.utc).isoformat()

    conn.execute('BEGIN')
    try:
        cursor = conn.execute(
            '''
            INSERT INTO daily_backtest_runs (
                run_timestamp_utc, execution_seconds, total_tickers, successful_tickers,
                no_trades_tickers, failed_tickers, total_trades, total_pnl, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                run_timestamp,
                float(row['execution_seconds']),
                int(row['total_tickers']),
                int(row['successful_tickers']),
                int(row['no_trades_tickers']),
                int(row['failed_tickers']),
                int(row['total_trades']),
                float(row['total_pnl']),
                created_at,
            ),
        )
        run_id = int(cursor.lastrowid)

        for record in ticker_df.to_dict('records'):
            conn.execute(
                '''
                INSERT INTO daily_backtest_tickers (
                    run_id, ticker, status, trade_count, total_pnl, win_rate, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    run_id,
                    str(record['ticker']),
                    str(record['status']),
                    _to_int_default(record.get('trade_count', 0)),
                    _to_float_default(record.get('total_pnl', 0.0)),
                    _to_float_default(record.get('win_rate', 0.0)),
                    (str(record.get('error', '')) or None),
                ),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        'run_id': run_id,
        'total_tickers': int(row['total_tickers']),
        'failed_tickers': int(row['failed_tickers']),
        'total_pnl': float(row['total_pnl']),
    }


def _extract_optimized_total_pnl(comparison_csv: Path | None, summary_df: pd.DataFrame) -> float:
    if comparison_csv is not None and comparison_csv.exists():
        comparison_df = pd.read_csv(comparison_csv)
        scenario_rows = comparison_df[comparison_df['scenario'] == 'per_ticker_best_global']
        if not scenario_rows.empty:
            return _to_float_default(scenario_rows.iloc[0].get('total_pnl'), 0.0)

    if 'ticker' in summary_df.columns:
        dedup = summary_df.drop_duplicates(subset=['ticker'], keep='first')
    else:
        dedup = summary_df
    return _to_float_default(dedup.get('total_pnl', pd.Series(dtype=float)).sum(), 0.0)


def log_monthly(
    conn: sqlite3.Connection,
    optimized_params_json: Path,
    summary_by_ticker_csv: Path,
    comparison_csv: Path | None = None,
) -> Dict:
    payload = _load_json(optimized_params_json)
    ticker_payload = payload.get('tickers') if isinstance(payload.get('tickers'), dict) else payload
    if not isinstance(ticker_payload, dict):
        raise ValueError('optimized params JSON does not contain a valid ticker map')

    summary_df = pd.read_csv(summary_by_ticker_csv)
    summary_map = {
        str(row['ticker']): row
        for row in summary_df.to_dict('records')
        if isinstance(row.get('ticker'), str)
    }

    ranking: List[tuple] = []
    for ticker, params in ticker_payload.items():
        if not isinstance(params, dict):
            continue
        resolved = params.get('params') if isinstance(params.get('params'), dict) else params
        missing_keys = [key for key in ('window_profile', 'price_tolerance', 'lvn_threshold') if key not in resolved]
        if missing_keys:
            raise ValueError(
                f"Missing required params for ticker {ticker}: {', '.join(missing_keys)}"
            )
        ranking.append((ticker, resolved))

    ranking = sorted(
        ranking,
        key=lambda item: (_to_float_default(summary_map.get(item[0], {}).get('total_pnl', 0.0), 0.0)),
        reverse=True,
    )

    if not ranking:
        raise ValueError('No optimized ticker params found for monthly logging')

    total_pnl = _extract_optimized_total_pnl(comparison_csv, summary_df)
    previous_total_pnl = _latest_monthly_total_pnl(conn)
    pnl_delta = None if previous_total_pnl is None else total_pnl - previous_total_pnl

    run_timestamp = str(payload.get('generated_at_utc') or datetime.now(timezone.utc).isoformat())
    created_at = datetime.now(timezone.utc).isoformat()

    conn.execute('BEGIN')
    try:
        cursor = conn.execute(
            '''
            INSERT INTO monthly_optimization_runs (
                run_timestamp_utc, total_tickers, total_pnl, previous_total_pnl,
                pnl_delta, parameters_json, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                run_timestamp,
                len(ranking),
                total_pnl,
                previous_total_pnl,
                pnl_delta,
                json.dumps(payload, ensure_ascii=False),
                created_at,
            ),
        )
        run_id = int(cursor.lastrowid)

        for index, (ticker, params) in enumerate(ranking, start=1):
            params = params if isinstance(params, dict) else {}
            stats = summary_map.get(ticker, {})
            conn.execute(
                '''
                INSERT INTO monthly_optimization_tickers (
                    run_id, rank_position, ticker, window_profile, price_tolerance,
                    lvn_threshold, trade_count, total_pnl, win_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    run_id,
                    index,
                    ticker,
                    int(params['window_profile']),
                    float(params['price_tolerance']),
                    float(params['lvn_threshold']),
                    _to_nullable_int(stats.get('trade_count')) if stats else None,
                    _to_nullable_float(stats.get('total_pnl')) if stats else None,
                    _to_nullable_float(stats.get('win_rate')) if stats else None,
                ),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    top = ranking[0][0]
    bottom = ranking[-1][0]
    return {
        'run_id': run_id,
        'total_tickers': len(ranking),
        'total_pnl': total_pnl,
        'previous_total_pnl': previous_total_pnl,
        'pnl_delta': pnl_delta,
        'top_ticker': top,
        'bottom_ticker': bottom,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Log daily/monthly results into SQLite database')
    parser.add_argument('--db-path', default='backtest_results.db')
    parser.add_argument('--report-json', default=None)

    subparsers = parser.add_subparsers(dest='mode', required=True)

    daily = subparsers.add_parser('daily')
    daily.add_argument('--summary-csv', required=True)
    daily.add_argument('--ticker-csv', required=True)

    monthly = subparsers.add_parser('monthly')
    monthly.add_argument('--optimized-params-json', required=True)
    monthly.add_argument('--summary-by-ticker-csv', required=True)
    monthly.add_argument('--comparison-csv', default=None)

    args = parser.parse_args()

    db_path = Path(args.db_path).resolve()
    conn = _connect(db_path)
    try:
        _ensure_schema(conn)
        if args.mode == 'daily':
            report = log_daily(conn, Path(args.summary_csv), Path(args.ticker_csv))
        else:
            report = log_monthly(
                conn,
                Path(args.optimized_params_json),
                Path(args.summary_by_ticker_csv),
                Path(args.comparison_csv) if args.comparison_csv else None,
            )
    finally:
        conn.close()

    report['db_path'] = str(db_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.report_json:
        report_path = Path(args.report_json)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
