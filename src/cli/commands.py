from __future__ import annotations

from pathlib import Path

import click
import pandas as pd

from src.backtest.engine import run_backtest_for_ticker
from src.backtest.reporter import write_html_report, write_json_report
from src.backtest.results import BacktestResult
from src.config.settings import SETTINGS
from src.data.loader import discover_tickers, validate_data_dir
from src.engine.metrics import summarize_trades
from src.engine.signals import StrategyParams
from src.optimizer.grid_search import run_grid_search
from src.optimizer.walk_forward import run_walk_forward
from src.visualization.charts import plot_equity_curve
from src.visualization.dashboard import generate_dashboard


def _build_params() -> StrategyParams:
    cfg = SETTINGS.strategy
    return StrategyParams(
        window_profile=cfg.window_profile,
        price_tolerance=cfg.price_tolerance,
        lvn_threshold=cfg.lvn_threshold,
        bin_step=cfg.bin_step,
        min_profile_levels=cfg.min_profile_levels,
        rsi_period=cfg.rsi_period,
        rsi_long_max=cfg.rsi_long_max,
        rsi_short_min=cfg.rsi_short_min,
    )


@click.command()
@click.option("--ticker", required=True)
@click.option("--data-dir", default=str(SETTINGS.runtime.data_dir))
@click.option("--output-dir", default=str(SETTINGS.runtime.output_dir))
def backtest(ticker: str, data_dir: str, output_dir: str) -> None:
    params = _build_params()
    trades = run_backtest_for_ticker(
        Path(data_dir),
        ticker,
        params,
        SETTINGS.strategy.investimento_per_trade,
        SETTINGS.strategy.commissione_apertura,
        SETTINGS.strategy.commissione_chiusura,
    )
    by_ticker, global_summary = summarize_trades(trades)
    result = BacktestResult(trades=trades, summary_by_ticker=by_ticker, summary_global=global_summary)
    result_dir = Path(output_dir) / "single_run" / ticker
    result.to_csv(result_dir)
    write_json_report(result, result_dir / "report.json")
    write_html_report(result, result_dir / "report.html", title=f"LVN Backtest - {ticker}")
    click.echo(f"Output saved in {result_dir}")


@click.command()
@click.option("--data-dir", default=str(SETTINGS.runtime.data_dir))
@click.option("--output-dir", default=str(SETTINGS.runtime.output_dir))
def optimize(data_dir: str, output_dir: str) -> None:
    tickers = discover_tickers(Path(data_dir))
    if not tickers:
        raise click.ClickException(f"No tickers found in {data_dir}")
    cfg = SETTINGS
    params = _build_params()
    run_grid_search(
        data_dir=Path(data_dir),
        output_dir=Path(output_dir),
        tickers=tickers,
        base_params=params,
        window_profiles=cfg.grid.window_profiles,
        price_tolerances=cfg.grid.price_tolerances,
        lvn_thresholds=cfg.grid.lvn_thresholds,
        top_n=cfg.grid.top_n,
        investimento_per_trade=cfg.strategy.investimento_per_trade,
        commissione_apertura=cfg.strategy.commissione_apertura,
        commissione_chiusura=cfg.strategy.commissione_chiusura,
    )
    click.echo(f"Optimization completed. Output: {output_dir}")


@click.command(name="walk-forward")
@click.option("--ticker", required=True)
@click.option("--data-dir", default=str(SETTINGS.runtime.data_dir))
@click.option("--output-dir", default=str(SETTINGS.runtime.output_dir))
def walk_forward(ticker: str, data_dir: str, output_dir: str) -> None:
    params = _build_params()
    result = run_walk_forward(
        data_dir=Path(data_dir),
        ticker=ticker,
        params=params,
        investimento_per_trade=SETTINGS.strategy.investimento_per_trade,
        commissione_apertura=SETTINGS.strategy.commissione_apertura,
        commissione_chiusura=SETTINGS.strategy.commissione_chiusura,
    )
    out = Path(output_dir) / "reports" / f"walk_forward_{ticker}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    result.windows.to_csv(out, index=False)
    click.echo(f"Walk-forward results saved in {out}")


@click.command()
@click.option("--ticker", required=True)
@click.option("--results-dir", default=str(SETTINGS.runtime.output_dir))
def visualize(ticker: str, results_dir: str) -> None:
    trades_path = Path(results_dir) / "single_run" / ticker / "trades.csv"
    if not trades_path.exists():
        raise click.ClickException(f"Missing trades file: {trades_path}")
    trades = pd.read_csv(trades_path)
    chart_path = Path(results_dir) / "charts" / f"trades_{ticker}.png"
    plot_equity_curve(trades, chart_path)
    click.echo(f"Chart saved in {chart_path}")


@click.command()
@click.option("--results-dir", default=str(SETTINGS.runtime.output_dir))
def report(results_dir: str) -> None:
    base = Path(results_dir)
    summary_global = pd.read_csv(base / "baseline_global" / "summary_global.csv")
    summary_by_ticker = pd.read_csv(base / "baseline_global" / "summary_by_ticker.csv")
    dashboard = base / "reports" / "dashboard.html"
    generate_dashboard(summary_global, summary_by_ticker, dashboard)
    click.echo(f"Dashboard saved in {dashboard}")


@click.command()
@click.option("--data-dir", default=str(SETTINGS.runtime.data_dir))
def validate(data_dir: str) -> None:
    problems = validate_data_dir(Path(data_dir))
    if problems:
        lines = [f"{k}: {v}" for k, v in problems.items()]
        raise click.ClickException("Data validation failed:\n" + "\n".join(lines))
    click.echo("Data validation passed")
