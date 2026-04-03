# FIX POSITIONS NOT SELLING — DEAD SIMPLE VERSION

## READ ERROR_LOG.md FIRST

## THE PROBLEM
Bot finds winners (ZEN +6.4%, Piece +12%, Community +9.5%, NIVORA +11.2%)
but doesn't sell them. They ride back down to 0% or negative.

## THE FIX — 3 EXACT LINE CHANGES

### CHANGE 1: scanner.py line ~6000
Find this EXACT line:
    if p.pct_change >= 5.0 and not p.is_moonbag:

Change the 5.0 to 3.0:
    if p.pct_change >= 3.0 and not p.is_moonbag:

That's it. One number change. 5.0 becomes 3.0.

### CHANGE 2: After line ~5907 (after the _dex_batch_prices block)
After the line that says:
    p.heat_score, p.heat_pattern = calc_heat_score(p)

Add these lines:
    # FALLBACK price update — if pct_change is stale, recalc from current price
    if p.current_price_sol > 0 and p.entry_price_sol > 0:
        fresh_pct = (p.current_price_sol - p.entry_price_sol) / p.entry_price_sol * 100
        if abs(fresh_pct - p.pct_change) > 1.0:
            p.pct_change = fresh_pct  # price was stale, update it

### CHANGE 3: Right after the NUCLEAR_TP block (after line ~6003)
Add a second safety net:
    # SAFETY NET: Any position at +3% that somehow didn't trigger NUCLEAR_TP
    if not exit_reason and p.pct_change >= 3.0 and not p.is_moonbag and hold_sec > 5:
        exit_reason = f"SAFETY_TP(+{p.pct_change:.1f}%)"
        _dbg(f"SAFETY_TP: {p.symbol} [{p.strategy}] NUCLEAR missed this somehow")

## WHY THESE 3 CHANGES FIX IT
- Change 1: Catches +3% positions that were below the +5% threshold
- Change 2: Fixes stale pct_change so the exit logic sees the real price
- Change 3: Belt-and-suspenders catch-all in case NUCLEAR still misses

## DO NOT CHANGE ANYTHING ELSE
Do not restructure the exit logic.
Do not add new strategies.
Do not change position sizes.
Do not touch grid trading.
Just these 3 changes. Test by restarting and watching for NUCLEAR_TP 
or SAFETY_TP exits in the logs.

## COMMIT
git add scanner.py && git commit -m "Fix selling: NUCLEAR 5->3%, stale pct_change fallback, safety net TP"
