from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass
from typing import Dict, Optional, TextIO


@dataclass(frozen=True)
class RunMetrics:
    trades_found: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    max_drawdown: float = 0.0


def format_currency(value: float) -> str:
    return f"€{float(value):,.2f}"


def format_percentage(value: float) -> str:
    return f"{float(value):.1f}%"


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None or math.isinf(seconds):
        return "n/a"
    seconds = max(float(seconds), 0.0)
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remaining_seconds = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return f"{minutes}m {remaining_seconds:02d}s"
    hours, remaining_minutes = divmod(minutes, 60)
    return f"{hours}h {remaining_minutes:02d}m"


class ProgressDisplay:
    def __init__(
        self,
        title: str,
        total_units: int,
        unit_label: str,
        update_interval_seconds: float = 1.0,
        bar_width: int = 32,
        enabled: bool = True,
        stream: Optional[TextIO] = None,
        use_unicode: Optional[bool] = None,
    ) -> None:
        self.title = title
        self.total_units = max(int(total_units), 1)
        self.unit_label = unit_label
        self.update_interval_seconds = float(update_interval_seconds)
        self.bar_width = max(int(bar_width), 10)
        self.enabled = enabled
        self.stream = stream or sys.stdout
        self.use_unicode = self._supports_unicode() if use_unicode is None else use_unicode
        self.start_time = time.monotonic()
        self.last_render_time = 0.0
        self.ticker_results: Dict[str, Dict[str, float]] = {}
        self.skipped_tickers: set[str] = set()

    def set_total_units(self, total_units: int) -> None:
        self.total_units = max(int(total_units), 1)

    def record_ticker_result(self, ticker: str, trade_count: int, total_pnl: float) -> None:
        self.skipped_tickers.discard(ticker)
        self.ticker_results[ticker] = {"trade_count": int(trade_count), "total_pnl": float(total_pnl)}

    def record_skipped_ticker(self, ticker: str) -> None:
        self.skipped_tickers.add(ticker)
        self.ticker_results.pop(ticker, None)

    def has_skipped_ticker(self, ticker: str) -> bool:
        return ticker in self.skipped_tickers

    def update(
        self,
        processed_units: int,
        current_ticker: str,
        metrics: RunMetrics,
        context: Optional[str] = None,
        force: bool = False,
    ) -> None:
        if not self.enabled:
            return

        now = time.monotonic()
        processed_units = min(max(int(processed_units), 0), self.total_units)
        if not force and processed_units < self.total_units and now - self.last_render_time < self.update_interval_seconds:
            return

        self.last_render_time = now
        elapsed = now - self.start_time
        eta = None
        if processed_units > 0:
            eta = (elapsed / processed_units) * (self.total_units - processed_units)

        progress_ratio = processed_units / self.total_units if self.total_units else 0.0
        progress_percent = progress_ratio * 100

        lines = [
            self._header(),
            "",
            f"Progress: [{self._bar(progress_ratio)}] {progress_percent:.1f}% ({processed_units}/{self.total_units} {self.unit_label})",
        ]
        if context:
            lines.append(f"Stage: {context}")
        lines.extend(
            [
                "",
                f"Current: {current_ticker}",
                f"  {'├' if self.use_unicode else '|'}- Trades: {metrics.trades_found}",
                f"  {'├' if self.use_unicode else '|'}- Total P&L: {format_currency(metrics.total_pnl)}",
                f"  {'├' if self.use_unicode else '|'}- Win Rate: {format_percentage(metrics.win_rate)}",
                f"  {'└' if self.use_unicode else '|'}- Max Drawdown: {format_currency(metrics.max_drawdown)}",
                "",
                f"Elapsed: {format_duration(elapsed)} | Estimated Remaining: {format_duration(eta)}",
                "",
                f"Best Ticker (so far): {self._format_best_or_worst(best=True)}",
                f"Worst Ticker (so far): {self._format_best_or_worst(best=False)}",
                "",
            ]
        )
        self._emit(lines)

    def print_summary(self, total_time_seconds: Optional[float] = None) -> None:
        if not self.enabled:
            return

        elapsed = total_time_seconds if total_time_seconds is not None else time.monotonic() - self.start_time
        with_trades = sum(1 for result in self.ticker_results.values() if int(result["trade_count"]) > 0)
        without_trades = len(self.ticker_results) - with_trades
        lines = [
            self._header("Run Summary"),
            "",
            f"Total processing time: {format_duration(elapsed)}",
            f"Tickers with trades: {with_trades}",
            f"Tickers without trades: {without_trades}",
            f"Skipped tickers: {len(self.skipped_tickers)}",
            f"Best performing ticker: {self._format_best_or_worst(best=True)}",
            f"Worst performing ticker: {self._format_best_or_worst(best=False)}",
            "",
        ]
        self._emit(lines)

    def _format_best_or_worst(self, best: bool) -> str:
        if not self.ticker_results:
            return "n/a"
        ordered = sorted(
            self.ticker_results.items(),
            key=lambda item: ((-1 if best else 1) * float(item[1]["total_pnl"]), item[0]),
        )
        ticker, metrics = ordered[0]
        return f"{ticker} ({format_currency(metrics['total_pnl'])})"

    def _header(self, title: Optional[str] = None) -> str:
        title = title or self.title
        width = max(len(title) + 4, 64)
        if self.use_unicode:
            return f"╔{'═' * (width - 2)}╗\n║ {title.ljust(width - 4)} ║\n╚{'═' * (width - 2)}╝"
        return f"+{'-' * (width - 2)}+\n| {title.ljust(width - 4)} |\n+{'-' * (width - 2)}+"

    def _bar(self, ratio: float) -> str:
        filled = min(max(int(round(ratio * self.bar_width)), 0), self.bar_width)
        empty = self.bar_width - filled
        if self.use_unicode:
            return ("█" * filled) + ("░" * empty)
        return ("#" * filled) + ("-" * empty)

    def _supports_unicode(self) -> bool:
        encoding = (getattr(self.stream, "encoding", None) or "").lower()
        return "utf" in encoding

    def _emit(self, lines: list[str]) -> None:
        try:
            print("\n".join(lines), file=self.stream, flush=True)
        except BrokenPipeError:
            self.enabled = False
