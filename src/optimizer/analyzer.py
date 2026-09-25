from __future__ import annotations

import pandas as pd


def compare_summaries(baseline: pd.DataFrame, optimized: pd.DataFrame) -> pd.DataFrame:
    base = baseline.iloc[0]
    opt = optimized.iloc[0]
    return pd.DataFrame(
        [
            {
                "scenario": "baseline",
                "total_trades": base.get("total_trades", 0),
                "total_pnl": base.get("total_pnl", 0.0),
                "overall_win_rate": base.get("overall_win_rate", 0.0),
            },
            {
                "scenario": "optimized",
                "total_trades": opt.get("total_trades", 0),
                "total_pnl": opt.get("total_pnl", 0.0),
                "overall_win_rate": opt.get("overall_win_rate", 0.0),
            },
            {
                "scenario": "delta",
                "total_trades": float(opt.get("total_trades", 0)) - float(base.get("total_trades", 0)),
                "total_pnl": float(opt.get("total_pnl", 0.0)) - float(base.get("total_pnl", 0.0)),
                "overall_win_rate": float(opt.get("overall_win_rate", 0.0)) - float(base.get("overall_win_rate", 0.0)),
            },
        ]
    )
