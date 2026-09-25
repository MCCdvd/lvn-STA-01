from __future__ import annotations

import math

import numpy as np
import pandas as pd


def profit_factor(pnls: pd.Series) -> float:
    gross_profit = float(pnls[pnls > 0].sum())
    gross_loss = float(pnls[pnls < 0].sum())
    if gross_loss < 0:
        return round(gross_profit / abs(gross_loss), 4)
    if gross_profit > 0:
        return float("inf")
    return 0.0


def max_drawdown(trades_df: pd.DataFrame) -> float:
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


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    series = returns.dropna()
    if series.empty:
        return 0.0
    std = float(series.std(ddof=1))
    if std == 0.0:
        return 0.0
    excess = series - risk_free_rate
    return float(np.sqrt(len(series)) * excess.mean() / std)


def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    series = returns.dropna()
    if series.empty:
        return 0.0
    downside = series[series < risk_free_rate]
    downside_std = float(downside.std(ddof=1)) if not downside.empty else 0.0
    if downside_std == 0.0:
        return 0.0
    return float(np.sqrt(len(series)) * (series.mean() - risk_free_rate) / downside_std)


def calmar_ratio(total_return: float, drawdown: float) -> float:
    if drawdown <= 0:
        return 0.0
    return float(total_return / drawdown)


def summarize_trades(trades_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if trades_df.empty:
        by_ticker = pd.DataFrame(columns=["ticker", "trade_count", "win_rate", "total_pnl", "avg_pnl_per_trade", "profit_factor", "max_drawdown", "sharpe", "sortino", "calmar"])
        global_df = pd.DataFrame([{"total_trades": 0, "total_pnl": 0.0, "overall_win_rate": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0, "sharpe": 0.0, "sortino": 0.0, "calmar": 0.0}])
        return by_ticker, global_df

    rows: list[dict[str, float | int | str]] = []
    for ticker, grp in trades_df.groupby("ticker", sort=True):
        count = int(len(grp))
        wins = int((grp["realized_pnl"] > 0).sum())
        returns = grp["return_pct"] / 100.0
        dd = max_drawdown(grp)
        total_pnl = float(grp["realized_pnl"].sum())
        rows.append(
            {
                "ticker": ticker,
                "trade_count": count,
                "win_rate": round((wins / count) * 100, 2) if count else 0.0,
                "total_pnl": round(total_pnl, 2),
                "avg_pnl_per_trade": round(float(grp["realized_pnl"].mean()), 2) if count else 0.0,
                "profit_factor": profit_factor(grp["realized_pnl"]),
                "max_drawdown": dd,
                "sharpe": round(sharpe_ratio(returns), 4),
                "sortino": round(sortino_ratio(returns), 4),
                "calmar": round(calmar_ratio(total_pnl, dd), 4),
            }
        )

    by_ticker = pd.DataFrame(rows).sort_values("total_pnl", ascending=False).reset_index(drop=True)
    total_trades = int(len(trades_df))
    total_wins = int((trades_df["realized_pnl"] > 0).sum())
    all_returns = trades_df["return_pct"] / 100.0
    global_dd = max_drawdown(trades_df)
    global_df = pd.DataFrame(
        [
            {
                "total_trades": total_trades,
                "total_pnl": round(float(trades_df["realized_pnl"].sum()), 2),
                "overall_win_rate": round((total_wins / total_trades) * 100, 2) if total_trades else 0.0,
                "profit_factor": profit_factor(trades_df["realized_pnl"]),
                "max_drawdown": global_dd,
                "sharpe": round(sharpe_ratio(all_returns), 4),
                "sortino": round(sortino_ratio(all_returns), 4),
                "calmar": round(calmar_ratio(float(trades_df["realized_pnl"].sum()), global_dd), 4),
            }
        ]
    )
    return by_ticker, global_df
