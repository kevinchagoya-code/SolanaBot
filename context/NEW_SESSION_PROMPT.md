# New Session Prompt — Copy/paste this when starting a new Claude Code session

---

## PASTE THIS:

I'm working on a Solana crypto trading bot. The project is at C:\Users\kevin\SolanaBot

Before doing ANYTHING, read these files in this order:

1. `C:\Users\kevin\SolanaBot\CLAUDE.md` — The constitution. 10 non-negotiable rules.
2. `C:\Users\kevin\SolanaBot\context\SESSION.md` — Current state. Where we left off, what's working, known issues.
3. `C:\Users\kevin\SolanaBot\context\ERROR_LOG.md` — 16+ bugs we've found and fixed. Every lesson learned. Check this BEFORE making any changes to avoid repeating mistakes.

The main bot code is `scanner.py` (~7,300 lines). The web dashboard is `dashboard.py` (localhost:8080). 

Key things to know:
- We're in SIMULATION mode (EXECUTE_TRADES=false). Not real money yet.
- HFT strategy is DISABLED (0% win rate). Don't re-enable it.
- SCALP is our best strategy (52% WR). GRAD_SNIPE is second (75% WR).
- We use Jupiter V3 for pricing (API key in .env) and Helius $49 tier for RPC/WebSocket.
- ATR-based dynamic exits replace flat % stops — each token gets custom SL/TP based on its volatility.
- The biggest bug class: silent exceptions in the update loop that skip exit logic. Always check for NoneType errors.
- GitHub repo: github.com/kevinchagoya-code/SolanaBot (private). Always commit after changes.
- Always kill all Python processes before restarting: `powershell.exe -NoProfile -Command "Stop-Process -Name python -Force -ErrorAction SilentlyContinue"`
- The iteration log at `context/ITERATION_LOG.md` shows what parameter changes worked vs failed — read it before changing any trading parameters.

After reading those files, tell me what you see and ask what I want to work on.

---
