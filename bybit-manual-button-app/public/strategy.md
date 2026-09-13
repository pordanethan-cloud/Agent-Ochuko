# Spot Micro-Scalping Strategy — Manual Range-Trading Draft v1.3

> **Five-line summary**
> Trade liquid spot markets manually; do not use leverage, shorting, or automated decisions.
> Trade only a stable, gradually moving range: consider buys near support and sells near resistance.
> Use RSI and Stochastic as confirmation, never as standalone instructions to enter or exit.
> Avoid the middle of the range, breakouts, aggressive chasing, and thin or high-slippage conditions.
> Judge every trade by net result after fees, spread, slippage, and stop execution—not chart movement.

## Purpose

This document defines a manual, long-only spot micro-scalping approach for liquid crypto markets. The trader reads price action, identifies the range, interprets RSI and Stochastic, decides whether conditions are valid, and enters and exits manually.

This is not an automated system, signal bot, alert engine, or algorithmic strategy. No indicator settings, risk limits, range widths, spread thresholds, targets, stop distances, or order rules are hard-coded. Those choices remain deliberate, session-by-session trader decisions.

> This is a trading process, not a return guarantee. Crypto markets are volatile. Record results after fees, spread, slippage, and losses—not chart movement alone.

---

## 1. Scope and Trading Style

| Item | Approach |
|---|---|
| Market type | Liquid spot pairs only |
| Direction | Buy first, then sell; no shorting, margin, borrowing, or leverage |
| Holding period | Intraday only unless a separate plan is made before entry |
| Trade style | Manual range-bound mean-reversion micro-scalping |
| Market selection | Active volatility with usable liquidity, controlled spread, and practical exit depth |
| Decision-maker | The trader, using chart and order-book judgment |
| App role | Optional manual order-entry and record-keeping interface only |

The objective is to trade repeated movement within a stable, identifiable range. The goal is not to catch breakouts, chase every move, or predict every candle.

---

## 2. Core Market Idea: A Gradually Moving Range

The preferred environment is a market that rotates between a support floor and a resistance ceiling. The boundaries may move gradually over time, but they must not expand or shift aggressively. Price may have a mild broader trend, but the immediate structure should still behave like a range with repeated reactions at both edges.

Consider buying near the lower edge only after support holds and momentum begins to turn upward. Consider selling as price reaches the upper edge and momentum weakens. The middle of the range is generally avoided because there is less remaining upside and less clarity about which boundary price will test next.

RSI and Stochastic are confirmation tools, not trade commands. An oversold reading does not make a long safe during a breakdown, and an overbought reading does not guarantee a reversal during a breakout.

---

## 3. Range Structure

### Defining the range manually

The trader identifies a support floor and resistance ceiling from the selected chart timeframe. The range should show repeated reactions at both boundaries and should be understandable without forcing lines onto random price points.

```text
range width = resistance − support
range position % = (current price − support) ÷ range width × 100
```

| Price location | Interpretation | Manual response |
|---|---|---|
| Lower part of the range | Price is near the support floor | Watch for support holding and upward confirmation before considering a buy |
| Middle of the range | Price is between the boundaries | Normally wait; reward-to-risk is usually weaker |
| Upper part of the range | Price is near the resistance ceiling | Consider taking profit, selling, or avoiding a fresh long |
| Outside the range | Price has moved beyond support or resistance | Stop applying range logic and reassess market structure |

The lower-quarter and upper-quarter concepts are visual guides, not hard-coded trigger percentages. The trader decides the usable entry and exit areas based on range width, price behaviour, costs, and current volatility.

### Signs the range is valid

- Price has clearly reacted from support more than once.
- Price has clearly reacted from resistance more than once.
- The range has existed long enough on the chosen timeframe to be observable.
- Price is rotating rather than persistently forming directional higher highs/higher lows or lower highs/lower lows.
- Volatility allows a meaningful move between the edges without the order book becoming disorderly.
- Spread and available depth make the intended position practical to enter and exit.

### Signs to stop range trading

Suspend range logic when price action changes character: a decisive close outside a boundary, abrupt volume expansion during a break, repeated failure to return into the range, rapidly widening candles, widening spread, or an order book clearing too quickly to judge fills reliably.

Do not keep buying simply because RSI or Stochastic appears oversold. When support fails, the original long thesis is invalid until a new stable structure appears.

---

## 4. Manual Entry Framework

A possible long setup begins only when price is near the manually identified support area. The trader then checks whether support is holding, whether selling pressure is easing, and whether RSI/Stochastic are turning upward in a way that agrees with price structure.

Before placing an order, manually identify the invalidation point, expected exit area, visible spread, available liquidity, and realistic total cost. If price is in the middle of the range, the range is unclear, or the remaining move is too small after costs, take no trade.

### Manual entry checklist

- Is the pair liquid enough for the intended trade size?
- Is price near a credible support area rather than in the middle of the range?
- Has support shown a real response rather than a single weak bounce?
- Are RSI and Stochastic turning in the same direction as the intended trade?
- Is there enough distance to the intended exit area after all likely costs?
- Is the invalidation level clear before entry?
- Is this a planned setup rather than a response to fear of missing out or an earlier loss?

If any answer is unclear, wait.

---

## 5. Manual Exit and Risk Discipline

Decide position size, protective exit, and intended profit area before buying. Select these manually for current market conditions and record them in the journal. They are not pre-filled by the app or imposed as universal percentages.

A protective stop belongs where the support-based idea is genuinely invalid, not at a random distance chosen only to make position size look attractive. Understand that exchange stop orders can slip or fill differently in fast markets.

