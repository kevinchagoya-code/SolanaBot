# SolanaBot Constitution

## What This Is
Solana crypto trading bot. Simulates trades, tracks P&L, targets profitability before going live.

## Non-Negotiable Rules
1. **TP must be above breakeven.** CLMM: 0.10% RT. AMM: 0.50% RT. Pump.fun: 2.2% RT.
2. **Entry and exit logic are independent.** Disabling entry must never disable exits.
3. **Clean start every restart.** Balance resets to 100 SOL. No stale positions restored.
4. **Loss cap: -0.05 SOL per trade.** No single trade loses more regardless of what happens.
5. **Never enter without a verified price.** No hardcoded estimates. No zero prices.
6. **Test math before deploying.** Run calc_sim_pnl to verify profit > 0 before any TP/SL change.
7. **Batch API calls.** Never make N individual calls when 1 batch exists.
8. **SOL in SOL = 1.0.** Never trade an asset denominated in itself.
9. **Always commit after changes.** Push to github.com/kevinchagoya-code/SolanaBot.
10. **Always kill all Python before restart.** `Stop-Process -Name python -Force`

## Files
```
scanner.py        — Main bot (all strategies, exits, pricing)
dashboard.py      — Web UI at localhost:8080
watchdog.py       — Crash recovery
.env              — API keys (never commit)
state.json        — Settings only (balance resets)
```

## Context Files
```
context/SESSION.md — Current session state (read this for where we are)
ERROR_LOG.md       — All bugs found + lessons learned
ITERATION_LOG.md   — What parameter changes worked vs didn't
```

## APIs
- **Helius** ($49/mo): RPC, DAS, WebSocket, priority fees
- **Jupiter V3** (free key): Price API, batch 50 tokens, CLMM routing
- **DEXScreener** (free): Token discovery, trending, boosts
- **Groq** (free): AI entry/exit decisions (llama-3.1-8b-instant)

## Active Strategies
| Strategy | Tokens | Entry | Exit |
|---|---|---|---|
| SCALP | DEXScreener trending | +1-10% 5min, heat>50 | ATR-based dynamic TP/SL |
| GRAD_SNIPE | Pump.fun graduations | 60s DEX delay, 3/hr max | Pattern-aware, -30% SL |
| GRID | 12 established tokens | Buy at 1% grid levels | Sell at +1% above entry |
| MICRO | 7 CLMM tokens | 0.15% dip + bounce | +1.5% TP, -0.5% SL, 60s max |

## Restart Command
```bash
powershell.exe -NoProfile -Command "Stop-Process -Name python -Force -ErrorAction SilentlyContinue"
sleep 3
powershell -Command "Start-Process cmd -ArgumentList '/k', 'cd /d C:\Users\kevin\SolanaBot && title Solana Bot Dashboard && python watchdog.py' -WindowStyle Normal"
powershell -Command "Start-Process cmd -ArgumentList '/k', 'cd /d C:\Users\kevin\SolanaBot && title Dashboard Web Server && python dashboard.py' -WindowStyle Normal"
powershell -Command "Start-Process 'http://localhost:8080'"
```
