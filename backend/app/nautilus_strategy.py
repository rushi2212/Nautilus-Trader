"""NautilusTrader testnet strategy for the BTC ATM short straddle assignment.

Execution is intentionally isolated from FastAPI: start this file explicitly to
connect to Bybit Testnet and place orders. The Bybit adapter has no native
conditional orders/OCO for options, so the combined-premium exit trigger is
implemented in the strategy; Nautilus handles orders, fills, positions and the
market-exit workflow.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from nautilus_trader.adapters.bybit import BybitEnvironment, BybitProductType

from nautilus_trader.model import (
    ClientId,
    CryptoOption,
    InstrumentId,
    OptionKind,
    OptionSeriesId,
    OrderSide,
    QuoteTick,
    StrikeRange,
    TimeInForce,
    Venue,
)
from nautilus_trader.trading import Strategy
from nautilus_trader.config import StrategyConfig


BYBIT = ClientId("BYBIT")
BYBIT_VENUE = Venue("BYBIT")
STATE_KEY = "btc_atm_straddle"
MAX_QUOTE_AGE_NS = 15_000_000_000
ENTRY_TIMEOUT_NS = 30_000_000_000
CHAIN_RANGE = StrikeRange.atm_relative(strikes_above=3, strikes_below=3)


class BtcAtmShortStraddleConfig(StrategyConfig):
    """Nautilus v2 strategy config with the assignment's risk parameters."""

    def __init__(
        self,
        *,
        contracts: float = 1.0,
        stop_loss_fraction: float = 0.01,
        take_profit_fraction: float = 0.02,
        **_kwargs: Any,
    ) -> None:
        # Nautilus v2 reads its base fields in StrategyConfig.__new__.
        super().__init__()
        self.contracts = contracts
        self.stop_loss_fraction = stop_loss_fraction
        self.take_profit_fraction = take_profit_fraction


