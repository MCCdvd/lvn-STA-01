from __future__ import annotations

import argparse
import os
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

from config import CONFIG
from engine import StrategyParams, safe_read_csv, signal_for_index


@dataclass
class PositionState:
    ticker: str
    direction: str
    entry_date: str
    entry_price: float
    quantity: int
    initial_quantity: int
    invested_amount: float
    pnl_euro: float
    tp1_hit: bool = False
    current_stop: float = 0.0


def _execution_price(next_row: pd.Series) -> float:
    if "Open" in next_row.index:
        open_price = pd.to_numeric(next_row["Open"], errors="coerce")
        if pd.notna(open_price) and float(open_price) > 0:
            return float(open_price)
    return float(next_row["Close"])


def _open_position(ticker: str, signal: str, date_str: str, price: float, investimento_per_trade: float, commissione_apertura: float) -> Optional[PositionState]:
    if signal not in {"LONG", "SHORT"} or price <= 0:
        return None
    quantity = int(investimento_per_trade / price)
    if quantity <= 0:
        return None

    invested_amount = round(quantity * price, 2)
    return PositionState(
        ticker=ticker,
        direction=signal,
        entry_date=date_str,
        entry_price=float(price),
        quantity=quantity,
        initial_quantity=quantity,
        invested_amount=invested_amount,
        pnl_euro=-float(commissione_apertura),
    )


def _close_trade(position: PositionState, exit_date: str, exit_price: float, exit_reason: str, commissione_chiusura: float) -> Dict:
    pnl_move = (
        (exit_price - position.entry_price) * position.quantity
        if position.direction == "LONG"
        else (position.entry_price - exit_price) * position.quantity
    )
    realized_pnl = position.pnl_euro + pnl_move - float(commissione_chiusura)
    return {
        "ticker": position.ticker,
        "direction": position.direction,
        "entry_date": position.entry_date,
        "exit_date": exit_date,
        "entry_price": round(position.entry_price, 4),
        "entry_notional": round(position.entry_price * position.initial_quantity, 2),
        "exit_price": round(float(exit_price), 4),
        "quantity": int(position.initial_quantity),
        "realized_pnl": round(float(realized_pnl), 2),
        "return_pct": round((float(realized_pnl) / position.invested_amount) * 100, 4) if position.invested_amount else 0.0,
        "exit_reason": exit_reason,
    }


def _update_position(
    position: PositionState,
    df: pd.DataFrame,
    idx: int,
    signal_price: float,
    execution_date_str: str,
    execution_price: float,
    params: StrategyParams,
    commissione_chiusura: float,
) -> Optional[Dict]:
    if not position.tp1_hit:
        if position.direction == "LONG" and signal_price <= position.entry_price * 0.97:
            return _close_trade(position, execution_date_str, execution_price, "Hard stop exit", commissione_chiusura)
        if position.direction == "SHORT" and signal_price >= position.entry_price * 1.03:
            return _close_trade(position, execution_date_str, execution_price, "Hard stop exit", commissione_chiusura)

        signal, _, _, _ = signal_for_index(df, idx, params)
        opposite_signal = "SHORT" if position.direction == "LONG" else "LONG"
        if signal == opposite_signal:
            half_qty = position.quantity // 2 or position.quantity
            closed_pnl = (
                (execution_price - position.entry_price) * half_qty
                if position.direction == "LONG"
                else (position.entry_price - execution_price) * half_qty
            )
            position.pnl_euro = position.pnl_euro + closed_pnl - float(commissione_chiusura)
            position.quantity -= half_qty
            position.tp1_hit = True
            position.current_stop = signal_price * 0.98 if position.direction == "LONG" else signal_price * 1.02
            if position.quantity <= 0:
                return _close_trade(position, execution_date_str, execution_price, "Opposite LVN TP1 full close", 0.0)
    else:
        is_exit = False
        if position.direction == "LONG":
            position.current_stop = max(position.current_stop, signal_price * 0.98)
            is_exit = signal_price <= position.current_stop
        else:
            if position.current_stop == 0.0:
                position.current_stop = signal_price * 1.02
            position.current_stop = min(position.current_stop, signal_price * 1.02)
            is_exit = signal_price >= position.current_stop
        if is_exit:
            return _close_trade(position, execution_date_str, execution_price, "Trailing stop exit", commissione_chiusura)
    return None


