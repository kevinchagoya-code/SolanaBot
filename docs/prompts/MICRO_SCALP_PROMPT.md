# COMPREHENSIVE IMPROVEMENT PROMPT — Based on Micro-Scalping Research

## READ ERROR_LOG.md FIRST — all 15 rules apply

## CURRENT STATE PROBLEMS (from dashboard_data.json right now)
1. JTO opened 5 DUPLICATE positions — same token, same strategy. Bug.
2. BENJ -92.5%, Doug -41.8% — GRAD_SNIPE entering scam tokens
3. MEZo held 458 seconds at -3.2% — SCALP exit not firing
4. Geyser WebSocket HTTP 403 — connection being rejected
5. Grid is WORKING (PYTH +1.0% cycle completed) but too slow/few cycles

## THE GOAL: $0.10-0.30 per minute = many small fast trades

## WHAT RESEARCH SAYS WE NEED TO CHANGE

### CHANGE 1: Route through CLMM pools (0.04-0.05% fee), NOT standard AMM (0.25%)
This is the #1 improvement. Current bot assumes 0.25% fee per side.
CLMM pools on SOL/USDC, JUP/USDC cost only 0.04-0.05% per side.
Round trip: 0.10% instead of 0.50%. This QUINTUPLES the profit per trade.

A $20 trade capturing 1.5% move:
- Old (0.25% AMM): 1.5% - 0.50% = 1.0% net = $0.20 profit
- New (0.05% CLMM): 1.5% - 0.10% = 1.4% net = $0.28 profit

Implementation: When using Jupiter quote API, check which pool it routes 
through. For SOL/USDC, JUP/USDC, RAY/USDC — Jupiter already finds CLMM 
pools automatically. Update calc_sim_pnl fee model:

```python
# UPDATE fee model in calc_sim_pnl:
CLMM_TOKENS = {"SOL", "JUP", "RAY", "ORCA", "PYTH", "HNT", "wETH", "BONK"}
# These route through 0.04-0.05% CLMM pools via Jupiter
CLMM_FEE_BPS = 5        # 0.05% per side
AMM_FEE_BPS = 25         # 0.25% for standard AMM (meme coins)
PUMP_FEE_BPS = 100       # 1.0% for pump.fun bonding curve

def get_fee_bps(symbol, graduated=True):
    if symbol in CLMM_TOKENS:
        return CLMM_FEE_BPS  # 0.05%
    elif graduated:
        return AMM_FEE_BPS   # 0.25%
    else:
        return PUMP_FEE_BPS  # 1.0%
```

### CHANGE 2: Faster trade cycle — 10-30 second holds, not 60-600 seconds
Current SCALP holds positions 60-600 seconds. Research says profitable
micro-scalpers hold 10-60 seconds max. The longer you hold, the more
random noise kills your trade.

```python
# NEW micro-scalp parameters for established tokens:
MICRO_MAX_HOLD_SEC = 60      # hard max 60 seconds
MICRO_TIME_EXIT_SEC = 30     # if flat after 30s, exit
MICRO_TP_PCT = 1.5           # take profit at +1.5%
MICRO_SL_PCT = -0.5          # tight stop at -0.5% (NOT -2% or -5%)
MICRO_ENTRY_SOL = 0.25       # $20 per trade at $80/SOL
MICRO_MAX_POSITIONS = 8      # run 8 parallel trades
MICRO_POLL_SEC = 3            # check price every 3 seconds (not 10)
```

### CHANGE 3: Parallel trades on multiple tokens simultaneously
Instead of one trade at a time, run 5-8 micro-trades in parallel:
- SOL dips → buy $20 of SOL
- JUP dips → buy $20 of JUP  
- PYTH dips → buy $20 of PYTH
- All bounce together → 3 × $0.20 = $0.60 in 30 seconds

The bot already supports multiple simultaneous positions. Just increase
MAX_PER_STRATEGY and reduce position sizes to spread across more tokens.


### CHANGE 4: MUCH tighter stop-loss (0.3-0.5%, not 2-5%)
Current SCALP_SL_PCT = -2.0 to -5.0%. That's way too loose for micro-scalps.
A -5% loss ($1.00 on $20) wipes out 5 winning trades at $0.20 each.
Research says: keep average loss at 1-1.5x average win.

If average win = $0.20 (+1%), average loss must be < $0.30 (-1.5%).
With tight stop at -0.5% ($0.10 loss), win/loss ratio is 2:1 = very profitable.

```python
# Micro-scalp risk: tight stops, small losses
MICRO_SL_PCT = -0.5          # $0.10 loss on $20 position
# At 65% WR: 65 wins × $0.20 = $13.00, 35 losses × $0.10 = $3.50
# Net per 100 trades: $9.50 = $0.095 per trade average
# At 2 trades/minute: $0.19/minute ← hits the target
```

### CHANGE 5: Fix duplicate position bug
JTO has 5 identical positions open. The bot must check:
```python
# Before opening ANY position:
if mint in STATE.sim_positions:
    return  # already have a position in this token
```
This check may exist but isn't working for GRID/MOMENTUM entries.

### CHANGE 6: Fix Geyser 403 error
"Geyser FULL ERROR: server rejected WebSocket connection: HTTP 403"
This means Helius is rejecting the WebSocket. Possible causes:
- API key expired or rate limited
- WebSocket URL changed
- Too many concurrent connections

Fix: Add reconnection logic with exponential backoff. If 403 persists,
log it and continue with Jupiter/DEXScreener only (HFT won't work 
without Geyser but GRID/SCALP/DIPBUY will).


