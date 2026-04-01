# Upgrades Log — scanner.py v3

Date: 2026-03-30 | 1791 lines, 72 functions

---

## What Was Added

### 1. Bonding Curve Velocity Tracking
- `calc_bc_progress()` — 0-100% from virtual_sol_reserves (30 SOL start, 85 SOL graduation)
- `calc_bc_velocity()` — %/minute from rolling 60-entry history
- SimPosition tracks `bc_progress`, `bc_velocity`, `bc_history[]`
- Dashboard shows progress bar `[████░░░░░░]` with color coding
- +30 score boost when velocity hits 10%+/min (`BC_FAST` signal)
- Alerts at 75% (`BC_75%`), 85% (`BC_85%`), 95% (`BC_95%`)
- GRADUATING badge in dashboard when curve over 75%
- VELOCITY badge when moving fast

### 2. Exit Ladder
- 50% sold at 2x (+100%) — logged as `TP1_50%` in snipe_log.csv
- 75% of remainder sold at 3x (+200%) — logged as `TP2_75%`
- Hard exit 100% at 30 minutes regardless of price
- -60% stop loss unchanged
- Each partial exit logged separately via `_log_partial_exit()`
- Dashboard shows exit ladder progress: `----` / `2x--` / `2x3x`

### 3. RugCheck.xyz Integration
- `fetch_rugcheck()` queries `api.rugcheck.xyz/v1/tokens/{mint}/report`
- `parse_rugcheck()` returns status (Good/Warn/Danger) and warnings
- DANGER tokens skipped entirely (not sim-tracked)
- WARN: -20 score penalty
- GOOD: included in scoring via `rugcheck_ok` field
- RC column in dashboard with color coding (green/yellow/red)

### 4. Updated Safety Scoring (12 checks, 0-200 scale)
- Mint authority revoked: +20 (via `getAccountInfo` jsonParsed)
- Freeze authority revoked: +20 (honeypot prevention)
- Bundle detection: -40 (3+ buys in same slot = insider bundler)
- Dev holds <5%: +15
- Serial deployer (50+ recent txs): logged
- BC >50% in first hour: +20
- Organic holder growth (5+ holders): +15
- Social links: +15
- Holder concentration <50%: +15
- Dev not sold: +15
- Liquidity >10 SOL: +15
- Age >2 min: +10

### 5. Narrative Meta Scoring
- AI/agent: +25 | Political: +20 | Animal: +20 | Celebrity: +15
- Absurdist: +10 | Generic moon/rocket: -10

### 6. Twitter Search Terms (14 high-signal queries)
Replaced 31 generic terms with:
```
"CA:" pump.fun -filter:replies min_faves:3
"just launched" pump.fun -filter:replies
"stealth launch" solana -is:retweet
"just graduated" pump.fun
"about to graduate" pump.fun
"LP burned" "renounced" solana min_faves:5
has:cashtags "pump.fun" min_faves:5 -is:retweet
$SOL ("just ape" OR "aping" OR "aped") pump.fun
"bonding curve" solana -is:retweet
"king of the hill" pump.fun
"migrating" pump.fun
"CTO" solana min_faves:5
"dev wallet" pump.fun -is:retweet
"bundled" pump.fun -is:retweet
```

### 7. Bitquery Integration
- `bitquery_scan()` queries Bitquery GraphQL every 30 seconds
- Finds pump.fun tokens with $500+ volume in last 60 seconds
- These are high-probability graduation candidates (BC velocity proxy)
- Creates BITQUERY pre-fire signal with score 85
- Requires `BITQUERY_API_KEY` in .env

### 8. Jito Bundle Support
- `send_jito_bundle()` sends signed tx bundles to Jito block engine
- `build_jito_tip_instruction()` creates SOL transfer tip to Jito account
- Tip account: `96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5`
- Configured via `JITO_TIP_LAMPORTS` in .env (default 10000 = 0.00001 SOL)
- Only active when `EXECUTE_TRADES=true`
- Ensures block-level priority for live trades

### 9. Watch Wallet Copy Trading
- `watch_wallets_scanner()` checks WATCH_WALLETS every 15 seconds
- Detects new pump.fun buys within 30 seconds of execution
- Immediately opens sim position with WALLET_COPY source and score 90
- Tracks last-seen signature per wallet to avoid re-processing
- Configure via `WATCH_WALLETS=addr1,addr2,addr3` in .env

### 10. Timing Boost
- 12PM-4PM EST: +10 (PEAK label in header)
- 8AM-12PM / 4PM-8PM: +5 (ACTIVE)
- 8PM-2AM: 0 (DEGEN)
- Midnight-8AM: -10 (LOW)

### 11. Dashboard Upgrades
- BC progress bar: `[████░░░░░░]` with green (>85%), cyan (>50%), dim
- VELOCITY badge (green) when curve moving 10%+/min
- GRADUATING badge (gold) when curve over 75%
- RugCheck status badge (Good/Warn/Danger with colors)
- Narrative/source badge column showing discovery source
- Exit ladder column showing `----` / `2x--` / `2x3x` tranche status
- Timing window label in header (PEAK/ACTIVE/DEGEN/LOW)
- Bitquery signal count in stats

### 12. .env Additions
```
BITQUERY_API_KEY=your_key
JITO_TIP_LAMPORTS=10000
WATCH_WALLETS=wallet1,wallet2,wallet3
```

### 13. Bot-Dominated Token Filtering
- `detect_bot_cluster()`: if >60% of first 30 trades from one wallet = skip
- Skipped count shown in stats panel

---

## File Inventory

| File | Purpose |
|------|---------|
| scanner.py | Main scanner (1791 lines, 72 functions) |
| .env | Configuration (API keys, wallets, settings) |
| requirements.txt | Python dependencies |
| snipe_log.csv | Closed positions + partial exits (16 columns) |
| new_tokens_log.csv | All discovered tokens (12 columns) |
| intelligence_log.csv | Twitter/Bitquery/wallet signals (13 columns) |
| prefirelist.json | Live pre-fire watchlist (survives restarts) |
| successful_wallets.json | Wallets that produced 400%+ winners |
| patterns.json | Term performance + last 500 closed positions |
| debug.log | Internal diagnostics |
| SIGNAL_RESEARCH.md | Research documentation |
| UPGRADES.md | This file |
