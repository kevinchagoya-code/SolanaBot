# Claude Code Session Summary
**Date:** March 31 - April 1, 2026
**Duration:** ~18 hours continuous session
**Model:** Claude Opus 4.6 (1M context)

---

## STARTING STATE
- scanner.py existed with basic HFT strategy, Geyser WebSocket, pump.fun detection
- Dashboard using Rich library (already existed)
- 4 watched whale wallets (inactive)
- No scalping, no multi-strategy, no AI

## ENDING STATE
- 5-strategy trading bot with AI decision engine
- Groq-powered entry/exit decisions
- Multi-chain token scalping (Solana + ETH + Base)
- Heat score momentum analysis
- Moonbag system for catching runners
- Creator reputation tracking
- Adaptive market state engine
- 24/7 operation with established token scalping

---

## FILES MODIFIED

### Core Bot
- `C:\Users\kevin\SolanaBot\scanner.py` — Main bot (~6000+ lines). Every change listed below.
- `C:\Users\kevin\SolanaBot\watchdog.py` — Crash recovery with rate limiter (5 crashes/10min = halt + email)
- `C:\Users\kevin\SolanaBot\.env` — Added: HELIUS_RPC_URL_2, HELIUS_RPC_URL_3, ALERT_EMAIL, TWITTER_USERNAME/PASSWORD, GROQ_API_KEY, AI_DECISION_ENGINE, WATCH_WALLETS expanded

### New Files Created
- `C:\Users\kevin\SolanaBot\CLAUDE_CONTEXT.md` — Auto-updated every 5 min with live bot state
- `C:\Users\kevin\SolanaBot\analysis_report.txt` — Performance analysis from snipe_log.csv
- `C:\Users\kevin\SolanaBot\profit_tracker.py` — Live P&L display (run in separate terminal)
- `C:\Users\kevin\Desktop\SolanaBot.bat` — Desktop shortcut to start bot
- `C:\Users\kevin\Desktop\ProfitTracker.bat` — Desktop shortcut for P&L tracker
- `C:\Users\kevin\SolanaBot\GITHUB_RESEARCH_V3.md` — Migration detection research
- `C:\Users\kevin\SolanaBot\GITHUB_RESEARCH_V4.md` — Position management research
- `C:\Users\kevin\SolanaBot\GITHUB_RESEARCH_V5.md` — PumpSwap pool decoding research
- `C:\Users\kevin\SolanaBot\GITHUB_RESEARCH_V6.md` — Adaptive filters research
- `C:\Users\kevin\SolanaBot\GITHUB_RESEARCH_V7.md` — Heat score system research
- `C:\Users\kevin\SolanaBot\GITHUB_RESEARCH_V8.md` — Rich UI + Swing research
- `C:\Users\kevin\SolanaBot\GITHUB_RESEARCH_V9.md` — Scalp strategy + creator scoring + GMGN + DEX WS research
- `C:\Users\kevin\SolanaBot\requirements.txt` — Updated with twikit

### CSV Logs Created
- `snipe_log.csv` — All trades (added strategy, pyramid_count columns)
- `hft_log.csv` — HFT-specific trades (added strategy column)
- `moonbag_log.csv` — Moonbag creation/exit events
- `swing_log.csv` — Swing trade entries
- `scalp_log.csv` — Scalp-specific trades
- `ai_decisions.csv` — Every Groq AI decision with latency

---

## CHANGES TO SCANNER.PY (chronological)

