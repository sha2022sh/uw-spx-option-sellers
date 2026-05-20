from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

import httpx
from cachetools import TTLCache
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

load_dotenv()

API_KEY = os.getenv("UNUSUAL_WHALES_API_KEY", "")
BASE_URL = os.getenv("UW_BASE_URL", "https://api.unusualwhales.com").rstrip("/")
CACHE_SECONDS = int(os.getenv("CACHE_SECONDS", "20"))

if not API_KEY:
    print("WARNING: UNUSUAL_WHALES_API_KEY is missing. Add it in .env")

app = FastAPI(title="Abu Wissam SPX Option Sellers API", version="1.0.0")
cache = TTLCache(maxsize=256, ttl=CACHE_SECONDS)


class ContractRow(BaseModel):
    type: str
    strike: float
    volume: float
    oi: float
    gex: float
    premium: float = 0.0
    side: str = ""
    role: str = ""


class LevelsResponse(BaseModel):
    ticker: str
    expiry: Optional[str] = None
    updated_at: float
    call_wall: float
    put_wall: float
    gamma_wall: float
    max_pain: float
    total_gex: float
    gamma_state: str
    top_contracts: List[ContractRow]
    pine_inputs: Dict[str, Any]
    notes: List[str]


def _num(v: Any, default: float = 0.0) -> float:
    if v is None or v == "":
        return default
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return default


def _pick(d: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


async def uw_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    key = (path, tuple(sorted((params or {}).items())))
    if key in cache:
        return cache[key]

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.get(f"{BASE_URL}{path}", headers=headers, params=params or {})
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text[:800])
    data = r.json()
    cache[key] = data
    return data


