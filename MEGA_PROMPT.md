# COMBINED MEGA-PROMPT — ALL FIXES + DASHBOARD UPGRADE

## OVERVIEW
This prompt combines 3 fix categories + 1 dashboard upgrade:
1. HFT filter tuning (re-enable disabled filters)
2. GRAD entry delay (stop FETCH_FAIL spam)
3. SCALP open to ALL Solana tokens (not just pump.fun)
4. Dashboard upgrade (live positions, ATR, better real-time feel)

Read this ENTIRE prompt before making changes. Then implement in order.

---

## 1. HFT FILTER TUNING — Re-enable Disabled Filters

These filters ALREADY EXIST in scanner.py (lines 76-81) but are 
disabled or set too low. Just change the values:

```
HFT_MIN_BC_VELOCITY  = 25.0    # was 10.0 — research proves fast inflow predicts success
HFT_MIN_BC_PROGRESS  = 2.0     # was 0.0 (disabled) — filters 90% dead-on-arrival tokens
HFT_MIN_PRICE_MOVE   = 0.5     # was 0.0 (disabled) — only enter tokens already moving up
HFT_MIN_BUYERS       = 3       # already 3, keep it
```

IMPORTANT: Verify these filters are actually ENFORCED in the HFT entry 
logic. Search for where HFT positions are opened and confirm that 
bc_velocity, bc_progress, and price_move checks happen BEFORE entry.
The "Avoided" dashboard counter should show vel: blocking some tokens.
If velocity is blocking 0, the check isn't wired up — fix that.

---

## 2. GRAD_SNIPE ENTRY DELAY — Stop Entering Before DEXScreener Indexes

Find the GRAD_SNIPE entry function. After detecting a graduation event,
DON'T enter immediately. Add a delay + price verification:

```python
# After graduation detected:
_dbg(f"GRAD_WAIT: {symbol} — waiting 45s for DEXScreener to index")
await asyncio.sleep(45)

# Try to get price
price = await dexscreener_get_price(session, mint)
if not price or price <= 0:
    _dbg(f"GRAD_WAIT2: {symbol} — no price at 45s, waiting 30 more")
    await asyncio.sleep(30)
    price = await dexscreener_get_price(session, mint)

if not price or price <= 0:
    _dbg(f"GRAD_SKIP: {symbol} — no price after 75s, skipping")
    return

# NOW enter with confirmed price
_dbg(f"GRAD_ENTER: {symbol} — price confirmed at {price:.10f}")
```

This eliminates ALL "graduated but DEX+POOL both failed" errors.

---

## 3. SCALP — Open to ALL Solana Tokens (Not Just Pump.fun)

### THE PROBLEM
The dexscreener_scanner function (~line 4085) ONLY looks at pump.fun tokens.
- Search URL is literally: search?q=pump.fun
- Filter at lines 4108-4112 skips anything without "pump" in URL/labels
- This means Raydium, Orca, Jupiter, PumpSwap, Meteora tokens all get SKIPPED
- BONK/JUP/WIF leak through but are too big to move. Real opportunities are missed.

### THE FIX

#### A. Remove the pump.fun-only filter (lines ~4108-4112)
Change from:
```python
if "pump" not in item_url.lower() and "pump" not in desc.lower():
    if "pump" not in labels.lower(): continue
```
To:
```python
# Accept any Solana token — filter by metrics (mcap, volume, heat), not by DEX
pass  # removed pump.fun-only filter
```

#### B. Add broader DEXScreener search queries
In the dexscreener_scanner URL list, add Solana-wide searches:
```python
# EXISTING (keep):
"https://api.dexscreener.com/token-boosts/top/v1",
"https://api.dexscreener.com/token-boosts/latest/v1",

# CHANGE search from pump.fun-only to broader:
"https://api.dexscreener.com/latest/dex/search?q=solana%20trending",
"https://api.dexscreener.com/latest/dex/search?q=solana%20gainers",
```

#### C. Add SCALP blacklist + mcap filter (near line 114)
```python
SCALP_MAX_MCAP        = 10_000_000  # $10M max market cap
SCALP_MIN_MCAP        = 50_000      # $50K min
SCALP_MIN_LIQUIDITY   = 10_000      # $10K min liquidity
SCALP_MIN_5M_CHANGE   = 1.0         # must have moved +1% in 5 min
SCALP_BLACKLIST = {
    "SOL", "USDC", "USDT", "BONK", "WIF", "JUP", "PYTH", "BRETT",
    "POPCAT", "MEW", "BOME", "PENGU", "RAY", "ORCA", "JTO", "RENDER",
    "HNT", "MOBILE", "FIDA", "MNGO", "STEP", "ATLAS", "FLOKI",
    "PEPE", "SHIB", "DOGE", "WBTC", "WETH"
}
```

