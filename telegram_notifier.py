from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

import pandas as pd

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None


LOGGER = logging.getLogger("telegram_notifier")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def send_telegram_alert(message: str, parse_mode: str = "HTML") -> bool:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        LOGGER.warning("Telegram secrets are not configured; skipping notification")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    for attempt in range(1, 4):
        try:
            data = urllib.parse.urlencode(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))
            if response_data.get("ok"):
                return True
            LOGGER.error("Telegram API returned non-ok response: %s", response_data)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            LOGGER.error("Telegram notification attempt %s failed: %s", attempt, exc)

        if attempt < 3:
            time.sleep(2)

    return False


def _now_rome() -> datetime:
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo("Europe/Rome"))
        except Exception:
            pass
    return datetime.now()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _compute_profit_factor_from_pnl(pnls: pd.Series) -> float:
    gross_profit = float(pnls[pnls > 0].sum())
    gross_loss = float(pnls[pnls < 0].sum())
    if gross_loss < 0:
        return round(gross_profit / abs(gross_loss), 2)
    if gross_profit > 0:
        return float("inf")
    return 0.0


def _compute_max_drawdown_from_trade_pnl(pnls: pd.Series) -> float:
    if pnls.empty:
        return 0.0
    equity = pnls.cumsum()
    equity = pd.concat([pd.Series([0.0]), equity], ignore_index=True)
    drawdown = float((equity - equity.cummax()).min())
    return round(abs(drawdown), 2)


def format_daily_success_message(summary_df: pd.DataFrame, execution_time: float) -> str:
    df = summary_df.copy()
    if df.empty:
        return (
            "✅ <b>DAILY BACKTEST - SUCCESS</b>\n\n"
            "📊 <b>Execution Summary</b>\n"
            f"├─ Date: {_now_rome().strftime('%Y-%m-%d')}\n"
            f"├─ Time: {_now_rome().strftime('%H:%M')} Rome\n"
            f"└─ Duration: {execution_time:.1f} seconds"
        )

    if {"ticker", "realized_pnl"}.issubset(df.columns):
        by_ticker = (
            df.groupby("ticker", as_index=False)
            .agg(
                trade_count=("realized_pnl", "size"),
                total_pnl=("realized_pnl", "sum"),
                win_rate=("realized_pnl", lambda s: round((s > 0).mean() * 100, 2) if len(s) else 0.0),
            )
            .sort_values("total_pnl", ascending=False)
        )
        total_trades = int(len(df))
        total_pnl = round(float(df["realized_pnl"].sum()), 2)
        profit_factor = _compute_profit_factor_from_pnl(df["realized_pnl"])
        max_drawdown = _compute_max_drawdown_from_trade_pnl(df["realized_pnl"])
    else:
        by_ticker = df.copy()
        if "trade_count" not in by_ticker.columns:
            by_ticker["trade_count"] = 0
        if "win_rate" not in by_ticker.columns:
            by_ticker["win_rate"] = 0.0
        if "total_pnl" not in by_ticker.columns and "realized_pnl" in by_ticker.columns:
            by_ticker["total_pnl"] = by_ticker["realized_pnl"]
        if "total_pnl" not in by_ticker.columns:
            by_ticker["total_pnl"] = 0.0

        by_ticker = by_ticker.sort_values("total_pnl", ascending=False)
        total_trades = int(by_ticker.get("trade_count", pd.Series(dtype=float)).sum())
        total_pnl = round(float(by_ticker.get("total_pnl", pd.Series(dtype=float)).sum()), 2)
        profit_factor = _safe_float(by_ticker.get("profit_factor", pd.Series([0.0])).iloc[0], 0.0) if "profit_factor" in by_ticker.columns else 0.0
        max_drawdown = _safe_float(by_ticker.get("max_drawdown", pd.Series([0.0])).max(), 0.0) if "max_drawdown" in by_ticker.columns else 0.0

    ticker_count = int(by_ticker["ticker"].nunique()) if "ticker" in by_ticker.columns else int(len(by_ticker))
    profitable = int((by_ticker["total_pnl"] > 0).sum()) if "total_pnl" in by_ticker.columns else 0
    top = by_ticker.head(5)

    now_rome = _now_rome()
    lines = [
        "✅ <b>DAILY BACKTEST - SUCCESS</b>",
        "",
        "📊 <b>Execution Summary</b>",
        f"├─ Date: {now_rome.strftime('%Y-%m-%d')}",
        f"├─ Time: {now_rome.strftime('%H:%M')} Rome",
        f"├─ Duration: {execution_time:.1f} seconds",
        f"├─ Tickers: {ticker_count}",
        f"├─ Total Trades: {total_trades}",
        f"└─ Total P&L: €{total_pnl:,.2f}",
        "",
        "🏆 <b>Top 5 Performers:</b>",
    ]

    if top.empty:
        lines.append("No ticker summary available")
    else:
        for i, row in enumerate(top.itertuples(index=False), 1):
            ticker = getattr(row, "ticker", "N/A")
            pnl = _safe_float(getattr(row, "total_pnl", 0.0), 0.0)
            win_rate = _safe_float(getattr(row, "win_rate", 0.0), 0.0)
            lines.append(f"{i}. {ticker}: €{pnl:,.2f} ({win_rate:.2f}% win_rate)")

    lines.extend(
        [
            "",
            "📈 <b>Portfolio Overview</b>",
            f"├─ Profitable tickers: {profitable}/{ticker_count}",
            f"├─ Profit factor: {profit_factor:.2f}" if profit_factor != float("inf") else "├─ Profit factor: ∞",
            f"└─ Max drawdown: €{max_drawdown:,.2f}",
        ]
    )

    issue_url = os.getenv("DAILY_ISSUE_URL") or os.getenv("GITHUB_ISSUE_URL")
    if issue_url:
        lines.extend(["", f"🔗 Full Results: {issue_url}"])

    return "\n".join(lines)


