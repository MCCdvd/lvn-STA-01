from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from src.utils.constants import DEFAULT_DATA_DIR, DEFAULT_OUTPUT_DIR, LEGACY_DATA_DIR
from src.utils.validators import ensure_non_negative, ensure_positive

Profile = Literal["dev", "test", "prod"]


@dataclass(frozen=True)
class RuntimeConfig:
    data_dir: Path
    output_dir: Path


@dataclass(frozen=True)
class StrategyConfig:
    investimento_per_trade: float = 10_000.0
    commissione_apertura: float = 10.0
    commissione_chiusura: float = 10.0
    window_profile: int = 25
    price_tolerance: float = 0.05
    lvn_threshold: float = 0.50
    bin_step: float = 0.05
    min_profile_levels: int = 5
    rsi_period: int = 14
    rsi_long_max: float = 35.0
    rsi_short_min: float = 65.0

    def validate(self) -> None:
        ensure_positive("investimento_per_trade", self.investimento_per_trade)
        ensure_non_negative("commissione_apertura", self.commissione_apertura)
        ensure_non_negative("commissione_chiusura", self.commissione_chiusura)
        ensure_positive("window_profile", self.window_profile)
        ensure_positive("price_tolerance", self.price_tolerance)
        ensure_positive("lvn_threshold", self.lvn_threshold)
        ensure_positive("bin_step", self.bin_step)
        ensure_positive("min_profile_levels", self.min_profile_levels)
        ensure_positive("rsi_period", self.rsi_period)


@dataclass(frozen=True)
class GridConfig:
    window_profiles: list[int] = field(default_factory=lambda: [12, 15, 18, 20])
    price_tolerances: list[float] = field(default_factory=lambda: [0.15, 0.18, 0.20, 0.22, 0.25])
    lvn_thresholds: list[float] = field(default_factory=lambda: [0.25, 0.30, 0.35, 0.40])
    top_n: int = 20


@dataclass(frozen=True)
class AppConfig:
    profile: Profile
    runtime: RuntimeConfig
    strategy: StrategyConfig
    grid: GridConfig = field(default_factory=GridConfig)


def _data_dir_from_env() -> Path:
    env_dir = os.getenv("LVN_DATA_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    if DEFAULT_DATA_DIR.exists() and any(DEFAULT_DATA_DIR.glob("*.csv")):
        return DEFAULT_DATA_DIR
    return LEGACY_DATA_DIR


def load_settings(profile: Profile | None = None) -> AppConfig:
    active = profile or os.getenv("LVN_PROFILE", "dev")
    if active not in {"dev", "test", "prod"}:
        raise ValueError(f"Invalid LVN_PROFILE '{active}'. Use dev/test/prod.")

    output_dir = Path(os.getenv("LVN_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))).expanduser().resolve()
    cfg = AppConfig(
        profile=active,
        runtime=RuntimeConfig(
            data_dir=_data_dir_from_env(),
            output_dir=output_dir,
        ),
        strategy=StrategyConfig(),
    )
    cfg.strategy.validate()
    return cfg


SETTINGS = load_settings()
