from src.engine.signals import StrategyParams, get_lvn_nodes, signal_for_index
from src.data.loader import load_ticker_data


def safe_read_csv(file_path: str):
    from pathlib import Path

    try:
        return load_ticker_data(Path(file_path).parent, Path(file_path).stem)
    except Exception:  # noqa: BLE001
        return None


__all__ = ["StrategyParams", "signal_for_index", "get_lvn_nodes", "safe_read_csv"]
