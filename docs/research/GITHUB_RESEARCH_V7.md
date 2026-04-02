# GitHub Research V7 - Heat Score & Live Momentum Analysis

## memecoin.watch (krecicki)
- Heat = 1min_volume / 5min_volume * 100 (threshold: <33 cold, 33-48 building, 48+ hot)
- Buy/Sell ratio: buy_volume / total_volume (target: >70%)
- Pump Detector requires: 1min vol > 20% of 5min vol AND buy/sell ratio > 1.2x
- Three scanners: Big Swap (>3 SOL clusters), Pump (volume patterns), Early Warning (GenAI)

## kasbecker gist (PRD only, no code)
- Pseudocode for MomentumStrategy, DataValidationEngine, MCPOrchestrator
- Five agents: Scout, Analyst, Social, Risk, Market
- All stubs/pass — design document only

## pumpfun-monitor-client (muhammetakkurtt)
- SSE streaming from Apify actor (requires paid API key)
- Endpoints: tokens/new, tokens/graduated, trades/pump, trades/pumpswap
- Trade data: {solAmount, marketCap, isBuy, updatedData: {ticker, name, volume}}

## Our Implementation: Heat Score System
- Calculated from: buy_ratio(40%) + volume_acceleration(30%) + price_momentum(20%) + consecutive_buys(10%)
- Patterns: ROCKET(80+), HEATING(60-80), WARM(40-60), COLD(<40), DUMP(buy_ratio<30%)
- HEAT_DUMP exit: immediate close when pattern is DUMP
- Dashboard shows heat score and pattern per position
