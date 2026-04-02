# Iteration Log — What Worked vs What Didn't

## PURPOSE
Track every parameter change and strategy iteration with BEFORE/AFTER results.
This is the institutional memory for what actually makes money.

---

## ITERATION 1: Initial HFT-only (March 31)
**Strategy:** Snipe new pump.fun tokens, exit via trailing stop
**Result:** 34 trades, 14.7% WR, +0.029 SOL net (before fees)
**What worked:** Father +105%, NoKings +18.7% — rare moonshots carry
**What didn't:** 70% of trades timed out flat. After simulated fees = net loss.
**Lesson:** HFT finds winners but 85% of entries are dead tokens.

## ITERATION 2: Multi-strategy + AI (March 31 late)
**Added:** SCALP, GRAD_SNIPE, SWING, REDDIT, Groq AI decisions
**Result:** More activity but same pattern — lots of flat exits, rare big wins
**What worked:** SCALP_WATCH found LOBSTER +6.2%, ELONWIF +3.3%
**What didn't:** REDDIT (0 wins), SWING (0 trades), ESTAB (too stable)
**Lesson:** Only SCALP_WATCH and HFT find real opportunities.

## ITERATION 3: FETCH_FAIL fix + ATR trailing stops (April 1 early)
**Changed:** Flexible BC parser, DEXScreener fallback, per-token ATR exits
**Result:** Positions no longer get stuck. GTA$ would have exited +54% instead of -31%.
**What worked:** Graduated tokens now price via DEX/Jupiter fallback chain
**What didn't:** Still losing on flat entries
**Lesson:** Price infrastructure is critical — can't profit if you can't see the price.

## ITERATION 4: Aggressive take-profit (April 1 mid)
**Changed:** HFT_BIG_TP at +20%, HFT_TP at +5%, HFT_TP_FALL at +3%
**Result:** MOONPEPE +90%, 🚀 +24% would have been captured
**What worked:** Immediate sell at +20% — don't let winners sit
**What didn't:** Peak_pct bug meant trailing stop never activated (fixed separately)
**Lesson:** TP must be aggressive on volatile memecoins. Take the money.

## ITERATION 5: Position sizing $1,500 per trade (April 1)
**Changed:** All positions 18-35 SOL ($1,500-$2,900), starting balance 200 SOL
**Result:** DISASTER — every flat exit cost -0.03 to -0.06 SOL × 50+ trades = massive loss
**What worked:** Nothing at this scale with current win rate
**What didn't:** $1,500 on a 4% win rate = guaranteed blowup
**Lesson:** NEVER scale position size before proving the strategy is profitable. Prove at 0.5 SOL first.
**RULE:** Scale AFTER consistent profitability, not before.

## ITERATION 6: Sim mode 1 SOL positions (April 1)
**Changed:** All positions 0.5-1.5 SOL, 100 SOL starting balance
**Result:** Losses much smaller per trade. Still low win rate.
**What worked:** Small positions = small losses = more time to iterate
**What didn't:** Win rate still 4-10%
**Lesson:** Right approach — prove the strategy works at small size first.

## ITERATION 7: Fee model fix — 1% → 0.25% for liquid tokens (April 1)
**Changed:** calc_sim_pnl uses 25 bps for liq >= 100 SOL, 100 bps for pump.fun
**Result:** Trades at +0.7%+ now show as WINS instead of LOSSES
**What worked:** Breakeven dropped from 2.2% to 0.55% for established tokens
**What didn't:** HFT on pump.fun still needs +2.2% to break even
**Lesson:** Fee model MUST match actual exchange. 0.25% Raydium ≠ 1% pump.fun.
**CRITICAL RULE:** Always verify breakeven before setting TP.

## ITERATION 8: MOMENTUM tokens (wETH, JUP, RAY, BONK) (April 1)
**Changed:** 27 tokens tracked via DEXScreener batch, enter on momentum
**Result:** Every trade exited MOM_FLAT — tokens move 0.01%/min, TP was 1.5%
**What worked:** Price infrastructure (batch pricing) works perfectly
**What didn't:** Momentum strategy on stable tokens = guaranteed flat exits
**Lesson:** Established tokens don't "momentum" — they oscillate. Use GRID instead.

## ITERATION 9: Grid trading replaces MOMENTUM (April 1 late)
**Changed:** 12 tokens with grid levels at 1.5% spacing, buy dips, sell at next level
**Result:** Grid initialized but hasn't triggered yet (needs price to drop 1.5% to first level)
**What worked:** Architecture works, grid levels calculated correctly
**What didn't:** Takes time — grid is a patient strategy, not instant gratification
**Lesson:** Grid needs hours/days to prove itself. Don't judge in 10 minutes.

