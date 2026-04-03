# QUICK FIX — 3 Critical Issues Before MICRO_SCALP

## READ ERROR_LOG.md FIRST — all 15 rules apply

## FIX 1: DISABLE HFT IMMEDIATELY
HFT has been the #1 loss source across EVERY session:
- Session 10: 22 trades, 0% WR, -0.459 SOL (-$36)
- Session 174: 12 trades, 0% WR, -0.466 SOL (-$37)
- Session 173: 9 trades, 0% WR, -0.385 SOL (-$30)
Total HFT losses today: over $100 in sim

Every single HFT trade enters a pump.fun token that goes flat and 
exits as HFT_FLAT_30S at +0.0% with a ~0.02 SOL fee loss.

FIX: Set HFT_ENABLED = False or add at the very top of open_sim_position:
```python
# DISABLE HFT — 0% win rate across all sessions
if strategy == "HFT":
    return
```
Do NOT delete HFT code — just disable entry. Keep exit logic working
for any existing positions (ERROR_LOG Rule 2: entry/exit independent).


## FIX 2: POSITIONS STUCK FOR HOURS — Exit logic not reaching them
MEZo [SCALP] held 8,135 seconds (2.2 HOURS) at +2.2% — TP2 should 
have fired at +2.0% but didn't. rocky [TRENDING] held 8,282 seconds 
at -4.5% — SL should have caught this ages ago.

These positions are "stuck" — the update_sim_positions loop is either:
a) Not iterating over them (skipping due to strategy filter)
b) Not reaching exit logic (an early continue/return before exits)
c) Price not updating (price_source stuck, no fresh price data)

DEBUG: Add logging to find WHY these aren't exiting:
```python
# At the START of update_sim_positions, for each position:
for mint, p in list(STATE.sim_positions.items()):
    held = time.monotonic() - p.open_time
    if held > 300:  # any position held > 5 minutes
        _dbg(f"STUCK_CHECK: {p.symbol} {p.strategy} held={held:.0f}s "
             f"pct={p.pct_change:+.1f}% price_src={p.price_source}")
```

Also add a HARD TIME LIMIT for ALL strategies:
```python
# After all other exit checks, BEFORE the continue:
MAX_HOLD_ANY = 600  # 10 minutes absolute max for ANY position
if held > MAX_HOLD_ANY:
    exit_reason = f"MAX_HOLD({p.pct_change:+.1f}%@{held:.0f}s)"
    # close position at current price
```
No position should EVER be held for 2+ hours in a scalping bot.


## FIX 3: DUPLICATE POSITIONS IN SAME TOKEN
RAY has 2 positions open. Earlier JTO had 5. The duplicate check 
isn't working for MOMENTUM/GRID entries.

The check `if mint in STATE.sim_positions` should prevent this, but 
GRID opens multiple positions at different levels. The issue is that 
grid BUY positions share the same mint address.

FIX: For GRID specifically, track positions by mint+level:
```python
# For grid entries, use a composite key:
grid_key = f"{mint}_GRID_L{level}"
if grid_key in STATE.sim_positions:
    return  # already have this grid level filled

# For ALL other strategies, prevent any duplicate:
if any(p.mint == mint and p.strategy == strategy 
       for p in STATE.sim_positions.values() if p.status == "OPEN"):
    _dbg(f"DUP_SKIP: {symbol} already has {strategy} position")
    return
```

## FIX 4 (BONUS): Geyser 403 — Don't spam reconnection
Geyser is returning HTTP 403 since 11:05. The bot is retrying every 
few minutes, wasting resources. Add:
```python
# If Geyser gets 403, wait 30 minutes before retrying (not 60 seconds)
GEYSER_403_BACKOFF = 1800  # 30 minutes
# After 3 consecutive 403s, stop trying until next restart
GEYSER_MAX_403_RETRIES = 3
```
This doesn't affect SCALP, GRID, or TRENDING — only HFT needs Geyser,
and we're disabling HFT anyway.

## IMPLEMENTATION ORDER
1. Disable HFT entry (1 line change, immediate impact)
2. Add MAX_HOLD_ANY = 600s for all positions
3. Fix duplicate position check for grid entries
4. Add Geyser 403 backoff

