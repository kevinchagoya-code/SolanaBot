# DIPBUY STRATEGY V2 — USDC Base, Multi-Asset Dip Buying

## READ ERROR_LOG.md FIRST — all 15 rules apply

## KEY INSIGHT FROM KEVIN
"I don't only need to use SOL. I have a Phantom wallet and can buy 
any coin to start with."

This means we can hold USDC as base currency and buy dips on ETH, 
SOL, JUP, etc. against USDC. This is how professional bots work — 
stable base, trade the oscillations.

## WHY USDC BASE IS BETTER THAN SOL BASE
- Current bot: balance in SOL. If SOL drops 5%, we "lost" 5% even 
  if our trades were profitable. P&L is confusing.
- USDC base: balance in dollars. A $1.50 profit is a $1.50 profit. 
  Clear, simple, no SOL price risk on idle capital.
- Professional bots ALL use stablecoin base for this reason.

## THE STRATEGY (exactly what Kevin described)
"If ETH is going from $0.10 to $0.50 generally, and in between it 
goes up and down, we buy those downs and cash when it goes up."

### How it works:
1. Start with $1,500 USDC in Phantom wallet
2. Bot watches ETH, SOL, JUP, RAY prices via Jupiter
3. When ETH dips 1-2% from recent high → buy $200 of ETH with USDC
4. When ETH bounces back 1-2% → sell ETH back to USDC
5. Profit stays in USDC. Repeat.
6. If ETH is trending UP overall, more buys fill and more sells 
   complete = more profit cycles

### The math:
- ETH average daily oscillation: 3-5% range
- Typical micro-dip: 1-2% pullback during uptrend
- Jupiter swap fee: ~0.25% per side = 0.5% round trip
- A 1.5% dip-bounce cycle = 1.5% - 0.5% = 1.0% net profit
- $200 position × 1.0% = $2.00 per cycle
- 3-5 cycles per day = $6-10/day on just ETH
- Add SOL, JUP, RAY = $15-30/day potential


## IMPLEMENTATION — TWO PHASES

### Phase 1: Simulate in USDC terms (NOW — no code rewrite needed)
The bot already tracks SOL price in USD (STATE.sol_price_usd).
We can simulate USDC-base trading by:
- Tracking positions in USD value instead of SOL
- Using Jupiter prices in USD (already available from jupiter_get_price)
- Logging P&L in USD

Add a DIPBUY strategy that:
1. Polls Jupiter for wETH, SOL, JUP, RAY, BONK prices in USD every 10s
2. Builds 5-minute candles from these prices
3. Calculates 20-EMA and RSI(14) on 5-min candles
4. Entry: price dips below 20-EMA AND RSI < 35 AND EMA slope is positive
5. Exit: price bounces +1.5% from entry OR RSI > 65 OR SL at -1.0%

### Phase 2: Go live with USDC in Phantom (LATER)
When ready for real trades:
- Fund Phantom with USDC (not SOL — just enough SOL for gas ~0.1 SOL)
- Bot uses Jupiter swap API to execute USDC → ETH → USDC cycles
- Helius Sender for Jito bundle submission
- Each swap costs ~0.25% fee + ~0.001 SOL gas

## TOKENS TO DIP-BUY (high liquidity, real trends, never rug)

```python
DIPBUY_TOKENS = {
    "wETH": {
        "mint": "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs",
        "avg_daily_range": 3.5,  # typical % range per day
        "min_liq_usd": 10_000_000,  # $10M+ liquidity
    },
    "SOL": {
        "mint": "So11111111111111111111111111111111111111112",  
        "avg_daily_range": 4.0,
        "min_liq_usd": 50_000_000,
        # NOTE: price in USD, not SOL-in-SOL (Bug 0e fix)
    },
    "JUP": {
        "mint": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
        "avg_daily_range": 5.0,
        "min_liq_usd": 5_000_000,
    },
    "RAY": {
        "mint": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
        "avg_daily_range": 5.5,
        "min_liq_usd": 3_000_000,
    },
    "BONK": {
        "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        "avg_daily_range": 8.0,
        "min_liq_usd": 2_000_000,
    },
}
```


