# GitHub Research V4 - Position Management & Pyramiding

## YZYLAB/solana-trade-bot
- Simple Map-based position tracking with JSON persistence
- All-or-nothing exits (no partial exits)
- Two concurrent loops via Promise.allSettled (buy monitor + position monitor)
- Fire-and-forget buys for parallel execution
- Binary stop-loss/take-profit thresholds only
- No pyramiding, no scaling-in

## outsmartchad/solana-trading-cli
- Rich PositionState tracking for LP positions (range, fees, bins)
- 12-provider TX landing orchestrator with concurrent/race/sequential strategies
- Durable nonce accounts for exactly-once execution across concurrent providers
- Jito: legacy HTTP (5 endpoints parallel) + modern gRPC (jito-ts Bundle + tip)
- Risk management: IL threshold with 80% warning, stop-loss, cooldown-gated rebalancing
- Fee compounding: claims accumulated fees and re-deposits as additional liquidity
- No pyramiding for spot trades

## Key Takeaways for Our Bot
1. Neither repo implements pyramiding — we design from scratch
2. Guard sets for dedup (prevent double-buying) — we already have this via `STATE.sim_positions`
3. Parallel position monitoring via gather/allSettled — we already do this with asyncio.gather
4. The concurrent TX landing with durable nonce is interesting but we're simulation only
5. LP rebalancing pattern (remove 100%, re-deposit centered on current price) could inspire
   dynamic position re-centering for GRAD_SNIPE

## Pyramiding Design for GRAD_SNIPE
- Only GRAD_SNIPE positions (30min hold = enough time)
- NOT HFT positions (90s too short)
- Pyramid levels: +5%, +10%, +20% from entry
- Each add: 50% of original position size
- Max 3 pyramids per position (original + 3 adds = 2.5x original size)
- Average entry price recalculated on each add
- Stop loss moves up with each pyramid (locks in some profit)
