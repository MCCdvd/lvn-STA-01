import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from dataclasses import dataclass
from types import SimpleNamespace


def _load_module():
    pandas_stub = types.ModuleType("pandas")
    pandas_stub.DataFrame = object
    sys.modules["pandas"] = pandas_stub

    backtest_stub = types.ModuleType("backtest")
    backtest_stub.build_summaries = lambda *_args, **_kwargs: (None, None)
    backtest_stub.run_backtest_for_ticker = lambda *_args, **_kwargs: None
    sys.modules["backtest"] = backtest_stub

    config_stub = types.ModuleType("config")
    config_stub.CONFIG = SimpleNamespace(
        strategy=SimpleNamespace(
            bin_step=0.1,
            min_profile_levels=10,
            rsi_period=14,
            rsi_long_max=70.0,
            rsi_short_min=30.0,
            investimento_per_trade=0.0,
            commissione_apertura=0.0,
            commissione_chiusura=0.0,
        )
    )
    sys.modules["config"] = config_stub

    engine_stub = types.ModuleType("engine")

    @dataclass
    class StrategyParams:
        window_profile: int
        price_tolerance: float
        lvn_threshold: float
        bin_step: float
        min_profile_levels: int
        rsi_period: int
        rsi_long_max: float
        rsi_short_min: float

    engine_stub.StrategyParams = StrategyParams
    sys.modules["engine"] = engine_stub

    if "run_all_tickers_backtest" in sys.modules:
        del sys.modules["run_all_tickers_backtest"]
    return importlib.import_module("run_all_tickers_backtest")


class IterTickerPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_nested_tickers_dict_format(self):
        payload = {
            "generated_at": "2026-09-26T00:00:00",
            "tickers": {
                "BFF": {"parameters": {"window_profile": 12, "price_tolerance": 0.15, "lvn_threshold": 0.25}},
            },
        }
        rows = self.mod._iter_ticker_payloads(payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "BFF")

    def test_flat_legacy_format(self):
        payload = {"CBK": {"window_profile": 10, "price_tolerance": 0.2, "lvn_threshold": 0.3}}
        rows = self.mod._iter_ticker_payloads(payload)
        self.assertEqual(rows, [("CBK", payload["CBK"])])

    def test_invalid_nested_tickers_type_raises(self):
        with self.assertRaises(ValueError):
            self.mod._iter_ticker_payloads({"tickers": "invalid"})

    def test_metadata_rows_are_ignored(self):
        payload = {
            "summary": {"source": "x"},
            "BFF": {"window_profile": 12, "price_tolerance": 0.15, "lvn_threshold": 0.25},
        }
        rows = self.mod._iter_ticker_payloads(payload)
        self.assertEqual(rows, [("BFF", payload["BFF"])])

    def test_null_required_values_not_treated_as_ticker_row(self):
        payload = {"BFF": {"window_profile": None, "price_tolerance": 0.15, "lvn_threshold": 0.25}}
        rows = self.mod._iter_ticker_payloads(payload)
        self.assertEqual(rows, [])

    def test_parse_specs_nested_null_optional_ints_use_defaults(self):
        payload = {
            "tickers": {
                "BFF": {
                    "parameters": {
                        "window_profile": 12,
                        "price_tolerance": 0.15,
                        "lvn_threshold": 0.25,
                        "min_profile_levels": None,
                        "rsi_period": None,
                    }
                }
            }
        }
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as handle:
            json.dump(payload, handle)
            path = handle.name
        try:
            specs, invalid = self.mod._parse_specs(path)
        finally:
            os.unlink(path)

        self.assertEqual(len(invalid), 0)
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].params.min_profile_levels, 10)
        self.assertEqual(specs[0].params.rsi_period, 14)


if __name__ == "__main__":
    unittest.main()
