# CLEANUP + FIX + IMPROVE — COMPREHENSIVE PROMPT

## STEP 0: READ ERROR_LOG.md FIRST
Read C:\Users\kevin\SolanaBot\ERROR_LOG.md completely. All 15 rules apply.

## STEP 1: CODE CLEANUP — scanner.py is 7,446 lines with dead code

### Remove dead strategies entirely:
- **REDDIT strategy**: Remove all REDDIT-related code. It entered "Q" and "cod" 
  which sat flat for 300s and lost -0.087 SOL. Zero wins ever. Delete:
  - REDDIT_ENTRY_SOL, REDDIT_SL_PCT, REDDIT_MAX_HOLD_SEC constants
  - REDDIT_POLL_INTERVAL, REDDIT subreddits list, REDDIT_HEADERS
  - The entire reddit_scanner async function
  - Any REDDIT entry logic in open_sim_position or open_trending_position
  - REDDIT strategy in strategy breakdown on dashboard
  
- **ESTAB strategy**: Never fires, 0 trades across all sessions. Remove entirely.
  - All ESTAB constants, entry logic, token lists
  
- **SWING strategy**: 0 trades all day. Remove or disable completely.
  - SWING constants, watchlist file, swing_scanner function

- **NEAR_GRAD strategy**: Merged into GRAD_SNIPE. Remove separate NEAR_GRAD code.
  - NEAR_GRAD_ENTRY_SOL = 18.0 (BUG: still at $1,500!), NEAR_GRAD_SL_PCT, etc.

- **Twikit/Twitter code**: Already disabled. Remove the entire Twikit login 
  function, Twitter search function, TWITTER_USERNAME/PASSWORD constants.
  Keep TWITTER_ENABLED=false flag but remove ~200 lines of dead Twitter code.

### Remove dead/duplicate utility code:
- Any functions that are defined but never called
- Duplicate price fetching functions (we have get_universal_price now)
- Old bonding curve parser code that's been replaced
- Commented-out code blocks longer than 5 lines
- Debug print statements that aren't behind _dbg()

### Goal: Get scanner.py under 5,000 lines by removing ~2,000 lines of dead code.


## STEP 2: FIX CRITICAL BUGS FOUND RIGHT NOW

### BUG: ROCKET lost -96% (-0.96 SOL) on a SCALP trade
ROCKET [SCALP] SCALP_SL(-96.0%) lost -0.9626 SOL in 3 seconds.
That's a $76 loss on a single SCALP trade. The stop loss should be -2%, 
not -96%. Either:
- The entry price was wrong (entered at a stale/zero price)
- The price crashed 96% in 3 seconds (possible for scam token but SL 
  should have caught it much earlier)
- The position size was too large (1.0 SOL on a micro-cap scam token)

FIX: Add a maximum loss cap per trade. No single trade should ever lose 
more than 5% of position size regardless of what the price does:
```python
# In calc_sim_pnl or close_position:
max_loss = entry_sol * 0.05  # never lose more than 5% per trade
if abs(profit_sol) > max_loss and profit_sol < 0:
    profit_sol = -max_loss  # cap the loss
```

Also add a price sanity check on SCALP entry:
```python
# Before opening any SCALP position:
if price_sol <= 0 or price_sol > 1.0:  # most memecoins < 0.01 SOL
    _dbg(f"SCALP_SKIP: {symbol} insane price {price_sol}")
    return
```

### BUG: NEAR_GRAD_ENTRY_SOL still 18.0 (line 95)
This was supposed to be fixed. Change to 0.5 SOL for sim mode.

### BUG: Position sizes inconsistent
Some strategies use sim-safe sizes, others still have live sizes:
```python
# FIX ALL of these to sim-safe values:
HFT_ENTRY_SOL         = 0.5     # was correct
GRAD_ENTRY_SOL        = 0.5     # was correct  
NEAR_GRAD_ENTRY_SOL   = 0.5     # BUG: was 18.0
TRENDING_ENTRY_SOL    = 0.5     # was 1.0, lower to 0.5
SCALP_ENTRY_SOL       = 0.5     # check current value
REDDIT_ENTRY_SOL      = REMOVE  # strategy removed
WHALE_ENTRY_SOL       = 0.5     # was 2.0, lower to 0.5
```


## STEP 3: IMPLEMENT RESEARCH-BACKED IMPROVEMENTS

### From deep research analysis (50+ sources, academic papers, real performance data):

### A. Grid Trading is already implemented — VERIFY it's working
Check that the grid engine is:
- Tracking 12 tokens (PYTH, ORCA, HNT, W, JUP, RAY, JTO, TNSR, NOS, MNDE, MOBILE, DRIFT)
- Using Jupiter batch pricing every 10s
- Logging GRID_BUY and GRID_SELL to snipe_log.csv
- Grid spacing = 1.5% (geometric, not arithmetic)
- Position per level = 0.5 SOL
- Recentering when price moves 5%+ from grid center

