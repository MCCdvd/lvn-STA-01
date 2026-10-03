import contextlib
import io
import os
import sqlite3
import tempfile
import textwrap
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import fetch_latest_prices
import optimizer
from config import INDEX_TICKERS, TICKERS, YAHOO_SYMBOLS


REPO = Path(__file__).resolve().parents[1]


class TickerUniverseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.data_dir = self.repo / "data"
        self.data_dir.mkdir()
        self.index_tickers = set().union(*INDEX_TICKERS.values())

    def test_complete_index_configuration(self):
        self.assertEqual(set(INDEX_TICKERS), {"MIB40", "DAX40", "CAC40"})
        for index, tickers in INDEX_TICKERS.items():
            with self.subTest(index=index):
                self.assertEqual(len(tickers), 40)
                self.assertEqual(len(set(tickers)), 40)
                self.assertTrue(set(tickers).issubset(TICKERS))
                suffix = {"MIB40": ".MI", "DAX40": ".DE", "CAC40": ".PA"}[index]
                for ticker in tickers:
                    expected_suffix = ".AS" if ticker == "MT" else suffix
                    self.assertTrue(YAHOO_SYMBOLS[ticker].endswith(expected_suffix), ticker)
        self.assertEqual(len(TICKERS), len(set(TICKERS)))
        self.assertEqual(set(TICKERS), set(YAHOO_SYMBOLS))
        self.assertIs(fetch_latest_prices.TICKERS, TICKERS)
        self.assertEqual(YAHOO_SYMBOLS["BAY"], "BAYN.DE")
        self.assertEqual(YAHOO_SYMBOLS["DB"], "DBK.DE")
        self.assertEqual(YAHOO_SYMBOLS["AIR"], "AIR.PA")
        self.assertEqual(YAHOO_SYMBOLS["AIR.DE"], "AIR.DE")
        self.assertEqual(YAHOO_SYMBOLS["STLAM"], "STLAM.MI")
        self.assertEqual(YAHOO_SYMBOLS["STLAP"], "STLAP.PA")
        self.assertEqual(YAHOO_SYMBOLS["STMMI"], "STMMI.MI")
        self.assertEqual(YAHOO_SYMBOLS["STM"], "STM.PA")
        self.assertEqual(YAHOO_SYMBOLS["VOW3"], "VOW3.DE")
        self.assertEqual(YAHOO_SYMBOLS["BC"], "BC.MI")
        self.assertEqual(YAHOO_SYMBOLS["MT"], "MT.AS")
        self.assertEqual(YAHOO_SYMBOLS["TPRO"], "TPRO.MI")
        self.assertEqual(YAHOO_SYMBOLS["HOT"], "HOT.DE")
        self.assertIn("TPRO", INDEX_TICKERS["MIB40"])
        self.assertNotIn("DIA", INDEX_TICKERS["MIB40"])
        self.assertEqual(YAHOO_SYMBOLS["DIA"], "DIA.MI")
        self.assertIn("HOT", INDEX_TICKERS["DAX40"])
        self.assertNotIn("PAH3", INDEX_TICKERS["DAX40"])

    def test_fetch_defaults_bootstrap_and_incremental_updates(self):
        prices = pd.DataFrame({
            "Date": ["2026-10-01"], "Close": [10.0], "Volume": [100],
        })
        with patch("sys.argv", [
            "fetch_latest_prices.py", "--data-dir", str(self.data_dir),
        ]), patch("fetch_latest_prices._download_prices", return_value=prices) as download:
            with contextlib.redirect_stdout(io.StringIO()):
                fetch_latest_prices.main()
        self.assertEqual(download.call_count, len(TICKERS))
        self.assertEqual(
            [call.args[0] for call in download.call_args_list],
            [YAHOO_SYMBOLS[ticker] for ticker in TICKERS],
        )
        self.assertTrue(all(call.args[1] == "2020-01-01" for call in download.call_args_list))
        self.assertEqual({path.stem for path in self.data_dir.glob("*.csv")}, set(TICKERS))
        self.assertEqual(set(optimizer._discover_tickers(str(self.data_dir))), set(TICKERS))

        for ticker in self.index_tickers:
            with self.subTest(ticker=ticker):
                updated_prices = pd.DataFrame({
                    "Date": ["2026-10-01", "2026-10-02"],
                    "Close": [99.0, 11.0], "Volume": [100, 200],
                })
                with patch("fetch_latest_prices._download_prices", return_value=updated_prices) as download:
                    _, updated = fetch_latest_prices._upsert_ticker(
                        self.data_dir, ticker, date(2026, 10, 2), date(2020, 1, 1),
                    )
                self.assertTrue(updated)
                download.assert_called_once_with(YAHOO_SYMBOLS[ticker], "2026-10-02", "2026-10-03")
                result = pd.read_csv(self.data_dir / f"{ticker}.csv")
                self.assertEqual(result["Date"].tolist(), ["2026-10-01", "2026-10-02"])
                self.assertEqual(result["Close"].tolist(), [10.0, 11.0])

    def test_explicit_tickers_still_override_defaults(self):
        with patch("sys.argv", [
            "fetch_latest_prices.py", "--data-dir", str(self.data_dir), "--tickers", "UCG", "SAP", "SAN",
        ]), patch("fetch_latest_prices._upsert_ticker", return_value=("updated", True)) as upsert:
            with contextlib.redirect_stdout(io.StringIO()):
                fetch_latest_prices.main()
        self.assertEqual([call.args[1] for call in upsert.call_args_list], ["UCG", "SAP", "SAN"])

    def test_fetch_continues_after_download_error_and_empty_data(self):
        prices = pd.DataFrame({
            "Date": ["2026-10-01"], "Close": [10.0], "Volume": [100],
        })
        output = io.StringIO()
        with patch("sys.argv", [
            "fetch_latest_prices.py", "--data-dir", str(self.data_dir), "--tickers", "UCG", "SAP", "SAN",
        ]), patch("fetch_latest_prices._download_prices", side_effect=[
            RuntimeError("download unavailable"), pd.DataFrame(), prices,
        ]) as download:
            with contextlib.redirect_stdout(output):
                fetch_latest_prices.main()
        self.assertEqual(download.call_count, 3)
        self.assertEqual({path.stem for path in self.data_dir.glob("*.csv")}, {"SAN"})
        self.assertIn("- Updated: 1", output.getvalue())
        self.assertIn("- Skipped: 1", output.getvalue())
        self.assertIn("- Errors: 1", output.getvalue())

    def test_daily_workflow_processes_all_index_tickers(self):
        for ticker in self.index_tickers:
            (self.data_dir / f"{ticker}.csv").touch()
        workflow = (REPO / ".github/workflows/daily-backtest.yml").read_text(encoding="utf-8")
        code = textwrap.dedent(
            workflow.split("python - <<'PY' 2>&1 | tee daily_backtest.log\n", 1)[1]
            .split("          PY\n", 1)[0]
        )
        with patch.dict(os.environ, {
            "GITHUB_WORKSPACE": str(self.repo),
            "RUNNER_TEMP": str(self.repo),
            "RUN_DATE": "2026-10-03",
        }), patch("backtest.run_backtest_for_ticker", return_value=pd.DataFrame()) as run:
            with contextlib.redirect_stdout(io.StringIO()):
                exec(compile(code, str(REPO / ".github/workflows/daily-backtest.yml"), "exec"), {})
        self.assertEqual({call.kwargs["ticker"] for call in run.call_args_list}, self.index_tickers)
        with sqlite3.connect(self.repo / "backtest_results.db") as conn:
            self.assertEqual(
                {row[0] for row in conn.execute("SELECT ticker FROM daily_backtest_runs")},
                self.index_tickers,
            )

    def test_monthly_optimizer_processes_all_index_tickers(self):
        for ticker in self.index_tickers:
            (self.data_dir / f"{ticker}.csv").touch()
        output_dir = self.repo / "optimization"
        with patch("sys.argv", [
            "optimizer.py", "--data-dir", str(self.data_dir), "--output-dir", str(output_dir),
            "--window-profiles", "12", "--price-tolerances", "0.15", "--lvn-thresholds", "0.25",
        ]), patch("optimizer.run_backtest_for_ticker", return_value=pd.DataFrame()) as run:
            with contextlib.redirect_stdout(io.StringIO()):
                optimizer.main()
        self.assertEqual(run.call_count, 3 * len(self.index_tickers))
        self.assertEqual({call.kwargs["ticker"] for call in run.call_args_list}, self.index_tickers)
        best = pd.read_csv(output_dir / "per_ticker_best_global" / "best_params_all_tickers.csv")
        self.assertEqual(set(best["ticker"]), self.index_tickers)


if __name__ == "__main__":
    unittest.main()
