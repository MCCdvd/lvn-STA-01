from __future__ import annotations

from pathlib import Path

import pandas as pd


def generate_dashboard(summary_global: pd.DataFrame, summary_by_ticker: pd.DataFrame, output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    html = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>LVN Dashboard</title></head>
<body>
<h1>LVN Dashboard</h1>
<h2>Global</h2>
{summary_global.to_html(index=False)}
<h2>By Ticker</h2>
{summary_by_ticker.to_html(index=False)}
</body></html>
"""
    output_file.write_text(html, encoding="utf-8")
