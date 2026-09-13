"""
Bybit Manual Spot-Trading Button App — Execution Backend
FastAPI server handling Bybit V5 Spot API authentication, HMAC-SHA256 signature calculation,
real-time price proxying, and order execution safety guards.
"""

import os
import time
import hmac
import hashlib
import json
import logging
from typing import Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bybit-button-app")

app = FastAPI(title="Bybit Manual Button App", version="1.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Runtime configuration state
APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR

CONFIG = {
    "api_key": os.getenv("BYBIT_API_KEY", ""),
    "api_secret": os.getenv("BYBIT_API_SECRET", ""),
    "environment": os.getenv("BYBIT_ENVIRONMENT", "testnet").lower(),  # 'testnet' | 'mainnet'
    "symbol": "BTCUSDT",
    "support_price": 0.0,
    "resistance_price": 0.0,
    "order_size_usdt": 100.0,
    "order_size_pct": 10.0,
    "size_mode": "fixed",  # 'fixed' or 'percentage'
    "daily_loss_limit_usdt": 200.0,
    "realized_pnl_today": 0.0,
}

MAINNET_BASE_URL = "https://api.bybit.com"
TESTNET_BASE_URL = "https://api-testnet.bybit.com"


def get_base_url() -> str:
    return TESTNET_BASE_URL if CONFIG["environment"] == "testnet" else MAINNET_BASE_URL


def generate_bybit_signature(api_key: str, api_secret: str, timestamp: str, recv_window: str, query_or_body: str) -> str:
    """Generates Bybit V5 HMAC-SHA256 signature."""
    payload = f"{timestamp}{api_key}{recv_window}{query_or_body}"
    return hmac.new(
        api_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


async def bybit_request(method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Sends an authenticated or public request to Bybit V5 API."""
    api_key = CONFIG["api_key"].strip()
    api_secret = CONFIG["api_secret"].strip()
    base_url = get_base_url()
    url = f"{base_url}{endpoint}"

    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"

    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
        "Content-Type": "application/json",
    }

    payload_str = ""
    if method.upper() == "GET":
        if params:
            query_parts = [f"{k}={v}" for k, v in sorted(params.items()) if v is not None]
            payload_str = "&".join(query_parts)
    elif method.upper() == "POST":
        payload_str = json.dumps(body or {}) if body else "{}"

    if api_key and api_secret:
        sig = generate_bybit_signature(api_key, api_secret, timestamp, recv_window, payload_str)
        headers["X-BAPI-SIGN"] = sig

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            if method.upper() == "GET":
                resp = await client.get(url, params=params, headers=headers)
            else:
                resp = await client.post(url, json=body or {}, headers=headers)

            data = resp.json()
            if data.get("retCode") != 0:
                logger.warning(f"Bybit V5 warning {endpoint}: code={data.get('retCode')}, msg={data.get('retMsg')}")
            return data
        except Exception as err:
            logger.error(f"Bybit API request exception ({endpoint}): {err}")
            raise HTTPException(status_code=502, detail=f"Bybit connection failure: {str(err)}")


# ─────────────────────────────────────────────────────────────────────────────
# API Models
# ─────────────────────────────────────────────────────────────────────────────
class ConfigUpdate(BaseModel):
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    environment: Optional[str] = None
    symbol: Optional[str] = None
    support_price: Optional[float] = None
    resistance_price: Optional[float] = None
    order_size_usdt: Optional[float] = None
    order_size_pct: Optional[float] = None
    size_mode: Optional[str] = None
    daily_loss_limit_usdt: Optional[float] = None


class OrderCreateRequest(BaseModel):
    symbol: Optional[str] = None
    side: str  # 'Buy' or 'Sell'
    order_type: str  # 'Limit' or 'Market'
    price: Optional[float] = None
    qty: Optional[float] = None
    target_zone: Optional[str] = None  # 'support', 'resistance', 'manual'


class OrderCancelRequest(BaseModel):
    symbol: Optional[str] = None
    order_id: Optional[str] = None
    order_link_id: Optional[str] = None


class ClosePercentRequest(BaseModel):
    symbol: Optional[str] = None
    percentage: float  # e.g. 50.0 or 100.0


# ─────────────────────────────────────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/status")
async def get_status():
    """Returns application state, environment, and sanitized credentials status."""
    has_key = bool(CONFIG["api_key"].strip())
    has_secret = bool(CONFIG["api_secret"].strip())
    key_masked = (CONFIG["api_key"][:4] + "..." + CONFIG["api_key"][-4:]) if len(CONFIG["api_key"]) > 8 else ("Configured" if has_key else "Missing")

    return {
        "status": "online",
        "environment": CONFIG["environment"],
        "symbol": CONFIG["symbol"],
        "api_configured": has_key and has_secret,
        "api_key_masked": key_masked,
        "support_price": CONFIG["support_price"],
        "resistance_price": CONFIG["resistance_price"],
        "midpoint_price": round((CONFIG["support_price"] + CONFIG["resistance_price"]) / 2, 4) if CONFIG["support_price"] and CONFIG["resistance_price"] else 0.0,
        "order_size_usdt": CONFIG["order_size_usdt"],
        "order_size_pct": CONFIG["order_size_pct"],
        "size_mode": CONFIG["size_mode"],
        "daily_loss_limit_usdt": CONFIG["daily_loss_limit_usdt"],
        "realized_pnl_today": CONFIG["realized_pnl_today"],
        "circuit_breaker_tripped": CONFIG["realized_pnl_today"] <= -CONFIG["daily_loss_limit_usdt"] if CONFIG["daily_loss_limit_usdt"] > 0 else False,
    }


@app.post("/api/config")
async def update_config(payload: ConfigUpdate):
    """Updates runtime trading configuration and credentials."""
    if payload.api_key is not None:
        CONFIG["api_key"] = payload.api_key.strip()
    if payload.api_secret is not None:
        CONFIG["api_secret"] = payload.api_secret.strip()
    if payload.environment is not None:
        CONFIG["environment"] = payload.environment.lower()
    if payload.symbol is not None:
        CONFIG["symbol"] = payload.symbol.upper().strip()
    if payload.support_price is not None:
        CONFIG["support_price"] = max(0.0, float(payload.support_price))
    if payload.resistance_price is not None:
        CONFIG["resistance_price"] = max(0.0, float(payload.resistance_price))
    if payload.order_size_usdt is not None:
        CONFIG["order_size_usdt"] = max(1.0, float(payload.order_size_usdt))
    if payload.order_size_pct is not None:
        CONFIG["order_size_pct"] = min(100.0, max(1.0, float(payload.order_size_pct)))
    if payload.size_mode is not None:
        CONFIG["size_mode"] = payload.size_mode.lower()
    if payload.daily_loss_limit_usdt is not None:
        CONFIG["daily_loss_limit_usdt"] = max(0.0, float(payload.daily_loss_limit_usdt))

    return {"status": "updated", "config": await get_status()}


@app.get("/api/ticker")
async def get_ticker(symbol: Optional[str] = None):
    """Fetches real-time spot market ticker for symbol."""
    sym = (symbol or CONFIG["symbol"]).upper().strip()
    res = await bybit_request("GET", "/v5/market/tickers", params={"category": "spot", "symbol": sym})
    if res.get("retCode") == 0 and res.get("result", {}).get("list"):
        item = res["result"]["list"][0]
        last_price = float(item.get("lastPrice", 0))
        high_24h = float(item.get("highPrice24h", 0))
        low_24h = float(item.get("lowPrice24h", 0))
        volume_24h = float(item.get("volume24h", 0))
        change_24h = float(item.get("price24hPcnt", 0)) * 100.0

        # Calculate position relative to range
        supp = CONFIG["support_price"]
        resis = CONFIG["resistance_price"]
        range_pct = None
        zone = "undefined"

        if supp > 0 and resis > supp:
            range_span = resis - supp
            range_pct = round(((last_price - supp) / range_span) * 100.0, 2)
            if last_price < supp:
                zone = "Below Support (Oversold / Danger)"
            elif last_price <= supp + (range_span * 0.25):
                zone = "Buy Zone (Near Support)"
            elif last_price >= resis - (range_span * 0.25):
                zone = "Sell Zone (Near Resistance)"
            elif last_price > resis:
                zone = "Above Resistance (Overbought / Breakout)"
            else:
                zone = "Mid-Range (Neutral)"

        return {
            "symbol": sym,
            "last_price": last_price,
            "high_24h": high_24h,
            "low_24h": low_24h,
            "volume_24h": volume_24h,
            "change_24h_pct": round(change_24h, 2),
            "range_pct": range_pct,
            "zone": zone,
        }
    return {"symbol": sym, "last_price": 0.0, "error": res.get("retMsg", "No data")}


@app.get("/api/wallet")
async def get_wallet():
    """Fetches wallet balances (USDT and base currency)."""
    if not CONFIG["api_key"] or not CONFIG["api_secret"]:
        return {"balances": {"USDT": 10000.0, "BTC": 0.5}, "simulated": True, "note": "API keys not set; showing test mock."}

    # Try UNIFIED account balance first, fallback to SPOT
    res = await bybit_request("GET", "/v5/account/wallet-balance", params={"accountType": "UNIFIED"})
    if res.get("retCode") != 0:
        res = await bybit_request("GET", "/v5/account/wallet-balance", params={"accountType": "SPOT"})

    balances = {}
    total_equity_usdt = 0.0

    if res.get("retCode") == 0 and res.get("result", {}).get("list"):
        coins = res["result"]["list"][0].get("coin", [])
        for c in coins:
            coin_name = c.get("coin")
            wallet_bal = float(c.get("walletBalance", 0) or 0)
            if wallet_bal > 0:
                balances[coin_name] = {
                    "balance": wallet_bal,
                    "available": float(c.get("availableToWithdraw", wallet_bal) or wallet_bal),
                    "usd_value": float(c.get("usdValue", 0) or 0),
                }
        total_equity_usdt = float(res["result"]["list"][0].get("totalEquity", 0) or 0)

    return {"balances": balances, "total_equity_usdt": total_equity_usdt, "simulated": False}


@app.get("/api/orders")
async def get_open_orders(symbol: Optional[str] = None):
    """Fetches open spot orders for the symbol."""
    if not CONFIG["api_key"] or not CONFIG["api_secret"]:
        return {"orders": [], "simulated": True}

    sym = (symbol or CONFIG["symbol"]).upper().strip()
    res = await bybit_request("GET", "/v5/order/realtime", params={"category": "spot", "symbol": sym})
    orders = []
    if res.get("retCode") == 0 and res.get("result", {}).get("list"):
        for o in res["result"]["list"]:
            orders.append({
                "order_id": o.get("orderId"),
                "symbol": o.get("symbol"),
                "side": o.get("side"),
                "order_type": o.get("orderType"),
                "price": float(o.get("price", 0) or 0),
                "qty": float(o.get("qty", 0) or 0),
                "cum_exec_qty": float(o.get("cumExecQty", 0) or 0),
                "status": o.get("orderStatus"),
                "created_time": o.get("createdTime"),
            })
    return {"orders": orders, "simulated": False}


@app.post("/api/order/create")
async def create_order(req: OrderCreateRequest):
    """Places a manual Spot order on Bybit V5 with safety verification."""
    # Check circuit breaker
    if CONFIG["daily_loss_limit_usdt"] > 0 and CONFIG["realized_pnl_today"] <= -CONFIG["daily_loss_limit_usdt"]:
        raise HTTPException(status_code=403, detail="Daily loss circuit breaker is active! Trading disabled.")

    sym = (req.symbol or CONFIG["symbol"]).upper().strip()
    side = req.side.capitalize()  # 'Buy' or 'Sell'
    order_type = req.order_type.capitalize()  # 'Limit' or 'Market'

    # Determine execution price and quantity
    price = req.price
    qty = req.qty

    # Fetch live ticker if price or qty needs derivation
    ticker_data = await get_ticker(sym)
    last_price = ticker_data.get("last_price", 0.0)

    if order_type == "Limit" and not price:
        if req.target_zone == "support" and CONFIG["support_price"] > 0:
            price = CONFIG["support_price"]
        elif req.target_zone == "resistance" and CONFIG["resistance_price"] > 0:
            price = CONFIG["resistance_price"]
        else:
            price = last_price

    if not qty or qty <= 0:
        # Compute qty from configured USDT sizing
        ref_price = price if (price and price > 0) else last_price
        if ref_price > 0:
            usdt_amt = CONFIG["order_size_usdt"]
            qty = round(usdt_amt / ref_price, 6)
        else:
            qty = 0.001

    if not CONFIG["api_key"] or not CONFIG["api_secret"]:
        # Simulated execution
        return {
            "success": True,
            "simulated": True,
            "order_id": f"sim_{int(time.time()*1000)}",
            "symbol": sym,
            "side": side,
            "order_type": order_type,
            "price": price,
            "qty": qty,
            "message": f"Simulated {side} {order_type} placed at {price or 'Market'}",
        }

    body = {
        "category": "spot",
        "symbol": sym,
        "side": side,
        "orderType": order_type,
        "qty": str(qty),
        "timeInForce": "GTC" if order_type == "Limit" else "IOC",
    }
    if order_type == "Limit" and price:
        body["price"] = str(price)

    res = await bybit_request("POST", "/v5/order/create", body=body)
    if res.get("retCode") == 0:
        return {
            "success": True,
            "order_id": res.get("result", {}).get("orderId"),
            "order_link_id": res.get("result", {}).get("orderLinkId"),
            "message": f"{side} {order_type} order placed successfully!",
        }
    else:
        raise HTTPException(status_code=400, detail=f"Bybit rejected order: {res.get('retMsg')} (code {res.get('retCode')})")


@app.post("/api/order/cancel")
async def cancel_order(req: OrderCancelRequest):
    """Cancels a single open order."""
    sym = (req.symbol or CONFIG["symbol"]).upper().strip()
    if not CONFIG["api_key"] or not CONFIG["api_secret"]:
        return {"success": True, "simulated": True, "message": "Simulated order cancelled."}

    body = {"category": "spot", "symbol": sym}
    if req.order_id:
        body["orderId"] = req.order_id
    if req.order_link_id:
        body["orderLinkId"] = req.order_link_id

    res = await bybit_request("POST", "/v5/order/cancel", body=body)
    if res.get("retCode") == 0:
        return {"success": True, "message": "Order cancelled successfully."}
    else:
        raise HTTPException(status_code=400, detail=f"Bybit error: {res.get('retMsg')}")


@app.post("/api/order/cancel-all")
async def cancel_all_orders(symbol: Optional[str] = None):
    """Cancels all active spot orders for symbol."""
    sym = (symbol or CONFIG["symbol"]).upper().strip()
    if not CONFIG["api_key"] or not CONFIG["api_secret"]:
        return {"success": True, "simulated": True, "message": "All simulated orders cancelled."}

    res = await bybit_request("POST", "/v5/order/cancel-all", body={"category": "spot", "symbol": sym})
    if res.get("retCode") == 0:
        return {"success": True, "message": f"All open orders for {sym} cancelled."}
    else:
        raise HTTPException(status_code=400, detail=f"Bybit error: {res.get('retMsg')}")


@app.post("/api/emergency-close")
async def emergency_panic_close(symbol: Optional[str] = None):
    """
    CRITICAL PANIC ACTION:
    1. Immediately cancels ALL pending open orders.
    2. Checks current available base token balance.
    3. Fires immediate Market Sell order for 100% of available base token.
    """
    sym = (symbol or CONFIG["symbol"]).upper().strip()
    base_coin = sym.replace("USDT", "").replace("USDC", "").replace("BTC", "")

    # 1. Cancel all orders
    await cancel_all_orders(sym)

    # 2. Check wallet
    wallet = await get_wallet()
    if wallet.get("simulated"):
        return {
            "success": True,
            "simulated": True,
            "message": f"EMERGENCY CLOSE: Cancelled all orders and sold 100% of {base_coin} to cash (Simulated).",
        }

    balances = wallet.get("balances", {})
    base_info = balances.get(base_coin) or balances.get("BTC") or {}
    avail_qty = float(base_info.get("available", 0.0))

    if avail_qty <= 0.0001:
        return {"success": True, "message": f"All orders cancelled. No remaining {base_coin} balance to liquidate."}

    # 3. Market sell
    res = await bybit_request("POST", "/v5/order/create", body={
        "category": "spot",
        "symbol": sym,
        "side": "Sell",
        "orderType": "Market",
        "qty": str(avail_qty),
    })

    if res.get("retCode") == 0:
        return {
            "success": True,
            "message": f"EMERGENCY CLOSE COMPLETE: Cancelled all orders and market sold {avail_qty} {base_coin}!",
            "order_id": res.get("result", {}).get("orderId"),
        }
    else:
        raise HTTPException(status_code=400, detail=f"Failed to market sell position: {res.get('retMsg')}")


@app.post("/api/close-percentage")
async def close_percentage(req: ClosePercentRequest):
    """Partially liquidates position (e.g. 50% Take Profit near Resistance)."""
    sym = (req.symbol or CONFIG["symbol"]).upper().strip()
    base_coin = sym.replace("USDT", "").replace("USDC", "").replace("BTC", "")
    pct = min(100.0, max(1.0, float(req.percentage))) / 100.0

    wallet = await get_wallet()
    if wallet.get("simulated"):
        return {
            "success": True,
            "simulated": True,
            "message": f"Partial close: Market sold {int(pct*100)}% of {base_coin} position (Simulated).",
        }

    balances = wallet.get("balances", {})
    base_info = balances.get(base_coin) or balances.get("BTC") or {}
    avail_qty = float(base_info.get("available", 0.0))
    qty_to_sell = round(avail_qty * pct, 6)

    if qty_to_sell <= 0.0001:
        raise HTTPException(status_code=400, detail=f"Insufficient {base_coin} balance to close {int(pct*100)}%.")

    res = await bybit_request("POST", "/v5/order/create", body={
        "category": "spot",
        "symbol": sym,
        "side": "Sell",
        "orderType": "Market",
        "qty": str(qty_to_sell),
    })

    if res.get("retCode") == 0:
        return {
            "success": True,
            "message": f"Successfully sold {qty_to_sell} {base_coin} ({int(pct*100)}% of position)!",
            "order_id": res.get("result", {}).get("orderId"),
        }
    else:
        raise HTTPException(status_code=400, detail=f"Failed to execute partial close: {res.get('retMsg')}")


# ─────────────────────────────────────────────────────────────────────────────
# Static files & SPA root
# ─────────────────────────────────────────────────────────────────────────────
PUBLIC_DIR = APP_DIR / "public"
STATIC_ROOT = PUBLIC_DIR if PUBLIC_DIR.exists() else APP_DIR


@app.get("/")
async def serve_landing():
    landing_path = STATIC_ROOT / "index.html"
    if landing_path.exists():
        return FileResponse(landing_path)
    return {"message": "Bybit Manual Button App Server Online"}


@app.get("/desk")
@app.get("/desk.html")
async def serve_desk():
    desk_path = STATIC_ROOT / "desk.html"
    if not desk_path.exists():
        desk_path = STATIC_ROOT / "index.html"
    if desk_path.exists():
        return FileResponse(desk_path)
    return {"message": "Desk interface not found"}


@app.get("/strategy.md")
@app.get("/fello-traders-range-strategy.md")
async def download_strategy():
    strat_path = STATIC_ROOT / "strategy.md"
    if strat_path.exists():
        return FileResponse(
            strat_path,
            media_type="text/markdown",
            filename="fello-traders-range-strategy.md"
        )
    return {"message": "Strategy manual not found"}


app.mount("/", StaticFiles(directory=str(STATIC_ROOT), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)

