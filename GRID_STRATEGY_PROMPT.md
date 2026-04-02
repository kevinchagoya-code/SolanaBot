# ADD GRID TRADING + MEAN REVERSION TO EXISTING BOT

## READ ERROR_LOG.md FIRST
Before making ANY changes, read C:\Users\kevin\SolanaBot\ERROR_LOG.md completely.
It contains 21 bugs and 15 rules from today. Every rule must be followed.

## WHAT WE'RE ADDING (maps to existing architecture)

### 1. GRID STRATEGY — replaces broken MOMENTUM strategy
The current MOMENTUM strategy loses money because established tokens 
move 0.01%/min — too slow for momentum. But they oscillate perfectly 
for GRID TRADING. Same tokens (PYTH, W, ORCA, JUP, etc.), different approach.

Instead of: "buy PYTH, wait for it to go up, sell"
Do this: "set buy orders at -1%, -2%, -3% below current price. 
Set sell orders at +1%, +2%, +3% above current price. When price 
oscillates, buy low levels fill, then sell high levels fill. Repeat."

Implementation using existing 10-second polling:

```python
# NEW: Grid Trading Engine (replaces MOMENTUM)

# Grid config per token
GRID_TOKENS = {
    # token_mint: {symbol, grid_pct, num_levels, position_sol}
    # grid_pct = spacing between levels (must be > 0.55% breakeven)
    # Research says 1.0-2.0% optimal for crypto with 0.25% fees
}

# Use the existing 27 MOMENTUM tokens but trade them differently:
# SOL-denominated tokens tracked via Jupiter batch pricing (already built)

class GridState:
    """Track grid levels for a single token."""
    def __init__(self, symbol, mint, center_price, grid_pct=1.5, levels=5, sol_per_level=0.5):
        self.symbol = symbol
        self.mint = mint
        self.center_price = center_price  # recalculate periodically
        self.grid_pct = grid_pct  # spacing between levels
        self.levels = levels  # buy levels below, sell levels above
        self.sol_per_level = sol_per_level
        # Track which levels are filled
        self.buy_levels = {}   # {level_price: True/False}
        self.sell_levels = {}  # {level_price: True/False}
        self.positions = []    # active positions from filled buys
        self.total_profit = 0.0
        self.completed_cycles = 0
        
    def calculate_levels(self):
        """Set buy/sell price levels using GEOMETRIC spacing."""
        ratio = 1 + (self.grid_pct / 100)
        self.buy_levels = {}
        self.sell_levels = {}
        for i in range(1, self.levels + 1):
            buy_price = self.center_price / (ratio ** i)
            sell_price = self.center_price * (ratio ** i)
            self.buy_levels[round(buy_price, 12)] = False  # not filled
            self.sell_levels[round(sell_price, 12)] = False
```


```python
    def check_price(self, current_price):
        """Called every 10s with latest price. Returns list of actions."""
        actions = []
        
        # Check if any buy levels triggered (price dropped to level)
        for level_price, filled in self.buy_levels.items():
            if not filled and current_price <= level_price:
                actions.append(("BUY", level_price, self.sol_per_level))
                self.buy_levels[level_price] = True
                self.positions.append({
                    "entry_price": level_price,
                    "sol": self.sol_per_level,
                    "time": time.monotonic()
                })
        
        # Check if any positions can be sold (price rose to sell level)
        for pos in list(self.positions):
            # Find the matching sell level (entry + grid_pct)
            target_sell = pos["entry_price"] * (1 + self.grid_pct / 100)
            if current_price >= target_sell:
                profit = self.sol_per_level * (self.grid_pct / 100 - 0.0055)
                actions.append(("SELL", current_price, profit))
                self.total_profit += profit
                self.completed_cycles += 1
                self.positions.remove(pos)
                # Reset the buy level so it can trigger again
                closest_buy = min(self.buy_levels.keys(), 
                    key=lambda x: abs(x - pos["entry_price"]))
                self.buy_levels[closest_buy] = False
        
        return actions
```

