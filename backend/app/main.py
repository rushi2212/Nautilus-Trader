from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from pathlib import Path
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .market import cached_overview, fetch_overview
from .models import ChatRequest, PreviewRequest

app = FastAPI(title="Nautilus BTC Straddle Lab", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

SYSTEM_PROMPT = """You are the learning assistant for Nautilus BTC Straddle Lab. Explain the intern challenge in plain language: a short straddle sells a call and put at the same BTC strike and expiry; ATM means the available strike closest to the BTC reference price. Level 2 monitors combined ask-side buyback premium, closing at +1% stop loss or -2% take profit relative to entry premium. Explain NautilusTrader and Bybit concepts accurately, and state when an answer is general guidance. This app is paper-only and does not execute trades. Never claim to know live account state or give personalized investment advice. Keep answers concise and useful."""


@app.get("/api/health")
async def health():
    settings = get_settings()
    return {"status": "ok", "mode": "paper", "groq_configured": bool(settings.groq_api_key), "live_trading_enabled": False}


@app.get("/api/market/overview")
async def market_overview():
    try:
        return await fetch_overview()
    except Exception as exc:
        try:
            return cached_overview(str(exc))
        except RuntimeError:
            raise HTTPException(status_code=503, detail=f"Market data is unavailable: {exc}") from exc


@app.post("/api/strategy/preview")
async def strategy_preview(request: PreviewRequest):
    entry = (request.entry_call + request.entry_put) * request.quantity
    buyback = (request.current_call_ask + request.current_put_ask) * request.quantity
    pnl = entry - buyback
    percent = (pnl / entry) * 100
    result = {
        "mode": "paper",
        "entry_premium": round(entry, 8),
        "buyback_premium": round(buyback, 8),
        "unrealized_pnl": round(pnl, 8),
        "return_percent": round(percent, 4),
        "quantity": request.quantity,
        "exit_signal": None,
        "risk_management": request.risk_management,
    }
    if request.risk_management:
        result["stop_loss_level"] = round(entry * 1.01, 8)
        result["take_profit_level"] = round(entry * 0.98, 8)
        if buyback >= entry * 1.01:
            result["exit_signal"] = "stop_loss"
        elif buyback <= entry * 0.98:
            result["exit_signal"] = "take_profit"
    return result


@app.post("/api/chat")
async def chat(request: ChatRequest):
    settings = get_settings()
    history = [{"role": message.role, "content": message.content} for message in request.messages]
    if not settings.groq_api_key:
        prompt = request.messages[-1].content.lower()
        answer = _local_answer(prompt)
        return {"reply": answer, "provider": "local", "model": None}
    try:
        client = Groq(api_key=settings.groq_api_key)
        completion = client.chat.completions.create(
            model=settings.groq_model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, *history],
            temperature=0.4,
            max_tokens=500,
        )
        return {"reply": completion.choices[0].message.content or "I couldn't form a reply.", "provider": "groq", "model": settings.groq_model}
    except Exception as exc:
        if getattr(exc, "status_code", None) == 404:
            detail = f"Groq model '{settings.groq_model}' is unavailable for this account. Choose an enabled model in GROQ_MODEL."
        elif getattr(exc, "status_code", None) == 401:
            detail = "Groq rejected the API key. Check GROQ_API_KEY in backend/.env."
        else:
            detail = f"Groq could not complete the request: {exc}"
        raise HTTPException(status_code=502, detail=detail) from exc


def _local_answer(prompt: str) -> str:
    if "stop" in prompt or "take profit" in prompt or "risk" in prompt:
        return "Level 2 compares the combined ask-side cost to buy back both legs with the combined entry premium. A 1% increase triggers the stop loss; a 2% decrease triggers take profit. This dashboard only previews those signals in paper mode."
    if "atm" in prompt or "strike" in prompt:
        return "ATM is the available strike closest to the BTC reference price. The app selects the nearest future expiry that has both a call and a put at that strike, so the legs share strike and expiry."
    if "nautilus" in prompt or "bybit" in prompt or "order" in prompt:
        return "NautilusTrader hosts the strategy and routes data/orders through an exchange adapter. Bybit public endpoints provide market data without credentials; authenticated Testnet execution requires a configured Nautilus Bybit execution client. This app intentionally remains paper-only."
    return "A short straddle sells one call and one put at the same strike and expiry. The premium is collected up front, and the combined cost to buy the legs back is monitored. Ask about ATM selection, NautilusTrader flow, or the Level 2 risk thresholds."


# In production, the Docker image places the Vite build here so Render can
# serve the UI and API from one origin. Local Vite development uses its proxy.
static_dir = Path(__file__).with_name("static")
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

