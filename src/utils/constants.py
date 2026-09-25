from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output"
DEFAULT_DATA_DIR = REPO_ROOT / "data"
LEGACY_DATA_DIR = REPO_ROOT
REQUIRED_DATA_COLUMNS = ("Date", "Close", "Volume")
TRADE_COLUMNS = (
    "ticker",
    "direction",
    "entry_date",
    "exit_date",
    "entry_price",
    "exit_price",
    "quantity",
    "realized_pnl",
    "return_pct",
    "exit_reason",
)
