---
name: analyze-trades
description: Analyze trade performance — find patterns in winners vs losers, calculate real P&L
---

# Analyze Trades

Run this to understand what's making money and what's not.

## Steps
1. Read snipe_log.csv — last 50 trades
2. Separate wins from losses by strategy
3. Calculate: avg win size, avg loss size, win rate, R:R ratio
4. Find tokens that appear multiple times (repeat winners like ZEN, SLOF, MOON)
5. Check exit reasons — which exits are profitable vs losers?
6. Verify P&L math: check for impossible profits (JTO +7.98 SOL on 0.5 position = bug)
7. Compare to ITERATION_LOG.md — is current iteration better or worse?

## Sanity Checks
- No position should profit more than entry_sol × 2 on a single trade (flag as bug)
- Check if calc_sim_pnl fee model matches actual DEX (CLMM 0.05% vs AMM 0.25% vs pump.fun 1%)
- Verify loss cap at -0.05 SOL is working

## Output
Add findings to ITERATION_LOG.md with before/after comparison.
