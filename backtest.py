from __future__ import annotations

import argparse
from pathlib import Path

from src.backtest.engine import run_backtest_for_ticker
from src.config.settings import SETTINGS
from src.engine.metrics import summarize_trades
from src.engine.signals import StrategyParams


def build_summaries(trades_df):
    return summarize_trades(trades_df)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest single ticker analysis")
    parser.add_argument("--data-dir", default=str(SETTINGS.runtime.data_dir))
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--output-dir", default=str(SETTINGS.runtime.output_dir))
    args = parser.parse_args()

    cfg = SETTINGS.strategy
    params = StrategyParams(
        window_profile=cfg.window_profile,
        price_tolerance=cfg.price_tolerance,
        lvn_threshold=cfg.lvn_threshold,
        bin_step=cfg.bin_step,
        min_profile_levels=cfg.min_profile_levels,
        rsi_period=cfg.rsi_period,
        rsi_long_max=cfg.rsi_long_max,
        rsi_short_min=cfg.rsi_short_min,
    )

    trades_df = run_backtest_for_ticker(
        data_dir=Path(args.data_dir),
        ticker=args.ticker,
        params=params,
        investimento_per_trade=cfg.investimento_per_trade,
        commissione_apertura=cfg.commissione_apertura,
        commissione_chiusura=cfg.commissione_chiusura,
    )
    summary_by_ticker_df, summary_global_df = summarize_trades(trades_df)

    ticker_dir = Path(args.output_dir) / "single_run" / args.ticker
    ticker_dir.mkdir(parents=True, exist_ok=True)
    trades_df.to_csv(ticker_dir / "trades.csv", index=False)
    summary_by_ticker_df.to_csv(ticker_dir / "summary_by_ticker.csv", index=False)
    summary_global_df.to_csv(ticker_dir / "summary_global.csv", index=False)
    print(f"Output saved in: {ticker_dir}")


if __name__ == "__main__":
    main()
