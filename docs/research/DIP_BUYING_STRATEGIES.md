# Dip-Buying Strategies for Crypto Uptrends: Concrete Algorithms & Code

Date: 2026-04-01 | Research for scanner.py oscillation trading

---

## Context

Token is up +5% on 1h timeframe. It oscillates: +2%, -1%, +3%, -1.5%.
Goal: Buy each dip, sell each bounce. Data: 10-second price polling + 1-minute OHLC candles.

---

## 1. PULLBACK DETECTION IN UPTRENDS

### Algorithm (Python pseudocode)

```python
def detect_pullback_in_uptrend(candles_1m, lookback=20):
    """
    Uptrend confirmed by: price > EMA20 > EMA50
    Pullback detected by: price drops toward EMA20 from above
    """
    closes = [c['close'] for c in candles_1m]
    ema9  = calc_ema(closes, 9)
    ema20 = calc_ema(closes, 20)
    ema50 = calc_ema(closes, 50)

    # Uptrend confirmation
    is_uptrend = ema9[-1] > ema20[-1] > ema50[-1]

    # Pullback: price was above EMA9, now touches/crosses below EMA9
    # but still above EMA20 (healthy pullback, not reversal)
    price = closes[-1]
    prev_price = closes[-2]
    pullback = (prev_price > ema9[-2]) and (price <= ema9[-1]) and (price > ema20[-1])

    return is_uptrend and pullback
```

### Key Parameters for Crypto
- EMA periods: 9/20/50 (not 50/200 like stocks -- crypto moves faster)
- Pullback depth: price touching EMA9 or EMA20 = buy zone
- Invalidation: if price breaks below EMA50, uptrend is over
- Works on 1-minute candles: YES -- use 9/20/50 period EMAs on 1m

### PAC (Price Action Channel) Method
From the Scalping Pullback Tool (fmzquant/strategies):
- Build a channel from EMA(34) of highs, lows, and closes
- Price above channel = bullish (blue bars)
- Price pulls back INTO channel from above = buy signal
- Trend filter: PAC + EMA89 must be above EMA200

### Expected Win Rate
60-70% when combined with uptrend confirmation (EMA stack in order).

### GitHub Repos
- https://github.com/fmzquant/strategies (Scalping-PullBack-Tool-R1)
- https://github.com/ilahuerta-IA/mt5_live_trading_bot (4-phase pullback state machine)

---

## 2. RSI DIP-BUYING

### Algorithm

```python
def rsi_dip_buy(candles_1m, rsi_period=3, trend_ema_period=20):
    """
    For 1-minute scalping: use RSI(3) not RSI(14).
    RSI(14) is too slow for 1m candles.
    """
    closes = [c['close'] for c in candles_1m]
    rsi = calc_rsi(closes, period=rsi_period)
    ema20 = calc_ema(closes, trend_ema_period)

    # Uptrend filter: price above EMA20
    is_uptrend = closes[-1] > ema20[-1]

    # Dip signal: RSI drops below threshold then crosses back above
    # For crypto on 1m: use 20/80 thresholds (not 30/70)
    rsi_was_oversold = rsi[-2] < 20
    rsi_recovering = rsi[-1] > 20

    return is_uptrend and rsi_was_oversold and rsi_recovering


def rsi_staged_entry(candles_1m, capital):
    """
    From asier13/Python-Trading-Bot (70%+ win rate backtested):
    Stage entries at different RSI levels for better average price.
    """
    rsi = calc_rsi([c['close'] for c in candles_1m], period=14)
    current_rsi = rsi[-1]

    if current_rsi < 29:      # First buy: 40% of capital
        return 'BUY', capital * 0.40
    elif current_rsi < 27.5:  # Second buy: 50% of remaining
        return 'BUY', capital * 0.30
    elif current_rsi < 26:    # Third buy: remaining capital
        return 'BUY', capital * 0.30

    # Take profit tiers
    if current_rsi > 65:      # TP2: full exit
        return 'SELL_ALL', None
    elif current_rsi > 55:    # TP1: partial exit
        return 'SELL_HALF', None

    return 'HOLD', None
```

### Key Parameters for Crypto

| Timeframe | RSI Period | Oversold | Overbought | Best Combined With |
|-----------|-----------|----------|------------|-------------------|
| 1-minute  | 2-3       | 20       | 80         | EMA9 trend filter |
| 5-minute  | 7-9       | 25       | 75         | EMA20 trend filter|
| 15-minute | 14        | 30       | 70         | EMA50 trend filter|

