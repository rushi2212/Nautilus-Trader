# Nautilus BTC ATM Short Straddle

This project contains two separate parts:

- A React + FastAPI learning dashboard. It reads public Bybit market data, previews hypothetical P&L, and provides an optional Groq study assistant. It never places orders.
- An explicitly launched NautilusTrader strategy for Bybit **Testnet**. It selects the nearest matched BTC call/put pair around Bybit's ATM reference, submits a short straddle, tracks Nautilus order/position events, and applies the assignment's Level 2 stop and target.

The Testnet runner can submit orders to your Bybit Testnet account. Do not launch it until you have configured Testnet API credentials and understand the flow. It is not launched by the web app or Render deployment.

## Requirements

- Windows: Python 3.13 (the pinned NautilusTrader wheel is installed by `start.ps1`), Node.js 18+, and PowerShell.
- A Bybit **Testnet** account and API key with options trading permission to run the strategy.
- Optional: a Groq API key for Groq-powered chat. Without one, the dashboard has a local Q&A fallback.

## Run the dashboard

In PowerShell at the project root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start.ps1
```

Open `http://127.0.0.1:5173`. The script creates `backend/.env` from `.env.example`, installs dependencies, and starts the API and UI in separate PowerShell windows. Keep those windows open. The dashboard refreshes public market data automatically and is paper-only.

## Configure and launch the Testnet strategy

1. Copy `backend/.env.example` to `backend/.env` if it does not already exist.
2. Set `BYBIT_TESTNET_API_KEY`, `BYBIT_TESTNET_API_SECRET`, and `BYBIT_TESTNET_ACCOUNT_ID` to credentials for **Bybit Testnet**, not mainnet. Set `BYBIT_TESTNET_CONTRACTS` to the desired per-leg quantity (defaults to 1). Never commit `.env` or expose the credentials in the frontend.
3. In one PowerShell window at the project root, run `.start.ps1` if dependencies have not been installed.
4. In a second PowerShell window at the project root, explicitly launch:

   ```powershell
   .\run-strategy.ps1
   ```

The runner connects a Nautilus `LiveNode` to the Bybit OPTION data and execution clients in Testnet mode, enables startup reconciliation, attaches one strategy, then runs the node. **Launching this command can place Testnet orders.** Stop it with Ctrl+C when you intend to shut down the node.

### Strategy execution flow

1. Nautilus builds the Bybit data and execution clients. On startup, the live node connects and reconciles open orders and positions before strategy startup.
2. The strategy reads cached BTC option instruments, chooses the nearest future expiry with a shared call/put strike, and subscribes to that option chain. It uses the chain's Bybit ATM reference and selects the nearest strike where both legs have quotes.
3. It subscribes to both leg quotes and sends one market SELL IOC order per leg once the Nautilus cache has fresh quotes for both instruments. Nautilus delivers acknowledgements, fills, cancellations, rejections, and position state through the strategy callbacks and cache; the strategy does not maintain a duplicate quote store.
4. It begins Level 2 risk monitoring after both legs are fully filled. Entry premium is based on each filled order's average fill price and filled quantity. Buyback value uses each leg's current ask and the corresponding position quantity.
5. A combined buyback value at least 1% above entry triggers a stop; a value at least 2% below entry triggers the target. Bybit options do not provide the required combined-premium OCO order, so the strategy monitors quotes and uses Nautilus `market_exit()` to cancel working orders and close strategy positions. If entry is partial or a leg fails, it uses that same exit workflow to flatten any exposure and does not re-enter. A 30-second strategy deadline handles a missing/incomplete two-leg entry event sequence; it complements the adapter's request timeouts and startup reconciliation rather than duplicating order or position management.

### Stop and restart behavior

Nautilus owns the live node's start/stop and venue reconciliation lifecycle. The strategy cancels its timers and market-data subscriptions in `on_stop`; it does not invent another execution engine. When a Redis cache database is configured, the runner enables Nautilus order/position snapshots and strategy `on_save`/`on_load` state callbacks. After restart, venue reconciliation occurs before the strategy starts; it resumes monitoring a matching pair owned by its stable StrategyId, and fails closed on unrelated BTC option positions/orders. Without Redis, a process restart does not retain the strategy's saved state; unrelated open BTC option positions/orders cause the strategy to stop instead of adding exposure. A new entry after a completed trade requires a new StrategyId/state namespace.

For persistence, provision a Redis-compatible service and set `NAUTILUS_REDIS_HOST`, `NAUTILUS_REDIS_PORT`, and optional username/password/TLS settings in `backend/.env`. Persistence is for Nautilus cache and saved strategy state; it does not turn the dashboard into an execution interface.

## Dashboard behavior

- The UI fetches public BTC prices and options on page load, every 15 seconds while visible, and when the tab becomes active. The refresh control requests an immediate update.
- The dashboard's paper preview uses its displayed leg prices and lets you evaluate P&L and Level 2 thresholds without connecting to the strategy runner.
- The FastAPI chatbot uses Groq only when `GROQ_API_KEY` is configured. `GROQ_MODEL` defaults to `openai/gpt-oss-120b`; use a model available to your account.
- `/api/health` reports dashboard status. `/api/market/overview`, `/api/strategy/preview`, and `/api/chat` serve the dashboard.

## Render

The included Docker/Render deployment serves the dashboard and FastAPI only. It does not include or start `run-strategy.py`, and should not be used to run the trading process. Deploy with the included `render.yaml`; add `GROQ_API_KEY` in Render if desired. Keep all Bybit Testnet secrets local and use the explicit local runner for the assignment demonstration.

## Relevant files

- `backend/app/nautilus_strategy.py` — Nautilus strategy and assignment logic.
- `backend/run-strategy.py` — Bybit Testnet live-node configuration and runner.
- `run-strategy.ps1` — explicit Windows launcher.
- `backend/app/market.py` and `backend/app/main.py` — public market dashboard and paper/chat APIs.
- `backend/.env.example` — environment variable template; copy it to `.env` and keep secrets private.

## Official references

- [NautilusTrader Bybit integration](https://nautilustrader.io/docs/latest/integrations/bybit/)
- [Official Bybit option-chain example](https://github.com/nautechsystems/nautilus_trader/blob/develop/examples/live/bybit/bybit_option_chain.py)
- [NautilusTrader strategy lifecycle](https://nautilustrader.io/docs/latest/concepts/strategies/)
- [NautilusTrader live configuration and persistence](https://nautilustrader.io/docs/latest/how_to/configure_live_trading/)
