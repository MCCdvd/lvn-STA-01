from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import pandas as pd


def _row_to_payload(row: pd.Series) -> Dict:
    return {
        "ticker": str(row["ticker"]),
        "parameters": {
            "window_profile": int(row["window_profile"]),
            "price_tolerance": float(row["price_tolerance"]),
            "lvn_threshold": float(row["lvn_threshold"]),
        },
        "metrics": {
            "total_pnl": float(row.get("total_pnl", 0.0)),
            "win_rate": float(row.get("overall_win_rate", row.get("win_rate", 0.0))),
            "profit_factor": float(row.get("profit_factor", 0.0)),
            "trade_count": int(row.get("trade_count", row.get("total_trades", 0))),
            "max_drawdown": float(row.get("max_drawdown", 0.0)),
        },
    }


def generate_optimized_params(input_path: str, output_path: str) -> Path:
    source = Path(input_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()

    df = pd.read_csv(source)
    required_columns = {"ticker", "window_profile", "price_tolerance", "lvn_threshold"}
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required columns in {source}: {missing}")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(source),
        "ticker_count": int(len(df)),
        "tickers": {str(row["ticker"]): _row_to_payload(row) for _, row in df.iterrows()},
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate optimized parameters JSON from optimizer CSV output")
    parser.add_argument("--input", required=True, help="Path to best_params_all_tickers.csv")
    parser.add_argument("--output", default="optimized_params.json", help="Path to optimized JSON output")
    args = parser.parse_args()

    output_path = generate_optimized_params(args.input, args.output)
    print(f"Optimized parameters JSON generated: {output_path}")


if __name__ == "__main__":
    main()
