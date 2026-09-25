from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

from config import CONFIG
from engine import StrategyParams, safe_read_csv, signal_for_index
from progress import ProgressDisplay, RunMetrics


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
        "exit_price": round(float(exit_price), 4),
        "quantity": int(position.initial_quantity),
        "realized_pnl": round(float(realized_pnl), 2),
        "return_pct": round((float(realized_pnl) / position.invested_amount) * 100, 4) if position.invested_amount else 0.0,
        "exit_reason": exit_reason,
    }


def _update_position(position: PositionState, df: pd.DataFrame, idx: int, date_str: str, current_price: float, params: StrategyParams, commissione_chiusura: float) -> Optional[Dict]:
    if not position.tp1_hit:
        if position.direction == "LONG" and current_price <= position.entry_price * 0.97:
            return _close_trade(position, date_str, current_price, "Hard stop exit", commissione_chiusura)
        if position.direction == "SHORT" and current_price >= position.entry_price * 1.03:
            return _close_trade(position, date_str, current_price, "Hard stop exit", commissione_chiusura)

        signal, _, _, _ = signal_for_index(df, idx, params)
        opposite_signal = "SHORT" if position.direction == "LONG" else "LONG"
        if signal == opposite_signal:
            half_qty = position.quantity // 2 or position.quantity
            closed_pnl = (
                (current_price - position.entry_price) * half_qty
                if position.direction == "LONG"
                else (position.entry_price - current_price) * half_qty
            )
            position.pnl_euro = position.pnl_euro + closed_pnl - float(commissione_chiusura)
            position.quantity -= half_qty
            position.tp1_hit = True
            position.current_stop = current_price * 0.98 if position.direction == "LONG" else current_price * 1.02
            if position.quantity <= 0:
                return _close_trade(position, date_str, current_price, "Opposite LVN TP1 full close", 0.0)
    else:
        is_exit = False
        if position.direction == "LONG":
            position.current_stop = max(position.current_stop, current_price * 0.98)
            is_exit = current_price <= position.current_stop
        else:
            if position.current_stop == 0.0:
                position.current_stop = current_price * 1.02
            position.current_stop = min(position.current_stop, current_price * 1.02)
            is_exit = current_price >= position.current_stop
        if is_exit:
            return _close_trade(position, date_str, current_price, "Trailing stop exit", commissione_chiusura)
    return None


def _update_live_metrics(
    trade: Dict,
    total_pnl: float,
    win_count: int,
    closed_trade_count: int,
    equity: float,
    equity_peak: float,
    max_drawdown: float,
) -> Tuple[float, int, int, float, float, float]:
    realized_pnl = float(trade["realized_pnl"])
    total_pnl += realized_pnl
    closed_trade_count += 1
    if realized_pnl > 0:
        win_count += 1
    equity += realized_pnl
    equity_peak = max(equity_peak, equity)
    max_drawdown = max(max_drawdown, equity_peak - equity)
    return total_pnl, win_count, closed_trade_count, equity, equity_peak, max_drawdown


