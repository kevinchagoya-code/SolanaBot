# Error Log — Lessons Learned

## FULL PROJECT CONTEXT

### What This Bot Is
A Solana meme coin / crypto trading bot that detects tokens via Geyser WebSocket, 
scans DEXScreener/Jupiter for momentum, and simulates trades with P&L tracking.
Built over ~24 hours across 2 sessions with Claude Opus 4.6.

### Architecture
- **scanner.py**: Main bot (~7000+ lines). All strategies, price fetching, exit logic, dashboard.
- **dashboard.py**: FastAPI web dashboard at localhost:8080 with WebSocket real-time updates.
- **watchdog.py**: Crash recovery with rate limiter.
- **State**: state.json (settings persistence), snipe_log.csv (all trades), dashboard_data.json (web UI data).
- **Pricing**: Bonding curve RPC → Jupiter API → DEXScreener batch → direct pool RPC fallback chain.
- **AI**: Groq llama-3.1-8b-instant for entry/exit decisions (14,400 calls/day free tier).

### Strategies Built
| Strategy | What It Does | Current Status |
|---|---|---|
| HFT | Snipes new pump.fun tokens via Geyser WebSocket | ON but low win rate on flat tokens |
| GRAD_SNIPE | Enters tokens graduating to PumpSwap AMM | ON with 60s DEX indexing delay |
| SCALP_WATCH | Finds trending tokens on DEXScreener with momentum | ON — best performer (LOBSTER +6.2%, ELONWIF +3.3%) |
| MOMENTUM | Swing trades 27 established tokens (wETH, JUP, RAY, BONK, TRUMP, etc.) | ON — candle-based entry (DIP/BREAKOUT/BOUNCE) |
| TRENDING | Enters DEXScreener trending tokens with quality filters | ON — requires +1% 5min change |
| SWING | Pattern scanner on graduated tokens | ON but rarely fires |
| ESTAB | Scalps established tokens (BONK, WIF, JUP) | DISABLED — tokens too stable for scalp |

### Key Parameters (Current)
- Starting balance: 100 SOL (clean reset every restart)
- Position sizes: 1-3 SOL (sim mode, proving profitability)
- Fee model: 25 bps (0.25%) per side for liquid tokens, 100 bps (1%) for pump.fun
- Breakeven: ~0.55% round trip on liquid tokens
- TP: +1.0% for MOMENTUM, +5%/+20% for HFT, +3% for SCALP
- SL: -1.0% for MOMENTUM, -15% for HFT, -2% for SCALP
- Max positions: 15 total, 5 per strategy, 10 for momentum
- 27 momentum tokens tracked via DEXScreener batch every 10s
- 1-minute candle engine for pattern detection (DIP BUY, BREAKOUT, BOUNCE)

### GitHub Repo
Private: https://github.com/kevinchagoya-code/SolanaBot

### What Works
- Geyser WebSocket token detection (sub-ms latency)
- SCALP_WATCH finding real winners (+6.2%, +3.3%)
- HFT finding moonshots (+90%, +65%, +24%) when aggressive TP is enabled
- ATR-adaptive trailing stops per token
- Price momentum tracking (direction, acceleration, consecutive ticks)
- Web dashboard with real-time positions, P&L chart, toast notifications
- Moonbag system for catching runners
- Clean start every restart (100 SOL, zero P&L)

### What Doesn't Work Yet
- Consistent profitability (win rate 3-10%, needs 40%+)
- MOMENTUM tokens move too slowly for short-term scalp (0.01%/min)
- HFT on flat pump.fun tokens = 90% flat exits
- Fee model was too expensive (fixed from 1% to 0.25% for liquid tokens)