**CRITICAL for 1-minute crypto**: Use RSI(2) or RSI(3), NOT RSI(14).
RSI(14) on 1m candles barely moves. RSI(2-3) reacts to every micro-dip.

### Stop Loss
-2% fixed (from asier13 backtests). Keeps drawdown low while allowing
the RSI dip to play out.

### Expected Win Rate
70%+ with staged entries (asier13 backtested). ~55-60% with simple
RSI cross-back-above-threshold.

### GitHub Repos
- https://github.com/asier13/Python-Trading-Bot (RSI scalping, 70%+ WR, backtested)
- https://github.com/TRetraint/RSI_Trading_Bot (RSI 30/70 on Binance)
- https://github.com/blankly-finance/rsi-crypto-trading-bot (25-line RSI bot)
- https://github.com/BashirMohamedAli/crypto-trading-bot (RSI + EMA combined)
- https://github.com/pythonjokeun/thewife (auto-optimized RSI via hyperopt)
- https://github.com/scotran/rsibot (RSI indicator bot)

---

## 3. BOLLINGER BAND BOUNCE IN UPTRENDS

### Algorithm

```python
def bb_bounce_buy(candles_1m, bb_period=20, bb_std=2.0, trend_ema=50):
    """
    Buy when price touches lower BB during uptrend.
    Sell at middle band or upper band.
    """
    closes = [c['close'] for c in candles_1m]
    highs  = [c['high'] for c in candles_1m]
    lows   = [c['low'] for c in candles_1m]

    # Bollinger Bands
    sma = calc_sma(closes, bb_period)
    std = calc_std(closes, bb_period)
    upper_bb = sma[-1] + (bb_std * std[-1])
    lower_bb = sma[-1] - (bb_std * std[-1])
    middle_bb = sma[-1]

    # Trend filter
    ema50 = calc_ema(closes, trend_ema)
    is_uptrend = closes[-1] > ema50[-1]

    price = closes[-1]
    prev_price = closes[-2]

    # Buy signal: price touches/crosses below lower BB, then bounces
    touched_lower = lows[-1] <= lower_bb or lows[-2] <= lower_bb
    bouncing = price > prev_price  # price recovering

    # Sell signal: price reaches middle or upper BB
    at_middle = price >= middle_bb
    at_upper = price >= upper_bb

    if is_uptrend and touched_lower and bouncing:
        return 'BUY'
    elif at_upper:
        return 'SELL_ALL'
    elif at_middle and holding:
        return 'SELL_HALF'  # partial at middle, rest at upper

    return 'HOLD'
```

### Key Parameters for Crypto on 1-Minute Candles
- BB Period: 20 (standard)
- BB StdDev: 2.0 (standard) -- some use 1.5 for tighter bands on 1m
- For more signals on 1m: use BB(20, 1.5) -- price touches bands more often
- Trend filter: EMA50 on 1m candles

### Combined with RSI (from OmarElNaja/CryptoBot)
- BUY when: close < lower_bb AND RSI > 7 (filters out extreme crashes)
- SELL when: close > upper_bb AND RSI > 74
- The RSI > 7 filter prevents buying during freefall crashes

### Implementation with ta-lib
```python
import talib
import numpy as np

upper, middle, lower = talib.BBANDS(
    np.array(closes),
    timeperiod=20,
    nbdevup=2.0,
    nbdevdn=2.0,
    matype=talib.MA_Type.EMA  # Use EMA-based BB for faster response
)
rsi = talib.RSI(np.array(closes), timeperiod=3)
```

### Expected Win Rate
65-75% in trending markets. Drops to 40-50% in sideways/choppy markets.
NoisyBoyAlgotrader reported 85% win rate and 1.6 Sharpe on daily candles.

### GitHub Repos
- https://github.com/yungalyx/NoisyBoyAlgotrader (85% WR, Sharpe 1.6)
- https://github.com/OmarElNaja/CryptoBot (BB + RSI combined)
- https://github.com/arambarnett/Bollinger-Band-Mean-Reversion (BTC)
- https://github.com/coasensi/bollingerbands-backtest (full backtest)
- https://github.com/lhandal/crypto-trading-bot (BB + RSI on Binance)

---

## 4. EMA PULLBACK STRATEGY