def run_backtest_for_ticker(
    data_dir: str,
    ticker: str,
    params: StrategyParams,
    investimento_per_trade: float,
    commissione_apertura: float,
    commissione_chiusura: float,
    progress_display: Optional[ProgressDisplay] = None,
    manage_progress_total: bool = False,
) -> pd.DataFrame:
    file_path = os.path.join(data_dir, f"{ticker}.csv")
    df = safe_read_csv(file_path)
    if df is None or len(df) < params.window_profile + 1:
        if progress_display is not None:
            if manage_progress_total:
                progress_display.set_total_units(1)
            progress_display.record_skipped_ticker(ticker)
            progress_display.update(
                processed_units=1,
                current_ticker=ticker,
                metrics=RunMetrics(),
                context="Single ticker backtest (skipped: missing or insufficient data)",
                force=True,
            )
        return pd.DataFrame(columns=["ticker", "direction", "entry_date", "exit_date", "entry_price", "exit_price", "quantity", "realized_pnl", "return_pct", "exit_reason"])

    trades: List[Dict] = []
    position: Optional[PositionState] = None
    total_steps = max(len(df) - params.window_profile, 1)
    if progress_display is not None and manage_progress_total:
        progress_display.set_total_units(total_steps)

    total_pnl = 0.0
    win_count = 0
    closed_trade_count = 0
    equity = 0.0
    equity_peak = 0.0
    max_drawdown = 0.0

    for step_number, idx in enumerate(range(params.window_profile, len(df)), start=1):
        row = df.iloc[idx]
        date_str = str(pd.to_datetime(row["Date"]).date())
        close_price = float(row["Close"])
        signal, _, _, _ = signal_for_index(df, idx, params)

        if position is not None:
            closed_trade = _update_position(position, df, idx, date_str, close_price, params, commissione_chiusura)
            if closed_trade is not None:
                trades.append(closed_trade)
                total_pnl, win_count, closed_trade_count, equity, equity_peak, max_drawdown = _update_live_metrics(
                    closed_trade,
                    total_pnl,
                    win_count,
                    closed_trade_count,
                    equity,
                    equity_peak,
                    max_drawdown,
                )
                position = None

        if position is None and signal in {"LONG", "SHORT"}:
            position = _open_position(ticker, signal, date_str, close_price, investimento_per_trade, commissione_apertura)

        if progress_display is not None and step_number < total_steps:
            win_rate = (win_count / closed_trade_count) * 100 if closed_trade_count else 0.0
            progress_display.update(
                processed_units=step_number,
                current_ticker=ticker,
                metrics=RunMetrics(
                    trades_found=closed_trade_count,
                    total_pnl=total_pnl,
                    win_rate=win_rate,
                    max_drawdown=max_drawdown,
                ),
                context="Single ticker backtest",
            )

    if position is not None:
        last_row = df.iloc[-1]
        final_trade = _close_trade(position, str(pd.to_datetime(last_row["Date"]).date()), float(last_row["Close"]), "End of data", commissione_chiusura)
        trades.append(final_trade)
        total_pnl, win_count, closed_trade_count, equity, equity_peak, max_drawdown = _update_live_metrics(
            final_trade,
            total_pnl,
            win_count,
            closed_trade_count,
            equity,
            equity_peak,
            max_drawdown,
        )

    if progress_display is not None:
        win_rate = (win_count / closed_trade_count) * 100 if closed_trade_count else 0.0
        progress_display.update(
            processed_units=total_steps,
            current_ticker=ticker,
            metrics=RunMetrics(
                trades_found=closed_trade_count,
                total_pnl=total_pnl,
                win_rate=win_rate,
                max_drawdown=max_drawdown,
            ),
            context="Single ticker backtest",
            force=True,
        )

    return pd.DataFrame(trades)


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


def build_summaries(trades_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if trades_df.empty:
        summary_by_ticker = pd.DataFrame(columns=["ticker", "trade_count", "win_rate", "total_pnl", "avg_pnl_per_trade", "profit_factor", "max_drawdown"])
        summary_global = pd.DataFrame([{"total_trades": 0, "total_pnl": 0.0, "overall_win_rate": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0}])
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
    summary_global = pd.DataFrame(
        [
            {
                "total_trades": total_trades,
                "total_pnl": round(float(trades_df["realized_pnl"].sum()), 2),
                "overall_win_rate": round((total_wins / total_trades) * 100, 2) if total_trades else 0.0,
                "profit_factor": _profit_factor(trades_df["realized_pnl"]),
                "max_drawdown": _max_drawdown(trades_df),
            }
        ]
    )
    return summary_by_ticker, summary_global


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

    progress_display = ProgressDisplay(
        title="LVN Trading Strategy - Backtesting Progress",
        total_units=1,
        unit_label="bars",
        update_interval_seconds=CONFIG.progress.update_interval_seconds,
        bar_width=CONFIG.progress.bar_width,
        enabled=CONFIG.progress.enabled,
    )

    trades_df = run_backtest_for_ticker(
        data_dir=args.data_dir,
        ticker=args.ticker,
        params=params,
        investimento_per_trade=CONFIG.strategy.investimento_per_trade,
        commissione_apertura=CONFIG.strategy.commissione_apertura,
        commissione_chiusura=CONFIG.strategy.commissione_chiusura,
        progress_display=progress_display,
        manage_progress_total=True,
    )
    summary_by_ticker_df, summary_global_df = build_summaries(trades_df)

    if not progress_display.has_skipped_ticker(args.ticker) and summary_by_ticker_df.empty:
        progress_display.record_ticker_result(args.ticker, 0, 0.0)
    elif not progress_display.has_skipped_ticker(args.ticker):
        ticker_summary = summary_by_ticker_df.iloc[0]
        progress_display.record_ticker_result(args.ticker, int(ticker_summary["trade_count"]), float(ticker_summary["total_pnl"]))

    ticker_dir = os.path.join(args.output_dir, "single_run", args.ticker)
    os.makedirs(ticker_dir, exist_ok=True)
    trades_df.to_csv(os.path.join(ticker_dir, "trades.csv"), index=False)
    summary_by_ticker_df.to_csv(os.path.join(ticker_dir, "summary_by_ticker.csv"), index=False)
    summary_global_df.to_csv(os.path.join(ticker_dir, "summary_global.csv"), index=False)
    progress_display.print_summary()
    try:
        print(f"Output salvati in: {ticker_dir}")
    except BrokenPipeError:
        return


if __name__ == "__main__":
    main()
