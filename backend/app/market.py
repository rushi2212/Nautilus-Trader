from datetime import datetime, timezone
from typing import Any

import httpx

from .config import get_settings

_last_snapshot: dict[str, Any] | None = None


def _expiry_ms(instrument: dict[str, Any]) -> int | None:
    try:
        return int(instrument["deliveryTime"])
    except (KeyError, TypeError, ValueError):
        return None


def _strike(instrument: dict[str, Any]) -> float | None:
    """Read strike from an explicit field or Bybit's option symbol.

    Bybit's V5 instrument response identifies option type and expiry but does
    not include a dedicated strike field. Its symbols encode strike as the
    third dash-separated segment, e.g. BTC-27MAR26-70000-P-USDT.
    """
    value = instrument.get("strike")
    if value is None:
        parts = str(instrument.get("symbol", "")).split("-")
        value = parts[2] if len(parts) >= 5 else None
    try:
        parsed = float(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


async def fetch_overview() -> dict[str, Any]:
    """Fetch public BTC spot and option tickers; no authentication is used."""
    global _last_snapshot
    base = get_settings().bybit_base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=12) as client:
        spot_response = await client.get(
            f"{base}/v5/market/tickers", params={"category": "spot", "symbol": "BTCUSDT"}
        )
        spot_response.raise_for_status()
        spot_data = spot_response.json()
        if spot_data.get("retCode") != 0:
            raise RuntimeError(spot_data.get("retMsg", "Bybit spot request failed"))
        spot_rows = spot_data.get("result", {}).get("list", [])
        if not spot_rows:
            raise RuntimeError("BTCUSDT spot ticker was not returned")
        reference = float(spot_rows[0]["lastPrice"])

        instruments_response = await client.get(
            f"{base}/v5/market/instruments-info",
            params={"category": "option", "baseCoin": "BTC", "limit": 1000},
        )
        instruments_response.raise_for_status()
        instruments_data = instruments_response.json()
        if instruments_data.get("retCode") != 0:
            raise RuntimeError(instruments_data.get("retMsg", "Bybit instruments request failed"))
        instruments = instruments_data.get("result", {}).get("list", [])
        cursor = instruments_data.get("result", {}).get("nextPageCursor")
        while cursor:
            page = await client.get(
                f"{base}/v5/market/instruments-info",
                params={"category": "option", "baseCoin": "BTC", "limit": 1000, "cursor": cursor},
            )
            page.raise_for_status()
            payload = page.json()
            if payload.get("retCode") != 0:
                break
            instruments.extend(payload.get("result", {}).get("list", []))
            cursor = payload.get("result", {}).get("nextPageCursor")

        tickers_response = await client.get(
            f"{base}/v5/market/tickers", params={"category": "option", "baseCoin": "BTC"}
        )
        tickers_response.raise_for_status()
        tickers_data = tickers_response.json()
        if tickers_data.get("retCode") != 0:
            raise RuntimeError(tickers_data.get("retMsg", "Bybit option ticker request failed"))
        tickers = {row.get("symbol"): row for row in tickers_data.get("result", {}).get("list", [])}

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    by_symbol = {item.get("symbol"): item for item in instruments}
    grouped: dict[tuple[int, float], dict[str, dict[str, Any]]] = {}
    for item in instruments:
        expiry = _expiry_ms(item)
        strike = _strike(item)
        if strike is None:
            continue
        kind = str(item.get("optionsType", "")).lower()
        leg = "call" if kind in ("call", "c") else "put" if kind in ("put", "p") else None
        if expiry is None or expiry <= now_ms or leg is None or item.get("status") != "Trading":
            continue
        grouped.setdefault((expiry, strike), {})[leg] = item

    pairs = [(key, legs) for key, legs in grouped.items() if "call" in legs and "put" in legs]
    if not pairs:
        raise RuntimeError("No future BTC expiry currently has a matched call and put pair")
    nearest_expiry = min(expiry for (expiry, _), _legs in pairs)
    expiry_pairs = [(strike, legs) for (expiry, strike), legs in pairs if expiry == nearest_expiry]
    strike, selected = min(expiry_pairs, key=lambda pair: abs(pair[0] - reference))

    def leg_view(leg: str) -> dict[str, Any]:
        item = selected[leg]
        ticker = tickers.get(item["symbol"], {})
        return {
            "symbol": item["symbol"],
            "side": leg,
            "strike": strike,
            "expiry": datetime.fromtimestamp(nearest_expiry / 1000, timezone.utc).isoformat(),
            "bid": _number(ticker.get("bid1Price")),
            "ask": _number(ticker.get("ask1Price")),
            "mark": _number(ticker.get("markPrice")),
            "iv": _number(ticker.get("markIv")),
        }

    _last_snapshot = {
        "reference_price": reference,
        "pair": {"call": leg_view("call"), "put": leg_view("put")},
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "bybit_public_api",
        "is_stale": False,
        "contracts_considered": len(by_symbol),
    }
    return _last_snapshot


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def cached_overview(error: str) -> dict[str, Any]:
    if _last_snapshot:
        return {**_last_snapshot, "is_stale": True, "warning": error}
    raise RuntimeError(error)