### Bug Fixes
1. **SIAMI -84% loss** — Price fetch failure `continue` skipped all exit logic. Added `price_fetch_failures` counter, force-close after failures.
2. **Stop loss not triggering at -20%** — `PRICE_CHECK_INTERVAL` reduced 10s→3s. Added empty reserves detection.
3. **Peak hours wrong** — `_est_hour()` used hardcoded UTC-5 (EST), fixed to use `zoneinfo` for auto EDT/DST handling.
4. **PRICE_STALE exits** — Increased threshold to 10 failures, added exponential backoff, multi-RPC failover.
5. **Safety check 1048ms** — Replaced multi-RPC checks with single DAS `getAsset` call in HFT mode → 41-163ms.
6. **GRAD_SNIPE price bug** — Hardcoded estimate `0.0000004287` caused -100% losses. Replaced with DEXScreener verified pricing + PumpSwap pool reserve decoding.
7. **calc_price_impact returning 100%** — When `liq_sol=0`, impact was 1.0 (100%). Capped at 10%, default 2%.
8. **NameError HELIUS_API_KEY** — Moved definition before first usage.
9. **Established token PRICE_STALE** — Added `bc={}; vsolr=0; vtokr=0` for ESTAB tokens to skip BC processing.
10. **SOL/USDC price bug** — Entry at 0.0002, "gained" 500,000%. Removed SOL/USDC, wBTC, wETH from established tokens. Added 50x sanity check.

### Strategy: HFT (enhanced)
- `HFT_STOP_LOSS_PCT`: -20% → -30% (proven setting)
- `HFT_MEGA_STOP_LOSS_PCT`: -15% for score 130+ tokens
- `HFT_MIN_SCORE`: oscillated 88↔95↔100↔88 based on market conditions
- `HFT_MIN_BC_PROGRESS`: 10% → 5% → 0% (disabled)
- `HFT_MIN_BC_VELOCITY`: 25 → 10
- `HFT_MIN_PRICE_MOVE`: 3% → 1% → 0.5% → 0% (any non-negative)
- `HFT_MAX_HOLD_SEC`: 300 → 90 (fixed timeout issue)
- `HFT_PRICE_CHECK_SEC`: 10 → 2 (faster momentum check)
- Buyer check removed (was blocking too many entries)
- Momentum lock: if token hits +3%, disable flat exit, extend hold to 120s
- Pyramiding added: +3%, +8%, +15% with per-level ratios (50%, 100%, 50%)
- Negative velocity filter: skip if price drops >5% during momentum check

### Strategy: GRAD_SNIPE (new)
- Migration listener on `39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg` (migration wrapper program)
- DEXScreener verified entry price (3 attempts + pool RPC fallback)
- `_get_pool_price_direct()`: getProgramAccounts to find pool, decode vault balances
- Tiered exit: 50% at 2x, 25% at 3x, 25% moonbag
- Trailing stop + velocity dump exit
- Bad price validation: GRAD_BAD_ENTRY if -15% in first 15s
- Position size: dynamic by signal stack (GRAD, +TREND, +REDDIT, +WHALE)
- SL tightened: -30% → -15%
- NEAR_GRAD: implemented then disabled (lost 0.836 SOL)
- Restart cleanup: all GRAD positions closed on restart

### Strategy: SWING (new)
- Watchlist builder: DEXScreener scan every 30min for graduated tokens
- Pattern scanner: BREAKOUT, BOUNCE, CONTINUATION, VOL_SURGE
- 0.1 SOL positions, -8% SL, +15% TP (50% partial), 2hr max hold
- Dashboard shows watchlist count and top tokens

### Strategy: SCALP (new — primary profit engine)
- SCALP_WATCH: DEXScreener trending bounce scanner, 7s cycle
- SCALP (HFT piggyback): enters on tokens already in HFT positions with high heat
- ESTAB token scalper: BONK, WIF, JUP, JTO, PYTH, PEPE, FLOKI, BRETT, TOSHI
- Flat $0.012 SOL per trade (~$0.99)
- Trailing micro-profit: activate at +0.5%, trail 40% of peak, floor +0.3%
- Adaptive TP/SL by market state: HOT/WARM/SLOW/DEAD
- Token similarity check (difflib 60% threshold)
- Creator reputation tracking
- Heat-driven entry: heat>55, buy_ratio>60%, liq>$10K, txns>20
- Dynamic slot management: 5+ open → raise entry bar
- Blacklist: SL exits 2min, FLAT exits 30s, estab tokens never blacklisted
- Max 25 concurrent scalp positions

