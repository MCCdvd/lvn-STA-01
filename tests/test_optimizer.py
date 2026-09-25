from __future__ import annotations

import pandas as pd

from src.optimizer.grid_search import parse_float_list, parse_int_list


def test_parse_param_lists():
    assert parse_int_list("1, 2,3") == [1, 2, 3]
    assert parse_float_list("0.1, 0.2") == [0.1, 0.2]


def test_walk_forward_result_shape(tmp_path):
    from src.engine.signals import StrategyParams
    from src.optimizer.walk_forward import run_walk_forward

    ticker = "AAA"
    pd.DataFrame(
        {
            "Date": pd.date_range("2020-01-01", periods=330, freq="D"),
            "Close": [10 + (i % 10) * 0.1 for i in range(330)],
            "Volume": [100 + i for i in range(330)],
        }
    ).to_csv(tmp_path / f"{ticker}.csv", index=False)

    params = StrategyParams(25, 0.2, 0.9, 0.05, 5, 14, 70.0, 30.0)
    out = run_walk_forward(tmp_path, ticker, params, 10_000.0, 10.0, 10.0, train_size=200, test_size=50)
    assert "window_start" in out.windows.columns
