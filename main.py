from fastapi import FastAPI
import os
import time
import httpx

app = FastAPI(title="Abu Wissam SPX Option Sellers API")

API_KEY = os.getenv("UNUSUAL_WHALES_API_KEY")
BASE_URL = "https://api.unusualwhales.com"


@app.get("/")
async def root():
    return {
        "status": "running",
        "message": "Abu Wissam API is working"
    }


@app.get("/health")
async def health():
    return {
        "ok": True,
        "time": time.time()
    }


@app.get("/pine/SPX")
async def pine_spx():
    if not API_KEY:
        return {"error": "UNUSUAL_WHALES_API_KEY is missing"}

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json"
    }

    url = f"{BASE_URL}/api/option-trades/flow-alerts"

    params = {
        "ticker_symbol": "SPX",
        "limit": 100
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url, headers=headers, params=params)

    if response.status_code != 200:
        return {
            "error": "Unusual Whales API error",
            "status_code": response.status_code,
            "details": response.text
        }

    data = response.json()
    rows = data.get("data", [])

    calls = []
    puts = []

    for row in rows:
        strike = row.get("strike")
        volume = float(row.get("volume") or 0)
        oi = float(row.get("open_interest") or 0)
        premium = float(row.get("total_premium") or 0)
        option_type = str(row.get("type") or "").lower()

        contract = {
            "type": option_type,
            "strike": strike,
            "volume": volume,
            "oi": oi,
            "premium": premium,
            "price": row.get("price"),
            "expiry": row.get("expiry")
        }

        if option_type == "call":
            calls.append(contract)

        if option_type == "put":
            puts.append(contract)

    top_call = max(calls, key=lambda x: x["volume"], default=None)
    top_put = max(puts, key=lambda x: x["volume"], default=None)

    call_wall = top_call["strike"] if top_call else None
    put_wall = top_put["strike"] if top_put else None

    strongest = sorted(
        calls + puts,
        key=lambda x: x["volume"],
        reverse=True
    )[:10]

    gamma_bias = "NEUTRAL"

    if len(calls) > len(puts):
        gamma_bias = "POSITIVE"

    if len(puts) > len(calls):
        gamma_bias = "NEGATIVE"

    return {
        "status": "success",
        "ticker": "SPX",

        "call_wall": call_wall,
        "put_wall": put_wall,
        "gamma_bias": gamma_bias,

        "top_call": top_call,
        "top_put": top_put,

        "total_calls": len(calls),
        "total_puts": len(puts),

        "top_contracts": strongest
    }
