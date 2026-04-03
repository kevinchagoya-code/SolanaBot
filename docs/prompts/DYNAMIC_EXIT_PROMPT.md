# DYNAMIC ATR-BASED EXITS — Replace flat % floors with per-token volatility

## READ ERROR_LOG.md FIRST — all rules apply

## THE PROBLEM
FLOOR_SL at -0.5% kills proven winners (Community, MOON, LOL) because
meme coins naturally move ±1-2% in the first 30 seconds. Meanwhile,
NUCLEAR_TP at +5% (or +3%) misses tokens that only move +2% per cycle.

A flat % doesn't work because every token has different volatility:
- PYTH moves 0.1%/tick → -0.5% SL is fine, +1% TP is fine  
- Community moves 2%/tick → -0.5% SL is noise, needs -4% SL
- ZEN moves 1%/tick → needs something in between

Production bots use ATR (Average True Range) multiples:
- SL = entry_price - (ATR × multiplier)
- TP = entry_price + (ATR × multiplier)

We ALREADY HAVE calc_position_atr() (line ~1173) and 
calc_adaptive_trail() (line ~1189). They're used for moonbags only.
We need to use them EVERYWHERE.

## THE FIX — Replace FLOOR_SL with ATR-based dynamic SL

### CHANGE 1: Replace the FLOOR_SL block (line ~5920)

FIND this code:
    if p.pct_change <= -0.5:
        exit_reason = f"FLOOR_SL({p.pct_change:+.1f}%)"

REPLACE with:
    # DYNAMIC SL — adapts to each token's volatility
    atr = calc_position_atr(p)
    # SL = 2x ATR (give the token room to breathe)
    # Minimum -1.5%, maximum -10% (hard safety net)
    dynamic_sl = -max(1.5, min(atr * 2.0, 10.0))
    if p.pct_change <= dynamic_sl:
        exit_reason = f"ATR_SL({p.pct_change:+.1f}% floor:{dynamic_sl:+.1f}% atr:{atr:.1f})"

### CHANGE 2: Replace NUCLEAR_TP with ATR-based dynamic TP

FIND this code (line ~6000):
    if p.pct_change >= 5.0 and not p.is_moonbag:
        exit_reason = f"NUCLEAR_TP(+{p.pct_change:.1f}% pk:{p.peak_pct:.1f}%)"

REPLACE with:
    # DYNAMIC TP — adapts to each token's volatility
    atr = calc_position_atr(p)
    # TP = 3x ATR (let winners run proportional to their volatility)
    # Minimum +2.0%, maximum +25% (already have CEILING_TP at 25%)
    dynamic_tp = max(2.0, min(atr * 3.0, 25.0))
    if p.pct_change >= dynamic_tp and not p.is_moonbag:
        exit_reason = f"ATR_TP(+{p.pct_change:.1f}% target:{dynamic_tp:+.1f}% atr:{atr:.1f})"

### CHANGE 3: Add ATR-based partial exit at 1.5x ATR

After the ATR_TP block, add:
    # PARTIAL EXIT at 1.5x ATR — lock in half the profit early
    dynamic_partial = max(1.5, min(atr * 1.5, 12.0))
    if (not exit_reason and p.pct_change >= dynamic_partial 
        and not p.is_moonbag and p.strategy == "SCALP"
        and not p.partial_exit_2x and p.remaining_sol > 0.1):
        sell_amount = p.remaining_sol * 0.50
        profit = sell_amount * (p.pct_change / 100)
        STATE.balance_sol += sell_amount + profit
        p.remaining_sol -= sell_amount
        p.partial_exit_2x = True
        _dbg(f"ATR_PARTIAL: {p.symbol} sold 50% at +{p.pct_change:.1f}% "
             f"(target:{dynamic_partial:.1f}% atr:{atr:.1f})")
        _log_partial_exit(p, f"ATR_PARTIAL(+{p.pct_change:.1f}%)", 
                          sell_amount, profit)


## HOW THE MATH WORKS — Examples

Token: Community (meme coin, ATR = 2.5%/tick)
  SL = -max(1.5, min(2.5 * 2.0, 10.0)) = -5.0%
  Partial = max(1.5, min(2.5 * 1.5, 12.0)) = +3.75% → sell 50%
  TP = max(2.0, min(2.5 * 3.0, 25.0)) = +7.5% → sell remaining
  Result: Community has room to breathe, sells half at +3.75%

Token: PYTH (established, ATR = 0.3%/tick)
  SL = -max(1.5, min(0.3 * 2.0, 10.0)) = -1.5% (minimum)
  Partial = max(1.5, min(0.3 * 1.5, 12.0)) = +1.5% (minimum)
  TP = max(2.0, min(0.3 * 3.0, 25.0)) = +2.0% (minimum)
  Result: PYTH exits tight — appropriate for slow-moving token

Token: ZEN (moderate meme, ATR = 1.2%/tick)
  SL = -max(1.5, min(1.2 * 2.0, 10.0)) = -2.4%
  Partial = max(1.5, min(1.2 * 1.5, 12.0)) = +1.8%
  TP = max(2.0, min(1.2 * 3.0, 25.0)) = +3.6%
  Result: ZEN gets mid-range treatment — matches its actual pattern

Token: New pump.fun (brand new, ATR defaults to 5.0%)
  SL = -max(1.5, min(5.0 * 2.0, 10.0)) = -10.0% (maximum)
  Partial = max(1.5, min(5.0 * 1.5, 12.0)) = +7.5%
  TP = max(2.0, min(5.0 * 3.0, 25.0)) = +15.0%
  Result: New tokens get maximum room — they either moon or die

## WHAT THE ATR MULTIPLIERS MEAN
- SL at 2x ATR: "If price drops 2 normal-sized moves, it's actually dumping"
- Partial at 1.5x ATR: "If price rises 1.5 normal moves, lock in half"
- TP at 3x ATR: "If price rises 3 normal moves, take full profit"
- This gives a 1.5:1 reward-to-risk ratio (3x TP vs 2x SL)

## KEEP THE HARD FLOORS AS SAFETY NETS
The min/max clamps act as safety nets:
- SL never tighter than -1.5% (avoids noise kills)
- SL never wider than -10% (avoids disaster)
- TP never lower than +2.0% (always profitable)
- TP never higher than +25% (already have CEILING_TP)

## ALSO ADD: Debug logging for ATR values
At the start of the exit logic section, add:
    if hold_sec > 5 and hold_sec % 30 < 4:  # log every ~30 seconds
        atr = calc_position_atr(p)
        _dbg(f"ATR_CHECK: {p.symbol} [{p.strategy}] pct={p.pct_change:+.1f}% "
             f"atr={atr:.1f} sl={-max(1.5,min(atr*2,10)):.1f}% "
             f"tp={max(2,min(atr*3,25)):.1f}%")

## DO NOT CHANGE
- Grid trading engine
- Moonbag trailing (already uses ATR adaptively)
- HFT disable
- Loss cap 0.05 SOL
- SCALP_TP tier exits inside the elif chain (keep those as secondary)

## COMMIT
git add scanner.py && git commit -m "Dynamic ATR exits: SL=2xATR, partial=1.5xATR, TP=3xATR — no more flat percentages"