def format_daily_failure_message(error: str, run_url: str) -> str:
    return "\n".join(
        [
            "⚠️ <b>DAILY BACKTEST - FAILED</b>",
            "",
            "❌ <b>Error Details:</b>",
            error.strip() if error else "Unknown error",
            "",
            "📍 Location: Daily Backtest Workflow",
            f"🔗 View Run: {run_url}",
        ]
    )


def _query_first_success(conn: sqlite3.Connection, queries: list[str]) -> pd.DataFrame:
    for query in queries:
        try:
            df = pd.read_sql_query(query, conn)
            if not df.empty:
                return df
        except Exception:
            continue
    return pd.DataFrame()


def format_monthly_success_message(db_path: str, run_month: str) -> str:
    old_params: dict[str, Any] = {"window_profile": "N/A", "price_tolerance": "N/A", "lvn_threshold": "N/A"}
    new_params: dict[str, Any] = old_params.copy()

    baseline_metrics = {"total_pnl": 0.0, "overall_win_rate": 0.0, "profit_factor": 0.0}
    optimized_metrics = baseline_metrics.copy()
    top_rows = pd.DataFrame(columns=["ticker", "total_pnl", "net_pnl_delta"])

    conn = sqlite3.connect(db_path)
    try:
        baseline_params_df = _query_first_success(
            conn,
            [
                "SELECT window_profile, price_tolerance, lvn_threshold FROM optimization_parameters WHERE lower(coalesce(scenario,'')) LIKE '%baseline%' ORDER BY rowid DESC LIMIT 1",
                "SELECT window_profile, price_tolerance, lvn_threshold FROM baseline_parameters ORDER BY rowid DESC LIMIT 1",
            ],
        )
        if not baseline_params_df.empty:
            row = baseline_params_df.iloc[0]
            old_params = {
                "window_profile": int(_safe_float(row.get("window_profile"), 0)),
                "price_tolerance": _safe_float(row.get("price_tolerance"), 0.0),
                "lvn_threshold": _safe_float(row.get("lvn_threshold"), 0.0),
            }

        params_df = _query_first_success(
            conn,
            [
                "SELECT window_profile, price_tolerance, lvn_threshold FROM optimization_parameters ORDER BY rowid DESC LIMIT 1",
                "SELECT window_profile, price_tolerance, lvn_threshold FROM best_parameters ORDER BY rowid DESC LIMIT 1",
            ],
        )
        if not params_df.empty:
            row = params_df.iloc[0]
            new_params = {
                "window_profile": int(_safe_float(row.get("window_profile"), 0)),
                "price_tolerance": _safe_float(row.get("price_tolerance"), 0.0),
                "lvn_threshold": _safe_float(row.get("lvn_threshold"), 0.0),
            }

        metrics_df = _query_first_success(
            conn,
            [
                "SELECT scenario, total_pnl, overall_win_rate, profit_factor FROM optimization_summary ORDER BY rowid DESC LIMIT 10",
                "SELECT scenario, total_pnl, overall_win_rate, profit_factor FROM comparison_baseline_vs_per_ticker ORDER BY rowid DESC LIMIT 10",
            ],
        )
        if not metrics_df.empty and "scenario" in metrics_df.columns:
            baseline_row = metrics_df[metrics_df["scenario"].astype(str).str.contains("baseline", case=False, na=False)]
            optimized_row = metrics_df[metrics_df["scenario"].astype(str).str.contains("optimized|best", case=False, na=False)]
            if not baseline_row.empty:
                b = baseline_row.iloc[0]
                baseline_metrics = {
                    "total_pnl": _safe_float(b.get("total_pnl")),
                    "overall_win_rate": _safe_float(b.get("overall_win_rate")),
                    "profit_factor": _safe_float(b.get("profit_factor")),
                }
            if not optimized_row.empty:
                o = optimized_row.iloc[0]
                optimized_metrics = {
                    "total_pnl": _safe_float(o.get("total_pnl")),
                    "overall_win_rate": _safe_float(o.get("overall_win_rate")),
                    "profit_factor": _safe_float(o.get("profit_factor")),
                }

        top_rows = _query_first_success(
            conn,
            [
                "SELECT ticker, total_pnl, net_pnl_delta FROM optimized_ticker_results ORDER BY total_pnl DESC LIMIT 5",
                "SELECT ticker, total_pnl, (total_pnl - baseline_pnl) AS net_pnl_delta FROM ticker_optimization_results ORDER BY total_pnl DESC LIMIT 5",
            ],
        )
    finally:
        conn.close()

    pnl_delta_pct = 0.0
    if baseline_metrics["total_pnl"]:
        pnl_delta_pct = ((optimized_metrics["total_pnl"] - baseline_metrics["total_pnl"]) / abs(baseline_metrics["total_pnl"])) * 100

    lines = [
        "✅ <b>MONTHLY OPTIMIZATION - SUCCESS</b>",
        "",
        f"📊 <b>Optimization Results ({run_month})</b>",
        "",
        "🎯 <b>Parameter Changes:</b>",
        "Old Parameters:",
        f"├─ window_profile: {old_params['window_profile']}",
        f"├─ price_tolerance: {old_params['price_tolerance']}",
        f"└─ lvn_threshold: {old_params['lvn_threshold']}",
        "",
        "New Optimized:",
        f"├─ window_profile: {new_params['window_profile']}",
        f"├─ price_tolerance: {new_params['price_tolerance']}",
        f"└─ lvn_threshold: {new_params['lvn_threshold']}",
        "",
        "📈 <b>Performance Improvement:</b>",
        f"├─ Total P&L: €{baseline_metrics['total_pnl']:,.2f} → €{optimized_metrics['total_pnl']:,.2f} ({pnl_delta_pct:+.1f}%)",
        f"├─ Overall Win Rate: {baseline_metrics['overall_win_rate']:.1f}% → {optimized_metrics['overall_win_rate']:.1f}%",
        f"└─ Profit Factor: {baseline_metrics['profit_factor']:.2f} → {optimized_metrics['profit_factor']:.2f}",
        "",
        "🏆 <b>Top 5 Optimized Tickers:</b>",
    ]

    if top_rows.empty:
        lines.append("No optimized ticker rows found in database")
    else:
        for i, row in enumerate(top_rows.itertuples(index=False), 1):
            ticker = getattr(row, "ticker", "N/A")
            total_pnl = _safe_float(getattr(row, "total_pnl", 0.0))
            delta = _safe_float(getattr(row, "net_pnl_delta", 0.0))
            lines.append(f"{i}. {ticker}: €{total_pnl:,.2f} (net {delta:+,.2f})")

    issue_url = os.getenv("MONTHLY_ISSUE_URL") or os.getenv("GITHUB_ISSUE_URL")
    if issue_url:
        lines.extend(["", f"🔗 Full Analysis: {issue_url}"])

    return "\n".join(lines)


