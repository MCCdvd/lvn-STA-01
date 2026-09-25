from __future__ import annotations

import pandas as pd

from src.utils.validators import ensure_columns


def preprocess_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    ensure_columns(df)
    work = df.copy()
    work["Date"] = pd.to_datetime(work["Date"], errors="coerce")
    work["Close"] = pd.to_numeric(work["Close"], errors="coerce")
    work["Volume"] = pd.to_numeric(work["Volume"], errors="coerce")
    work = work.dropna(subset=["Date", "Close", "Volume"]).sort_values("Date").reset_index(drop=True)
    if work.empty:
        raise ValueError("No valid rows after preprocessing")
    return work
