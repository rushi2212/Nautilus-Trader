"""Explicit runner for the Bybit Testnet BTC ATM short-straddle strategy."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from nautilus_trader.adapters.bybit import (
    BybitDataClientConfig,
    BybitDataClientFactory,
    BybitEnvironment,
    BybitExecutionClientConfig,
    BybitExecutionClientFactory,
    BybitProductType,
)
from nautilus_trader.common import Environment
from nautilus_trader.config import LiveExecutionEngineConfig
from nautilus_trader.infrastructure import RedisCacheConfig
from nautilus_trader.live import LiveNode
from nautilus_trader.model import AccountId, StrategyId, TraderId

from app.nautilus_strategy import BtcAtmShortStraddle, BtcAtmShortStraddleConfig


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Set {name} in backend/.env before starting the strategy")
    return value


def main() -> None:
    api_key = required("BYBIT_TESTNET_API_KEY")
    api_secret = required("BYBIT_TESTNET_API_SECRET")
    account_id = required("BYBIT_TESTNET_ACCOUNT_ID")
    contracts = float(os.getenv("BYBIT_TESTNET_CONTRACTS", "1"))

    data_config = BybitDataClientConfig(
        product_types=[BybitProductType.OPTION],
        environment=BybitEnvironment.TESTNET,
    )
    exec_config = BybitExecutionClientConfig(
        product_types=[BybitProductType.OPTION],
        environment=BybitEnvironment.TESTNET,
        api_key=api_key,
        api_secret=api_secret,
        account_id=AccountId(account_id),
    )

    builder = (
        LiveNode.builder("BYBIT-BTC-STRADDLE", TraderId("STRADDLE-TESTNET"), Environment.LIVE)
        .add_data_client(None, BybitDataClientFactory(), data_config)
        .add_exec_client(None, BybitExecutionClientFactory(), exec_config)
        .with_reconciliation(True)
        .with_delay_post_stop_secs(5)
    )

    redis_host = os.getenv("NAUTILUS_REDIS_HOST", "").strip()
    if redis_host:
        redis = RedisCacheConfig(
            host=redis_host,
            port=int(os.getenv("NAUTILUS_REDIS_PORT", "6379")),
            username=os.getenv("NAUTILUS_REDIS_USERNAME") or None,
            password=os.getenv("NAUTILUS_REDIS_PASSWORD") or None,
            ssl=os.getenv("NAUTILUS_REDIS_SSL", "false").lower() == "true",
        )
        builder = (
            builder.with_cache_database_factory(redis)
            .with_exec_engine_config(
                LiveExecutionEngineConfig(snapshot_orders=True, snapshot_positions=True),
            )
            .with_load_state(True)
            .with_save_state(True)
        )
        print("Nautilus cache persistence enabled; startup reconciliation is enabled.")
    else:
        print(
            "WARNING: Redis cache persistence is not configured. Nautilus will reconcile "
            "venue positions, but a restart with an unowned BTC option position fails closed.",
        )

    node = builder.build()
    strategy_config = BtcAtmShortStraddleConfig(
        strategy_id=StrategyId("BTC-ATM-STRADDLE-STRD"),
        order_id_tag="STRD",
        manage_stop=True,
        market_exit_reduce_only=True,
        contracts=contracts,
        stop_loss_fraction=0.01,
        take_profit_fraction=0.02,
    )
    node.add_strategy(BtcAtmShortStraddle(config=strategy_config))
    print("Connecting to BYBIT TESTNET. This runner can submit real testnet orders.")
    try:
        node.run()
    finally:
        node.dispose()


if __name__ == "__main__":
    main()
