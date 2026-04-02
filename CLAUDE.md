# SolanaBot — Claude Code Guide

## Quick Start
```bash
# Kill old processes, start fresh
powershell -Command "Stop-Process -Name python -Force -ErrorAction SilentlyContinue"
sleep 3
powershell -Command "Start-Process cmd -ArgumentList '/k', 'cd /d C:\Users\kevin\SolanaBot && title Solana Bot Dashboard && python watchdog.py' -WindowStyle Normal"
powershell -Command "Start-Process cmd -ArgumentList '/k', 'cd /d C:\Users\kevin\SolanaBot && title Dashboard Web Server && python dashboard.py' -WindowStyle Normal"
# Dashboard: http://localhost:8080
```

## File Structure
```
C:\Users\kevin\SolanaBot\
├── scanner.py          # MAIN BOT (~6,800 lines) — all strategies, pricing, exits
├── dashboard.py        # Web dashboard (FastAPI + WebSocket, port 8080)
├── watchdog.py         # Crash recovery + rate limiter
├── profit_tracker.py   # Separate P&L display (optional)
├── requirements.txt    # Python dependencies
├── .env                # API keys (NEVER commit) — Helius, Groq, Jupiter
├── state.json          # Settings persistence (balance/P&L reset on restart)
├── dashboard_data.json # Written every 3s by scanner, read by dashboard
│
├── ERROR_LOG.md        # 21 bugs + 15 rules — READ BEFORE ANY CHANGES
├── ITERATION_LOG.md    # What worked vs didn't — READ BEFORE PARAMETER CHANGES
├── CLAUDE.md           # This file
│
├── docs/
│   ├── CLAUDE_CODE_SESSION.md    # Session 1 summary (March 31)
│   ├── CLAUDE_CONTEXT.md         # Auto-updated bot state
│   ├── research/                 # GitHub research V3-V9, DIP strategies, etc.
│   └── prompts/                  # Past implementation prompts (MEGA, GRID, etc.)
│
├── *.csv               # Trade logs (snipe_log, hft_log, moonbag_log, etc.)
├── *.json              # Runtime state (patterns, prefirelist, wallets, watchlist)
└── debug.log           # Full debug output (can be 100MB+)
```

## Before Making Changes — READ THESE:
1. **ERROR_LOG.md** — 21 bugs and 15 development rules. Every rule was learned the hard way.
2. **ITERATION_LOG.md** — 14 iterations of parameter changes with before/after results.

## Key Rules (from ERROR_LOG.md)
1. Calculate breakeven BEFORE setting TP (0.55% for Jupiter/Raydium, 2.2% for pump.fun)
2. Entry and exit controls must be independent
3. Different fee models: pump.fun 1%, Raydium/Jupiter 0.25%
4. Clean start every restart (load_state only restores settings)
5. Test math before deploying TP/SL changes
6. Never enter without verified price
7. Batch API calls (DEXScreener rate limits at ~30 req/min)

## Active Strategies
| Strategy | What | Entry | Exit | Status |
|---|---|---|---|---|
| GRID | Buy/sell at 1% levels on 12 tokens | Price hits grid level | Price rises 1% above entry | Waiting for fills |
| SCALP | DEXScreener trending tokens | +1-10% 5min, heat>55, liq>$5K | Ratcheting TP + pattern detection | Primary earner |
| HFT | Pump.fun new launches via Geyser | Score>88, momentum check | +5%/+20% TP, -15% SL | Daytime only (10am-10pm EST) |
| GRAD_SNIPE | Graduation to PumpSwap | 60s DEX delay, 3/hour max | -30% SL (pattern-aware hold), trailing | Has big winners |
| TRENDING | DEXScreener quality-filtered | +1% 5min, $10K liq, heat>55 | Time/SL/TP | Active |

## How scanner.py Is Organized (~6,800 lines)
```
Lines 1-300:      Constants, config, .env loading
Lines 300-700:    State class, position dataclass, helper functions
Lines 700-1200:   Technical indicators (EMA, RSI, BB, ATR, heat, momentum, patterns)
Lines 1200-1900:  Scoring, safety checks, price calculation, logging
Lines 1900-3400:  Position management, state save/load, context writer
Lines 3400-3900:  HFT entry (open_sim_position), GRAD entry, TRENDING entry
Lines 3900-4200:  DEXScreener scanner, Jupiter/DEXScreener price functions
Lines 4200-4600:  Grid trading engine
Lines 4600-4900:  SCALP_WATCH scanner loop
Lines 4900-5300:  Geyser WebSocket, migration listener
Lines 5300-6200:  update_sim_positions (ALL exit logic lives here)
Lines 6200-6800:  Rich terminal dashboard, main(), task launcher
```

## Git
- Repo: https://github.com/kevinchagoya-code/SolanaBot (private)
- Always commit after changes: `git add -A && git commit -m "..." && git push`
- PATH for gh: `export PATH="$PATH:/c/Program Files/GitHub CLI"`

## Dashboard
- Web: http://localhost:8080 (primary view)
- Terminal: Rich Live dashboard in the bot CMD window
- Dashboard reads dashboard_data.json (written by scanner every 3s)
