from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from .constants import REQUIRED_DATA_COLUMNS


class ValidationError(ValueError):
    """Raised when user input or market data is invalid."""


def ensure_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValidationError(f"{name} must be positive, got {value}")


def ensure_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValidationError(f"{name} must be >= 0, got {value}")


def ensure_columns(df: pd.DataFrame, required: Iterable[str] = REQUIRED_DATA_COLUMNS) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValidationError(f"Missing required columns: {', '.join(missing)}")


def ensure_path(path: Path) -> None:
    if not path.exists():
        raise ValidationError(f"Path does not exist: {path}")