def run_backtest_df(
    df: pd.DataFrame,
    ticker: str,
    params: StrategyParams,
    investimento_per_trade: float,
    commissione_apertura: float,
    commissione_chiusura: float,
) -> pd.DataFrame:
    if df is None or df.empty or len(df) < params.window_profile + 2:
        return pd.DataFrame(
            columns=[
                "ticker",
                "direction",
                "entry_date",
                "exit_date",
                "entry_price",
                "entry_notional",
                "exit_price",
                "quantity",
                "realized_pnl",
                "return_pct",
                "exit_reason",
            ]
        )

    trades: List[Dict] = []
    position: Optional[PositionState] = None

    for idx in range(params.window_profile, len(df) - 1):
        row = df.iloc[idx]
        next_row = df.iloc[idx + 1]
        close_price = float(row["Close"])
        execution_date = str(pd.to_datetime(next_row["Date"]).date())
        execution_price = _execution_price(next_row)
        signal, _, _, _ = signal_for_index(df, idx, params)
        closed_this_step = False

        if position is not None:
            closed_trade = _update_position(position, df, idx, close_price, execution_date, execution_price, params, commissione_chiusura)
            if closed_trade is not None:
                trades.append(closed_trade)
                position = None
                closed_this_step = True

        if position is None and not closed_this_step and signal in {"LONG", "SHORT"}:
            position = _open_position(ticker, signal, execution_date, execution_price, investimento_per_trade, commissione_apertura)

    if position is not None:
        last_row = df.iloc[-1]
        trades.append(_close_trade(position, str(pd.to_datetime(last_row["Date"]).date()), float(last_row["Close"]), "End of data", commissione_chiusura))

    return pd.DataFrame(trades)


def run_backtest_for_ticker(data_dir: str, ticker: str, params: StrategyParams, investimento_per_trade: float, commissione_apertura: float, commissione_chiusura: float) -> pd.DataFrame:
    file_path = os.path.join(data_dir, f"{ticker}.csv")
    df = safe_read_csv(file_path)
    if df is None:
        return pd.DataFrame(
            columns=[
                "ticker",
                "direction",
                "entry_date",
                "exit_date",
                "entry_price",
                "entry_notional",
                "exit_price",
                "quantity",
                "realized_pnl",
                "return_pct",
                "exit_reason",
            ]
        )
    return run_backtest_df(df, ticker, params, investimento_per_trade, commissione_apertura, commissione_chiusura)


def _profit_factor(pnls: pd.Series) -> float:
    gross_profit = float(pnls[pnls > 0].sum())
    gross_loss = float(pnls[pnls < 0].sum())
    if gross_loss < 0:
        return round(gross_profit / abs(gross_loss), 4)
    if gross_profit > 0:
        return float("inf")
    return 0.0


def _max_drawdown(trades_df: pd.DataFrame) -> float:
    if trades_df.empty:
        return 0.0
    ordered = trades_df.copy()
    ordered["exit_date"] = pd.to_datetime(ordered["exit_date"], errors="coerce")
    ordered = ordered.dropna(subset=["exit_date"]).sort_values("exit_date")
    if ordered.empty:
        return 0.0
    equity = ordered["realized_pnl"].cumsum()
    equity = pd.concat([pd.Series([0.0]), equity], ignore_index=True)
    return round(abs(float((equity - equity.cummax()).min())), 2)


