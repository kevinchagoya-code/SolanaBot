# Current Session State
**Last updated:** April 2, 2026 ~2:30pm EDT

## Where We Are
- **P&L:** +0.08 SOL (+$6.32) over 1.5 hours
- **Win Rate:** 60% (15W/10L) — best ever
- **Best strategy:** SCALP at 52.6% WR, GRAD at 75% WR
- **HFT:** Disabled (0% WR across all sessions)

## What Just Got Fixed
- **NoneType crash in calc_bc_progress_from_raw** — this was THE bug causing positions not to sell. Every fallback-priced position hit `None.get()` → exception → exit logic skipped → position sat forever. ONE LINE FIX.
- **ATR-based dynamic exits** — SL=2xATR, partial=1.5xATR, TP=3xATR. Adapts to each token's volatility.
- **`continue` bug** — bare `continue` after price fallback was skipping all exits for Jupiter-priced positions.

## What's Working
- SCALP_TP3 exits catching +3-5% wins (HEART +4.6%, Chicky +4.3%, MOON +4.2%)
- ATR_TP catching big wins (xiaoju +13.3%)
- Grid completing cycles (PYTH +1.0%)
- Loss cap at -0.05 SOL preventing disasters
- 18 smart wallets being monitored for copy trades
- Jupiter V3 batch pricing on 7 MICRO tokens every 3s

## Known Issues
- MEZo stuck from pre-fix session (will clear on restart)
- JTO grid had price glitch causing fake +39 SOL profit (bug in price conversion)
- MICRO_SCALP finds dips but rarely enters (tokens mostly flat)
- Grid only fills when tokens oscillate (slow during trends)

## Key Numbers
- Position sizes: 0.25-0.5 SOL
- Starting balance: 100 SOL (resets every restart)
- CLMM fee: 0.05% per side (PYTH, JUP, RAY, ORCA, etc.)
- AMM fee: 0.25% per side (meme coins)
- Pump.fun fee: 1.0% per side

## Top Performing Tokens (across all sessions)
ZEN (5 wins), SLOF (5), MOON (5), ARTEMIS (4), ELONWIFLOB (4),
LOBSTER (4), bunbun (4), Community (4), Piece (4)
