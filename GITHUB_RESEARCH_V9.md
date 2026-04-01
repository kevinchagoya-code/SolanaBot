# V9 Research — Scalp Strategy

## Core Philosophy
Not hunting moonshots. Hunting tiny guaranteed moves.
Many small wins per hour = $0.15-0.30/min target.

## Entry Logic (from Hummingbot pure market making)
- Check every 2s for tokens with confirmed upward momentum
- Piggyback on existing HFT position data (heat score, price history)
- Score >= 70 (wider net), heat >= 50, buy ratio >= 60%
- No momentum wait — enter immediately
- Fast safety only: DAS getAsset (no RugCheck)

## Exit Logic (check every price update)
- TP: +2.5% → exit 100%
- Rocket: +4% → exit 100%
- SL: -3% → exit 100%
- Flat: 20s held + <1% change → exit
- Time: 30s max → exit
- Dump: heat pattern = DUMP → exit
- NO trailing, NO moonbag, NO pyramiding

## Position Sizing
- Flat 0.01 SOL always (no scaling)
- Max 10 concurrent scalp positions
- Uses SCALP_{mint} key to allow same token in HFT + SCALP

## $/min Tracking
- Rolling 60s window for trades/min
- Dollar per minute = total scalp P&L / uptime minutes
- Target tiers: $0.10 baseline, $0.18 good, $0.30 target

## DEGEN Mode Behavior
- SCALP stays ON when all other strategies shut down
- Lower thresholds: score 60+, heat 40+
- Smaller TP: 1.5%, tighter SL: -2%
- Dead markets still have tiny oscillations to capture

## Known Limitations
- 0.01 SOL per trade = ~$0.83, so +2.5% = ~$0.02 per win
- Need high trade frequency to make meaningful profit
- Simulation P&L includes pump.fun fees (1% each way)
- Real execution would need sub-second Jito confirmation

## SCALP_WATCH Batch Price Fix
- Replaced per-position DEX calls with single batch endpoint
- Endpoint: GET https://api.dexscreener.com/tokens/v1/solana/{mint1},{mint2},...
- One call returns prices for ALL SCALP/GRAD/SWING positions
- Reduces from 200 calls/min to ~20 calls/min
- Heat score from buy/sell ratio: heat = buys/(buys+sells)*100
- dexscreen SDK confirmed: subscribe_pairs() exists but needs pair_addresses

## dexscreen SDK Methods Available
- get_pairs_by_token_addresses_async (batch)
- subscribe_pairs (streaming, needs pair addresses)
- subscribe_tokens (streaming by token)
- FilterPresets.significant_price_changes()

## Creator Reputation (from FLOCK4H/Dexter)
- Track creator wallet → {launches, wins, rugs, avg_peak}
- Trust factor = wins / launches (>50% = good creator)
- Anti-spam: exclude creators launching <900s apart
- Rug detection: final_mcap < 20% of peak = rug
- Performance score = launches * median_peak * success_ratio
- Implemented: _track_creator(), _creator_score() in scanner.py

## Token Similarity (from bloodbee)
- difflib.SequenceMatcher ratio, threshold 0.6
- Prevents buying DOGE2, DOGE3, DOGEKING etc.
- Checks against open positions + recent 50 token names

## Trailing Micro-Profit System
- Activate trail at +0.5% (SCALP_TRAIL_ACTIVATE)
- Trail = 40% of peak gain (so +1.0% peak → exit at +0.6%)
- Floor at +0.3% (never trail below this)
- Hard cap at +2.0%
- Heat-accelerated exit: +0.3% gain + dying heat = take it
- Weak SL: -0.8% + heat<30 = early cut

## GMGN Smart Money (from 1f1n/Dragon)
- API: gmgn.ai/defi/quotation/v1/rank/sol/pump (soaring tokens)
- API: gmgn.ai/vas/api/v1/token_traders/sol/{ca} (top traders per token)
- Extracts: wallet address, realized_profit, buy/sell counts
- Top 50 profitable wallets added to WATCH_WALLETS automatically
- Refreshes every 30 minutes

## DEXScreener WebSocket (from sashaboulouds gist)
- URL: wss://io.dexscreener.com/dex/screener/pairs/h24/1?rankBy[key]=trendingScoreH6&rankBy[order]=desc
- Plain JSON (not protobuf): type="pairs", pairs=[{chainId, baseToken, priceUsd, txns, liquidity, priceChange}]
- Streams every ~10s with full data
- Replaces HTTP polling for faster SCALP detection
- Filters: Solana, chg>0.3%, liq>$5K, buys>sells*1.3