### Algorithm

```python
def ema_pullback_buy(candles_1m):
    """
    Crypto pullback strategy from FMZQuant:
    - EMA9 (fast), EMA14 (medium), EMA20 (slow/trend)
    - Stochastic RSI for timing
    """
    closes = [c['close'] for c in candles_1m]
    ema9  = calc_ema(closes, 9)
    ema14 = calc_ema(closes, 14)
    ema20 = calc_ema(closes, 20)

    price = closes[-1]

    # Uptrend: price above EMA20
    is_uptrend = price > ema20[-1]

    # Pullback: price has dipped below EMA9 and EMA14
    # but still above EMA20 (the trend EMA)
    in_pullback = (price < ema9[-1]) and (price < ema14[-1])

    # StochRSI confirmation (oversold = momentum exhaustion)
    stoch_rsi = calc_stoch_rsi(closes, rsi_len=14, stoch_len=14, k=3, d=3)
    stoch_oversold = stoch_rsi['k'][-1] < 25

    if is_uptrend and in_pullback and stoch_oversold:
        return 'BUY'
    return 'HOLD'


def simple_ema_bounce(candles_1m):
    """
    Simpler version: 9/21 EMA crossover with pullback to 9-EMA.
    From 1-minute scalping strategies.
    """
    closes = [c['close'] for c in candles_1m]
    ema9  = calc_ema(closes, 9)
    ema21 = calc_ema(closes, 21)

    price = closes[-1]
    prev_price = closes[-2]

    # Uptrend: EMA9 > EMA21
    is_uptrend = ema9[-1] > ema21[-1]

    # Pullback to EMA9: price touched or crossed below EMA9
    touched_ema9 = prev_price <= ema9[-2] or price <= ema9[-1]

    # Bounce: price now recovering above EMA9
    bouncing = price > ema9[-1] and price > prev_price

    if is_uptrend and touched_ema9 and bouncing:
        return 'BUY'
    return 'HOLD'
```

### Key Parameters for Crypto
- Fast EMA: 9 (crypto standard, more responsive than 12)
- Medium EMA: 14 or 21
- Trend EMA: 20 or 50
- StochRSI: 14/14/3/3 with 25/85 thresholds
- Works on 1-minute candles: YES

### Freqtrade Strategy001 (EMA-based, backtested)
- Uses EMA20/EMA50/EMA100 with Heikin-Ashi candles
- Buy: EMA20 crosses above EMA50 + HA close > EMA20 + green HA candle
- Sell: EMA50 crosses above EMA100 + HA close < EMA20 + red HA candle
- Stoploss: -10%, tiered TP: 5% immediate, 4% after 20 candles, 3%/30, 1%/60

### Expected Win Rate
55-65% for simple EMA bounce. 65-75% with StochRSI confirmation.

### GitHub Repos
- https://github.com/tahaabbas/binance-spot-trading-bot (EMA crossover)
- https://github.com/tahaabbas/binance-future-trading-bot (EMA futures)
- https://github.com/calum-mcg/gdax-tradingbot (5/20 EMA crossover)
- https://github.com/vishnugovind10/emacrossover (EMA + VWAP)
- https://github.com/freqtrade/freqtrade-strategies (Strategy001 EMA-based)

---

## 5. VOLUME-CONFIRMED DIPS

### Algorithm