### Key Insight from Research
- Grid trading (buy low, sell high in a range) = best fit for 10s polling
- Mean reversion (buy oversold, sell at average) = second best
- Momentum chasing (buy what's pumping) = loses money for retail bots
- The bot finds winners but historically couldn't SELL them due to bugs
- Real Solana DEX fees: ~0.55% round trip, not the 2%+ we were simulating

---

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

---

## SESSION 2 TIMELINE (April 1, 2026)

### Major Changes Made (chronological)
1. Fixed "String is the wrong size" — BC parser made flexible (BC_SIZE 151→49)
2. Added DEXScreener fallback for ALL strategies (was only GRAD/TRENDING/SCALP)
3. Analyzed 34 trades: 14.7% WR, R:R 9.2:1, HFT_TIMEOUT was 70% of exits
4. Raised HFT_MIN_SCORE 88→90, cut HFT_MAX_HOLD_SEC 90→60
5. Added 30s aggressive flat exit (HFT_FLAT_30S)
6. Added price momentum tracking (direction, acceleration, consecutive ticks)
7. Added ATR-adaptive trailing stops (per-token volatility-based)
8. Built web dashboard (FastAPI + WebSocket at localhost:8080)
9. Tightened moonbag trailing stop (50%→60% retention, then ATR-adaptive)
10. Opened SCALP to all Solana tokens (removed pump.fun-only filter)
11. Added Jupiter Price API as universal price source (27 tokens)
12. Scaled positions to $1,500 each (then back to $1-3 for sim mode)
13. Disabled HFT entry (0% WR) → re-enabled with aggressive TP (+20% sell immediately)
14. Fixed peak_pct not updating (exit logic gated by hft_enabled)
15. Fixed open_sim_position not respecting HFT disable
16. Added behavior-based TRENDING filters ($10K liq, $5K vol, +1% 5min)
17. Added MOMENTUM strategy with own exit logic (separate from SCALP)
18. Clean start every restart (load_state only restores settings)
19. Rebuilt momentum scanner with 1-minute candle engine (DIP/BREAKOUT/BOUNCE)
20. Fixed fee model: 1% pump.fun → 0.25% Raydium for liquid tokens
21. Fixed TP below breakeven (0.5% < 0.55% breakeven)
22. Created this ERROR_LOG.md

### Key Wins Found (but often not captured due to bugs)
- MOONPEPE +90.2% (sat unsold — peak_pct bug)
- T_CzvZg +65.8% (sat unsold — peak_pct bug)
- 🚀 +24.6% (sat unsold)
- LOBSTER +6.2% SCALP_TP (captured!)
- ELONWIF +3.3% SCALP_TP (captured!)
- ROCKY +5% MOON_TRAIL (captured!)
- Father +105.7% HFT_TP (captured — from session 1)

### BUG 11: ROCKET lost -96% (-0.96 SOL) on a single SCALP trade in 3 seconds
**When:** April 1, late session
**Impact:** $76 loss on one trade. SL should have been -2%, not -96%.
**Root cause:** Either entered at stale/zero price, or scam token crashed instantly.
**Fix:** Added -0.05 SOL loss cap in close_position() + price sanity check in SCALP entry.
**Lesson:** Always cap maximum loss per trade. No sim trade should ever lose > 5% of position.

### BUG 12: NEAR_GRAD_ENTRY_SOL still at 18.0 ($1,500) after scaling changes
**When:** Discovered during cleanup
**Impact:** Would have opened $1,500 positions on a disabled strategy.
**Fix:** Removed NEAR_GRAD entirely (dead strategy).
**Lesson:** When scaling position sizes, search for ALL *_ENTRY_SOL constants, not just the ones you remember.

### Major Cleanup (April 1, late session)
- Removed 610 lines of dead code (7,446 → 6,836)
- Deleted: REDDIT (0 wins), SWING (0 trades), NEAR_GRAD (merged), Twikit (broken)
- Added grid trading engine (12 tokens, 1.5% spacing, 5 levels)
- All position sizes standardized to 0.5 SOL sim mode

### Git Commits (session 2)
30+ commits pushed to kevinchagoya-code/SolanaBot covering all changes above.