### Groq AI Decision Engine (new)
- `ai_should_enter()`: Groq llama-3.1-8b-instant decides BUY/SKIP + position size
- `ai_should_exit()`: Groq decides HOLD/SELL_HALF/SELL_ALL at crossroads
- AI monitor: Groq adjusts TP and heat thresholds every 2 minutes
- Rate limit: 14,400 calls/day max, fallback to hardcoded rules
- All decisions logged to ai_decisions.csv
- Dashboard: "AI: Groq OK 281ms calls:47/14400"

### Heat Score System (new)
- `calc_heat_score()`: buy_ratio(40%) + volume_acceleration(30%) + price_momentum(20%) + consecutive_buys(10%)
- Patterns: ROCKET(80+), HEATING(60-80), WARM(40-60), COLD(<40), DUMP(buy_ratio<30%)
- Universal HEAT_DUMP exit: fires on DUMP pattern for all strategies
- DEXScreener buy/sell ratio as heat proxy for WATCH_SCAN positions

### Moonbag System (new)
- On trailing stop exit: sell 75%, keep 25% as moonbag
- Moonbag exits only on: price drops 50% from peak, OR DEXScreener trending
- Moonbag skips all normal exit logic (no SL, no time stop)
- Logged to moonbag_log.csv
- Dashboard shows: BAGS: X tokens +Y.YYY SOL

### Adaptive Market State Engine (new)
- `update_market_state()`: runs every 5 minutes
- Classifies: HOT/WARM/SLOW/DEAD based on BC velocity, token launch rate, avg score
- Auto-adjusts: MIN_SCORE, momentum threshold, BC progress, position size multiplier
- Win rate adaptive: WR>40% loosens filters, WR<20% tightens

### Dynamic Position Sizing (new)
- HFT: score-based (88-100: 0.02, 101-115: 0.05, 116-130: 0.08, 131+: 0.12)
- GRAD: signal-stack based (GRAD: 0.10, +TREND: 0.15, +REDDIT: 0.20, +WHALE: 0.30)
- Loss limits: max 0.10/trade, 0.50/hour, 1.20/day
- `_cap_position_size()` enforces maximum
- Daily loss counter shown in dashboard with progress bar

### Capital Management (new)
- `STARTING_BALANCE_SOL = 5.0`
- Balance tracking: deducted on open, returned + profit on close
- Persisted in state.json across crashes
- Capital check before every position open

### Infrastructure
- Helius Developer plan integration: DAS getAsset, getPriorityFeeEstimate, Enhanced Transactions API
- 3 RPC endpoints (standard + dedicated + gatekeeper)
- Migration listener (logsSubscribe on migration wrapper)
- DEXScreener batch pricing (one call for all positions)
- Reddit scanner (5 subreddits, feeds into prefire system)
- Twikit Twitter scraper (blocked by upstream KEY_BYTE bug)
- Wallet activity checker (getSignaturesForAddress, hourly)
- Context email (Gmail, 30min heartbeat + conditional on important changes)
- Watchdog crash rate limiter (5 crashes/10min = halt + email)
- Settings persistence in state.json (survives crashes)
- `CLAUDE_CONTEXT.md` auto-updates every 5 minutes

### Dashboard Enhancements
- Market state color background in header
- Daily loss progress bar
- Exit type icons in results panel
- Color-coded log panel
- Strategy breakdown with per-strategy win rate
- Scalp stats: trades/min, $/min, heat threshold
- Keyboard shortcuts: H(hft), P(scalp), +/-(score adjust)
- Refresh rate: 2→4 per second

---

## WHAT'S WORKING
- HFT detection via Geyser WebSocket (~0.1ms latency)
- SCALP_WATCH finding and trading tokens from DEXScreener
- Established token scalping (BONK, WIF, JUP, PEPE, etc.)
- Groq AI making entry/exit decisions
- Heat score tracking and DUMP exits
- Moonbag system (created 2 moonbags this session)
- Trailing micro-profit exits catching +2-18% wins
- Migration listener detecting graduations
- All exit logic (SL, trail, flat, time, heat, AI)
- Dashboard with Rich Live display
- Profit tracker (separate terminal)
- Email context updates
- Watchdog with crash recovery