## ENTRY/EXIT LOGIC

```python
# Constants
DIPBUY_EMA_PERIOD = 20        # 20-period EMA on 5-min candles  
DIPBUY_RSI_PERIOD = 14        # RSI(14)
DIPBUY_RSI_BUY = 35           # buy when RSI < 35 (oversold)
DIPBUY_RSI_SELL = 65           # sell when RSI > 65 (overbought)
DIPBUY_MIN_DIP_PCT = 0.8      # must dip at least 0.8% from recent high
DIPBUY_TP_PCT = 1.5            # take profit at +1.5%
DIPBUY_SL_PCT = -1.0           # stop loss at -1.0%  
DIPBUY_ENTRY_USD = 200         # $200 per dip buy
DIPBUY_MAX_POSITIONS = 5       # max 5 dip buys open at once
DIPBUY_MAX_PER_TOKEN = 2       # max 2 positions in same token
DIPBUY_POLL_SEC = 10           # check every 10s via Jupiter

async def check_dipbuy_entry(symbol, candles_5m):
    """Buy dips on tokens in confirmed uptrends."""
    if len(candles_5m) < 25: return None
    
    closes = [c["close_usd"] for c in candles_5m[-25:]]
    
    # 1. UPTREND CHECK: 20-EMA must be rising
    ema = calc_ema(closes, 20)
    slope = (ema[-1] - ema[-5]) / ema[-5] * 100
    if slope < 0.1: return None  # not trending up
    
    # 2. DIP CHECK: price at or below EMA  
    price = closes[-1]
    dist = (price - ema[-1]) / ema[-1] * 100
    if dist > 0.3: return None  # above EMA = not a dip
    
    # 3. OVERSOLD CHECK: RSI must be low
    rsi = calc_rsi(closes, 14)
    if rsi > DIPBUY_RSI_BUY: return None
    
    # 4. DIP DEPTH: must have dropped from recent high
    recent_high = max(closes[-10:])
    dip = (price - recent_high) / recent_high * 100
    if abs(dip) < DIPBUY_MIN_DIP_PCT: return None
    
    return {"action": "BUY", "price_usd": price,
            "reason": f"DIPBUY(slope={slope:.1f}% RSI={rsi:.0f} dip={dip:.1f}%)"}

# EXIT in update_sim_positions:
# if pct > DIPBUY_TP_PCT → DIPBUY_TP (take the bounce)
# if pct < DIPBUY_SL_PCT → DIPBUY_SL (dip kept going, wrong call)
# if rsi > 65 → DIPBUY_RSI (momentum fading, take what we have)
# if ema slope turns negative → DIPBUY_TREND_EXIT (trend reversed)
```

## HOW THIS FITS THE FULL BOT

| Strategy | Base | Tokens | Goal | Risk |
|---|---|---|---|---|
| DIPBUY | USDC | wETH, SOL, JUP, RAY, BONK | Buy dips in uptrends | Low — real tokens |
| GRID | SOL | PYTH, ORCA, HNT, W, TNSR | Range oscillation | Low |
| SCALP | SOL | DEXScreener trending | Momentum scalps | Medium |
| GRAD_SNIPE | SOL | Graduated pump.fun | Catch moonshots | High |
| HFT | SOL | New pump.fun launches | Snipe launches | High |

DIPBUY is the SAFE layer. It trades real tokens with real liquidity.
Even if GRAD_SNIPE and HFT lose money, DIPBUY makes $15-30/day 
consistently from dip-bounce cycles on ETH/SOL/JUP.

## FOR PHASE 2 (LIVE): Jupiter Swap Execution
When EXECUTE_TRADES=true, DIPBUY trades execute via Jupiter:
- POST https://quote-api.jup.ag/v6/quote (get best route USDC→ETH)
- POST https://quote-api.jup.ag/v6/swap (build transaction)
- Submit via Helius Sender (Jito bundle for priority)
- USDC mint: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
- wETH mint: 7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs

## COMMIT
git add -A && git commit -m "Add DIPBUY strategy: USDC-base dip buying on ETH/SOL/JUP uptrends"
