from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from src.data.processor import preprocess_ohlcv


def discover_tickers(data_dir: Path) -> list[str]:
    if not data_dir.exists():
        return []
    return sorted(
        p.stem
        for p in data_dir.glob("*.csv")
        if p.name != "failed_tickers.csv"
    )


def load_ticker_data(data_dir: Path, ticker: str) -> pd.DataFrame:
    file_path = data_dir / f"{ticker}.csv"
    if not file_path.exists():
        raise FileNotFoundError(f"Ticker file not found: {file_path}")
    return preprocess_ohlcv(pd.read_csv(file_path))


def validate_data_dir(data_dir: Path, tickers: Iterable[str] | None = None) -> dict[str, str]:
    problems: dict[str, str] = {}
    target = list(tickers) if tickers else discover_tickers(data_dir)
    if not target:
        return {"_global": f"No CSV files found in {data_dir}"}

    for ticker in target:
        try:
            load_ticker_data(data_dir, ticker)
        except Exception as exc:  # noqa: BLE001
            problems[ticker] = str(exc)
    return problems