## WHAT'S DISABLED/BLOCKED
- **NEAR_GRAD**: disabled (lost 0.836 SOL pre-graduation)
- **Twikit Twitter**: blocked by Twitter JS encryption change (KEY_BYTE error)
- **GMGN scraping**: needs tls_client fingerprint spoofing (run Dragon CLI separately)
- **DEXScreener WebSocket**: needs socket.io protocol (using HTTP polling instead)
- **Live trading**: EXECUTE_TRADES=false (simulation only)

## SESSION 2 FIXES (April 1, 2026)

### FIX: FETCH_FAIL "String is the wrong size" — positions getting stuck
**Root cause**: Pump.fun updated their bonding curve smart contract (added volume accumulators, v2, cashback fields). Our parser expected exactly 151 bytes → `struct.unpack` threw "String is the wrong size". Also, profitable runners (+10-20%) graduate to PumpSwap AMM, making bonding curve reads return empty/changed data.

**Changes to scanner.py:**
1. `BC_SIZE`: 151 → 49 (minimum bytes needed: discriminator + reserves + complete flag)
2. `parse_bc_account_data`: flexible parsing via slice notation, handles list/string/bytes response formats, catches `struct.error`+`ValueError`+`IndexError`+`KeyError`
3. `fetch_bc_direct`: on `ValueError`/`struct.error` returns `_parse_error=True` marker instead of retrying all endpoints with same broken data
4. Main position loop (bc=None): DEXScreener fallback now works for ALL strategies (was only GRAD/TRENDING/SCALP), logs `PRICE_FALLBACK` to activity feed
5. Main position loop (bc returned): graduated tokens skip BC entirely → go straight to DEXScreener → PumpSwap pool RPC fallback chain. Graduation detected in same cycle gets immediate DEXScreener price.
6. Force-exit threshold: 10 → 5 consecutive failures. Uses **last known price** (not entry price) so profitable stuck positions keep their gains.
7. Dashboard: `Conf` column → `Src` column showing BC/DEX/POOL price source per position
8. `_get_pool_price_rpc` + `_get_pool_price_direct`: exception handlers now catch `struct.error`

**Result**: ROCKET (+20%), TARO (+16%), wbtc (+10%) type runners can now exit properly. No more stuck positions blocking slots.

## KEY METRICS (end of session 1)
- Balance: ~5.0 SOL (reset multiple times for testing)
- Best single trade: NoKings +18.7%, FOOL +8.8%, Rapunzel +4.9%
- Strategies: 5 active (HFT, GRAD_SNIPE, SCALP, SWING, ESTAB)
- Max concurrent positions: 40
- AI calls: Groq free tier (14,400/day)

## NEXT SESSION TODO
1. Run Dragon CLI to populate smart_wallets.json with 30-50 profitable wallets
2. Train LightGBM model from scalp_log.csv (train_model.py)
3. Add socket.io client for DEXScreener WebSocket streaming
4. Extract sell transaction builders from chainstacklabs for live execution
5. Analyze overnight P&L to tune scalp parameters
6. Consider going live with small real capital (0.5 SOL test)

## REPOS RESEARCHED
1. chainstacklabs/pumpfun-bonkfun-bot — Migration detection, PumpSwap sell logic
2. caterpillardev/pumpfun-sniper-go — Geyser gRPC patterns
3. coffellas-cto copy trading bot — Racing transaction confirm
4. YZYLAB/solana-trade-bot — Position management patterns
5. outsmartchad/solana-trading-cli — Jito bundles, TX orchestrator
6. LouisdeMagician/pumpswap-watcher — Pool account decoding
7. FLOCK4H/Dexter — Creator scoring algorithm
8. bloodbee/pump-fun-sniper-bot — Graduated sell strategy, token similarity
9. krecicki/memecoin.watch — Heat metric, buy/sell ratio
10. Sarthak-006/Solana-Advanced-Market-Making-Bot — Volatility calculation
11. Jackhuang166/ai-memecoin-trading-bot — Win probability, circuit breaker
12. 1f1n/Dragon — GMGN smart money wallet finder
13. sashaboulouds DEXScreener WebSocket gist — WS streaming format
