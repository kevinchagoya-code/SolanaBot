# Error Log — Lessons Learned

## Session: March 31, 2026 (Pre-Error-Log Bugs)

### BUG 0a: SIAMI -84% loss — price fetch failure skipped all exit logic
**When:** March 31, early session
**Impact:** Lost 84% on a single position because `continue` after price fetch failure skipped stop loss checks.
**Root cause:** When price fetch returned None, the code did `continue` which jumped to the next position, skipping ALL exit logic (SL, trail, time stop).
**Fix:** Added `price_fetch_failures` counter, force-close after consecutive failures.
**Lesson:** Price fetch failure must NEVER skip exit logic. No price = force exit, don't hold blind.

### BUG 0b: Stop loss not triggering at -20%
**When:** March 31
**Impact:** Positions held past -20% SL because PRICE_CHECK_INTERVAL was 10 seconds — tokens gapped past the SL between checks.
**Root cause:** 10-second price check interval too slow for volatile memecoins.
**Fix:** Reduced PRICE_CHECK_INTERVAL from 10s to 3s.
**Lesson:** SL must be checked frequently enough that fast-moving tokens can't gap through it.

### BUG 0c: Peak hours timezone wrong (EST vs EDT)
**When:** March 31
**Impact:** Trading at wrong times — "peak hours" were off by 1 hour during daylight saving.
**Root cause:** `_est_hour()` used hardcoded UTC-5 (EST), didn't handle EDT (UTC-4).
**Fix:** Used `zoneinfo` for automatic EDT/DST handling.
**Lesson:** Never hardcode timezone offsets. Use timezone libraries.

### BUG 0d: GRAD_SNIPE entered with hardcoded price estimate
**When:** March 31
**Impact:** -100% losses on graduated tokens because entry price was a hardcoded estimate (0.0000004287) that was wildly wrong.
**Root cause:** No real price source for graduated tokens — used a guess.
**Fix:** DEXScreener verified pricing + PumpSwap pool reserve decoding.
**Lesson:** NEVER enter a position without a verified price from an actual data source.

### BUG 0e: SOL/USDC price bug — +500,000% "gain"
**When:** March 31
**Impact:** Phantom +500,000% gains on SOL/USDC/wBTC/wETH positions corrupted P&L tracking.
**Root cause:** SOL priced in SOL = entry at 0.0002, "gained" 500,000%. Price math doesn't work for base-layer assets.
**Fix:** Removed SOL/USDC/wBTC/wETH from ESTAB tokens. Added 50x sanity check.
**Lesson:** Don't trade an asset denominated in itself. SOL in SOL = always 1.0.

### BUG 0f: calc_price_impact returning 100%
**When:** March 31
**Impact:** Simulated trades showed impossible losses from 100% price impact.
**Root cause:** When `liq_sol=0`, impact calculated to 1.0 (100%).
**Fix:** Capped at 10%, default 2%.
**Lesson:** Division by zero / near-zero in financial calculations = catastrophic. Always clamp.

### BUG 0g: Safety check too slow (1048ms)
**When:** March 31, HFT mode
**Impact:** Missed fast-moving tokens — by the time safety check completed, the pump was over.
**Root cause:** Multiple sequential RPC calls for mint/freeze authority checks.
**Fix:** Replaced multi-RPC checks with single DAS `getAsset` call: 1048ms → 41-163ms.
**Lesson:** For time-sensitive operations, batch RPC calls or use specialized APIs.

### BUG 0h: DEXScreener rate limiting killed SCALP scanner
**When:** April 1
**Impact:** SCALP_WATCH scanner crashed/restarted repeatedly, found zero tokens.
**Root cause:** For each boost token, made a separate DEXScreener API call for pair data = 20-40 calls per cycle = instant 429.
**Fix:** Used inline pair data from search results, Jupiter for boost tokens without pair data.
**Lesson:** Batch API calls. Never make N individual calls when 1 batch call exists.

### BUG 0i: Fee model correction — 0.3% was still too high
**When:** April 1, after first fee fix
**Impact:** MOM_TP trades at +0.5% still showed as losses.
**Root cause:** Used 0.3% (30 bps) fee + 0.1% impact = 0.7% breakeven. Real cost: 0.25% + 0.01% = 0.55% breakeven.
**Fix:** Updated to 25 bps fee + 0.01% impact. Verified: +0.7% = WIN, +1.0% = +$0.79.
**Lesson:** Research ACTUAL exchange fees before modeling. Jupiter=0%, Raydium=0.25%, not 0.3%.

### BUG 0j: Twikit KEY_BYTE error spam
**When:** All of April 1
**Impact:** Error log flooded with Twitter login failures every 60 seconds.
**Root cause:** Twitter changed JS encryption, twikit library couldn't get KEY_BYTE indices.
**Fix:** Added TWITTER_ENABLED=false flag to skip login entirely.
**Lesson:** External dependencies break. Always have a disable flag for non-critical services.

### BUG 0k: GRAD_SNIPE entering before DEXScreener indexed
**When:** April 1
**Impact:** "graduated but DEX+POOL both failed" spam — positions stuck with no price source.
**Root cause:** Entered immediately after graduation, but DEXScreener needs ~60s to index new pools.
**Fix:** Added 60s delay with 2 test price fetches before entering.
**Lesson:** Newly created on-chain state takes time to propagate to indexers. Wait and verify.

---

## Session: April 1, 2026 (Post-Error-Log Bugs)

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

1. **Calculate breakeven BEFORE setting TP:** TP must be > (entry_fee% + exit_fee% + impact% + gas). Actual breakeven on Solana via Jupiter/Raydium: ~0.55% round trip for liquid tokens.
2. **Entry and exit controls are independent:** Disabling entry must NEVER disable exits on existing positions.
3. **Different tokens need different fee models:** pump.fun BC = 1%, Raydium/Jupiter = 0.25%, PumpSwap = 0.25%.
4. **Clean starts must be truly clean:** Don't restore stale balance/P&L/positions from state.json.
5. **Test with math first:** Before deploying any TP/SL change, run calc_sim_pnl math to verify profit > 0.
6. **Parse flexibly:** Always handle variable-length data, extra bytes, format changes from smart contracts.
7. **Direction matters:** "Volume" or "trending" without positive price direction = buying into a dump.
8. **Never force-close winners:** Any timed exit must check P&L before closing.
9. **Price fetch failure must not skip exit logic:** No price = force exit at last known price, don't hold blind.
10. **Never enter without a verified price:** Hardcoded estimates, stale prices, or zero prices = guaranteed loss.
11. **Batch API calls:** Never make N individual calls when 1 batch call exists. DEXScreener rate limits at ~30 req/min.
12. **External services break:** Always have a disable flag for non-critical services.
13. **Wait for indexers:** Newly created pools take 30-60s to appear in DEXScreener/Jupiter. Verify before entering.
14. **Clamp financial calculations:** Division by zero/near-zero = catastrophic. Always clamp to reasonable bounds.
15. **SOL in SOL = 1.0:** Never trade an asset denominated in itself.
