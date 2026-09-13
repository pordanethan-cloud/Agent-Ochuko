# Bybit Manual Range Scalping — Fast Execution Panel (v1.3)

A high-performance, single-click manual execution panel for range scalping on **Bybit Spot V5**, built in accordance with `manual_range_scalping_strategy_manual_v1_3.md`.

---

## 🚀 Key Features

- **1-Click High-Impact Execution**:
  - `[ BUY AT SUPPORT ]`: Instant Limit Buy at configured Support boundary.
  - `[ SELL AT RESISTANCE ]`: Instant Limit Sell at configured Resistance boundary.
  - `[ BUY MARKET ]`: Instant Market Buy with configured USDT sizing.
  - `[ SELL MARKET ]`: Instant Market Sell with configured USDT sizing.
  - `[ CLOSE 50% ]`: Partial take-profit (market sells 50% of base token position).
  - `[ CANCEL ALL ORDERS ]`: 1-click purge of all active open orders.
  - `[ EMERGENCY PANIC CLOSE 100% ]`: Hard stop that cancels all open orders and liquidates 100% of base asset back to USDT.
- **Interactive Range Visualizer**:
  - Live animated Range Position Track showing exactly where market price sits relative to Support (0%), Midpoint (50%), and Resistance (100%).
  - Dynamic Zone Badges: *Buy Zone (Near Support)*, *Mid-Range (Neutral)*, *Sell Zone (Near Resistance)*, *Out of Bounds*.
- **Secure Backend Authentication**:
  - Python FastAPI backend handles Bybit V5 HMAC-SHA256 request signing with millisecond timestamps and replay protection (`recv_window`).
  - API keys remain protected on the server side and never leak to the public web.
- **Dual Network Mode**:
  - 1-click toggle between Bybit **Testnet** (`api-testnet.bybit.com`) and **Mainnet** (`api.bybit.com`).
- **Active Open Orders & Live Execution Audit**:
  - Real-time order table with 1-click cancel buttons.
  - Timestamped execution log box recording all API responses and error codes.

---

## 📋 Security Checklist for Bybit API Keys

> [!CAUTION]
> **API Key Permissions Rule**:
> - Only check **Read** and **Spot Trade** permissions in your Bybit API Management console.
> - **NEVER** enable *Withdrawal*, *Transfer*, or *Sub-account Transfer* permissions.
> - For production, bind your API key to your specific static IP address.

---

## 🛠️ Quick Start

### 1. Install Dependencies
Ensure Python 3.9+ is installed:
```bash
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)
Copy `.env.example` to `.env` or enter credentials directly in the Web UI:
```bash
cp .env.example .env
```
Edit `.env`:
```ini
BYBIT_API_KEY=your_bybit_api_key
BYBIT_API_SECRET=your_bybit_api_secret
BYBIT_ENVIRONMENT=testnet
PORT=8080
```

### 3. Run Application
Run with Python:
```bash
python server.py
```
Or on Windows:
```cmd
run.bat
```

### 4. Open in Browser
Open `http://localhost:8080` in your web browser.

---

## 📊 Range Scalping Strategy Workflow

1. **Identify High-Probability Range**:
   - On 15m or 1h charts, identify clear Support (Lower Range boundary) and Resistance (Upper Range boundary).
2. **Configure Parameters**:
   - Enter Support & Resistance prices in the left panel.
   - Set your trade size (e.g. $100 USDT per click).
   - Click **Save Range Boundaries**.
3. **Execution**:
   - When price reaches the **Buy Zone (Near Support)**, click `BUY AT SUPPORT` or `BUY MARKET`.
   - Take profit near **Midpoint** or **Resistance** by clicking `CLOSE 50%` or `SELL AT RESISTANCE`.
   - If price breaks down hard below Support, click `EMERGENCY CLOSE 100%` to preserve capital.
