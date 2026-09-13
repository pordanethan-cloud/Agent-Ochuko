/**
 * Bybit Manual Range Scalping — Client Application Logic (v1.3)
 */

(function () {
  'use strict';

  // State
  let state = {
    symbol: 'BTCUSDT',
    environment: 'testnet',
    supportPrice: 0.0,
    resistancePrice: 0.0,
    midpointPrice: 0.0,
    lastPrice: 0.0,
    orderSizeUsdt: 100.0,
    dailyLossLimit: 200.0,
    realizedPnlToday: 0.0,
    apiConfigured: false,
    openOrders: [],
    baseCoin: 'BTC',
  };

  let pollTimer = null;

  // DOM Elements
  const el = {
    envToggleBtn: document.getElementById('envToggleBtn'),
    headerUsdtBal: document.getElementById('headerUsdtBal'),
    headerBaseCoinLabel: document.getElementById('headerBaseCoinLabel'),
    headerBaseBal: document.getElementById('headerBaseBal'),
    apiStatusIndicator: document.getElementById('apiStatusIndicator'),

    symbolInput: document.getElementById('symbolInput'),
    updateSymbolBtn: document.getElementById('updateSymbolBtn'),
    symbolBadge: document.getElementById('symbolBadge'),

    supportInput: document.getElementById('supportInput'),
    resistanceInput: document.getElementById('resistanceInput'),
    midpointDisplay: document.getElementById('midpointDisplay'),
    useCurrentAsSupportBtn: document.getElementById('useCurrentAsSupportBtn'),
    useCurrentAsResBtn: document.getElementById('useCurrentAsResBtn'),
    saveRangeBtn: document.getElementById('saveRangeBtn'),

    orderSizeUsdtInput: document.getElementById('orderSizeUsdtInput'),
    dailyLossInput: document.getElementById('dailyLossInput'),
    dailyPnlDisplay: document.getElementById('dailyPnlDisplay'),

    apiKeyInput: document.getElementById('apiKeyInput'),
    apiSecretInput: document.getElementById('apiSecretInput'),
    saveApiKeysBtn: document.getElementById('saveApiKeysBtn'),

    livePrice: document.getElementById('livePrice'),
    priceChange24h: document.getElementById('priceChange24h'),
    zoneBadge: document.getElementById('zoneBadge'),
    priceMarker: document.getElementById('priceMarker'),
    labelSupportPrice: document.getElementById('labelSupportPrice'),
    labelMidpointPrice: document.getElementById('labelMidpointPrice'),
    labelResistancePrice: document.getElementById('labelResistancePrice'),

    btnBuySupport: document.getElementById('btnBuySupport'),
    buySupportSub: document.getElementById('buySupportSub'),
    btnSellResistance: document.getElementById('btnSellResistance'),
    sellResistanceSub: document.getElementById('sellResistanceSub'),
    btnBuyMarket: document.getElementById('btnBuyMarket'),
    buyMarketSub: document.getElementById('buyMarketSub'),
    btnSellMarket: document.getElementById('btnSellMarket'),
    sellMarketSub: document.getElementById('sellMarketSub'),

    btnClose50: document.getElementById('btnClose50'),
    btnCancelAll: document.getElementById('btnCancelAll'),
    btnPanicClose: document.getElementById('btnPanicClose'),

    openOrderCount: document.getElementById('openOrderCount'),
    ordersTableBody: document.getElementById('ordersTableBody'),
    refreshOrdersBtn: document.getElementById('refreshOrdersBtn'),

    logBox: document.getElementById('logBox'),
    clearLogsBtn: document.getElementById('clearLogsBtn'),

    panicModal: document.getElementById('panicModal'),
    cancelPanicBtn: document.getElementById('cancelPanicBtn'),
    confirmPanicBtn: document.getElementById('confirmPanicBtn'),
  };

  // Helper: Log message to UI
  function addLog(msg, type = 'info') {
    const timeStr = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = 'log-entry';

    let colorClass = '';
    if (type === 'success') colorClass = 'log-success';
    else if (type === 'warn') colorClass = 'log-warn';
    else if (type === 'error') colorClass = 'log-error';

    entry.innerHTML = `<span class="log-time">[${timeStr}]</span> <span class="${colorClass}">${msg}</span>`;
    el.logBox.appendChild(entry);
    el.logBox.scrollTop = el.logBox.scrollHeight;
  }

  // API Call Wrapper
  async function api(path, options = {}) {
    try {
      const res = await fetch(path, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.message || `HTTP ${res.status}`);
      }
      return data;
    } catch (err) {
      addLog(`API error (${path}): ${err.message}`, 'error');
      throw err;
    }
  }

  // Calculate & Update Range UI
  function updateRangeVisuals() {
    const supp = state.supportPrice;
    const resis = state.resistancePrice;
    const cur = state.lastPrice;

    el.labelSupportPrice.textContent = supp > 0 ? supp.toLocaleString() : '--';
    el.labelResistancePrice.textContent = resis > 0 ? resis.toLocaleString() : '--';

    if (supp > 0 && resis > supp) {
      const mid = (supp + resis) / 2;
      state.midpointPrice = mid;
      el.midpointDisplay.value = mid.toLocaleString();
      el.labelMidpointPrice.textContent = mid.toLocaleString();

      el.buySupportSub.textContent = `Limit @ ${supp.toLocaleString()}`;
      el.sellResistanceSub.textContent = `Limit @ ${resis.toLocaleString()}`;

      // Calculate percentage inside range
      const rangeSpan = resis - supp;
      const pct = ((cur - supp) / rangeSpan) * 100;
      const clampedPct = Math.max(0, Math.min(100, pct));
      el.priceMarker.style.left = `${clampedPct}%`;

      // Update Zone Badge
      if (cur < supp) {
        el.zoneBadge.textContent = 'Below Support (Breakdown)';
        el.zoneBadge.className = 'zone-badge zone-sell';
      } else if (cur <= supp + rangeSpan * 0.25) {
        el.zoneBadge.textContent = 'Buy Zone (Near Support)';
        el.zoneBadge.className = 'zone-badge zone-buy';
      } else if (cur >= resis - rangeSpan * 0.25) {
        el.zoneBadge.textContent = 'Sell Zone (Near Resistance)';
        el.zoneBadge.className = 'zone-badge zone-sell';
      } else if (cur > resis) {
        el.zoneBadge.textContent = 'Above Resistance (Breakout)';
        el.zoneBadge.className = 'zone-badge zone-buy';
      } else {
        el.zoneBadge.textContent = 'Mid-Range (Neutral)';
        el.zoneBadge.className = 'zone-badge zone-mid';
      }
    } else {
      el.midpointDisplay.value = '--';
      el.labelMidpointPrice.textContent = '--';
      el.priceMarker.style.left = '50%';
      el.zoneBadge.textContent = 'Awaiting Range Setup';
      el.zoneBadge.className = 'zone-badge zone-mid';
    }

    el.buyMarketSub.textContent = `Instant ~$${state.orderSizeUsdt} USDT`;
    el.sellMarketSub.textContent = `Instant ~$${state.orderSizeUsdt} USDT`;
  }

  // Refresh System Status
  async function fetchStatus() {
    try {
      const data = await api('/api/status');
      state.environment = data.environment;
      state.symbol = data.symbol;
      state.apiConfigured = data.api_configured;
      state.supportPrice = data.support_price;
      state.resistancePrice = data.resistance_price;
      state.orderSizeUsdt = data.order_size_usdt;
      state.dailyLossLimit = data.daily_loss_limit_usdt;
      state.realizedPnlToday = data.realized_pnl_today;

      // Update Header elements
      el.envToggleBtn.textContent = state.environment.toUpperCase();
      el.envToggleBtn.className = `env-pill ${state.environment}`;
      el.symbolBadge.textContent = state.symbol;
      el.symbolInput.value = state.symbol;

      const base = state.symbol.replace('USDT', '').replace('USDC', '').replace('BTC', '');
      state.baseCoin = base || 'BTC';
      el.headerBaseCoinLabel.textContent = state.baseCoin;

      if (state.supportPrice > 0 && !el.supportInput.value) {
        el.supportInput.value = state.supportPrice;
      }
      if (state.resistancePrice > 0 && !el.resistanceInput.value) {
        el.resistanceInput.value = state.resistancePrice;
      }
      el.orderSizeUsdtInput.value = state.orderSizeUsdt;
      el.dailyLossInput.value = state.dailyLossLimit;

      el.apiStatusIndicator.style.background = state.apiConfigured ? '#10b981' : '#f59e0b';
      el.apiStatusIndicator.title = state.apiConfigured ? 'API Connected' : 'Simulated Mode (No Keys)';
    } catch {
      // Ignored in poll
    }
  }

  // Refresh Live Ticker
  async function fetchTicker() {
    try {
      const data = await api(`/api/ticker?symbol=${state.symbol}`);
      if (data.last_price > 0) {
        state.lastPrice = data.last_price;
        el.livePrice.textContent = data.last_price.toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 4,
        });

        const chg = data.change_24h_pct || 0;
        el.priceChange24h.textContent = `24h: ${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%`;
        el.priceChange24h.style.color = chg >= 0 ? '#10b981' : '#ef4444';

        updateRangeVisuals();
      }
    } catch {
      // Ignored
    }
  }

  // Refresh Wallet Balances
  async function fetchWallet() {
    try {
      const data = await api('/api/wallet');
      const balances = data.balances || {};
      const usdt = balances['USDT']?.available || balances['USDT']?.balance || 0;
      const base = balances[state.baseCoin]?.available || balances[state.baseCoin]?.balance || balances['BTC']?.available || 0;

      el.headerUsdtBal.textContent = `$${Number(usdt).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
      el.headerBaseBal.textContent = Number(base).toFixed(4);
    } catch {
      // Ignored
    }
  }

  // Refresh Open Orders
  async function fetchOrders() {
    try {
      const data = await api(`/api/orders?symbol=${state.symbol}`);
      const orders = data.orders || [];
      state.openOrders = orders;
      el.openOrderCount.textContent = orders.length;

      if (orders.length === 0) {
        el.ordersTableBody.innerHTML = `
          <tr>
            <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">
              No active open orders
            </td>
          </tr>
        `;
        return;
      }

      el.ordersTableBody.innerHTML = orders.map((o) => {
        const time = o.created_time ? new Date(Number(o.created_time)).toLocaleTimeString() : '--';
        const sideClass = o.side === 'Buy' ? 'side-buy' : 'side-sell';
        return `
          <tr>
            <td>${time}</td>
            <td><span class="side-badge ${sideClass}">${o.side}</span></td>
            <td>${o.order_type}</td>
            <td>${Number(o.price).toLocaleString()}</td>
            <td>${o.qty}</td>
            <td><span style="color: #60a5fa;">${o.status}</span></td>
            <td>
              <button class="btn-cancel-single" data-order-id="${o.order_id}">Cancel</button>
            </td>
          </tr>
        `;
      }).join('');

      // Attach cancel listeners
      el.ordersTableBody.querySelectorAll('.btn-cancel-single').forEach((btn) => {
        btn.addEventListener('click', async (e) => {
          const id = e.target.getAttribute('data-order-id');
          await cancelSingleOrder(id);
        });
      });
    } catch {
      // Ignored
    }
  }

  // Order Execution Handlers
  async function placeOrder(side, orderType, price = null, targetZone = null) {
    try {
      addLog(`Submitting ${side} ${orderType} order...`, 'info');
      const body = {
        symbol: state.symbol,
        side: side,
        order_type: orderType,
        price: price,
        target_zone: targetZone,
      };
      const res = await api('/api/order/create', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      addLog(`✓ ${res.message || 'Order placed!'} (ID: ${res.order_id || 'N/A'})`, 'success');
      await fetchOrders();
      await fetchWallet();
    } catch (err) {
      addLog(`✗ Order placement failed: ${err.message}`, 'error');
    }
  }

  async function cancelSingleOrder(orderId) {
    try {
      addLog(`Cancelling order ${orderId}...`, 'info');
      const res = await api('/api/order/cancel', {
        method: 'POST',
        body: JSON.stringify({ symbol: state.symbol, order_id: orderId }),
      });
      addLog(`✓ ${res.message}`, 'success');
      await fetchOrders();
    } catch (err) {
      addLog(`✗ Cancel failed: ${err.message}`, 'error');
    }
  }

  async function cancelAllOrders() {
    try {
      addLog(`Cancelling all open orders for ${state.symbol}...`, 'warn');
      const res = await api('/api/order/cancel-all', {
        method: 'POST',
        body: JSON.stringify({ symbol: state.symbol }),
      });
      addLog(`✓ ${res.message}`, 'success');
      await fetchOrders();
    } catch (err) {
      addLog(`✗ Cancel all failed: ${err.message}`, 'error');
    }
  }

  async function closePercentage(pct) {
    try {
      addLog(`Executing partial close: ${pct}% of ${state.baseCoin}...`, 'warn');
      const res = await api('/api/close-percentage', {
        method: 'POST',
        body: JSON.stringify({ symbol: state.symbol, percentage: pct }),
      });
      addLog(`✓ ${res.message}`, 'success');
      await fetchWallet();
      await fetchOrders();
    } catch (err) {
      addLog(`✗ Partial close failed: ${err.message}`, 'error');
    }
  }

  async function executeEmergencyClose() {
    try {
      addLog(`🚨 INITIATING EMERGENCY PANIC CLOSE 100% 🚨`, 'error');
      const res = await api('/api/emergency-close', {
        method: 'POST',
        body: JSON.stringify({ symbol: state.symbol }),
      });
      addLog(`✓ ${res.message}`, 'success');
      await fetchWallet();
      await fetchOrders();
    } catch (err) {
      addLog(`✗ EMERGENCY CLOSE FAILED: ${err.message}`, 'error');
    }
  }

  // Event Listeners Setup
  function initListeners() {
    // Environment Toggle
    el.envToggleBtn.addEventListener('click', async () => {
      const nextEnv = state.environment === 'testnet' ? 'mainnet' : 'testnet';
      if (nextEnv === 'mainnet') {
        const ok = confirm('WARNING: Switching to Bybit MAINNET with real funds! Confirm?');
        if (!ok) return;
      }
      await api('/api/config', {
        method: 'POST',
        body: JSON.stringify({ environment: nextEnv }),
      });
      addLog(`Switched network to ${nextEnv.toUpperCase()}`, 'warn');
      await fetchStatus();
      await fetchWallet();
      await fetchOrders();
    });

    // Symbol Update
    el.updateSymbolBtn.addEventListener('click', async () => {
      const newSym = el.symbolInput.value.trim().toUpperCase();
      if (!newSym) return;
      await api('/api/config', {
        method: 'POST',
        body: JSON.stringify({ symbol: newSym }),
      });
      state.symbol = newSym;
      addLog(`Active trading pair set to ${newSym}`, 'info');
      await fetchStatus();
      await fetchTicker();
      await fetchOrders();
    });

    // Set Range Boundaries
    el.saveRangeBtn.addEventListener('click', async () => {
      const supp = parseFloat(el.supportInput.value) || 0;
      const resis = parseFloat(el.resistanceInput.value) || 0;
      const sizeUsdt = parseFloat(el.orderSizeUsdtInput.value) || 100;
      const lossLimit = parseFloat(el.dailyLossInput.value) || 200;

      if (resis <= supp && supp > 0) {
        alert('Resistance price must be strictly greater than Support price.');
        return;
      }

      await api('/api/config', {
        method: 'POST',
        body: JSON.stringify({
          support_price: supp,
          resistance_price: resis,
          order_size_usdt: sizeUsdt,
          daily_loss_limit_usdt: lossLimit,
        }),
      });

      state.supportPrice = supp;
      state.resistancePrice = resis;
      state.orderSizeUsdt = sizeUsdt;
      state.dailyLossLimit = lossLimit;

      updateRangeVisuals();
      addLog(`Range updated: Support=${supp.toLocaleString()}, Resistance=${resis.toLocaleString()}, Size=$${sizeUsdt}`, 'success');
    });

    // Quick set from last price
    el.useCurrentAsSupportBtn.addEventListener('click', () => {
      if (state.lastPrice > 0) el.supportInput.value = state.lastPrice;
    });

    el.useCurrentAsResBtn.addEventListener('click', () => {
      if (state.lastPrice > 0) el.resistanceInput.value = state.lastPrice;
    });

    // API Key Save
    el.saveApiKeysBtn.addEventListener('click', async () => {
      const key = el.apiKeyInput.value.trim();
      const secret = el.apiSecretInput.value.trim();
      if (!key || !secret) {
        alert('Please enter both Bybit API Key and Secret.');
        return;
      }
      await api('/api/config', {
        method: 'POST',
        body: JSON.stringify({ api_key: key, api_secret: secret }),
      });
      el.apiKeyInput.value = '';
      el.apiSecretInput.value = '';
      addLog('Bybit API Credentials saved securely.', 'success');
      await fetchStatus();
      await fetchWallet();
      await fetchOrders();
    });

    // Execution Buttons
    el.btnBuySupport.addEventListener('click', () => {
      if (!state.supportPrice || state.supportPrice <= 0) {
        alert('Please configure a Support Price first.');
        return;
      }
      placeOrder('Buy', 'Limit', state.supportPrice, 'support');
    });

    el.btnSellResistance.addEventListener('click', () => {
      if (!state.resistancePrice || state.resistancePrice <= 0) {
        alert('Please configure a Resistance Price first.');
        return;
      }
      placeOrder('Sell', 'Limit', state.resistancePrice, 'resistance');
    });

    el.btnBuyMarket.addEventListener('click', () => {
      placeOrder('Buy', 'Market');
    });

    el.btnSellMarket.addEventListener('click', () => {
      placeOrder('Sell', 'Market');
    });

    // Utilities
    el.btnClose50.addEventListener('click', () => closePercentage(50));
    el.btnCancelAll.addEventListener('click', cancelAllOrders);

    // Panic Modal
    el.btnPanicClose.addEventListener('click', () => {
      el.panicModal.classList.add('open');
    });

    el.cancelPanicBtn.addEventListener('click', () => {
      el.panicModal.classList.remove('open');
    });

    el.confirmPanicBtn.addEventListener('click', async () => {
      el.panicModal.classList.remove('open');
      await executeEmergencyClose();
    });

    // Order refresh & Log clear
    el.refreshOrdersBtn.addEventListener('click', fetchOrders);
    el.clearLogsBtn.addEventListener('click', () => {
      el.logBox.innerHTML = '';
    });
  }

  // Main Loop
  async function poll() {
    await fetchTicker();
    await fetchOrders();
  }

  // Init
  async function init() {
    initListeners();
    await fetchStatus();
    await fetchTicker();
    await fetchWallet();
    await fetchOrders();

    // Regular polling: ticker & orders every 1.5s, wallet every 6s
    pollTimer = setInterval(poll, 1500);
    setInterval(fetchWallet, 6000);
  }

  window.addEventListener('DOMContentLoaded', init);
})();
