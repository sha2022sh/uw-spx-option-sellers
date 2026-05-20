from fastapi import FastAPI
import os
import httpx

app = FastAPI(title="Abu Wissam SPX API")

API_KEY = os.getenv("UNUSUAL_WHALES_API_KEY")

BASE_URL = "https://api.unusualwhales.com"


@app.get("/")
async def root():
    return {
        "status": "running",
        "message": "Abu Wissam API is working"
    }


@app.get("/pine/SPX")
async def pine_spx():

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json"
    }

    url = f"{BASE_URL}/api/option-trades/flow-alerts"

    params = {
        "ticker_symbol": "SPX",
        "limit": 50
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            url,
            headers=headers,
            params=params
        )

    data = response.json()

    rows = data.get("data", [])

    calls = []
    puts = []

    for row in rows:

        strike = row.get("strike")
        volume = row.get("volume", 0)
        oi = row.get("open_interest", 0)
        premium = row.get("total_premium", 0)
        option_type = row.get("type", "")

        contract = {
            "strike": strike,
            "volume": volume,
            "oi": oi,
            "premium": premium
        }

        if option_type == "call":
            calls.append(contract)

        if option_type == "put":
            puts.append(contract)

    top_call = max(calls, key=lambda x: x["volume"], default=None)
    top_put = max(puts, key=lambda x: x["volume"], default=None)

    call_wall = top_call["strike"] if top_call else None
    put_wall = top_put["strike"] if top_put else None

    return {
        "status": "success",

        "call_wall": call_wall,
        "put_wall": put_wall,

        "top_call": top_call,
        "top_put": top_put,

        "total_calls": len(calls),
        "total_puts": len(puts),

        "contracts": rows[:10]
    }
