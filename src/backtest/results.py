from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class BacktestResult:
    trades: pd.DataFrame
    summary_by_ticker: pd.DataFrame
    summary_global: pd.DataFrame

    def to_csv(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        self.trades.to_csv(output_dir / "trades.csv", index=False)
        self.summary_by_ticker.to_csv(output_dir / "summary_by_ticker.csv", index=False)
        self.summary_global.to_csv(output_dir / "summary_global.csv", index=False)
