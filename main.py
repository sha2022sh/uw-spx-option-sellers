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
        return {
            "error": "UNUSUAL_WHALES_API_KEY is missing"
        }

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json"
    }

    url = f"{BASE_URL}/api/option-trades/flow-alerts"

    params = {
        "ticker_symbol": "SPX",
        "limit": 5
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, headers=headers, params=params)

    if response.status_code != 200:
        return {
            "error": "Unusual Whales API error",
            "status_code": response.status_code,
            "details": response.text
        }

    data = response.json()

    return {
        "status": "success",
        "ticker": "SPX",
        "data": data
    }
