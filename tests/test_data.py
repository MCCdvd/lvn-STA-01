from __future__ import annotations

import pandas as pd

from src.data.loader import load_ticker_data


def test_load_ticker_data_preprocesses_rows(tmp_path):
    file_path = tmp_path / "AAA.csv"
    pd.DataFrame(
        {
            "Date": ["2024-01-02", "bad-date", "2024-01-01"],
            "Close": [10.0, 11.0, 9.0],
            "Volume": [100, 200, 50],
        }
    ).to_csv(file_path, index=False)

    df = load_ticker_data(tmp_path, "AAA")
    assert len(df) == 2
    assert str(df.iloc[0]["Date"].date()) == "2024-01-01"