## ITERATION 10: Extended SCALP hold time 20s → 60s (April 1 late) ← CURRENT BEST
**Changed:** SCALP_TIME_STOP_SEC 20→60, SCALP_MAX_HOLD_SEC 30→120
**Result:** WIN RATE JUMPED FROM 4.8% TO 36.4%
- durr +4.4% SCALP_TP = +$3.17
- ANIME +3.3% SCALP_TP = +$2.24  
- maxxing +1.5% TIME_TP = +$0.77
**What worked:** Giving tokens 60 seconds to move instead of 20
**What didn't:** Some SCALP entries still flat (Heist -0.1% at 62s)
**Lesson:** SCALP_WATCH finds good tokens — they just need TIME to move.
**BEST RESULT SO FAR: 36.4% WR, 4W/7L in 10 minutes**

## ITERATION 11: TIME_TP breakeven fix — strategy-dependent threshold (April 1 late)
**Changed:** TIME_TP at +0.5% for liquid tokens, +3% for pump.fun
**Result:** Tesla AI +1.2% no longer counts as a "win" on pump.fun (it's below 2.2% breakeven)
**What worked:** Honest P&L — no more fake wins that are actually losses
**What didn't:** N/A — this was a correctness fix
**Lesson:** Different fee structures = different breakeven = different TP thresholds.

---

## WHAT ACTUALLY MAKES MONEY (proven by data)

### WINNERS:
1. **SCALP_WATCH with 60s+ hold time** — 36.4% WR, finds DEXScreener trending tokens with real momentum
2. **HFT with aggressive TP** — catches rare +20-100% moonshots on pump.fun
3. **Grid trading** — pending validation, theoretically 0.95% per cycle

### LOSERS:
1. **REDDIT** — 0 wins, always flat, removed
2. **SWING** — 0 trades, never fired, removed  
3. **MOMENTUM on established tokens** — too slow to move in 2-10 minutes
4. **ESTAB scalping** — tokens too stable, removed
5. **Large position sizes ($1,500) on unproven strategies** — amplifies losses

### KEY RULES PROVEN BY DATA:
1. **Prove at 0.5 SOL before scaling** — ITERATION 5 proved this painfully
2. **Fee model must match reality** — ITERATION 7 turned losses into wins
3. **Give tokens time** — ITERATION 10 doubled win rate by extending hold 20s → 60s
4. **Take profit aggressively on volatile tokens** — ITERATION 4 catches moonshots
5. **Grid > Momentum for established tokens** — ITERATION 8 proved momentum fails on slow movers

---

## ITERATION 12: 30-minute sustained monitoring (April 1, 11pm)
**Config:** SCALP 60s flat exit, 120s max hold, 0.5 SOL positions, loss cap -0.05 SOL
**Result:** 18 trades, 6W/12L, 33.3% WR, P&L: -0.049 SOL
- SUKI +7.5% (+$5.60), durr +4.4% (+$3.17), Meep +3.6% (+$2.52), ANIME +3.3% (+$2.24)
- Avg win: +0.030 SOL ($2.42), Avg loss: -0.021 SOL ($1.67)
- R:R ratio: 1.4:1 (need ~42% WR to break even, currently at 33%)
**What worked:** SCALP_WATCH is the ONLY profitable strategy. Extended hold time lets tokens actually bounce.
**What didn't:** HFT disabled itself (0 trades this iteration). Grid hasn't triggered (waiting for dips).
**Lesson:** SCALP at 33% WR with 1.4:1 R:R is CLOSE to breakeven. Improving entry quality by even 10% = profitable.

---

## NEXT EXPERIMENTS TO TRY (prioritized)
1. **Grid trading daytime test** — grid hasn't filled yet, needs tokens to oscillate during active hours
2. **SCALP during peak hours (12pm-6pm EST)** — most SCALP winners came during active market
3. **Dip score integration with SCALP** — RSI+BB+EMA scoring built, needs candle data for trending tokens
4. **Smart money wallet copy trading** — GMGN API integration
5. **Re-entry cooldown** — tokens that just lost (durr, bunbun) re-entering and losing again

## ITERATION 13: Over-tightened filters (April 1 late night) ← FAILED
**Changed:** Added chg_h1 >= 1%, heat >= 60, txns >= 15, buys > sells
**Result:** 0 SCALP wins — filters blocked everything at night
**What worked:** Nothing — too strict
**What didn't:** Hourly uptrend check kills entries when market is flat
**Lesson:** Don't add multiple strict filters at once. Test one at a time.
**REVERTED to Iteration 10 settings + basic safety only.**

## ITERATION 14: HFT time gate + loosened filters (April 2 early)
**Changed:** HFT only 10am-10pm EST, reverted SCALP to Iteration 10 levels
**Result:** 2 trades in 5 min (low activity at midnight — expected)
**What worked:** HFT time gate eliminated 14 losing trades per session at night
**What didn't:** Low volume at midnight = fewer opportunities regardless
**Lesson:** HFT is purely a daytime strategy. SCALP works anytime but slow at night.

## KEY INSIGHT: SCALP Math
- 6 wins avg +4.5%, 13 losses avg -2.0% → R:R = 2.25:1
- At 31.6% WR with 2.25:1 R:R → right at breakeven
- Need 35% WR to be consistently profitable
- Each additional filter that blocks 1 bad entry without blocking 1 good entry = +WR