class BtcAtmShortStraddle(Strategy):
    """Sell one matched ATM BTC call/put and monitor Level 2 exits."""

    def __init__(self, config: BtcAtmShortStraddleConfig) -> None:
        if config.contracts <= 0:
            raise ValueError("contracts must be greater than zero")
        if not 0 < config.stop_loss_fraction < 1 or not 0 < config.take_profit_fraction < 1:
            raise ValueError("risk fractions must be between zero and one")

        super().__init__(config=config)
        self.contracts = config.contracts
        self.stop_loss_fraction = config.stop_loss_fraction
        self.take_profit_fraction = config.take_profit_fraction

        self._phase = "STARTING"
        self._traded = False
        self._series_id: OptionSeriesId | None = None
        self._call_id: InstrumentId | None = None
        self._put_id: InstrumentId | None = None
        self._call_qty = 0.0
        self._put_qty = 0.0
        self._entry_order_ids: list[Any] = []
        self._entry_premium: float | None = None
        self._asks: dict[InstrumentId, tuple[float, int]] = {}
        self._loaded_pair: tuple[str, str] | None = None

    def on_load(self, state: dict[str, bytes]) -> None:
        raw = state.get(STATE_KEY)
        if not raw:
            return
        saved = json.loads(raw.decode("utf-8"))
        self._traded = bool(saved.get("traded", False))
        self._entry_premium = saved.get("entry_premium")
        ids = saved.get("instrument_ids")
        if ids and len(ids) == 2:
            self._loaded_pair = (ids[0], ids[1])
        self.log.info("Restored straddle state from Nautilus cache backing")

    def on_save(self) -> dict[str, bytes]:
        payload = {
            "traded": self._traded,
            "entry_premium": self._entry_premium,
            "instrument_ids": [str(self._call_id), str(self._put_id)]
            if self._call_id and self._put_id
            else None,
        }
        return {STATE_KEY: json.dumps(payload).encode("utf-8")}

    def on_start(self) -> None:
        instruments = [
            inst
            for inst in self.cache.instruments(BYBIT_VENUE)
            if isinstance(inst, CryptoOption)
            and inst.underlying.code == "BTC"
        ]
        now_ns = self.clock.timestamp_ns()

        # Reconciliation runs before this hook. Resume this strategy's own open
        # pair instead of placing duplicate entry orders after a restart.
        open_positions = [
            position
            for position in self.cache.positions_open(venue=BYBIT_VENUE)
            if position.is_open
            and position.strategy_id == self.id
            and isinstance(self.cache.instrument(position.instrument_id), CryptoOption)
        ]
        if open_positions:
            if not self._adopt_open_pair(open_positions, instruments):
                self.log.error("Found non-matching open strategy positions; refusing new orders")
                self.stop()
                return
            self._phase = "MANAGING"
            self._traded = True
            self._subscribe_pair_quotes()
            self.log.info("Resumed reconciled short BTC straddle; risk monitoring is active")
            return

        # Never trade over an account position or unresolved order that was not
        # restored as belonging to this strategy.
        other_btc_positions = [
            position
            for position in self.cache.positions_open(venue=BYBIT_VENUE)
            if position.is_open
            and isinstance(self.cache.instrument(position.instrument_id), CryptoOption)
            and self.cache.instrument(position.instrument_id).underlying.code == "BTC"
        ]
        if other_btc_positions:
            self.log.error("Unowned BTC option positions exist on the account; refusing to trade")
            self.stop()
            return

        other_btc_orders = [
            order
            for order in self.cache.orders_open(venue=BYBIT_VENUE)
            if isinstance(self.cache.instrument(order.instrument_id), CryptoOption)
            and self.cache.instrument(order.instrument_id).underlying.code == "BTC"
        ]
        if other_btc_orders:
            self.log.error("Unresolved BTC option orders exist on the account; refusing to trade")
            self.stop()
            return

        if self._traded:
            self._phase = "DONE"
            self.log.info("This strategy has already traded; start a new strategy ID to run again")
            self.stop()
            return

        groups: dict[tuple[int, str], dict[str, set[float]]] = defaultdict(
            lambda: {"call": set(), "put": set()},
        )
        for inst in instruments:
            if inst.expiration_ns <= now_ns:
                continue
            side = "call" if inst.option_kind == OptionKind.CALL else "put"
            groups[(inst.expiration_ns, inst.settlement_currency.code)][side].add(
                inst.strike_price.as_double(),
            )

        eligible = [
            (expiry_ns, settlement)
            for (expiry_ns, settlement), sides in groups.items()
            if sides["call"] & sides["put"]
        ]
        if not eligible:
            self.log.error("No future BTC option expiry has a matched call/put strike")
            self.stop()
            return

        expiry_ns, settlement = min(eligible, key=lambda item: item[0])
        self._series_id = OptionSeriesId.from_expiry(
            BYBIT_VENUE,
            "BTC",
            settlement,
            expiry_ns,
        )
        self._phase = "SELECTING"
        self.subscribe_option_chain(
            self._series_id,
            CHAIN_RANGE,
            snapshot_interval_ms=1_000,
            client_id=BYBIT,
        )
        self.log.info(
            f"Subscribed to BTC option chain for nearest matched expiry {expiry_ns}; waiting for Bybit ATM reference",
        )

    def _adopt_open_pair(self, positions: list[Any], instruments: list[CryptoOption]) -> bool:
        by_id = {inst.id: inst for inst in instruments}
        legs: dict[str, tuple[Any, CryptoOption]] = {}
        for position in positions:
            inst = by_id.get(position.instrument_id)
            if inst is None or not position.is_short:
                return False
            side = "call" if inst.option_kind == OptionKind.CALL else "put"
            if side in legs:
                return False
            legs[side] = (position, inst)
        if set(legs) != {"call", "put"}:
            return False
        call_pos, call_inst = legs["call"]
        put_pos, put_inst = legs["put"]
        if self._loaded_pair and self._loaded_pair != (str(call_inst.id), str(put_inst.id)):
            self.log.error("Reconciled positions do not match the pair saved by this strategy")
            return False
        if (
            call_inst.expiration_ns != put_inst.expiration_ns
            or call_inst.strike_price != put_inst.strike_price
            or call_pos.quantity != put_pos.quantity
        ):
            return False
        self._call_id, self._put_id = call_inst.id, put_inst.id
        self._call_qty = call_pos.quantity.as_double()
        self._put_qty = put_pos.quantity.as_double()
        if not self._entry_premium:
            call_avg = float(call_pos.avg_px_open or 0)
            put_avg = float(put_pos.avg_px_open or 0)
            if call_avg <= 0 or put_avg <= 0:
                return False
            self._entry_premium = call_avg * self._call_qty + put_avg * self._put_qty
        return self._entry_premium > 0

    def on_option_chain(self, chain: Any) -> None:
        if self._phase != "SELECTING" or self._series_id is None:
            return
        atm = chain.atm_strike
        if atm is None:
            return

        matched = [
            strike
            for strike in chain.strikes()
            if chain.get_call_quote(strike) is not None
            and chain.get_put_quote(strike) is not None
        ]
        if not matched:
            return
        strike = min(matched, key=lambda value: abs(value.as_double() - atm.as_double()))
        call_quote = chain.get_call_quote(strike)
        put_quote = chain.get_put_quote(strike)
        if call_quote is None or put_quote is None:
            return
        self._call_id = call_quote.instrument_id
        self._put_id = put_quote.instrument_id
        call_inst = self.cache.instrument(self._call_id)
        put_inst = self.cache.instrument(self._put_id)
        if not isinstance(call_inst, CryptoOption) or not isinstance(put_inst, CryptoOption):
            self._begin_exit("Selected contracts are not valid Bybit CryptoOption instruments")
            return
        self._call_qty = call_inst.make_qty(self.contracts).as_double()
        self._put_qty = put_inst.make_qty(self.contracts).as_double()
        if self._call_qty <= 0 or self._put_qty <= 0 or abs(self._call_qty - self._put_qty) > 1e-12:
            self._begin_exit("Bybit option lot sizes do not allow matched quantities")
            return

        self._phase = "WAITING_QUOTES"
        self.unsubscribe_option_chain(self._series_id, client_id=BYBIT)
        self.subscribe_quotes(self._call_id, client_id=BYBIT)
        self.subscribe_quotes(self._put_id, client_id=BYBIT)
        self.log.info(
            f"Selected ATM pair strike={strike} expiry={self._series_id}; "
            f"call={self._call_id}, put={self._put_id}, qty={self._call_qty} per leg",
        )
        self._update_quote(call_quote)
        self._update_quote(put_quote)
        self._maybe_submit_entry()

    def on_quote(self, tick: QuoteTick) -> None:
        if tick.instrument_id not in (self._call_id, self._put_id):
            return
        self._update_quote(tick)
        if self._phase == "WAITING_QUOTES":
            self._maybe_submit_entry()
            return
        if self._phase != "MANAGING" or self._entry_premium is None:
            return

        now_ns = self.clock.timestamp_ns()
        call = self._asks.get(self._call_id)
        put = self._asks.get(self._put_id)
        if not call or not put:
            return
        if now_ns - call[1] > MAX_QUOTE_AGE_NS or now_ns - put[1] > MAX_QUOTE_AGE_NS:
            return
        if call[0] <= 0 or put[0] <= 0:
            return

        buyback = call[0] * self._call_qty + put[0] * self._put_qty
        if buyback >= self._entry_premium * (1 + self.stop_loss_fraction):
            self._begin_exit(f"stop loss: buyback {buyback:.8f} >= entry × 1.01")
        elif buyback <= self._entry_premium * (1 - self.take_profit_fraction):
            self._begin_exit(f"take profit: buyback {buyback:.8f} <= entry × 0.98")

    def _update_quote(self, tick: QuoteTick) -> None:
        self._asks[tick.instrument_id] = (tick.ask_price.as_double(), tick.ts_event)

    def _maybe_submit_entry(self) -> None:
        if self._phase != "WAITING_QUOTES" or not self._call_id or not self._put_id:
            return
        call = self._asks.get(self._call_id)
        put = self._asks.get(self._put_id)
        if not call or not put:
            return
        now_ns = self.clock.timestamp_ns()
        if now_ns - call[1] > MAX_QUOTE_AGE_NS or now_ns - put[1] > MAX_QUOTE_AGE_NS:
            return
        if call[0] <= 0 or put[0] <= 0:
            return

        call_order = self.order_factory.market(
            self._call_id,
            OrderSide.SELL,
            self.cache.instrument(self._call_id).make_qty(self._call_qty),
            time_in_force=TimeInForce.IOC,
        )
        put_order = self.order_factory.market(
            self._put_id,
            OrderSide.SELL,
            self.cache.instrument(self._put_id).make_qty(self._put_qty),
            time_in_force=TimeInForce.IOC,
        )
        self._entry_order_ids = [call_order.client_order_id, put_order.client_order_id]
        self._phase = "ENTERING"
        self._traded = True
        self.clock.set_time_alert_ns(
            "straddle-entry-timeout",
            now_ns + ENTRY_TIMEOUT_NS,
        )
        self.log.info("Submitting Bybit Testnet market SELL for call and put")
        try:
            self.submit_order(call_order, client_id=BYBIT)
            self.submit_order(put_order, client_id=BYBIT)
        except Exception as exc:
            self._begin_exit(f"entry submission failed: {exc}")

    def on_order_accepted(self, event: Any) -> None:
        if event.client_order_id in self._entry_order_ids:
            self.log.info(f"Entry order accepted: {event.client_order_id}")

    def on_order_filled(self, event: Any) -> None:
        if event.client_order_id not in self._entry_order_ids or self._phase != "ENTERING":
            return
        self.log.info(
            f"Entry fill: {event.instrument_id} {event.last_qty} @ {event.last_px}; trade={event.trade_id}",
        )
        orders = [self.cache.order(order_id) for order_id in self._entry_order_ids]
        if any(order is None for order in orders):
            return
        fully_filled = all(
            order.filled_qty.as_double() >= order.quantity.as_double()
            for order in orders
        )
        if fully_filled:
            self.clock.cancel_timer("straddle-entry-timeout")
            self._entry_premium = sum(
                float(order.avg_px) * order.filled_qty.as_double()
                for order in orders
            )
            if self._entry_premium <= 0:
                self._begin_exit("Entry fills did not produce a valid premium")
                return
            self._phase = "MANAGING"
            self.log.info(
                f"Both legs filled; entry premium={self._entry_premium:.8f}; "
                f"stop={self._entry_premium * 1.01:.8f}; target={self._entry_premium * 0.98:.8f}",
            )
        elif any(
            order.is_closed
            and order.filled_qty.as_double() < order.quantity.as_double()
            for order in orders
        ):
            self._begin_exit("One entry leg closed before both legs were fully filled")

    def on_order_canceled(self, event: Any) -> None:
        if event.client_order_id in self._entry_order_ids and self._phase == "ENTERING":
            self._begin_exit("An entry leg was canceled before the pair completed")

    def on_order_rejected(self, event: Any) -> None:
        if event.client_order_id in self._entry_order_ids and self._phase == "ENTERING":
            self._begin_exit(f"Bybit rejected an entry leg: {event.reason}")

    def on_order_denied(self, event: Any) -> None:
        if event.client_order_id in self._entry_order_ids and self._phase == "ENTERING":
            self._begin_exit(f"Nautilus denied an entry leg: {event.reason}")

    def on_time_event(self, event: Any) -> None:
        if event.name == "straddle-entry-timeout" and self._phase == "ENTERING":
            self._begin_exit("Entry timeout: flattening any partial exposure")

    def _begin_exit(self, reason: str) -> None:
        if self._phase in {"EXITING", "DONE", "BLOCKED"} or self.is_exiting():
            return
        self._phase = "EXITING"
        self.log.warning(f"Starting Nautilus market exit: {reason}")
        self.market_exit()

    def on_market_exit(self) -> None:
        self.log.warning("Nautilus market exit: canceling active orders and closing strategy positions")

    def post_market_exit(self) -> None:
        self._phase = "DONE"
        remaining = [
            position
            for position in self.cache.positions_open(venue=BYBIT_VENUE)
            if position.is_open
            and position.strategy_id == self.id
            and position.instrument_id in (self._call_id, self._put_id)
        ]
        if remaining:
            self.log.error(
                f"Market exit finished with {len(remaining)} strategy position(s) still open; "
                "manual review is required",
            )
            return
        self.log.info("Market exit workflow completed; both strategy legs are flat and will not re-enter")

    def on_stop(self) -> None:
        self.clock.cancel_timer("straddle-entry-timeout")
        if self._series_id is not None:
            self.unsubscribe_option_chain(self._series_id, client_id=BYBIT)
        for instrument_id in (self._call_id, self._put_id):
            if instrument_id is not None:
                self.unsubscribe_quotes(instrument_id, client_id=BYBIT)

    def _subscribe_pair_quotes(self) -> None:
        if self._call_id is None or self._put_id is None:
            return
        self.subscribe_quotes(self._call_id, client_id=BYBIT)
        self.subscribe_quotes(self._put_id, client_id=BYBIT)
        self._phase = "MANAGING"





