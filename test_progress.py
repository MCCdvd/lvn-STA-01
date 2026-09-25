from __future__ import annotations

import io
import unittest

from progress import ProgressDisplay, RunMetrics, format_currency, format_duration, format_percentage


class ProgressDisplayTests(unittest.TestCase):
    def test_format_helpers(self) -> None:
        self.assertEqual(format_currency(1234.5), "€1,234.50")
        self.assertEqual(format_percentage(58.34), "58.3%")
        self.assertEqual(format_duration(45.2), "45.2s")
        self.assertEqual(format_duration(125), "2m 05s")
        self.assertEqual(format_duration(None), "n/a")
        self.assertEqual(format_duration(float("inf")), "n/a")

    def test_progress_and_summary_output(self) -> None:
        stream = io.StringIO()
        display = ProgressDisplay(
            title="LVN Progress",
            total_units=4,
            unit_label="runs",
            update_interval_seconds=0.0,
            stream=stream,
            use_unicode=False,
        )

        display.record_ticker_result("A2A", 2, 150.0)
        display.record_ticker_result("AIR", 0, -25.0)
        display.update(
            processed_units=2,
            current_ticker="A2A",
            metrics=RunMetrics(trades_found=2, total_pnl=150.0, win_rate=50.0, max_drawdown=20.0),
            context="Grid search",
            force=True,
        )
        display.print_summary(total_time_seconds=12.5)

        output = stream.getvalue()
        self.assertIn("Progress: [################----------------] 50.0% (2/4 runs)", output)
        self.assertIn("Current: A2A", output)
        self.assertIn("Best Ticker (so far): A2A (€150.00)", output)
        self.assertIn("Worst Ticker (so far): AIR (€-25.00)", output)
        self.assertIn("Total processing time: 12.5s", output)
        self.assertIn("Tickers with trades: 1", output)
        self.assertIn("Tickers without trades: 1", output)
        self.assertIn("Skipped tickers: 0", output)

    def test_empty_summary_and_disabled_rendering(self) -> None:
        stream = io.StringIO()
        display = ProgressDisplay(
            title="LVN Progress",
            total_units=1,
            unit_label="runs",
            update_interval_seconds=0.0,
            stream=stream,
            use_unicode=False,
        )
        display.record_skipped_ticker("BAD")
        display.print_summary(total_time_seconds=0.0)
        self.assertIn("Best performing ticker: n/a", stream.getvalue())
        self.assertIn("Worst performing ticker: n/a", stream.getvalue())
        self.assertIn("Skipped tickers: 1", stream.getvalue())

        disabled_stream = io.StringIO()
        disabled_display = ProgressDisplay(
            title="Disabled",
            total_units=1,
            unit_label="runs",
            enabled=False,
            stream=disabled_stream,
            use_unicode=False,
        )
        disabled_display.update(1, "A2A", RunMetrics(), force=True)
        disabled_display.print_summary(total_time_seconds=0.0)
        self.assertEqual(disabled_stream.getvalue(), "")

    def test_broken_pipe_disables_further_output(self) -> None:
        class BrokenStream:
            encoding = "utf-8"

            def write(self, _: str) -> int:
                raise BrokenPipeError()

            def flush(self) -> None:
                return None

        display = ProgressDisplay(
            title="Broken",
            total_units=1,
            unit_label="runs",
            update_interval_seconds=0.0,
            stream=BrokenStream(),
        )
        display.update(1, "A2A", RunMetrics(), force=True)
        self.assertFalse(display.enabled)
        display.print_summary(total_time_seconds=0.0)


if __name__ == "__main__":
    unittest.main()