### CHANGE 7: Add MICRO_SCALP as new strategy for established tokens
This is the core money-maker. Different from current SCALP (which trades
random DEXScreener trending tokens). MICRO_SCALP ONLY trades established
tokens with deep CLMM liquidity.

```python
MICRO_TOKENS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "PYTH": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "JTO": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
    "ORCA": "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
    "wETH": "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs",
}
# These NEVER rug. Deep liquidity. 0.05% CLMM fees.
# Each oscillates 3-8% daily = many micro-dip opportunities.
```

Entry logic for MICRO_SCALP:
```python
async def check_micro_entry(symbol, prices_1m):
    """Detect micro-dip on established token. 
    Uses 1-minute price history from Jupiter polling."""
    if len(prices_1m) < 20: return None
    
    current = prices_1m[-1]
    # Simple: price dropped 0.3%+ from 5-minute high
    recent_high = max(prices_1m[-5:])
    dip = (current - recent_high) / recent_high * 100
    
    if dip < -0.3:  # dipped at least 0.3%
        # Confirm it's bouncing (last price > price 2 ticks ago)
        if len(prices_1m) >= 3 and prices_1m[-1] > prices_1m[-3]:
            return {
                "action": "BUY",
                "reason": f"MICRO(dip={dip:.1f}% bouncing)",
                "tp": current * 1.015,   # +1.5% TP
                "sl": current * 0.995,   # -0.5% SL
            }
    return None
```

Exit logic:
```python
# In update_sim_positions for MICRO_SCALP:
# 1. TP at +1.5% → MICRO_TP (the target)
# 2. SL at -0.5% → MICRO_SL (tight stop, small loss)
# 3. Flat 30s → MICRO_FLAT (exit if not moving)
# 4. Hard cap 60s → MICRO_TIME (never hold longer)
# 5. Proactive TP: if +1.0% and not rising → MICRO_TP1 (take it)
```


### CHANGE 8: Price polling every 3 seconds for MICRO tokens
Current bot polls every 10 seconds. For 30-second trades, 10s polling
means you only see 3 price points during the entire trade. Need 3s 
polling for MICRO tokens specifically.

Use jupiter_get_prices_batch() on all 8 MICRO_TOKENS every 3 seconds.
This is ~20 req/min to Jupiter (well within 60/min free limit).
Build 1-minute candles from these 3-second price samples.

### CHANGE 9: Track P&L per trade in USD, not just SOL
Add a usd_profit field to each trade log entry:
  usd_profit = profit_sol * sol_price_usd_at_exit
This makes it easy to verify we're hitting $0.10-0.30 per trade.

### CHANGE 10: Circuit breakers (from research — most bots that fail skip these)
```python
DAILY_LOSS_LIMIT_USD = 30.0     # stop all trading if down $30 today
HOURLY_LOSS_LIMIT_USD = 10.0    # pause 1 hour if down $10 in last hour
CONSECUTIVE_LOSS_LIMIT = 5      # pause 10 min after 5 losses in a row
TX_FAIL_RATE_LIMIT = 0.20       # stop if >20% of trades fail to execute
```

## FINAL STRATEGY LINEUP AFTER CHANGES

| Strategy | Tokens | Hold Time | TP | SL | Fee | Goal |
|---|---|---|---|---|---|---|
| MICRO_SCALP | SOL,JUP,RAY,PYTH,BONK,JTO,ORCA,wETH | 10-60s | +1.5% | -0.5% | 0.05% CLMM | $0.10-0.30/trade |
| GRID | Same tokens | Hours | +1.0% per level | Grid rebalance | 0.05% CLMM | Steady background |
| GRAD_SNIPE | Graduated pump.fun | 30-600s | Trailing | -15% | 0.25% AMM | Moonshots |
| SCALP | DEXScreener trending | 10-60s | +3% proactive | -2% | 0.25% AMM | Meme momentum |

MICRO_SCALP is the new primary strategy. GRID runs in background.
GRAD_SNIPE is the lottery ticket. SCALP stays for meme coins.
HFT is disabled unless Geyser 403 is fixed.

## THE MATH THAT HITS $0.10-0.30/min
- 8 MICRO tokens polled every 3 seconds
- Each token dips 3-5 times per hour
- Bot catches ~50% of dips = ~15 entries per hour across all tokens
- 65% win rate: 10 wins × $0.20 = $2.00, 5 losses × $0.10 = $0.50
- Net: $1.50/hour from MICRO alone = $0.025/min
- PLUS grid cycles: ~$0.50/hour
- PLUS occasional SCALP/GRAD wins: ~$0.50/hour
- Total: ~$2.50/hour = $0.04/min with current $20 position sizes
- To hit $0.10/min: increase position size to $50-60 per trade
- To hit $0.30/min: increase position size to $150-200 per trade OR 
  scale to $5,000 capital with $50 positions × more parallel trades

## IMPLEMENTATION ORDER
1. Fix duplicate position bug (JTO × 5) — prevents waste
2. Update fee model for CLMM tokens (0.05% not 0.25%)
3. Add MICRO_SCALP strategy with 3s polling on 8 tokens
4. Tighten stop-loss to -0.5% for MICRO
5. Add circuit breakers
6. Increase price poll frequency to 3s for MICRO tokens
7. Track USD profit per trade

## DO NOT CHANGE
- Grid trading engine (it's working — PYTH cycle completed!)
- Proactive TP tiers (SCALP_TP2 working — CRIME +2.5%)
- Moonbag trailing (BROCCOLI +15.1% captured!)  
- Jupiter price integration
- Web dashboard structure
- Loss cap at 0.05 SOL

## COMMIT
git add -A && git commit -m "Add MICRO_SCALP: fast micro-trades on CLMM tokens, 3s polling, tight stops, parallel positions"
