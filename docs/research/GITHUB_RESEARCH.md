# GitHub Research: Pump.fun Sniping Techniques

Date: 2026-03-30 | 8 repos analyzed, 5 new functions integrated

---

## Repos Analyzed

| # | Repo | Lang | Stars | Focus |
|---|------|------|-------|-------|
| 1 | [1fge/pump-fun-sniper-bot](https://github.com/1fge/pump-fun-sniper-bot) | Go | ~200 | Full production sniper: WS detection, creator validation, Jito bundles |
| 2 | [TreeCityWes/Pump-Fun-Trading-Bot-Solana](https://github.com/TreeCityWes/Pump-Fun-Trading-Bot-Solana) | JS | ~100 | Selenium-based scraper with pumpapi.fun relay |
| 3 | [DracoR22/handi-cat_wallet-tracker](https://github.com/DracoR22/handi-cat_wallet-tracker) | TS | ~80 | Production Telegram bot: onLogs wallet tracking across Raydium/Jupiter/pump.fun |
| 4 | [jaimindp/Twitter_Activated_Crypto_Trading_Bot](https://github.com/jaimindp/Twitter_Activated_Crypto_Trading_Bot) | Python | ~300 | Exchange announcement keyword matching → instant Binance/Kraken trades |
| 5 | [Milofordegens/milo](https://github.com/Milofordegens/milo) | JS | ~50 | DexScreener scoring → Jupiter trading → ChatGPT tweet generation |
| 6 | [MbotixTech/meme-coins-signal](https://github.com/MbotixTech/meme-coins-signal) | TS | ~40 | DexScreener 3s polling with RugCheck + Birdeye filters |
| 7 | [solanabots/Solana-Twitter-Bot](https://github.com/solanabots/Solana-Twitter-Bot) | Python | ~30 | Twitter account monitor → multi-wallet swap execution |
| 8 | [nirholas/pump-fun-sdk](https://github.com/nirholas/pump-fun-sdk) | TS | ~100 | Complete pump.fun protocol SDK: bonding curve, AMM, fees, PDAs |

---

## What Was Integrated

### 1. Correct Bonding Curve Formula (from nirholas/pump-fun-sdk)
**Old:** `progress = (virtualSolReserves - 30) / (85 - 30) * 100` (approximation)
**New:** `progress = (1 - realTokenReserves / 793,100,000,000,000) * 100` (exact)
**Speed improvement:** None directly, but eliminates false graduation predictions that caused missed exits.
**Function:** `calc_bc_progress()` updated, `calc_bc_progress_from_raw()` added.

### 2. Direct RPC Bonding Curve Read (from 1fge/pump-fun-sniper-bot)
**Old:** Fetch bonding curve via pump.fun HTTP API (~500ms round trip)
**New:** Read bonding curve PDA directly via `getAccountInfo` with `commitment: processed` (~200ms)
**Speed improvement:** ~300ms faster per position update
**Functions:** `parse_bc_account_data()`, `fetch_bc_direct()`
**Key insight from 1fge:** Using `CommitmentProcessed` instead of `Confirmed` saves ~200ms. The bonding curve PDA is derived as `PDA(["bonding-curve", mint], PUMP_PROGRAM_ID)`.

### 3. onLogs WebSocket Wallet Watching (from DracoR22/handi-cat_wallet-tracker)
**Old:** Poll `getSignaturesForAddress` every 15 seconds per wallet
**New:** Subscribe to `logsSubscribe` per wallet via WebSocket, filter for pump.fun program IDs
**Speed improvement:** 15 seconds → ~400ms latency (37x faster)
**Function:** `watch_wallets_scanner()` completely rewritten
**Pattern from handi-cat:** Each wallet gets its own `logsSubscribe` with `mentions: [wallet_address]`. When logs arrive, check if any pump.fun program ID appears in the log text. If yes, fetch the full transaction and extract mint from `postTokenBalances`.

### 4. Fee-Aware Buy/Sell Quotes (from nirholas/pump-fun-sdk)
**Old:** `tokens = entry_sol / price` (ignoring fee structure)
**New:** Exact constant-product AMM with fee deduction matching on-chain logic
**Functions:** `pump_buy_quote()`, `pump_sell_quote()`
**Buy formula:** `input = (solAmount - 1) * 10000 / (feeBps + 10000)`, then `tokens = input * vtokr / (vsolr + input)`
**Sell formula:** `sol = tokens * vsolr / (vtokr + tokens)`, then `net = sol - ceil(sol * feeBps / 10000)`

### 5. Program IDs and Instruction Discriminators (from nirholas/pump-fun-sdk + 1fge)
**Added constants:**
- `PUMP_AMM_PROGRAM_ID` — graduated pool trading (PumpSwap)
- `PUMP_FEE_PROGRAM_ID` — fee sharing protocol
- `PUMP_MAYHEM_ID` — mayhem mode
- `PUMP_MINT_AUTH` — token mint authority (used in wallet filtering)
- `PUMP_IX_CREATE/BUY/SELL` — Anchor instruction discriminators (8-byte prefixes)
- `BC_SIZE = 151` — bonding curve account data size
- `PUMP_INITIAL_REAL_TOKEN_RESERVES = 793,100,000,000,000` — starting reserves

These are needed for building real transactions when `EXECUTE_TRADES=true`.

### 6. Bonding Curve Binary Layout (from nirholas/pump-fun-sdk + 1fge)
**Added:** Full 151-byte account data layout documentation and parser
```
Bytes 8-15:  virtualTokenReserves (u64 LE)
Bytes 16-23: virtualSolReserves (u64 LE)  
Bytes 24-31: realTokenReserves (u64 LE)
Bytes 32-39: realSolReserves (u64 LE)
Bytes 40-47: tokenTotalSupply (u64 LE)
Bytes 48:    complete (bool) ← graduation flag
Bytes 49-80: creator (PublicKey)
Bytes 81:    isMayhemMode (bool)
```

---

## What Was Skipped and Why

### Yellowstone Geyser gRPC (from Chainstack/Shyft docs)
**What:** 50-100ms faster token detection than logsSubscribe
**Why skipped:** Requires Geyser-enabled RPC endpoint (separate from standard Helius). Would need `grpcio` dependency and protocol buffer compilation. Tagged for future if sub-200ms detection becomes critical.

### Selenium Scraping (from TreeCityWes)
**What:** Scrape pump.fun web UI for bonding curve data
**Why skipped:** 5-15 second latency. Strictly inferior to our WebSocket + direct RPC approach. Fragile (breaks on any UI change).

### DexScreener Polling (from Milo, meme-coins-signal)
**What:** 3-10 second polling of DexScreener new pairs API
**Why skipped:** DexScreener indexes tokens AFTER they appear on-chain. Our WebSocket catches them at creation. DexScreener would always be slower for pump.fun specifically.

### Spam Sell Strategy (from 1fge)
**What:** Send 15 sell transactions over 6 seconds with `minSolOutput = 1`
**Why skipped:** Only useful for live execution. We're in simulation mode. The strategy is documented in UPGRADES.md for when `EXECUTE_TRADES` is enabled. The concept: fire 15 sells every 400ms alternating Jito/vanilla to guarantee exit.

### Creator ATA Subscription (from 1fge)
**What:** Subscribe to creator's Associated Token Account to detect selling in ~200ms
**Why skipped for now:** Would require subscribing to a new account per position (N subscriptions for N positions). The pump.fun trades API currently catches dev sells within our 10-second update cycle. Tagged for future when execution is live and 200ms matters.

### Exchange Account Twitter Monitoring (from jaimindp)
**What:** Monitor @binance, @coinbase for listing announcements with specific keywords
**Why skipped:** These exchange listings affect Binance/Coinbase-traded tokens, not pump.fun meme coins. Different market segment. Our Twitter queries are already tuned for pump.fun-specific signals.

### twikit Cookie-Based Twitter (from solanabots)
**What:** Unofficial Twitter API via browser cookie authentication
**Why skipped:** Fragile, breaks frequently, account ban risk. Our v2 bearer token approach is official and reliable.

### ChatGPT Tweet Generation (from Milo)
**What:** Generate trading tweets using GPT persona
**Why skipped:** We're building a scanner, not a social media bot. Would add OpenAI API cost for no trading edge.

---

## Speed Comparison

| Operation | Our Old | Our New | Best Found | Gap |
|-----------|---------|---------|------------|-----|
| New token detection | ~400ms (logsSubscribe) | ~400ms (unchanged) | ~100ms (Geyser gRPC) | 300ms — needs Geyser RPC |
| Bonding curve read | ~500ms (HTTP API) | ~200ms (direct RPC processed) | ~200ms (1fge) | Matched |
| Wallet copy trading | 15s (polling) | ~400ms (onLogs WS) | ~400ms (handi-cat) | Matched |
| Buy/sell quote accuracy | ~95% (approx fees) | ~99.9% (exact AMM) | ~99.9% (pump-fun-sdk) | Matched |
| BC progress accuracy | ~90% (vsolr approx) | ~99.9% (realTokenReserves) | ~99.9% (pump-fun-sdk) | Matched |
| Creator sell detection | 10s (trades API poll) | 10s (unchanged) | ~200ms (ATA subscribe) | 9.8s — tagged for live mode |
| Twitter signal latency | ~60s (search interval) | ~60s (unchanged) | ~1s (per-account poll) | 59s — different approach |

---

## Key Technical Findings

### No ML Models Exist
All 8 repos use rule-based scoring. No pre-trained models for pump.fun token quality. Our pattern learning system (term weights from closed positions) is more sophisticated than anything found.

### The 1fge Bot Is the Gold Standard
The archived Go sniper from 1fge is the most production-battle-tested codebase found. Key lessons:
- 2-second timeout on everything: if data isn't available in 2s, skip and move on
- Always create ATA, never check first (saves one RPC call)
- Creator validation is the #1 anti-rug technique (check funding wallets, not just the creator)
- Sell fast: spam 15 transactions, accept any price

### handi-cat Wallet Tracking Is Production-Grade
The TypeScript Telegram bot handles hundreds of wallets with per-wallet onLogs subscriptions, rate limiting, and ban management. Our new implementation follows the same pattern but simplified for our use case.

### pump-fun-sdk Has the Correct Math
Every other repo uses approximations for bonding curve progress and fee calculations. The nirholas SDK has the exact formulas matching on-chain Anchor code. We now use these exact formulas.
