from __future__ import annotations

from pathlib import Path

import click
import pandas as pd

from src.backtest.engine import run_backtest_for_ticker
from src.backtest.reporter import write_html_report, write_json_report
from src.backtest.results import BacktestResult
from src.config.settings import load_settings
from src.data.loader import discover_tickers, validate_data_dir
from src.engine.metrics import summarize_trades
from src.engine.signals import StrategyParams
from src.optimizer.grid_search import run_grid_search
from src.optimizer.walk_forward import run_walk_forward
from src.visualization.charts import plot_equity_curve
from src.visualization.dashboard import generate_dashboard


def _build_params(cfg: object) -> StrategyParams:
    strategy = cfg.strategy
    return StrategyParams(
        window_profile=strategy.window_profile,
        price_tolerance=strategy.price_tolerance,
        lvn_threshold=strategy.lvn_threshold,
        bin_step=strategy.bin_step,
        min_profile_levels=strategy.min_profile_levels,
        rsi_period=strategy.rsi_period,
        rsi_long_max=strategy.rsi_long_max,
        rsi_short_min=strategy.rsi_short_min,
    )


@click.command()
@click.option("--ticker", required=True)
@click.option("--data-dir", default=None)
@click.option("--output-dir", default=None)
def backtest(ticker: str, data_dir: str | None, output_dir: str | None) -> None:
    cfg = load_settings()
    active_data_dir = Path(data_dir) if data_dir else cfg.runtime.data_dir
    active_output_dir = Path(output_dir) if output_dir else cfg.runtime.output_dir
    params = _build_params(cfg)
    trades = run_backtest_for_ticker(
        active_data_dir,
        ticker,
        params,
        cfg.strategy.investimento_per_trade,
        cfg.strategy.commissione_apertura,
        cfg.strategy.commissione_chiusura,
    )
    by_ticker, global_summary = summarize_trades(trades)
    result = BacktestResult(trades=trades, summary_by_ticker=by_ticker, summary_global=global_summary)
    result_dir = active_output_dir / "single_run" / ticker
    result.to_csv(result_dir)
    write_json_report(result, result_dir / "report.json")
    write_html_report(result, result_dir / "report.html", title=f"LVN Backtest - {ticker}")
    click.echo(f"Output saved in {result_dir}")


@click.command()
@click.option("--data-dir", default=None)
@click.option("--output-dir", default=None)
def optimize(data_dir: str | None, output_dir: str | None) -> None:
    cfg = load_settings()
    active_data_dir = Path(data_dir) if data_dir else cfg.runtime.data_dir
    active_output_dir = Path(output_dir) if output_dir else cfg.runtime.output_dir
    tickers = discover_tickers(active_data_dir)
    if not tickers:
        raise click.ClickException(f"No tickers found in {active_data_dir}")
    params = _build_params(cfg)
    run_grid_search(
        data_dir=active_data_dir,
        output_dir=active_output_dir,
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
    click.echo(f"Optimization completed. Output: {active_output_dir}")


@click.command(name="walk-forward")
@click.option("--ticker", required=True)
@click.option("--data-dir", default=None)
@click.option("--output-dir", default=None)
def walk_forward(ticker: str, data_dir: str | None, output_dir: str | None) -> None:
    cfg = load_settings()
    active_data_dir = Path(data_dir) if data_dir else cfg.runtime.data_dir
    active_output_dir = Path(output_dir) if output_dir else cfg.runtime.output_dir
    params = _build_params(cfg)
    result = run_walk_forward(
        data_dir=active_data_dir,
        ticker=ticker,
        params=params,
        investimento_per_trade=cfg.strategy.investimento_per_trade,
        commissione_apertura=cfg.strategy.commissione_apertura,
        commissione_chiusura=cfg.strategy.commissione_chiusura,
    )
    out = active_output_dir / "reports" / f"walk_forward_{ticker}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    result.windows.to_csv(out, index=False)
    click.echo(f"Walk-forward results saved in {out}")


@click.command()
@click.option("--ticker", required=True)
@click.option("--results-dir", default=None)
def visualize(ticker: str, results_dir: str | None) -> None:
    cfg = load_settings()
    base = Path(results_dir) if results_dir else cfg.runtime.output_dir
    trades_path = base / "single_run" / ticker / "trades.csv"
    if not trades_path.exists():
        raise click.ClickException(f"Missing trades file: {trades_path}")
    trades = pd.read_csv(trades_path)
    chart_path = base / "charts" / f"trades_{ticker}.png"
    plot_equity_curve(trades, chart_path)
    click.echo(f"Chart saved in {chart_path}")


@click.command()
@click.option("--results-dir", default=None)
@click.option("--summary-global", default=None, help="Path to summary_global.csv")
@click.option("--summary-by-ticker", default=None, help="Path to summary_by_ticker.csv")
def report(results_dir: str | None, summary_global: str | None, summary_by_ticker: str | None) -> None:
    cfg = load_settings()
    base = Path(results_dir) if results_dir else cfg.runtime.output_dir
    summary_global_path = Path(summary_global) if summary_global else base / "baseline_global" / "summary_global.csv"
    summary_by_ticker_path = Path(summary_by_ticker) if summary_by_ticker else base / "baseline_global" / "summary_by_ticker.csv"
    if (not summary_global_path.is_file()) or (not summary_by_ticker_path.is_file()):
        raise click.ClickException(
            "Missing summary files. Provide --summary-global and --summary-by-ticker, "
            "or run optimize so baseline summaries are created under results_dir/baseline_global."
        )
    summary_global_df = pd.read_csv(summary_global_path)
    summary_by_ticker_df = pd.read_csv(summary_by_ticker_path)
    dashboard = base / "reports" / "dashboard.html"
    generate_dashboard(summary_global_df, summary_by_ticker_df, dashboard)
    click.echo(f"Dashboard saved in {dashboard}")


@click.command()
@click.option("--data-dir", default=None)
def validate(data_dir: str | None) -> None:
    cfg = load_settings()
    active_data_dir = Path(data_dir) if data_dir else cfg.runtime.data_dir
    problems = validate_data_dir(active_data_dir)
    if problems:
        lines = [f"{k}: {v}" for k, v in problems.items()]
        raise click.ClickException("Data validation failed:\n" + "\n".join(lines))
    click.echo("Data validation passed")
