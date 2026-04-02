# Error Log — Lessons Learned

## Session: April 1, 2026

### BUG 1: Sim fees charged 1% pump.fun rate on ALL tokens
**When:** All session
**Impact:** Every trade needed +3%+ to break even. +2.2% trades showed as losses.
**Root cause:** `calc_sim_pnl()` hardcoded `PUMP_FEE_BPS = 100` (1%) for all tokens.
**Fix:** Use 0.3% (30 bps) for tokens with >100 SOL liquidity.
**Lesson:** Always verify the fee model matches the actual DEX being used.

### BUG 2: TP set below breakeven fee threshold
**When:** After fixing fees to 0.3%
**Impact:** MOM_TP at +0.5% was BELOW the 0.7% breakeven (0.3% × 2 + 0.1% impact). Every "take profit" was actually a loss.
**Root cause:** Changed TP from 1.5% → 0.5% without recalculating breakeven.
**Fix:** TP must be > round-trip fees. At 0.3% per side + impact = 0.7% breakeven → TP must be ≥ 1.5%.
**Lesson:** ALWAYS calculate breakeven = (entry_fee + exit_fee + impact + gas) / position_size BEFORE setting TP.

### BUG 3: HARD_CAP killed profitable positions
**When:** All session  
**Impact:** bunbun at +2.2%, maxxing at +1.0% force-closed as "losses"
**Root cause:** HARD_CAP exit didn't check if position was profitable.
**Fix:** If pct_change > 0.5% at hard cap, exit as TIME_TP (win).
**Lesson:** Never force-close a winning position without checking P&L first.

### BUG 4: HFT exits disabled when hft_enabled=False
**When:** After disabling HFT entry
**Impact:** 65 positions with +22-90% gains couldn't exit — peak_pct stayed at 0.0%
**Root cause:** Exit logic gated by `and STATE.hft_enabled` — disabling entry also disabled exits.
**Fix:** Removed `and STATE.hft_enabled` from exit block.
**Lesson:** Entry controls and exit controls must be INDEPENDENT.

### BUG 5: open_sim_position didn't respect HFT disable
**When:** After setting HFT_MODE=False
**Impact:** 65+ HFT positions opened despite HFT being "disabled"
**Root cause:** `if STATE.hft_enabled` only controlled sizing, not whether to enter. Fell through to else branch.
**Fix:** Added `if not STATE.hft_enabled: return` at top of function.
**Lesson:** A disable flag must BLOCK the action, not just change parameters.

### BUG 6: state.json restoring old balance/positions
**When:** Every restart
**Impact:** Bot started with 5.7 SOL instead of 100, couldn't open 18 SOL positions
**Root cause:** load_state() restored old balance, overriding STARTING_BALANCE_SOL.
**Fix:** load_state() now only restores settings, not balance/P&L/positions.
**Lesson:** Clean starts must actually be clean — don't restore stale capital state.

### BUG 7: vsolr UnboundLocalError for graduated tokens
**When:** When graduated tokens updated prices
**Impact:** Position update crashed silently, positions couldn't reach exit logic = stuck forever
**Root cause:** `vsolr` defined in BC-path else branch but referenced after the if/else.
**Fix:** Changed to `_vsolr = bc.get(...) if bc else 0`
**Lesson:** Variables defined inside conditional branches must have defaults outside.

### BUG 8: Bonding curve parser rejected new pump.fun data format
**When:** When pump.fun updated their smart contract
**Impact:** "String is the wrong size" — positions stuck, can't get price, can't exit
**Root cause:** BC_SIZE = 151 exact match, pump.fun added new fields making data larger.
**Fix:** BC_SIZE = 49 (minimum needed), use slice notation not struct.unpack.
**Lesson:** Parse only the fields you need, ignore extra bytes at the end.

### BUG 9: Momentum threshold too high for established tokens
**When:** MOMENTUM scanner on wETH/JUP/RAY
**Impact:** Every trade exited as MOM_FLAT because tokens move 0.01%/min, threshold was 0.1%
**Root cause:** Threshold designed for memecoins (move 1-10%/min), not established tokens.
**Fix:** Lowered threshold, but the real fix is longer hold times + candle-based entry.
**Lesson:** Different token types need different parameters. One-size-fits-all doesn't work.

### BUG 10: TRENDING entered tokens going DOWN
**When:** All session
**Impact:** Bought nub at -0.9% just because it was "trending"
**Root cause:** Filter used abs(chg_5m) > 1.0, so -5% passed same as +5%.
**Fix:** Changed to chg_5m > 1.0 (must be positive).
**Lesson:** "Trending" means popular, not "going up." Always check direction.

---

## RULES FOR FUTURE DEVELOPMENT

1. **Calculate breakeven BEFORE setting TP:** TP must be > (entry_fee% + exit_fee% + impact% + gas)
2. **Entry and exit controls are independent:** Disabling entry must NEVER disable exits
3. **Different tokens need different fee models:** pump.fun = 1%, Raydium/Jupiter = 0.25-0.3%
4. **Clean starts must be truly clean:** Don't restore stale state
5. **Test with math first:** Before deploying any TP/SL change, calculate the exact breakeven point
6. **Parse flexibly:** Always handle variable-length data, extra bytes, format changes
7. **Direction matters:** "Volume" or "trending" without positive direction = buying into a dump
8. **Never force-close winners:** Any timed exit must check P&L before closing
