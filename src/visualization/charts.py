from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def plot_equity_curve(trades: pd.DataFrame, output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if trades.empty:
        plt.figure(figsize=(8, 4))
        plt.title("Equity Curve (No trades)")
        plt.savefig(output_file, bbox_inches="tight")
        plt.close()
        return

    ordered = trades.copy()
    ordered["exit_date"] = pd.to_datetime(ordered["exit_date"], errors="coerce")
    ordered = ordered.dropna(subset=["exit_date"]).sort_values("exit_date")
    if ordered.empty:
        plt.figure(figsize=(8, 4))
        plt.title("Equity Curve (No valid exit dates)")
        plt.savefig(output_file, bbox_inches="tight")
        plt.close()
        return
    ordered["equity"] = ordered["realized_pnl"].cumsum()

    plt.figure(figsize=(10, 5))
    plt.plot(ordered["exit_date"], ordered["equity"])
    plt.title("Equity Curve")
    plt.xlabel("Date")
    plt.ylabel("Cumulative PnL")
    plt.grid(True, alpha=0.3)
    plt.savefig(output_file, bbox_inches="tight")
    plt.close()
