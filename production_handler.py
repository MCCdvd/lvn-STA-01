from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


DEFAULT_OPTIMIZED_PARAMS_PATH = Path(__file__).resolve().with_name("optimized_params.json")


def _normalize_ticker(ticker: str) -> str:
    return str(ticker).strip().upper()


@dataclass(frozen=True)
class OptimizationMetrics:
    total_pnl: float
    win_rate: float
    profit_factor: float
    trade_count: int
    max_drawdown: float


@dataclass(frozen=True)
class OptimizedParams:
    ticker: str
    window_profile: int
    price_tolerance: float
    lvn_threshold: float
    metrics: OptimizationMetrics


class OptimizedParamsLoader:
    _instances: Dict[Path, "OptimizedParamsLoader"] = {}

    def __init__(self, json_path: Path):
        self.json_path = json_path
        self.file_found = False
        self.load_error: Optional[str] = None
        self.generated_at: Optional[str] = None
        self.source_file: Optional[str] = None
        self._params_by_ticker: Dict[str, OptimizedParams] = {}
        self._load()

    @classmethod
    def get_instance(cls, json_path: Optional[str] = None, force_reload: bool = False) -> "OptimizedParamsLoader":
        resolved_path = Path(json_path).expanduser().resolve() if json_path else DEFAULT_OPTIMIZED_PARAMS_PATH.resolve()
        if force_reload or resolved_path not in cls._instances:
            cls._instances[resolved_path] = cls(resolved_path)
        return cls._instances[resolved_path]

    def _load(self) -> None:
        if not self.json_path.exists():
            return

        self.file_found = True
        try:
            raw_payload = json.loads(self.json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self.load_error = f"Invalid JSON in {self.json_path}"
            return
        if not isinstance(raw_payload, dict):
            self.load_error = f"Invalid payload in {self.json_path}"
            return

        self.generated_at = raw_payload.get("generated_at")
        self.source_file = raw_payload.get("source_file")

        tickers = raw_payload.get("tickers", {})
        if not isinstance(tickers, dict):
            self.load_error = f"Invalid tickers payload in {self.json_path}"
            return
        self._params_by_ticker = {}
        for ticker, data in tickers.items():
            if not isinstance(data, dict):
                continue
            parameters = data.get("parameters", {})
            if not isinstance(parameters, dict):
                continue
            if not {"window_profile", "price_tolerance", "lvn_threshold"}.issubset(parameters):
                continue
            metrics = data.get("metrics", {})
            if not isinstance(metrics, dict):
                metrics = {}
            normalized_ticker = _normalize_ticker(ticker)
            self._params_by_ticker[normalized_ticker] = OptimizedParams(
                ticker=normalized_ticker,
                window_profile=int(parameters["window_profile"]),
                price_tolerance=float(parameters["price_tolerance"]),
                lvn_threshold=float(parameters["lvn_threshold"]),
                metrics=OptimizationMetrics(
                    total_pnl=float(metrics.get("total_pnl", 0.0)),
                    win_rate=float(metrics.get("win_rate", 0.0)),
                    profit_factor=float(metrics.get("profit_factor", 0.0)),
                    trade_count=int(metrics.get("trade_count", 0)),
                    max_drawdown=float(metrics.get("max_drawdown", 0.0)),
                ),
            )

    def has_ticker(self, ticker: str) -> bool:
        return _normalize_ticker(ticker) in self._params_by_ticker

    def get_ticker_params(self, ticker: str) -> Optional[OptimizedParams]:
        return self._params_by_ticker.get(_normalize_ticker(ticker))

    def get_ticker_statistics(self, ticker: str) -> Optional[OptimizationMetrics]:
        params = self.get_ticker_params(ticker)
        return params.metrics if params else None

    def get_available_tickers(self) -> list[str]:
        return sorted(self._params_by_ticker)


def get_optimized_params_loader(json_path: Optional[str] = None, force_reload: bool = False) -> OptimizedParamsLoader:
    return OptimizedParamsLoader.get_instance(json_path=json_path, force_reload=force_reload)
