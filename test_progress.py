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


if __name__ == "__main__":
    unittest.main()