## DO NOT CHANGE
- Grid trading engine (it's working! W +53.1%, PYTH +1.0%, JUP +0.9%)
- Proactive TP tiers (ZEN +3.6%, MOON +2.1%, CRIME +1.3%)
- Moonbag trailing (LEGOELON +6.9%, BROCCOLI +15.1%)
- Loss cap at 0.05 SOL
- Jupiter price integration
- Any exit logic for existing positions

## COMMIT
git add -A && git commit -m "Quick fix: disable HFT (0% WR), fix stuck positions (10min max hold), fix duplicate entries"

## CRITICAL: Add these bugs to ERROR_LOG.md (Bugs 13-15 already added)
Check ERROR_LOG.md — Bugs 13, 14, 15 describe exactly these issues.
The fixes below address all three.

## FIX 1 (BUG 13): HFT MUST BE DISABLED — It keeps coming back
Previous attempts to disable HFT failed. The flag doesn't persist or 
gets bypassed. This time, block at EVERY entry point:

```python
# Method 1: At the VERY TOP of open_sim_position(), line 1:
async def open_sim_position(...):
    if strategy == "HFT":
        return  # BUG 13: HFT 0% WR across 40+ trades, -$100+ losses

# Method 2: In the Geyser WebSocket handler, BEFORE calling open_sim_position:
# Where new pump.fun tokens are detected:
    # HFT DISABLED — Bug 13
    # Do NOT call open_sim_position for new BC tokens
    # Still detect them for GRAD_SNIPE graduation tracking

# Method 3: Set the constant:
HFT_ENABLED = False
# AND check it in EVERY code path that could open an HFT position
```

Use ALL THREE methods. Belt, suspenders, AND duct tape. HFT has lost 
money in every single session with zero exceptions.


## FIX 2 (BUG 14): HARD TIME LIMIT — No position survives 10 minutes
MEZo sat at +2.2% for 2.2 HOURS. rocky sat at -4.5% for 2.3 HOURS.
The exit loop is silently crashing on certain positions.

Add this check at the VERY START of the position loop in 
update_sim_positions, BEFORE any strategy-specific logic:

```python
# FIRST check in update_sim_positions — cannot be bypassed:
for mint, p in list(STATE.sim_positions.items()):
    try:
        held = time.monotonic() - p.open_time
        
        # BUG 14 FIX: Absolute max hold — nothing survives 10 minutes
        if held > 600:
            pct = p.pct_change if hasattr(p, 'pct_change') else 0
            exit_reason = f"MAX_HOLD({pct:+.1f}%@{held:.0f}s)"
            await close_sim_position(mint, p, exit_reason)
            continue
            
        # ... rest of strategy-specific exit logic ...
    except Exception as e:
        # BUG 14: Log the error but STILL force close after 10 min
        _dbg(f"EXIT_ERROR: {p.symbol} {e}")
        if held > 600:
            await close_sim_position(mint, p, f"ERROR_HOLD({held:.0f}s)")
            continue
```

The try/except wrapping EACH position ensures one bad position can't 
crash the loop and leave other positions stuck.

## FIX 3 (BUG 15): DUPLICATE CHECK — by (mint, strategy) pair
```python
# Before ANY entry, in open_sim_position or _can_open_strategy:
def _has_position(mint, strategy):
    """Check if we already have this token in this strategy."""
    for p in STATE.sim_positions.values():
        if p.mint == mint and p.strategy == strategy and p.status == "OPEN":
            return True
    return False

# Then at entry:
if _has_position(mint, strategy):
    _dbg(f"DUP_SKIP: {symbol} already has {strategy} position")
    return
```

## VERIFICATION AFTER FIXES
After implementing, restart the bot and verify:
1. NO HFT trades appear in recent_trades (strategy should be absent)
2. No position held > 600 seconds (check positions list)
3. No duplicate mints in positions list (each mint appears max once per strategy)
4. GRID, SCALP, and GRAD_SNIPE still work normally

## COMMIT
git add -A && git commit -m "Fix bugs 13-15: kill HFT permanently, 10min max hold, duplicate prevention"


## FIX 5 (BUG 16): SCALP positions at +12.7% not selling — peak_pct stuck at 0.0

Community [SCALP] at +12.7%, Alex [GRAD] at +42.3% — dashboard shows 
huge gains but positions don't close. peak_pct shows 0.0 for ALL positions.

### Root cause (found by reading scanner.py):
The exit logic at line ~6186 has proactive TPs:
  if pct >= 5.0: SCALP_TP
  elif pct >= 3.0: SCALP_TP3
  elif pct >= 2.0 and not UP: SCALP_TP2

These SHOULD fire for Community at +12.7%. But they're NOT firing.
This means either:

A) p.pct_change in the exit loop is NOT +12.7% — it's stale/wrong
B) The exit logic is gated by earlier elif conditions that fire first
C) The entire SCALP exit block isn't being reached for this position

### DEBUG: Add this RIGHT BEFORE the SCALP exit block:
```python
# DEBUG: Why isn't this selling?
if p.strategy == "SCALP" and p.pct_change > 3.0:
    _dbg(f"SCALP_SHOULD_SELL: {p.symbol} pct={p.pct_change:.1f}% "
         f"heat={p.heat_score:.1f} dir={p.price_direction} "
         f"peak={p.peak_pct:.1f} src={p.price_source}")
```

### ALSO: Add a nuclear TP — if pct > 5%, sell NO MATTER WHAT
Put this BEFORE ALL strategy-specific logic, right after the MAX_HOLD check:
```python
# NUCLEAR TP: if ANY position is up > 5%, sell immediately
# This overrides everything — heat checks, direction checks, all of it
if p.pct_change >= 5.0 and not p.is_moonbag:
    exit_reason = f"NUCLEAR_TP(+{p.pct_change:.1f}%)"
    _dbg(f"NUCLEAR_TP: {p.symbol} [{p.strategy}] at +{p.pct_change:.1f}% — force sell")
```

This goes at line ~5975, right after the MAX_HOLD check and BEFORE the 
strategy-specific elif blocks. Community at +12.7% would trigger this 
instantly on the next loop iteration.

### ALSO: peak_pct not updating
peak_pct = 0.0 for ALL positions means the peak tracker is broken.
Check: is p.peak_pct being set anywhere for SCALP positions?
The GRAD path updates it (line 6009) but SCALP might not have its own
peak update. Add one:
```python
# Update peak for ALL strategies, not just GRAD:
if p.pct_change > p.peak_pct:
    p.peak_pct = p.pct_change
```
This should go in the universal section BEFORE strategy-specific exits.