```python
def volume_confirmed_dip(candles_1m, vol_lookback=20):
    """
    Low volume dip = healthy pullback (BUY IT)
    High volume dip = real selling (AVOID IT)

    Also uses OBV (On-Balance Volume) and MFI (Money Flow Index).
    """
    closes  = [c['close'] for c in candles_1m]
    volumes = [c['volume'] for c in candles_1m]
    highs   = [c['high'] for c in candles_1m]
    lows    = [c['low'] for c in candles_1m]

    # Average volume over lookback period
    avg_vol = sum(volumes[-vol_lookback:]) / vol_lookback
    current_vol = volumes[-1]

    # Price is dipping
    price_dipping = closes[-1] < closes[-2]

    # Volume analysis
    vol_ratio = current_vol / avg_vol
    low_volume_dip = vol_ratio < 0.7    # below 70% of average = low volume
    high_volume_dip = vol_ratio > 1.5   # above 150% of average = high volume

    # OBV: On-Balance Volume (trend of volume flow)
    obv = calc_obv(closes, volumes)
    obv_rising = obv[-1] > obv[-5]  # OBV still rising = buyers in control

    # MFI: Money Flow Index (volume-weighted RSI)
    mfi = calc_mfi(highs, lows, closes, volumes, period=14)
    mfi_oversold = mfi[-1] < 30  # oversold on volume-weighted basis

    if price_dipping and low_volume_dip and obv_rising:
        return 'BUY'       # Healthy pullback, buy it
    elif price_dipping and high_volume_dip:
        return 'AVOID'     # Real selling pressure, stay out
    elif mfi_oversold and obv_rising:
        return 'BUY'       # Volume-weighted oversold, buyers still there

    return 'HOLD'


def calc_obv(closes, volumes):
    """On-Balance Volume"""
    obv = [0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i-1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return obv


def calc_mfi(highs, lows, closes, volumes, period=14):
    """Money Flow Index (Volume-Weighted RSI)"""
    typical_price = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
    money_flow = [tp * v for tp, v in zip(typical_price, volumes)]

    mfi_values = []
    for i in range(period, len(money_flow)):
        pos_flow = sum(money_flow[j] for j in range(i - period, i)
                       if typical_price[j] > typical_price[j-1])
        neg_flow = sum(money_flow[j] for j in range(i - period, i)
                       if typical_price[j] < typical_price[j-1])
        if neg_flow == 0:
            mfi_values.append(100)
        else:
            ratio = pos_flow / neg_flow
            mfi_values.append(100 - (100 / (1 + ratio)))
    return mfi_values
```

### Key Parameters for Crypto
- Volume lookback: 20 candles (20 minutes on 1m)
- Low volume threshold: < 0.7x average (pullback is weak selling)
- High volume threshold: > 1.5x average (real dumping)
- OBV trend window: 5 candles (is overall flow still positive?)
- MFI period: 14 (same as RSI, but volume-weighted)

### CRITICAL for Solana/Pump.fun tokens
Pump.fun tokens have irregular volume. Use relative volume (current vs
recent average), NOT absolute volume thresholds.

### Expected Win Rate
The volume filter itself is a MODIFIER, not standalone. It improves other
strategies by ~10-15% win rate when used as a confirmation layer.

### GitHub Repos
- https://github.com/Jayj3nks/Crypto-Volume-Profiler (volume profiling)
- https://github.com/CryptoSignal/crypto-signal (MFI, OBV, VWAP alerts)
- https://github.com/hal9000cc/live_trading_indicators (MFI + OBV)
- https://github.com/Magnifique-d/stock-trading-strategy (OBV strategy)
- https://github.com/VolumeFi/trading-bots (volume-based bots)

---

## 6. FREQTRADE DIP-BUYING STRATEGIES

### NostalgiaForInfinity (NFIX) -- The Gold Standard
The most backtested and optimized dip-buying strategy in the freqtrade ecosystem.
5,000+ lines of Python, 3k+ GitHub stars.

Key features:
- Multiple buy_dip conditions with configurable thresholds
- Combines RSI, BB, EMA, volume, and more
- Runs on 5-minute candles with 1h informative timeframe
- 6-12 simultaneous open trades
- Tiered buy conditions: "semi swing", "local dip", "1h minor dip"

### Strategy001 (Simpler, Good Starting Point)
```python
# From freqtrade-strategies/Strategy001.py (actual code)
# Timeframe: 5m
# Buy conditions:
#   - EMA20 crosses above EMA50
#   - Heikin-Ashi close > EMA20
#   - Heikin-Ashi candle is green (open < close)
# Sell conditions:
#   - EMA50 crosses above EMA100
#   - HA close < EMA20
#   - HA candle is red
# Stoploss: -10%
# TP: 5% immediate, 4% after 20 candles, 3% after 30, 1% after 60
```

### BuyMeAnIcecream Strategies (Hyperopt Optimized)
- Market condition filtering
- Hyperopt optimization for each parameter
- Optimized for current market conditions

### How to Adapt Freqtrade Logic to Your Bot
Freqtrade strategies use `populate_entry_trend()` and `populate_exit_trend()`.
The core logic is just pandas operations on OHLCV dataframes -- you can
extract the indicator calculations and condition checks directly.

