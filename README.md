# Nautilus BTC Straddle Lab

A React + FastAPI learning dashboard for the BTC ATM short straddle assignment. The app defaults to **paper mode**. The dashboard and strategy logic are educational and do not submit real orders. Groq chat is optional and requires a server-side `GROQ_API_KEY`.

## What is included

- React/Vite dashboard with a responsive BTC options strategy workspace.
- FastAPI backend with health, market-data, strategy-preview, and chat endpoints.
- Public Bybit V5 option instrument/ticker snapshots for BTC options (no credentials needed for market data).
- ATM strike and matched call/put selection for the nearest shared expiry.
- Paper short-straddle preview and combined ask-side buyback P&L calculation.
- Optional 1% stop-loss / 2% take-profit threshold monitor in paper mode.
- Groq chatbot grounded in the assignment, with a local fallback when no API key is configured.
- NautilusTrader strategy integration notes and a deliberately gated adapter skeleton.

## Run locally

Requirements: Node.js 18+, Python 3.10+.

1. Open PowerShell in the project folder and run:

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\start.ps1
   ```

   The script creates the Python environment if needed, installs backend and frontend dependencies, starts both services in separate PowerShell windows, and opens the dashboard. Keep those two service windows open while using the app. First startup may take a few minutes.

2. The script creates `backend/.env` from the example if it does not exist. Add your Groq key to `backend/.env` to enable Groq answers; the key stays on the backend. Restart the API window after changing `.env`.

To start services manually instead, use the commands below in two separate terminals.

API:

   ```powershell
   cd backend
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```

UI:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

Open `http://127.0.0.1:5173`. The API docs are at `http://127.0.0.1:8000/docs`.

## Using the dashboard

- The dashboard fetches a fresh BTC reference and option pair on page load, every 15 seconds while the tab is visible, and when you return to the tab. Use the refresh icon for an immediate update. The timestamp under the chart confirms each successful refresh.
- A red banner means the API or Bybit request failed; an amber banner means cached data is being shown. Keep the API PowerShell window open to see the detailed server error.
- The call and put rows show the selected ATM pair. Contract quantity changes the paper premium calculation. Enable risk management to display the 1% stop-loss and 2% take-profit paper signals.
- Select “Preview paper position” to see the two hypothetical legs. The app never sends orders.
- Open “Straddle guide” to ask questions. Without a Groq key, its built-in local answers still work.

If the page says “Market data API is offline,” confirm both PowerShell service windows remain open. If the API is running but quotes fail, check internet access and the Bybit API host in `backend/.env`. If the chatbot returns a Groq model error, choose a model enabled for your Groq account in `GROQ_MODEL`, then restart the API.

## Deploy to Render

This project is configured as one Docker web service: Render builds the React frontend into the image, and FastAPI serves the UI and API from the same URL. Render uses the included `render.yaml` Blueprint and checks `/api/health` before routing traffic.

1. Push the project folder to a GitHub, GitLab, or Bitbucket repository. Keep `backend/.env` out of Git; `.gitignore` excludes it.
2. In Render, choose **New + → Blueprint**, connect that repository, and select the branch that contains `render.yaml`.
3. Review the `nautilus-btc-straddle-lab` web service. Add `GROQ_API_KEY` in Render's environment settings if you want Groq responses; do not put the key in Git or `render.yaml`.
4. Apply the Blueprint. When the deploy and health check succeed, open the service's `onrender.com` URL. The React dashboard and `/api` routes share that origin, so no frontend API URL or CORS setting is needed.

The Blueprint sets `ALLOW_LIVE_TRADING=false`. This project has no order-submission endpoint and remains paper-only after deployment. Public Bybit market data needs no credentials. If you do not configure `GROQ_API_KEY`, chat uses its local fallback.

## Configuration

`backend/.env` supports:

- `GROQ_API_KEY` — optional; enables Groq chat.
- `GROQ_MODEL` — defaults to `openai/gpt-oss-120b`; change it to any model enabled for your Groq account.
- `BYBIT_BASE_URL` — defaults to Bybit mainnet public API; set to `https://api-testnet.bybit.com` to inspect Testnet data.
- `ALLOW_LIVE_TRADING` — defaults to `false`; this app currently has no live order route.

No API key is needed for public Bybit market data. Do not add exchange secrets to the frontend.

## Strategy flow

1. Fetch BTC option instruments and BTC spot reference price from Bybit public market endpoints.
2. Group option contracts by expiry and strike; select the nearest future expiry with both a call and a put.
3. Choose the strike nearest the BTC reference price and select its matching call/put pair.
4. Show a paper short entry. The dashboard's preview uses bid prices for entry and asks for buyback valuation.
5. Compare combined buyback premium with combined entry premium: close on a 1% increase (stop) or a 2% decrease (take profit).

The assignment's live execution, order acknowledgements, partial-fill handling, and position reconciliation require a configured NautilusTrader Bybit execution node and Testnet credentials. They are not simulated as live capability here. See `backend/app/nautilus_strategy.py` for an annotated integration boundary.

## API

- `GET /api/health` — API and mode status.
- `GET /api/market/overview` — BTC reference and matched option pair, with a cached last result if Bybit is unreachable.
- `POST /api/strategy/preview` — paper straddle P&L and optional risk thresholds.
- `POST /api/chat` — assignment Q&A via Groq or deterministic local fallback.

