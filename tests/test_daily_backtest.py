import json
import os
import sqlite3
import tempfile
import textwrap
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backtest import load_optimized_params
from config import CONFIG
from engine import StrategyParams


REPO = Path(__file__).resolve().parents[1]
OPTIMIZED = {"window_profile": 12, "price_tolerance": 0.15, "lvn_threshold": 0.25}


class DailyBacktestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.params_path = self.repo / "optimized_params.json"
        self.defaults = StrategyParams(
            **{key: getattr(CONFIG.strategy, key) for key in StrategyParams.__dataclass_fields__}
        )

    def write_optimized_params(self):
        self.params_path.write_text(
            json.dumps({
                "month": "2026-10",
                "generated_from": "monthly-optimize.yml",
                "tickers": [{"ticker": "BAY", **OPTIMIZED, "profit_factor": float("inf")}],
            }),
            encoding="utf-8",
        )

    def test_load_ticker_lookup_ignores_metadata(self):
        self.write_optimized_params()
        self.assertEqual(load_optimized_params(str(self.params_path)), {"BAY": OPTIMIZED})

    def test_missing_file_and_empty_export(self):
        self.assertEqual(load_optimized_params(str(self.params_path)), {})
        self.params_path.write_text('{"month": "2026-10", "tickers": []}', encoding="utf-8")
        self.assertEqual(load_optimized_params(str(self.params_path)), {})

    def run_workflow(self, optimized=True):
        data_dir = self.repo / "data"
        data_dir.mkdir(exist_ok=True)
        for ticker in ("BAY", "NEW"):
            (data_dir / f"{ticker}.csv").touch()

        workflow = (REPO / ".github/workflows/daily-backtest.yml").read_text(encoding="utf-8")
        code = textwrap.dedent(
            workflow.split("python - <<'PY' 2>&1 | tee daily_backtest.log\n", 1)[1]
            .split("          PY\n", 1)[0]
        )

        def backtest(**kwargs):
            expected = replace(self.defaults, **OPTIMIZED) if optimized and kwargs["ticker"] == "BAY" else self.defaults
            self.assertEqual(kwargs["params"], expected)
            self.assertEqual(kwargs["data_dir"], str(data_dir))
            self.assertEqual(kwargs["investimento_per_trade"], CONFIG.strategy.investimento_per_trade)
            self.assertEqual(kwargs["commissione_apertura"], CONFIG.strategy.commissione_apertura)
            self.assertEqual(kwargs["commissione_chiusura"], CONFIG.strategy.commissione_chiusura)
            if kwargs["ticker"] == "NEW":
                return pd.DataFrame()
            return pd.DataFrame([{
                "ticker": "BAY", "realized_pnl": 100.0, "exit_date": "2026-10-03",
            }])

        with patch.dict(os.environ, {
            "GITHUB_WORKSPACE": str(self.repo),
            "RUNNER_TEMP": str(self.repo),
            "RUN_DATE": "2026-10-03",
        }), patch("backtest.run_backtest_for_ticker", side_effect=backtest) as run:
            exec(compile(code, str(REPO / ".github/workflows/daily-backtest.yml"), "exec"), {})
        self.assertEqual(run.call_count, 2)
        with sqlite3.connect(self.repo / "backtest_results.db") as conn:
            rows = conn.execute(
                "SELECT ticker, window_profile, price_tolerance, lvn_threshold "
                "FROM daily_backtest_runs WHERE run_date = '2026-10-03' ORDER BY ticker"
            ).fetchall()
            self.assertEqual(rows, [
                ("BAY", *(OPTIMIZED.values() if optimized else (
                    self.defaults.window_profile, self.defaults.price_tolerance, self.defaults.lvn_threshold,
                ))),
                ("NEW", self.defaults.window_profile, self.defaults.price_tolerance, self.defaults.lvn_threshold),
            ])
            self.assertEqual(conn.execute(
                "SELECT total_trades, total_pnl FROM daily_backtest_totals"
            ).fetchall(), [(1, 100.0)])

    def test_daily_workflow_missing_file_creates_audited_history(self):
        self.run_workflow(optimized=False)

    def test_daily_workflow_migrates_history_and_reruns(self):
        with sqlite3.connect(self.repo / "backtest_results.db") as conn:
            conn.execute("""
                CREATE TABLE daily_backtest_runs (
                    run_date TEXT NOT NULL, ticker TEXT NOT NULL, status TEXT NOT NULL,
                    trade_count INTEGER NOT NULL, win_rate REAL NOT NULL, total_pnl REAL NOT NULL,
                    avg_pnl_per_trade REAL NOT NULL, profit_factor REAL NOT NULL,
                    max_drawdown REAL NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (run_date, ticker)
                )
            """)
            conn.execute("""
                INSERT INTO daily_backtest_runs
                VALUES ('2026-10-02', 'OLD', 'no trades', 0, 0, 0, 0, 0, 0, '2026-10-02')
            """)
        self.write_optimized_params()
        self.run_workflow()
        self.run_workflow()
        self.params_path.unlink()
        self.run_workflow(optimized=False)
        with sqlite3.connect(self.repo / "backtest_results.db") as conn:
            self.assertEqual(conn.execute(
                "SELECT * FROM daily_backtest_runs WHERE ticker = 'OLD'"
            ).fetchone(), (
                "2026-10-02", "OLD", "no trades", 0, 0.0, 0.0, 0.0, 0.0, 0.0,
                "2026-10-02", None, None, None,
            ))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM daily_backtest_runs").fetchone(), (3,))


if __name__ == "__main__":
    unittest.main()
