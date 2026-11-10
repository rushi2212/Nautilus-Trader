"""NautilusTrader integration boundary for the assignment.

This file intentionally does not connect or submit orders. Complete this adapter
once Testnet credentials, current NautilusTrader APIs, and a reviewable risk plan
are available. Keep all order submission out of the dashboard API.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class StraddleRisk:
    stop_loss_fraction: float = 0.01
    take_profit_fraction: float = 0.02


def exit_signal(entry_premium: float, call_ask: float, put_ask: float, quantity: float, risk: StraddleRisk) -> str | None:
    """Return a paper signal from the two ask-side buyback quotes."""
    if min(entry_premium, call_ask, put_ask, quantity) <= 0:
        return None
    buyback = (call_ask + put_ask) * quantity
    if buyback >= entry_premium * (1 + risk.stop_loss_fraction):
        return "stop_loss"
    if buyback <= entry_premium * (1 - risk.take_profit_fraction):
        return "take_profit"
    return None

