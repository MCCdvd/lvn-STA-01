from __future__ import annotations

import json
from pathlib import Path

from src.backtest.results import BacktestResult


def write_json_report(result: BacktestResult, output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary_global": result.summary_global.to_dict(orient="records"),
        "summary_by_ticker": result.summary_by_ticker.to_dict(orient="records"),
        "trades": result.trades.to_dict(orient="records"),
    }
    output_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_html_report(result: BacktestResult, output_file: Path, title: str = "LVN Backtest Report") -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    html = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>{title}</title></head>
<body>
  <h1>{title}</h1>
  <h2>Global Summary</h2>
  {result.summary_global.to_html(index=False, escape=True)}
  <h2>Summary by Ticker</h2>
  {result.summary_by_ticker.to_html(index=False, escape=True)}
  <h2>Trades (first 100)</h2>
  {result.trades.head(100).to_html(index=False, escape=True)}
</body></html>
"""
    output_file.write_text(html, encoding="utf-8")
