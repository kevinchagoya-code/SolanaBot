---
name: diagnose-bot
description: Diagnose the SolanaBot — check all systems, find bugs, analyze recent trades
---

# Diagnose Bot

Run this when something seems wrong or after any code change.

## Checklist
1. Read dashboard_data.json — check balance, P&L, open positions, recent trades
2. Check debug.log last 50 lines for errors (FETCH_FAIL, ERROR, Traceback, CRASH)
3. Verify all scanners running (SCALP_WATCH started, MICRO_SCALP started, GRID TRADER started)
4. Check Geyser WebSocket status (connected or 403?)
5. Check Jupiter V3 pricing (JUP_BATCH: got prices?)
6. Check MICRO heartbeat (MICRO_HEARTBEAT: 7/7 prices?)
7. Analyze win/loss by strategy — which strategy is making/losing money?
8. Check for stuck positions (held > 600s)
9. Check for duplicate positions (same mint, same strategy)
10. Verify FLOOR_SL / ATR_SL / NUCLEAR_TP / ATR_TP firing correctly

## Quick Commands
```bash
# Full status
cat dashboard_data.json | python -c "import json,sys; d=json.load(sys.stdin); print(f'Balance: {d[\"balance\"]:.1f} P&L: {d[\"pnl_sol\"]:+.4f}')"

# Recent errors
tail -50 debug.log | grep -iE "ERROR|FAIL|CRASH|Traceback"

# Scanner status
grep "started\|HEARTBEAT" debug.log | tail -10

# Trade analysis
grep "CLOSING" debug.log | tail -20
```