```python
# Example: extracting freqtrade logic for your bot
import pandas_ta as ta

def freqtrade_style_dip_check(df):
    """
    df = pandas DataFrame with columns: open, high, low, close, volume
    """
    # Indicators
    df['ema_20'] = ta.ema(df['close'], length=20)
    df['ema_50'] = ta.ema(df['close'], length=50)
    df['rsi'] = ta.rsi(df['close'], length=14)
    bb = ta.bbands(df['close'], length=20, std=2.0)
    df['bb_lower'] = bb['BBL_20_2.0']
    df['bb_middle'] = bb['BBM_20_2.0']

    # Buy condition (dip in uptrend)
    last = df.iloc[-1]
    buy = (
        (last['close'] > last['ema_50']) and       # uptrend
        (last['close'] < last['ema_20']) and       # pulled back below EMA20
        (last['rsi'] < 35) and                     # RSI oversold-ish
        (last['close'] <= last['bb_lower'] * 1.01) # near lower BB
    )
    return buy
```

### GitHub Repos
- https://github.com/iterativv/NostalgiaForInfinity (the gold standard, 3k stars)
- https://github.com/freqtrade/freqtrade-strategies (official strategies collection)
- https://github.com/BuyMeAnIcecream/freqtrade-strategies (hyperopt optimized)
- https://github.com/davidzr/freqtrade-strategies (community collection)
- https://github.com/nateemma/strategies (ML-based: Kalman, PCA, DWT)

---

## 7. FIBONACCI RETRACEMENT

### Algorithm

```python
def fibonacci_dip_buy(price_history, current_price):
    """
    Find swing high and swing low in recent history.
    Calculate fib levels. Buy at 38.2% or 50% retracement.

    Example: price goes $0.10 -> $0.15 (+50%)
    38.2% fib = $0.15 - (0.382 * ($0.15 - $0.10)) = $0.1309
    50.0% fib = $0.15 - (0.500 * ($0.15 - $0.10)) = $0.125
    61.8% fib = $0.15 - (0.618 * ($0.15 - $0.10)) = $0.119
    """
    # Find recent swing high and swing low
    swing_high = max(price_history[-60:])   # last 60 candles
    swing_low = min(price_history[-120:-60]) # prior 60 candles (the low before the run)

    if swing_high <= swing_low:
        return 'HOLD', {}  # no upswing detected

    diff = swing_high - swing_low

    # Fibonacci levels
    fib_levels = {
        '23.6%': swing_high - (0.236 * diff),
        '38.2%': swing_high - (0.382 * diff),
        '50.0%': swing_high - (0.500 * diff),
        '61.8%': swing_high - (0.618 * diff),
        '78.6%': swing_high - (0.786 * diff),
    }

    # Buy zones
    # For crypto: 38.2% and 50% are the most common bounce levels
    # 61.8% is the "last chance" level before trend reversal
    fib_38 = fib_levels['38.2%']
    fib_50 = fib_levels['50.0%']
    fib_61 = fib_levels['61.8%']

    tolerance = 0.005  # 0.5% tolerance around fib level

    if abs(current_price - fib_38) / fib_38 < tolerance:
        return 'BUY', {'level': '38.2%', 'price': fib_38, 'confidence': 'HIGH'}
    elif abs(current_price - fib_50) / fib_50 < tolerance:
        return 'BUY', {'level': '50.0%', 'price': fib_50, 'confidence': 'MEDIUM'}
    elif abs(current_price - fib_61) / fib_61 < tolerance:
        return 'BUY', {'level': '61.8%', 'price': fib_61, 'confidence': 'LOW'}

    # Invalidation: below 78.6% fib = trend is broken
    if current_price < fib_levels['78.6%']:
        return 'TREND_BROKEN', fib_levels

    return 'HOLD', fib_levels


def find_swing_points(closes, window=5):
    """
    ZigZag-style swing detection.
    A swing high = highest point with lower points on both sides.
    """
    swing_highs = []
    swing_lows = []

    for i in range(window, len(closes) - window):
        # Swing high: higher than all neighbors
        if all(closes[i] >= closes[i-j] for j in range(1, window+1)) and \
           all(closes[i] >= closes[i+j] for j in range(1, window+1)):
            swing_highs.append((i, closes[i]))

        # Swing low: lower than all neighbors
        if all(closes[i] <= closes[i-j] for j in range(1, window+1)) and \
           all(closes[i] <= closes[i+j] for j in range(1, window+1)):
            swing_lows.append((i, closes[i]))

    return swing_highs, swing_lows
```