#### D. Enforce filters in SCALP entry
In dexscreener_scanner, before opening a SCALP position, add:
```python
if symbol.upper() in SCALP_BLACKLIST: continue
if mcap > SCALP_MAX_MCAP or mcap < SCALP_MIN_MCAP: continue
liq = item.get("liquidity", {}).get("usd", 0) if isinstance(item.get("liquidity"), dict) else 0
if liq < SCALP_MIN_LIQUIDITY: continue
chg_5m = item.get("priceChange", {}).get("m5", 0) or 0
if chg_5m < SCALP_MIN_5M_CHANGE: continue
```

---

## 4. DISABLE TWITTER/TWIKIT (cleanup)

Add to .env: TWITTER_ENABLED=false

At the top of the Twikit login function, add:
```python
TWITTER_ENABLED = os.getenv("TWITTER_ENABLED", "true").lower() == "true"

# In the login function:
if not TWITTER_ENABLED:
    _dbg("Twitter disabled — skipping Twikit login")
    return
```

---

## 5. DASHBOARD UPGRADE — Live Positions + ATR + Better Real-Time Feel

The web dashboard at localhost:8080 needs these upgrades:

### A. Positions Table — Show ATR, Trail%, Direction, More Detail
The positions section should show a richer table for open positions:

```
Symbol  Strat  Score  P&L%   Peak%  ATR   Trail  Heat     Dir   Src  Held
SX      HFT    130    +2.9%  +3.7%  0.5   75%    36 COLD  →     BC   115s
VDOR    SCALP  75     +1.2%  +1.8%  2.1   65%    88 ROCK  ↑↑↑   DEX  4s
```

Fields to show per position (all available in dashboard_data.json):
- name, strategy, score
- pnl_pct with color (green if positive, red if negative)
- peak_pct (highest P&L reached)
- atr (from the new adaptive system — already in position data)
- trail % (calc_adaptive_trail result — add to dashboard_data.json if not there)
- heat + heat_label with color (ROCKET=red, HEATING=yellow, WARM=gray, COLD=blue, DUMP=red)
- price_direction with arrows: UP=↑↑↑ green, DOWN=↓↓ red, FLAT=→ gray
- price_source (BC or DEX)
- held time in seconds

When there are NO open positions, show a centered message:
"Scanning... 12,192 tokens found | Waiting for entry signal"
instead of just an empty table.

### B. Positions should UPDATE LIVE without page refresh
The WebSocket already pushes data every 2-3 seconds. Make the positions 
table re-render on each WebSocket update. The P&L%, heat, direction, 
and held time should all animate/update smoothly.

Add a subtle pulse/glow animation when a new position OPENS 
(wasn't in last update but is now). And a brief flash when a 
position CLOSES (was in last update, gone now — show a 2-second 
toast notification with the exit reason and P&L).

### C. Position Cards (for mobile)
On mobile (screen < 900px), show positions as cards instead of a table:
```
┌──────────────────────────┐
│ SX [HFT] Score:130       │
│ +2.9% (peak +3.7%)       │
│ ████████░░ 36 COLD  → BC │
│ ATR:0.5 Trail:75% 115s   │
└──────────────────────────┘
```

### D. Add Toast Notifications for Exits
When a trade closes, show a brief toast notification at the bottom:
- Green background for wins: "✓ SX +2.9% HFT_TRAIL (121s)"  
- Red background for losses: "✗ LAIKA -12.5% HFT_FLAT_30S (33s)"
- Auto-dismiss after 4 seconds
- Stack up to 3 toasts

### E. Add "Tokens Scanned" counter in header
Show the live token count next to the session number:
"S#137 | 12,192 scanned"

### F. Strategy breakdown — add P&L per strategy
The strategy cards already show open positions, trades, and WR.
Add the P&L per strategy (already in dashboard_data.json as strategies.{name}.pnl):
```
HFT               SCALP             GRAD_SNIPE
2 trades 100%     4 trades 0%       0 trades
+0.0012 SOL       -0.0016 SOL       $0.00
```

### G. Recent Trades — show ATR and adaptive trail info
If the exit reason contains "atr:" show it in the trades feed:
"Adelie +4.1% HFT_TRAIL atr:2.0 trail:4%" in green
"LAIKA -12.5% HFT_FLAT_30S" in red

### H. Balance chart — add position open/close markers
On the Chart.js balance chart, add small markers:
- Green dot when a WIN is closed
- Red dot when a LOSS is closed
This shows visually which trades moved the balance.

---

## DO NOT CHANGE
- Adaptive trailing stop system (calc_position_atr, calc_adaptive_trail)
- Moonbag exit logic (just upgraded)
- Heat score calculation
- Groq AI engine structure (just update prompts with new filter info)
- Watchdog, email alerts, circuit breaker
- How moonbags are CREATED (75/25 split)

## AFTER ALL CHANGES
1. Test that scanner.py starts without errors
2. Test that dashboard.py starts and loads at localhost:8080
3. Verify positions show ATR data in the web dashboard
4. Commit to git:
```
git add -A && git commit -m "Mega update: HFT filters, GRAD delay, all-Solana SCALP, dashboard upgrade"
```
