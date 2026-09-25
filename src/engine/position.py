from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PositionState:
    ticker: str
    direction: str
    entry_date: str
    entry_price: float
    quantity: int
    initial_quantity: int
    invested_amount: float
    pnl_euro: float
    tp1_hit: bool = False
    current_stop: float = 0.0


def open_position(
    ticker: str,
    signal: str,
    date_str: str,
    price: float,
    investimento_per_trade: float,
    commissione_apertura: float,
) -> PositionState | None:
    if signal not in {"LONG", "SHORT"} or price <= 0:
        return None
    quantity = int(investimento_per_trade / price)
    if quantity <= 0:
        return None
    invested_amount = round(quantity * price, 2)
    return PositionState(
        ticker=ticker,
        direction=signal,
        entry_date=date_str,
        entry_price=float(price),
        quantity=quantity,
        initial_quantity=quantity,
        invested_amount=invested_amount,
        pnl_euro=-float(commissione_apertura),
    )


def close_trade(position: PositionState, exit_date: str, exit_price: float, exit_reason: str, commissione_chiusura: float) -> dict[str, str | float | int]:
    pnl_move = (
        (exit_price - position.entry_price) * position.quantity
        if position.direction == "LONG"
        else (position.entry_price - exit_price) * position.quantity
    )
    realized_pnl = position.pnl_euro + pnl_move - float(commissione_chiusura)
    return {
        "ticker": position.ticker,
        "direction": position.direction,
        "entry_date": position.entry_date,
        "exit_date": exit_date,
        "entry_price": round(position.entry_price, 4),
        "exit_price": round(float(exit_price), 4),
        "quantity": int(position.initial_quantity),
        "realized_pnl": round(float(realized_pnl), 2),
        "return_pct": round((float(realized_pnl) / position.invested_amount) * 100, 4) if position.invested_amount else 0.0,
        "exit_reason": exit_reason,
    }