### How this fits the existing architecture:
- Uses `jupiter_get_prices_batch()` (already built) for 10s price polling
- Uses `calc_sim_pnl()` (already built) for P&L with correct fee model
- Uses `dashboard_data.json` (already built) to show grid state on web dashboard
- Uses `snipe_log.csv` (already built) to log grid trades
- Runs ALONGSIDE HFT/SCALP/GRAD — just another strategy in the loop

### Grid parameters (research-backed):
```python
# Minimum spacing = 1.0% (breakeven at 0.55%, so 1.0% gives 0.45% profit per cycle)
# Optimal spacing = 1.5% (gives 0.95% per cycle, accounts for slippage)
# Levels = 5 above + 5 below = 10 total levels
# Position per level = 0.5 SOL in sim (~$40)
# Total capital per grid token = 5 SOL (10 levels x 0.5 SOL)
# Run 5-8 tokens = 25-40 SOL allocated to grid

GRID_SPACING_PCT = 1.5  # 1.5% between levels
GRID_LEVELS = 5          # 5 buy + 5 sell = 10 levels per token
GRID_SOL_PER_LEVEL = 0.5 # 0.5 SOL per grid level in sim
GRID_RECENTER_PCT = 5.0  # recenter grid if price moves 5% from center
GRID_MAX_TOKENS = 8      # max tokens with active grids
```


### Best tokens for grid (from research — range-bound, liquid):
```python
GRID_TOKENS_LIST = [
    # Infrastructure tokens — oscillate in ranges, deep liquidity
    "PYTH", "ORCA", "HNT", "W", "JUP", "RAY",
    # Mid-cap with range behavior  
    "TNSR", "NOS", "MNDE", "MOBILE",
]
# EXCLUDE: BONK, WIF, PENGU (trend too hard during hype)
# EXCLUDE: wBTC, wETH, SOL (Bug 0e — price-in-SOL issues)
# EXCLUDE: USDC, USDT (stablecoins don't oscillate enough)
```

### Regime detection (pause grids during trends):
```python
def is_range_bound(candles_1h: list) -> bool:
    """Check if token is range-bound (good for grid) vs trending."""
    if len(candles_1h) < 20: return True  # assume range if not enough data
    
    # Simple ADX-like check: if price stayed within X% band for 20 candles
    prices = [c["close"] for c in candles_1h[-20:]]
    high = max(prices)
    low = min(prices)
    band_pct = (high - low) / low * 100
    
    # If 20-hour range is under 8%, token is range-bound (good for grid)
    # If range is 8%+, it's trending (pause grid, let momentum handle it)
    return band_pct < 8.0
```

---

## 2. MEAN REVERSION — upgrade existing SCALP_WATCH

Current SCALP finds trending tokens on DEXScreener and buys momentum.
Research shows this loses money for retail bots. Instead, use SCALP 
to buy OVERSOLD tokens and sell at the mean.

### Replace SCALP entry logic with mean reversion signals:
```python
def check_mean_reversion_entry(candles_15m: list) -> dict:
    """Check if token is oversold and ready to bounce.
    Uses RSI + Bollinger Bands — research shows 60-80% win rate."""
    if len(candles_15m) < 20: return {"action": "SKIP"}
    
    closes = [c["close"] for c in candles_15m[-20:]]
    
    # RSI(14) calculation
    gains, losses = [], []
    for i in range(1, min(15, len(closes))):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))
    avg_gain = sum(gains) / len(gains) if gains else 0
    avg_loss = sum(losses) / len(losses) if losses else 0.001
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    # Bollinger Bands(20, 2)
    sma = sum(closes) / len(closes)
    std = (sum((c - sma)**2 for c in closes) / len(closes)) ** 0.5
    lower_band = sma - 2 * std
    upper_band = sma + 2 * std
    current_price = closes[-1]
    
    # ENTRY: RSI < 30 AND price below lower Bollinger Band
    if rsi < 30 and current_price < lower_band:
        # Verify expected bounce > breakeven (0.55%)
        expected_move = (sma - current_price) / current_price * 100
        if expected_move > 1.5:  # need 1.5%+ expected move
            return {
                "action": "BUY",
                "reason": f"MEAN_REV(RSI={rsi:.0f} below_BB price_to_sma={expected_move:.1f}%)",
                "target": sma,  # exit at SMA (middle band)
                "stop": current_price * 0.985  # 1.5% stop
            }
    
    return {"action": "SKIP", "rsi": rsi}
```

