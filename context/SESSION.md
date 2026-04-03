# Current Session State
**Last updated:** April 2, 2026 ~3:30pm EDT
**Status:** SESSION ENDED — Starting new bot project

## Final Results This Session
- **P&L:** +0.08 SOL (+$6.32) over 1.5 hours — FIRST PROFITABLE SESSION
- **Win Rate:** 60% (15W/10L) — was 4.8% when we started
- **Best strategy:** SCALP at 52% WR, GRAD at 75% WR
- **HFT:** Disabled permanently (0% WR, $100+ losses)

## Critical Bug Fixed This Session
**NoneType crash in calc_bc_progress_from_raw** — THIS was the #1 bug.
Every fallback-priced position hit `None.get()` → exception → exit logic 
skipped → positions sat at +12% without selling. ONE LINE FIX.

## What's Proven Working
- ATR-based dynamic exits (SL=2xATR, partial=1.5xATR, TP=3xATR)
- SCALP_WATCH finding DEXScreener trending tokens (52% WR)
- GRAD_SNIPE catching graduations (75% WR)
- Jupiter V3 batch pricing (7 tokens, 3s polling)
- Proactive TP tiers (SCALP_TP2 at +2%, SCALP_TP3 at +3%)
- Moonbag system for catching runners
- Pattern detection (HIGHER_LOWS = hold, LOWER_HIGHS = sell)
- Loss cap at -0.05 SOL per trade
- 18 smart wallets being monitored for copy trades

## What Doesn't Work
- HFT on pump.fun (0% WR — tokens are flat)
- MICRO_SCALP (broken: undefined function call at line 4819)
- Grid trading (price glitches, no CSV logging, unverified profits)
- Groq AI entry/exit (return values never used in exit logic)
- Email alerts (disabled, unnecessary in sim mode)

## Architecture Decision
**Building NEW bot as separate project** using modular architecture:
- Each strategy = separate file with scan/enter/exit methods
- Centralized exit engine with per-strategy overrides
- Extracted from scanner.py's proven code, not rewritten from scratch
- See audit results in this conversation for full KEEP/REMOVE/FIX list

## Top Performing Tokens (across all sessions)
ZEN (5 wins), SLOF (5), MOON (5), ARTEMIS (4), ELONWIFLOB (4),
LOBSTER (4), bunbun (4), Community (4), Piece (4)