def format_monthly_failure_message(error: str, run_url: str) -> str:
    return "\n".join(
        [
            "⚠️ <b>MONTHLY OPTIMIZATION - FAILED</b>",
            "",
            "❌ Error in optimization process",
            f"Error: {error.strip() if error else 'Unknown error'}",
            "",
            f"🔗 View Run: {run_url}",
        ]
    )


def _default_run_url() -> str:
    server = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    repo = os.getenv("GITHUB_REPOSITORY", "")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    if repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram notifier for backtest workflows")
    sub = parser.add_subparsers(dest="command", required=True)

    daily = sub.add_parser("notify-daily")
    daily.add_argument("--results-file", required=True)
    daily.add_argument("--execution-time", type=float, default=float(os.getenv("WORKFLOW_DURATION_SECONDS", "0") or 0))
    daily.add_argument("--status", choices=["success", "failure"], default="success")
    daily.add_argument("--error", default="")
    daily.add_argument("--run-url", default=_default_run_url())

    monthly = sub.add_parser("notify-monthly")
    monthly.add_argument("--db", required=True)
    monthly.add_argument("--run-month", default=_now_rome().strftime("%B %Y"))
    monthly.add_argument("--status", choices=["success", "failure"], default="success")
    monthly.add_argument("--error", default="")
    monthly.add_argument("--run-url", default=_default_run_url())

    args = parser.parse_args()

    message = ""
    try:
        if args.command == "notify-daily":
            if args.status == "failure":
                message = format_daily_failure_message(args.error, args.run_url)
            else:
                summary_df = pd.read_csv(args.results_file)
                message = format_daily_success_message(summary_df, args.execution_time)
        elif args.command == "notify-monthly":
            if args.status == "failure":
                message = format_monthly_failure_message(args.error, args.run_url)
            else:
                message = format_monthly_success_message(args.db, args.run_month)
    except Exception as exc:
        LOGGER.error("Failed building Telegram message: %s", exc)
        if args.command == "notify-daily":
            message = format_daily_failure_message(
                args.error or f"Daily notification formatting error: {exc}",
                args.run_url,
            )
        else:
            message = format_monthly_failure_message(
                args.error or f"Monthly notification formatting error: {exc}",
                args.run_url,
            )

    sent = send_telegram_alert(message)
    if not sent:
        LOGGER.warning("Telegram message not delivered")


if __name__ == "__main__":
    main()