### Key Parameters for Crypto
- For 1-minute candles: use window=5 for swing detection (5 candles = 5 minutes)
- Primary buy levels: 38.2% and 50% (crypto usually bounces here)
- AlgoXTrader uses 78.6% fib as the primary signal (more aggressive)
- Tolerance: 0.5% around the fib level (crypto won't land exactly on it)
- Invalidation: price below 78.6% fib = the trend is broken, do not buy

### Adapting for Small Oscillations
For your use case (2-3% swings), the fib levels will be very close together.
Example: price $0.100 to $0.103 (+3%):
- 38.2% fib = $0.10185 (1.15% above swing low)
- 50.0% fib = $0.10150 (0.85% above swing low)
This gives very tight buy zones -- combine with RSI or BB for confirmation.

### Expected Win Rate
55-65% standalone. Fibs work better on larger swings (10%+). For micro
oscillations (2-3%), other methods (RSI, BB) are more reliable.

### GitHub Repos
- https://github.com/AlgoXTrader/Fibonacci-Trade-Finder (Binance scanner, 78.6% fib)
- https://github.com/beydah/ByBit-Scanner-Bot (ZigZag + fib + multi-timeframe)
- https://github.com/joengelh/binance-fibonaccibot (fib levels for crypto pairs)
- https://github.com/brandonlatherow/Fibonacci-Retracement-with-Python (analysis tool)

---

## COMBINED STRATEGY: THE MEGA DIP-BUYER

The highest-conviction dip-buy signal combines multiple confirmations:

```python
def mega_dip_buyer(candles_1m, price_history_10s):
    """
    Combined strategy: score-based dip buying in uptrends.
    Each confirmation adds points. Buy when score >= 3.
    """
    closes = [c['close'] for c in candles_1m]
    volumes = [c['volume'] for c in candles_1m]
    score = 0
    signals = []

    # --- UPTREND CONFIRMATION (REQUIRED) ---
    ema9 = calc_ema(closes, 9)
    ema20 = calc_ema(closes, 20)
    ema50 = calc_ema(closes, 50)

    is_uptrend = ema9[-1] > ema20[-1] > ema50[-1]
    if not is_uptrend:
        return 'NO_TRADE', 0, ['Uptrend not confirmed']

    # --- SIGNAL 1: RSI Oversold (+2 points) ---
    rsi = calc_rsi(closes, period=3)  # RSI(3) for 1m candles
    if rsi[-1] < 20:
        score += 2
        signals.append(f'RSI({rsi[-1]:.0f}) oversold')
    elif rsi[-1] < 30:
        score += 1
        signals.append(f'RSI({rsi[-1]:.0f}) near oversold')

    # --- SIGNAL 2: Price at Lower Bollinger Band (+1 point) ---
    bb_lower = calc_bb_lower(closes, period=20, std=2.0)
    if closes[-1] <= bb_lower[-1] * 1.01:  # within 1% of lower BB
        score += 1
        signals.append('At lower Bollinger Band')

    # --- SIGNAL 3: Price pulled back to EMA support (+1 point) ---
    if closes[-1] <= ema9[-1] * 1.005 and closes[-1] > ema20[-1]:
        score += 1
        signals.append('Pullback to EMA9 support')

    # --- SIGNAL 4: Low volume dip (+1 point) ---
    avg_vol = sum(volumes[-20:]) / 20
    if volumes[-1] < avg_vol * 0.7:
        score += 1
        signals.append('Low volume pullback (healthy)')
    elif volumes[-1] > avg_vol * 1.5:
        score -= 1  # PENALTY: high volume selling
        signals.append('WARNING: High volume selling')

    # --- SIGNAL 5: Price bouncing (10s data) (+1 point) ---
    if len(price_history_10s) >= 6:
        recent = price_history_10s[-6:]  # last 60 seconds
        min_price = min(recent)
        current = recent[-1]
        if current > min_price and current > recent[-2]:
            score += 1
            signals.append('Price bouncing on 10s data')

    # --- DECISION ---
    if score >= 3:
        return 'BUY', score, signals
    elif score >= 2:
        return 'WATCH', score, signals
    else:
        return 'HOLD', score, signals


def mega_dip_seller(candles_1m, entry_price, peak_price):
    """
    Exit logic: sell the bounce.
    """
    closes = [c['close'] for c in candles_1m]
    rsi = calc_rsi(closes, period=3)
    current = closes[-1]
    gain_pct = ((current - entry_price) / entry_price) * 100

    # Take profit conditions
    if rsi[-1] > 80:                    # RSI overbought
        return 'SELL', 'RSI overbought'
    if gain_pct >= 2.0:                 # +2% gain
        return 'SELL', f'+{gain_pct:.1f}% target hit'

    # Trailing stop: if price drops 0.5% from peak
    if peak_price > 0:
        drop_from_peak = ((peak_price - current) / peak_price) * 100
        if drop_from_peak >= 0.5 and gain_pct > 0.3:
            return 'SELL', f'Trailing stop: -{drop_from_peak:.1f}% from peak'

    # Hard stop loss
    if gain_pct <= -1.5:
        return 'SELL', f'Stop loss: {gain_pct:.1f}%'

    return 'HOLD', None
```

### Recommended Parameters Summary

| Parameter | Value | Why |
|-----------|-------|-----|
| RSI period | 3 | Fast enough for 1m candles |
| RSI oversold | 20 | Crypto-adjusted (not 30) |
| RSI overbought | 80 | Crypto-adjusted (not 70) |
| BB period | 20 | Standard |
| BB std | 2.0 | Standard (or 1.5 for more signals) |
| EMA fast | 9 | Crypto standard |
| EMA medium | 20 | Trend filter |
| EMA slow | 50 | Major trend |
| Volume low threshold | 0.7x avg | Below = healthy pullback |
| Volume high threshold | 1.5x avg | Above = real selling |
| Min score to buy | 3 | Out of ~7 possible points |
| Take profit | +2% | Realistic for micro-oscillations |
| Trailing stop | 0.5% from peak | Locks in gains |
| Stop loss | -1.5% | Limits downside |

### Python Libraries Needed
```
pip install ta-lib      # or: pip install pandas-ta (no C dependency)
pip install pandas
pip install numpy
```

### Helper Functions (using pandas-ta, no C dependency)
```python
import pandas as pd
import pandas_ta as ta

def calc_all_indicators(candles_1m):
    """Calculate all indicators from 1-minute OHLCV candles."""
    df = pd.DataFrame(candles_1m)

    # RSI (period 3 for 1m scalping)
    df['rsi_3'] = ta.rsi(df['close'], length=3)

    # EMAs
    df['ema_9'] = ta.ema(df['close'], length=9)
    df['ema_20'] = ta.ema(df['close'], length=20)
    df['ema_50'] = ta.ema(df['close'], length=50)

    # Bollinger Bands
    bb = ta.bbands(df['close'], length=20, std=2.0)
    df['bb_upper'] = bb['BBU_20_2.0']
    df['bb_middle'] = bb['BBM_20_2.0']
    df['bb_lower'] = bb['BBL_20_2.0']

    # Volume indicators
    df['obv'] = ta.obv(df['close'], df['volume'])
    df['mfi'] = ta.mfi(df['high'], df['low'], df['close'], df['volume'], length=14)

    # Stochastic RSI
    stoch_rsi = ta.stochrsi(df['close'], length=14, rsi_length=14, k=3, d=3)
    df['stoch_rsi_k'] = stoch_rsi['STOCHRSIk_14_14_3_3']
    df['stoch_rsi_d'] = stoch_rsi['STOCHRSId_14_14_3_3']

    return df
```

---

## PRACTICAL NOTES FOR YOUR SETUP

### 10-Second Polling vs 1-Minute Candles
- Use 1-minute candles for: RSI, EMA, BB, Fibonacci (need OHLC structure)
- Use 10-second polling for: bounce confirmation, trailing stops, entry timing
- Build your own 1m candles from 10s data if the exchange doesn't provide them

### For Pump.fun / Solana Memecoins
- These tokens are MORE volatile than BTC/ETH -- use tighter parameters
- RSI(2) instead of RSI(3), BB(20, 1.5) instead of BB(20, 2.0)
- Shorter EMA periods: 5/9/20 instead of 9/20/50
- Tighter stops: -1% instead of -2%
- Faster exits: +1.5% TP instead of +2%
- Volume data may be unreliable on new tokens -- weight it less

### Minimum Data Requirements
- RSI(3): needs 4+ candles
- EMA(50): needs 50+ candles (so ~50 minutes of 1m data)
- BB(20): needs 20+ candles
- Before you have enough data, use simpler logic (just price action + 10s polling)