def build_summaries(trades_df: pd.DataFrame, initial_capital: Optional[float] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if trades_df.empty:
        summary_by_ticker = pd.DataFrame(columns=["ticker", "trade_count", "win_rate", "total_pnl", "avg_pnl_per_trade", "profit_factor", "max_drawdown"])
        summary_global = pd.DataFrame(
            [{"total_trades": 0, "total_pnl": 0.0, "overall_win_rate": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0, "max_drawdown_pct": 0.0}]
        )
        return summary_by_ticker, summary_global

    rows: List[Dict] = []
    for ticker, grp in trades_df.groupby("ticker", sort=True):
        count = int(len(grp))
        wins = int((grp["realized_pnl"] > 0).sum())
        rows.append(
            {
                "ticker": ticker,
                "trade_count": count,
                "win_rate": round((wins / count) * 100, 2) if count else 0.0,
                "total_pnl": round(float(grp["realized_pnl"].sum()), 2),
                "avg_pnl_per_trade": round(float(grp["realized_pnl"].mean()), 2) if count else 0.0,
                "profit_factor": _profit_factor(grp["realized_pnl"]),
                "max_drawdown": _max_drawdown(grp),
            }
        )
    summary_by_ticker = pd.DataFrame(rows).sort_values("total_pnl", ascending=False).reset_index(drop=True)
    total_trades = int(len(trades_df))
    total_wins = int((trades_df["realized_pnl"] > 0).sum())
    max_dd_abs = _max_drawdown(trades_df)
    max_dd_pct = round((max_dd_abs / float(initial_capital)) * 100, 2) if initial_capital and initial_capital > 0 else 0.0
    summary_global = pd.DataFrame(
        [
            {
                "total_trades": total_trades,
                "total_pnl": round(float(trades_df["realized_pnl"].sum()), 2),
                "overall_win_rate": round((total_wins / total_trades) * 100, 2) if total_trades else 0.0,
                "profit_factor": _profit_factor(trades_df["realized_pnl"]),
                "max_drawdown": max_dd_abs,
                "max_drawdown_pct": max_dd_pct,
            }
        ]
    )
    return summary_by_ticker, summary_global


def _git_commit_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=os.path.dirname(__file__), text=True).strip()
    except Exception:
        return "unknown"


def _build_run_metadata(params: StrategyParams, ticker: str, data_dir: str, row_count: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": ticker,
                "data_dir": os.path.abspath(data_dir),
                "row_count": int(row_count),
                "window_profile": params.window_profile,
                "price_tolerance": params.price_tolerance,
                "lvn_threshold": params.lvn_threshold,
                "bin_step": params.bin_step,
                "min_profile_levels": params.min_profile_levels,
                "rsi_period": params.rsi_period,
                "rsi_long_max": params.rsi_long_max,
                "rsi_short_min": params.rsi_short_min,
                "investimento_per_trade": CONFIG.strategy.investimento_per_trade,
                "commissione_apertura": CONFIG.strategy.commissione_apertura,
                "commissione_chiusura": CONFIG.strategy.commissione_chiusura,
                "execution_model": "signal_on_close_execute_next_bar_open_or_close",
                "git_commit": _git_commit_hash(),
            }
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest single ticker analysis")
    parser.add_argument("--data-dir", default=CONFIG.runtime.data_dir)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--output-dir", default=CONFIG.runtime.output_dir)
    args = parser.parse_args()

    params = StrategyParams(
        window_profile=CONFIG.strategy.window_profile,
        price_tolerance=CONFIG.strategy.price_tolerance,
        lvn_threshold=CONFIG.strategy.lvn_threshold,
        bin_step=CONFIG.strategy.bin_step,
        min_profile_levels=CONFIG.strategy.min_profile_levels,
        rsi_period=CONFIG.strategy.rsi_period,
        rsi_long_max=CONFIG.strategy.rsi_long_max,
        rsi_short_min=CONFIG.strategy.rsi_short_min,
    )

    trades_df = run_backtest_for_ticker(
        data_dir=args.data_dir,
        ticker=args.ticker,
        params=params,
        investimento_per_trade=CONFIG.strategy.investimento_per_trade,
        commissione_apertura=CONFIG.strategy.commissione_apertura,
        commissione_chiusura=CONFIG.strategy.commissione_chiusura,
    )
    summary_by_ticker_df, summary_global_df = build_summaries(trades_df)

    ticker_dir = os.path.join(args.output_dir, "single_run", args.ticker)
    os.makedirs(ticker_dir, exist_ok=True)
    trades_df.to_csv(os.path.join(ticker_dir, "trades.csv"), index=False)
    summary_by_ticker_df.to_csv(os.path.join(ticker_dir, "summary_by_ticker.csv"), index=False)
    summary_global_df.to_csv(os.path.join(ticker_dir, "summary_global.csv"), index=False)
    source_df = safe_read_csv(os.path.join(args.data_dir, f"{args.ticker}.csv"))
    row_count = 0 if source_df is None else len(source_df)
    _build_run_metadata(params, args.ticker, args.data_dir, row_count).to_csv(os.path.join(ticker_dir, "run_metadata.csv"), index=False)
    print(f"Output salvati in: {ticker_dir}")


if __name__ == "__main__":
    main()