def _rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = payload.get("data", payload)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("data", "items", "results", "rows"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


def extract_oi_walls(oi_payload: Dict[str, Any]) -> Tuple[float, float]:
    rows = _rows(oi_payload)
    best_call = (0.0, 0.0)  # strike, oi
    best_put = (0.0, 0.0)

    for r in rows:
        strike = _num(_pick(r, ["strike", "strike_price", "price"]))
        call_oi = _num(_pick(r, ["call_oi", "calls_oi", "call_open_interest", "call_open_interest_sum", "call"]))
        put_oi = _num(_pick(r, ["put_oi", "puts_oi", "put_open_interest", "put_open_interest_sum", "put"]))

        # Some APIs return one side per row.
        put_call = str(_pick(r, ["put_call", "type", "option_type"], "")).lower()
        oi = _num(_pick(r, ["open_interest", "oi"]))
        if put_call.startswith("c") and oi:
            call_oi = max(call_oi, oi)
        if put_call.startswith("p") and oi:
            put_oi = max(put_oi, oi)

        if strike and call_oi > best_call[1]:
            best_call = (strike, call_oi)
        if strike and put_oi > best_put[1]:
            best_put = (strike, put_oi)

    return best_call[0], best_put[0]


def extract_max_pain(max_pain_payload: Dict[str, Any], expiry: Optional[str]) -> float:
    rows = _rows(max_pain_payload)
    if not rows:
        return 0.0

    if expiry:
        for r in rows:
            if str(_pick(r, ["expiry", "expiration", "expiry_date"], "")) == expiry:
                return _num(_pick(r, ["max_pain", "pain", "strike", "price"]))

    # newest/first fallback
    r = rows[0]
    return _num(_pick(r, ["max_pain", "pain", "strike", "price"]))


def extract_gex(gex_payload: Dict[str, Any]) -> Tuple[float, float]:
    rows = _rows(gex_payload)
    best = (0.0, 0.0)  # strike, abs gex
    total = 0.0
    for r in rows:
        strike = _num(_pick(r, ["strike", "strike_price", "price"]))
        gex = _num(_pick(r, ["gex", "gamma_exposure", "net_gex", "total_gex", "gamma"]))
        total += gex
        if strike and abs(gex) > best[1]:
            best = (strike, abs(gex))
    return best[0], total


def extract_top_contracts(flow_payload: Dict[str, Any], limit: int = 5) -> List[ContractRow]:
    rows = _rows(flow_payload)
    contracts: Dict[Tuple[str, float], Dict[str, Any]] = {}

    for r in rows:
        typ = str(_pick(r, ["put_call", "type", "option_type", "call_put"], "")).upper()
        if "CALL" in typ:
            typ = "C"
        elif "PUT" in typ:
            typ = "P"
        elif typ.startswith("C"):
            typ = "C"
        elif typ.startswith("P"):
            typ = "P"
        else:
            # Try option symbol C/P
            sym = str(_pick(r, ["option_symbol", "contract", "symbol"], ""))
            typ = "C" if "C" in sym[-15:] else ("P" if "P" in sym[-15:] else "?")

        strike = _num(_pick(r, ["strike", "strike_price"]))
        if not strike:
            # very rough fallback from OCC symbol ending, e.g. SPXW240621C05400000
            sym = str(_pick(r, ["option_symbol", "contract", "symbol"], ""))
            digits = "".join(ch for ch in sym[-8:] if ch.isdigit())
            strike = _num(digits) / 1000 if digits else 0.0

        volume = _num(_pick(r, ["volume", "vol", "total_volume", "size"]))
        oi = _num(_pick(r, ["open_interest", "oi"]))
        gex = _num(_pick(r, ["gex", "gamma_exposure", "net_gex", "gamma"]))
        premium = _num(_pick(r, ["premium", "total_premium", "notional"]))

        if not strike:
            continue

        key = (typ, strike)
        if key not in contracts:
            contracts[key] = {
                "type": typ, "strike": strike, "volume": 0.0, "oi": 0.0,
                "gex": 0.0, "premium": 0.0, "side": "", "role": ""
            }

        contracts[key]["volume"] += volume
        contracts[key]["oi"] = max(contracts[key]["oi"], oi)
        contracts[key]["gex"] += gex
        contracts[key]["premium"] += premium
        side = str(_pick(r, ["side", "ask_side", "bid_side"], ""))
        if side:
            contracts[key]["side"] = side

    sorted_rows = sorted(
        contracts.values(),
        key=lambda x: (x["volume"], x["premium"], x["oi"]),
        reverse=True
    )[:limit]

    out = []
    for x in sorted_rows:
        x["role"] = "Resistance / Call Sellers" if x["type"] == "C" else "Support / Put Sellers"
        out.append(ContractRow(**x))
    return out


def make_pine_inputs(levels: Dict[str, Any], contracts: List[ContractRow]) -> Dict[str, Any]:
    p = {
        "callWall": levels["call_wall"],
        "putWall": levels["put_wall"],
        "gammaWall": levels["gamma_wall"],
        "maxPain": levels["max_pain"],
        "gammaMode": "Positive Gamma" if levels["total_gex"] >= 0 else "Negative Gamma",
    }
    for i in range(5):
        row = contracts[i] if i < len(contracts) else ContractRow(type="C", strike=0, volume=0, oi=0, gex=0)
        p[f"type{i+1}"] = row.type
        p[f"strike{i+1}"] = row.strike
        p[f"vol{i+1}"] = row.volume
        p[f"oi{i+1}"] = row.oi
        p[f"gex{i+1}"] = row.gex
    return p


@app.get("/health")
async def health():
    return {"ok": True, "cache_seconds": CACHE_SECONDS}


@app.get("/levels/{ticker}", response_model=LevelsResponse)
async def levels(
    ticker: str = "SPX",
    expiry: Optional[str] = Query(default=None, description="YYYY-MM-DD optional"),
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD optional"),
    min_premium: int = 100000,
):
    ticker = ticker.upper()

    # Fast parallel calls.
    params_date = {"date": date} if date else {}
    flow_params = {"ticker_symbol": ticker, "limit": 200, "min_premium": min_premium}
    if expiry:
        # Flow endpoint may not always accept expiry. Keep analysis robust by filtering only if field exists.
        pass

    async with httpx.AsyncClient(timeout=8.0) as _:
        # Use uw_get to preserve cache.
        import asyncio
        oi_task = uw_get(f"/api/stock/{ticker}/oi-per-strike", params_date)
        max_pain_task = uw_get(f"/api/stock/{ticker}/max-pain", params_date)
        flow_task = uw_get("/api/option-trades/flow-alerts", flow_params)

        # Try the newer/available GEX endpoint names by strike; if one fails, continue.
        # These paths are separated because UW has several GEX/Greeks endpoints.
        gex_candidates = [
            (f"/api/stock/{ticker}/greeks", {"expiry": expiry, **params_date} if expiry else params_date),
            (f"/api/gex/{ticker}/strike", {"expiry": expiry, **params_date} if expiry else params_date),
        ]

        oi_payload, max_pain_payload, flow_payload = await asyncio.gather(oi_task, max_pain_task, flow_task)

    gex_payload = {"data": []}
    for path, params in gex_candidates:
        try:
            gex_payload = await uw_get(path, params)
            if _rows(gex_payload):
                break
        except Exception:
            continue

    call_wall, put_wall = extract_oi_walls(oi_payload)
    max_p = extract_max_pain(max_pain_payload, expiry)
    gamma_wall, total_gex = extract_gex(gex_payload)
    top = extract_top_contracts(flow_payload, 5)

    # If GEX endpoint didn't provide rows, approximate gamma wall from highest abs contract gex or highest-volume contract.
    if gamma_wall == 0 and top:
        gamma_wall = sorted(top, key=lambda x: (abs(x.gex), x.volume), reverse=True)[0].strike
        total_gex = sum(x.gex for x in top)

    levels_dict = {
        "call_wall": call_wall,
        "put_wall": put_wall,
        "gamma_wall": gamma_wall,
        "max_pain": max_p,
        "total_gex": total_gex,
    }

    notes = [
        "TradingView Pine لا يقرأ API مباشرة؛ هذا السيرفر يعطيك المستويات جاهزة للنسخ.",
        "Call/Put Wall محسوبة من أعلى Open Interest حسب strike.",
        "TOP contracts مرتبة حسب Volume ثم Premium ثم OI.",
        "إذا لم يرجع GEX من API، يتم استخدام أفضل تقدير من أقوى العقود."
    ]

    return LevelsResponse(
        ticker=ticker,
        expiry=expiry,
        updated_at=time.time(),
        call_wall=call_wall,
        put_wall=put_wall,
        gamma_wall=gamma_wall,
        max_pain=max_p,
        total_gex=total_gex,
        gamma_state="Positive Gamma" if total_gex >= 0 else "Negative Gamma",
        top_contracts=top,
        pine_inputs=make_pine_inputs(levels_dict, top),
        notes=notes,
    )


@app.get("/pine/{ticker}", response_class=PlainTextResponse)
async def pine_text(ticker: str = "SPX", expiry: Optional[str] = None, date: Optional[str] = None):
    data = await levels(ticker=ticker, expiry=expiry, date=date)
    p = data.pine_inputs
    lines = [
        f"callWall = {p['callWall']}",
        f"putWall = {p['putWall']}",
        f"gammaWall = {p['gammaWall']}",
        f"maxPain = {p['maxPain']}",
        f"gammaMode = {p['gammaMode']}",
        ""
    ]
    for i in range(1, 6):
        lines += [
            f"type{i} = {p[f'type{i}']}",
            f"strike{i} = {p[f'strike{i}']}",
            f"vol{i} = {p[f'vol{i}']}",
            f"oi{i} = {p[f'oi{i}']}",
            f"gex{i} = {p[f'gex{i}']}",
            ""
        ]
    return "\n".join(lines)
