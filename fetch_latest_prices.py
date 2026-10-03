from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import yfinance as yf

from config import TICKERS, YAHOO_SYMBOLS


def _extract_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column in frame.columns:
        return frame[column]
    if isinstance(frame.columns, pd.MultiIndex):
        level0 = frame.columns.get_level_values(0)
        if column in level0:
            return frame.xs(column, axis=1, level=0).iloc[:, 0]
    raise KeyError(f"Column '{column}' not found in downloaded data")


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _download_prices(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    data = yf.Ticker(symbol).history(
        start=start_date,
        end=end_date,
        auto_adjust=False,
        raise_errors=True,
    )
    if data is None or data.empty:
        return pd.DataFrame(columns=["Date", "Close", "Volume"])

    close = _extract_series(data, "Close")
    volume = _extract_series(data, "Volume")

    result = pd.DataFrame(
        {
            "Date": pd.to_datetime(data.index).strftime("%Y-%m-%d"),
            "Close": pd.to_numeric(close, errors="coerce"),
            "Volume": pd.to_numeric(volume, errors="coerce"),
        }
    )
    result = result.dropna(subset=["Date", "Close", "Volume"]).copy()
    return result[["Date", "Close", "Volume"]]


def _read_existing(csv_path: Path) -> Tuple[pd.DataFrame, Optional[date]]:
    if not csv_path.exists():
        return pd.DataFrame(columns=["Date", "Close", "Volume"]), None

    existing = pd.read_csv(csv_path)
    required_columns = ["Date", "Close", "Volume"]
    for column in required_columns:
        if column not in existing.columns:
            raise ValueError(f"Missing '{column}' column")

    existing = existing[required_columns].copy()
    existing["Date"] = pd.to_datetime(existing["Date"], errors="coerce").dt.date
    existing = existing.dropna(subset=["Date"]).copy()
    if existing.empty:
        return pd.DataFrame(columns=required_columns), None

    last_date = max(existing["Date"])
    existing["Date"] = existing["Date"].astype(str)
    return existing, last_date


def _upsert_ticker(data_dir: Path, ticker: str, today: date, bootstrap_start_date: date) -> Tuple[str, bool]:
    csv_path = data_dir / f"{ticker}.csv"
    existing, last_date = _read_existing(csv_path)

    if last_date is not None and last_date >= today:
        return f"last_date={last_date}, today={today} → Skipped", False

    start = bootstrap_start_date if last_date is None else (last_date + timedelta(days=1))
    yahoo_symbol = YAHOO_SYMBOLS.get(ticker, ticker)
    fetched = _download_prices(yahoo_symbol, start.isoformat(), (today + timedelta(days=1)).isoformat())

    if fetched.empty:
        last_repr = "None" if last_date is None else str(last_date)
        return f"last_date={last_repr}, today={today} → Skipped (no new data)", False

    fetched["Date"] = pd.to_datetime(fetched["Date"], errors="coerce").dt.date.astype(str)
    if last_date is not None:
        fetched = fetched[pd.to_datetime(fetched["Date"]).dt.date > last_date]
    fetched = fetched[pd.to_datetime(fetched["Date"]).dt.date <= today]

    if fetched.empty:
        last_repr = "None" if last_date is None else str(last_date)
        return f"last_date={last_repr}, today={today} → Skipped (already up to date)", False

    merged = pd.concat([existing, fetched], ignore_index=True)
    merged = merged.drop_duplicates(subset=["Date"], keep="last").sort_values("Date")
    merged.to_csv(csv_path, index=False)

    last_repr = "None" if last_date is None else str(last_date)
    return f"last_date={last_repr}, today={today} → Updated", True


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch latest Yahoo close price data for tracked tickers")
    parser.add_argument("--data-dir", default="./data", help="Directory containing ticker CSV files")
    parser.add_argument("--tickers", nargs="*", default=TICKERS, help="Ticker list to process")
    parser.add_argument(
        "--bootstrap-start-date",
        default="2020-01-01",
        type=_parse_iso_date,
        help="Start date used when a ticker CSV does not exist (YYYY-MM-DD)",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    today = date.today()
    total = len(args.tickers)
    updated = 0
    skipped = 0
    errors = 0

    for ticker in args.tickers:
        timestamp = datetime.now().strftime("%H:%M:%S")
        try:
            message, did_update = _upsert_ticker(
                data_dir,
                ticker,
                today,
                args.bootstrap_start_date,
            )
            if did_update:
                updated += 1
            else:
                skipped += 1
            print(f"[{timestamp}] Fetching {ticker}: {message}")
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"[{timestamp}] Fetching {ticker}: last_date=unknown, today={today} → Error: {exc}")

    print()
    print("Summary")
    print(f"- Total tickers processed: {total}")
    print(f"- Updated: {updated}")
    print(f"- Skipped: {skipped}")
    print(f"- Errors: {errors}")
    if errors:
        print(f"⚠️ Updated {updated}/{total} ({errors} errors)")
    else:
        print(f"✅ Updated {updated}/{total} tickers")


if __name__ == "__main__":
    main()