If grid is NOT actually executing trades, find why and fix it.
The grid should be the PRIMARY profit source — research shows 20-60% APR.

### B. Mean Reversion for SCALP — upgrade entry logic
Current SCALP buys "trending" tokens. Research shows buying momentum 
LOSES money for retail bots. Replace with mean reversion:

Entry signal: RSI(14) < 30 AND price below lower Bollinger Band(20,2)
Exit: Price returns to SMA(20) middle band
Stop: 1.5x ATR below entry
Minimum expected move: 1.5% (must clear 0.55% breakeven)

The 1-minute candle engine already exists. Use it to calculate RSI and BB.
Only enter when expected bounce from entry to SMA > 1.5%.

### C. Regime Detection — pause grid during trends
Simple check: if 20-hour price range > 8%, token is trending → pause grid.
If < 8%, token is range-bound → grid active.
Use ADX < 20 as secondary confirmation if candle data available.

### D. Better HFT filtering 
HFT still enters dead flat tokens. The research-backed filters:
- BC velocity >= 15 SOL/min (fast inflow)
- BC progress >= 1.5% (token has traction)  
- Price must have moved +0.3% in last 10s before entry
- Heat >= 50 at entry

Verify these are ACTUALLY ENFORCED in the entry path, not just defined 
as constants. The "Avoided" counter should show vel/bc/mom blocking tokens.

### E. Cap max loss per trade (from ROCKET -96% bug)
No single trade should lose more than 0.05 SOL in sim mode.
Add a hard cap in close_position():
```python
if profit_sol < -0.05:
    profit_sol = -0.05  # hard cap sim loss
    _dbg(f"LOSS_CAP: {p.symbol} capped at -0.05 SOL (was {original})")
```


## STEP 4: STRATEGY CONFIGURATION FOR PROFIT

After cleanup, the bot should have exactly these strategies:

| Strategy | What It Does | Entry Size | Max Open | Goal |
|---|---|---|---|---|
| GRID | Buy/sell at preset levels on 12 established tokens | 0.5 SOL/level | 5 levels × 12 tokens | Steady 0.95%/cycle |
| SCALP | Mean reversion on DEXScreener trending tokens | 0.5 SOL | 10 | Buy oversold, sell at mean |
| HFT | Snipe new pump.fun launches via Geyser WebSocket | 0.5 SOL | 5 | Catch moonshots (+5-100%) |
| GRAD_SNIPE | Enter tokens graduating to PumpSwap AMM | 0.5 SOL | 5 | Catch graduation pumps |
| TRENDING | DEXScreener trending with quality filters | 0.5 SOL | 5 | Momentum on verified tokens |

REMOVED: REDDIT, ESTAB, SWING, NEAR_GRAD, MOMENTUM (replaced by GRID)

### Capital Allocation (100 SOL sim):
- Grid: 30 SOL reserved (12 tokens × 5 levels × 0.5 SOL)
- Active trading (SCALP+HFT+GRAD+TRENDING): 30 SOL max deployed
- Cash reserve: 40 SOL never touched

### Fee Model (ERROR_LOG Rules 1-3):
- Liquid tokens (Jupiter/Raydium): 25 bps (0.25%) per side = 0.55% breakeven
- Pump.fun bonding curve: 100 bps (1%) per side = 2.2% breakeven  
- ALL take-profit levels MUST be above breakeven
- Grid: 1.5% spacing > 0.55% breakeven ✓
- SCALP mean reversion: target SMA = typically 2-5% > 0.55% ✓
- HFT: TP at +5% > 2.2% pump.fun breakeven ✓

## STEP 5: COMMIT AND VERIFY

After all changes:
1. Verify scanner.py is under 5,500 lines (removed ~2,000 lines of dead code)
2. Verify all position sizes are 0.5 SOL or less
3. Verify no strategy references REDDIT, ESTAB, SWING, or NEAR_GRAD
4. Verify grid engine is logging to snipe_log.csv
5. Verify ROCKET-style -96% losses are capped
6. Run scanner.py and confirm it starts without errors
7. Run dashboard.py and confirm it loads

```
git add -A && git commit -m "Major cleanup: remove dead strategies, fix position sizes, cap losses, verify grid trading, mean reversion SCALP"
```

## DO NOT CHANGE:
- Jupiter price integration (working)
- Geyser WebSocket detection (working)
- Adaptive trailing stops (working)
- Moonbag exit logic (working)
- Web dashboard structure (working)
- Groq AI engine (working)
- ERROR_LOG.md (append only, never delete)
