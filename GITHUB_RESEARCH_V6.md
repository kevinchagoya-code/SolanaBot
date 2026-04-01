# GitHub Research V6 - Adaptive Filters

## Solana-Advanced-Market-Making-Bot
- Volatility: std dev of percentage returns over sliding window
- Trend: linear regression slope normalized by avg price
- Adaptive: widens spreads by up to 50% at high volatility percentile

## ai-memecoin-trading-bot  
- Win probability: starts at 0.50, additive bonuses/penalties (honeypot, liquidity, velocity)
- Circuit breaker: daily loss limit triggers TradingHalted boolean
- Position sizing: Kelly-inspired, scaled by confidence (high=1.0, med=0.7, low=0.4)
- Stop loss adapts: high confidence=20%, medium=15%, low=10%
- Hold time adapts: high=60min, medium=30min, low=15min

## Our Implementation: Market State Engine
- HOT/WARM/SLOW/DEAD based on: BC velocity, token launch rate, avg score
- Adaptive thresholds auto-adjust MIN_SCORE, MOM, BC_PROGRESS, position size
- Rolling 20-trade win rate adjusts score threshold
