# TARGETED FIX — 3 Remaining Exit Bugs (from code + GitHub research)

## READ ERROR_LOG.md FIRST — all 15 rules apply

## PROBLEM 1: Lower NUCLEAR_TP from +5% to +3%
MEZo at +3.2% for 21 minutes without selling. NUCLEAR_TP at +5% doesn't 
catch it. The strategy-specific TP3 at +3.0% is buried in an elif chain 
and gets skipped.

Production bots (warp-id, YZYLAB) use a SEPARATE dedicated price check 
that ONLY checks TP/SL — not mixed into strategy logic.

FIX at line ~5983:
```python
# Was: if p.pct_change >= 5.0 and not p.is_moonbag:
# Now: lower to +3% — NO position should sit at +3% without selling
if p.pct_change >= 3.0 and not p.is_moonbag:
    exit_reason = f"NUCLEAR_TP(+{p.pct_change:.1f}% pk:{p.peak_pct:.1f}%)"
```


## PROBLEM 2: Partial exits — don't sell 100% at once
Community rode from +9.5% to -4.2% because the bot tried to sell ALL 
at one price point and missed the window. Production bots (NadirAli, 
TreeCityWes) sell in tiers:
- 50% at first milestone (+2%)
- 75% of remaining at second milestone (+5%)
- Keep 25% moonbag with trailing stop

FIX: Add partial exit for SCALP at +2%:
```python
# In the SCALP exit section, BEFORE the full TP checks:
# PARTIAL EXIT: Sell half at +2% to lock in profit
if (p.strategy == "SCALP" and p.pct_change >= 2.0 
    and not p.partial_exit_2x and p.remaining_sol > 0.1):
    sell_amount = p.remaining_sol * 0.50  # sell half
    profit = sell_amount * (p.pct_change / 100)
    STATE.balance_sol += sell_amount + profit
    p.remaining_sol -= sell_amount
    p.partial_exit_2x = True
    _dbg(f"SCALP_PARTIAL: {p.symbol} sold 50% at +{p.pct_change:.1f}%")
    _log_partial_exit(p, f"SCALP_HALF(+{p.pct_change:.1f}%)", 
                      sell_amount, profit)
    # DON'T continue — let remaining 50% ride with trailing stop
```

This way even if the remaining 50% crashes back to 0, you already 
banked half the profit. Community at +9.5% would have sold 50% = 
+$3.76 locked in, instead of total loss of -$3.73.


## PROBLEM 3: p.pct_change stale — peak_pct = 0.0 for all positions
Dashboard shows +3.2% but exit loop might see 0% or stale value.
peak_pct is 0.0 for EVERY position — means the universal peak update 
we requested isn't running for non-GRAD strategies.

FIX: Add universal peak update BEFORE all strategy-specific logic,
right after the price update section and BEFORE NUCLEAR_TP:
```python
# UNIVERSAL PEAK UPDATE — applies to ALL strategies
# Bug 16: peak_pct was only updated for GRAD_SNIPE
if p.pct_change > p.peak_pct:
    p.peak_pct = p.pct_change

# DEBUG: Log any position that should be selling but isn't
if p.pct_change >= 2.0 and hold_sec > 60:
    _dbg(f"WHY_NOT_SELLING: {p.symbol} [{p.strategy}] "
         f"pct={p.pct_change:.1f}% peak={p.peak_pct:.1f}% "
         f"heat={p.heat_score:.1f} dir={p.price_direction} "
         f"held={hold_sec:.0f}s src={p.price_source}")
```

## PROBLEM 4: ALSO NOTICED — SCALP_HARD_TP_PCT might be too high
Piece sold at +12.0% via SCALP_TP. That means SCALP_HARD_TP_PCT = 5.0 
or higher but the position was at +12% when it finally triggered. 
It should have sold at +5% but didn't until +12%.

Check what SCALP_HARD_TP_PCT is set to. If it's 5.0, why did Piece 
reach +12% before SCALP_TP fired? Either pct_change wasn't updating 
fast enough (3s gap) or the exit loop runs less frequently than price 
updates.

## SUMMARY OF CHANGES
1. NUCLEAR_TP: 5.0% → 3.0% (catches MEZo-style stuck positions)
2. PARTIAL EXIT: Sell 50% at +2% for SCALP (locks in profit early)
3. UNIVERSAL peak_pct update before all exits
4. DEBUG logging for positions that should be selling but aren't
5. Check SCALP_HARD_TP_PCT value and why Piece reached +12% before TP

## DO NOT CHANGE
- HFT disable (working)
- MAX_HOLD 600s (working)
- Grid trading (working)
- Moonbag trailing (working)
- Loss cap 0.05 SOL (working)

## COMMIT
git add -A && git commit -m "Fix exits: NUCLEAR_TP to 3%, partial exits at 2%, universal peak tracking, debug logging"