Take profit as price approaches resistance, when momentum weakens near the upper range area, or when price loses the short-term structure supporting the move. Do not wait for the exact ceiling if evidence shifts. Do not move a protective stop farther away to avoid accepting a loss, and do not add to a losing spot position.

Before each session, manually write a maximum loss, maximum number of attempts, and conditions that end the session. The session ends when that pre-written boundary is reached, execution quality deteriorates, the market stops matching the range thesis, or focus declines.

---

## 6. Execution Cost: Fees, Spread, and Slippage

A volatile meme coin is useful only if its movement can exceed real execution costs. Do not deliberately seek high slippage. Seek enough volatility for opportunity alongside enough liquidity to keep entries and exits predictable.

```text
total expected round-trip cost =
buy fee
+ sell fee
+ visible spread
+ entry slippage
+ exit slippage
+ possible stop slippage
```

Estimate these costs manually from the exchange fee schedule and live order book before entry. A displayed chart move is not profit. A trade has room to work only when expected gross movement is materially larger than likely all-in cost.

For a fast entry, an aggressive limit order can define the maximum acceptable price. The trader decides whether to use a passive limit, aggressive limit, or no order at all based on live conditions. This document does not prescribe fixed chase buffers, expiry periods, or slippage limits.

---

## 7. App Boundary: Manual Tool, Not an Automated Trader

The app is intentionally kept simple to minimise complexity and avoid introducing extra latency. It must not independently scan markets, interpret indicators, define ranges, issue alerts, calculate a setup score, send entries, chase orders, close positions, or change risk limits.

The trader reads the exchange chart and order book, makes the judgment, and chooses the action. If an app is used, its role is limited to receiving a direct manual Buy or Sell instruction and showing information returned by the exchange. Any protective order is manually chosen and submitted by the trader using available exchange functionality.

The app contains no hard-coded trading thresholds. It does not assume fixed RSI/Stochastic settings, fixed range-zone percentages, fixed risk per trade, fixed daily loss, fixed target, fixed stop distance, fixed minimum volume, fixed depth, fixed spread, fixed slippage, or fixed trade count.

### Minimal manual order flow

1. Manually review chart structure, RSI, Stochastic, volume, spread, and order-book depth.
2. Write or select the intended entry, invalidation, exit idea, and size.
3. Manually submit the Buy order.
4. After fill, manually submit the protective exchange-side order if it is part of the plan.
5. Manually watch the position and submit Sell when the exit condition is met or the thesis is invalid.
6. Record the completed trade, including real fees and fill quality.

The system must not interpret a manual choice as permission to perform further trading actions on its own.

---

## 8. Market and Venue Selection

Choose the venue that gives the best measured all-in execution for the exact pair being traded. Headline fees alone are insufficient. Compare the same pair across candidate venues using actual order-book depth, spread, fills, and fee tier.

Manually record actual maker/taker fees, spread at proposed entry, nearby liquidity, likely slippage, partial-fill behaviour, stop-order behaviour, access and jurisdiction constraints, and practical execution reliability. A lower-fee exchange can still be more expensive when the spread is wide or liquidity is thin.

---

## 9. Daily Workflow

### Before trading

- Choose markets that appear liquid and active enough for the intended style.
- Decide manually whether the market is ranging, trending, breaking out, or disorderly.
- Identify support, resistance, possible invalidation, and potential exit area.
- Review live spread and order-book depth.
- Write the session’s personal risk boundary and stop conditions.
- Trade only if a range-based setup is clear.

### During trading

- Buy only near a credible support area, not in the middle of the range.
- Use RSI/Stochastic as confirmation, never as a standalone command.
- Keep the original invalidation logic intact.
- Do not add to a losing position.
- Do not turn a failed range into a hope trade.
- Stop trading when structure or execution quality changes.

### After trading

- Record entry, exit, size, order type, fees, spread, and observed slippage.
- Note range boundaries and why the trade was taken.
- Record whether the exit matched the plan.
- Record errors separately from normal losses.
- Review a group of trades before changing personal rules.

---

## 10. Trade Journal Template

| Date/time | Venue | Pair | Market condition | Support | Resistance | Entry | Invalidation | Exit idea | Size | Exit | Fees | Spread/slippage | Net result | Rule followed? | Notes |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

Review a meaningful group of manual trades to determine whether range identification is accurate, entries near support remain positive after costs, exits are appropriate, fees/spread/slippage consume the edge, losses arise from normal invalidation or broken discipline, and a particular pair or venue provides better execution.

Prediction quality alone is not an edge. The method is viable only if net results remain positive after all costs and losing trades.

---

## Non-Negotiable Principles

1. Trade manually; no automated monitoring, signal generation, order placement, exits, or risk controls.
2. Keep all parameters manually chosen; no hard-coded trading values at this stage.
3. Trade range edges, not the middle of the range.
4. Use RSI and Stochastic to confirm price behaviour, not replace it.
5. Do not deliberately seek high slippage.
6. Stop applying range logic when the range breaks or becomes disorderly.
7. Do not add to losing positions or widen an invalidation point.
8. Judge every result after fees, spread, and slippage.
9. Preserve capital and discipline before pursuing frequency or return.

## Strategy Summary

**Method:** Manual long-only spot scalping of stable, liquid ranges.  
**Entry concept:** Near support after price-action and indicator confirmation.  
**Exit concept:** Near resistance or when the move loses supporting structure.  
**Tools:** Manually read charts, RSI, Stochastic, volume, and the order book.  
**App policy:** A simple manual interface only; no automation and no hard-coded trading parameters.  
**Priority:** Clear structure, controlled execution cost, disciplined risk, and honest journaling.