### Where this fits:
- Uses the same DEXScreener/Jupiter price data the SCALP scanner already fetches
- The 1-minute candle engine (already built for MOMENTUM) provides the candle data
- Entry decisions replace the "buy what's trending" logic
- Exit at SMA instead of fixed TP%
- Same position sizing, same logging, same dashboard


---

## 3. TAX-LOSS HARVESTING — always-on overlay (future, not now)

This runs on top of everything else. When any position is underwater,
the bot can sell and immediately rebuy to realize the tax loss while 
keeping the same position. No wash sale rule in crypto means unlimited
harvesting. BUT — this only matters for LIVE trading. Skip for sim mode.
Add as a future feature when EXECUTE_TRADES=true.

---

## HOW THE STRATEGIES MAP TO EXISTING CODE

| Research Strategy | Maps To | What Changes |
|---|---|---|
| Grid Trading | MOMENTUM strategy | Replace momentum entry/exit with grid levels |
| Mean Reversion | SCALP_WATCH strategy | Replace "buy trending" with "buy oversold" |
| Momentum/HFT | HFT strategy (keep) | No change — catches pump.fun runners |
| GRAD_SNIPE | GRAD_SNIPE (keep) | No change — catches graduations |
| Tax-Loss Harvest | New overlay | Future — only for live trading |

## CAPITAL ALLOCATION (100 SOL sim balance)

| Strategy | SOL Allocated | How |
|---|---|---|
| GRID (8 tokens) | 40 SOL | 8 tokens × 5 levels × 1.0 SOL/level |
| SCALP (mean rev) | 10 SOL | 0.5 SOL per position, max 20 positions |
| HFT | 5 SOL | 0.5 SOL per trade, max 10 open |
| GRAD_SNIPE | 5 SOL | 0.5 SOL per graduation, max 10 |
| Cash reserve | 40 SOL | Never touch — covers drawdowns |

## IMPLEMENTATION ORDER

1. **First**: Add GridState class and grid check loop alongside the 
   existing momentum price polling (reuse jupiter_get_prices_batch)
2. **Second**: Replace SCALP entry logic with mean reversion RSI+BB check
3. **Third**: Add regime detection to pause grids during strong trends
4. **DO NOT**: Change HFT, GRAD_SNIPE, dashboard, watchdog, or anything 
   in the ERROR_LOG rules

## POSITION SIZES (SIM MODE — follow ERROR_LOG Rule 5)

ALL positions must be small in sim mode:
- Grid: 0.5 SOL per level (NOT 2.0)
- SCALP/Mean Rev: 0.5 SOL per position (NOT 1.0)
- HFT: 0.5 SOL per trade
- GRAD: 0.5 SOL per graduation

Verify breakeven BEFORE setting any TP (ERROR_LOG Rule 1):
- Round-trip cost: 0.55% for liquid tokens, ~2% for pump.fun BC
- Grid TP: grid_spacing - 0.55% = profit per cycle
- Mean Rev TP: distance to SMA minus 0.55%
- Any TP below 0.55% = guaranteed loss = BUG

## DASHBOARD UPDATES

Show grid state on web dashboard:
- Grid Profits section: total completed cycles, total grid profit
- Per-token grid status: current price vs grid center, active levels
- Mean reversion signals: which tokens are oversold (RSI < 30)

## GIT COMMIT
git add -A && git commit -m "Add grid trading + mean reversion strategies — research-backed, builds on existing architecture"
