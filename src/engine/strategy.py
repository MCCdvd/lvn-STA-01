from __future__ import annotations

from dataclasses import dataclass

from src.engine.signals import StrategyParams


@dataclass(frozen=True)
class LVNStrategy:
    params: StrategyParams

    @classmethod
    def from_config(cls, cfg: object) -> "LVNStrategy":
        params = StrategyParams(
            window_profile=cfg.window_profile,
            price_tolerance=cfg.price_tolerance,
            lvn_threshold=cfg.lvn_threshold,
            bin_step=cfg.bin_step,
            min_profile_levels=cfg.min_profile_levels,
            rsi_period=cfg.rsi_period,
            rsi_long_max=cfg.rsi_long_max,
            rsi_short_min=cfg.rsi_short_min,
        )
        return cls(params=params)
