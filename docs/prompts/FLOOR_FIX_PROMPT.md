# URGENT FIX — FLOOR_SL at -0.5% is killing proven winners

## READ ERROR_LOG.md FIRST

## THE PROBLEM
FLOOR_SL at -0.5% (line ~5920 in scanner.py) fires BEFORE all other 
exit logic. It killed 6 of 7 trades in the last session:

Community -0.5% (PROVEN WINNER — avg +4.4%, hits +8%)
LOL -0.6%
MOON -0.6% (PROVEN WINNER — avg +3.4%, hits +9%)
gem -1.9%
ANIME -0.9%
SPIN -1.5%

These meme tokens naturally dip -0.5% to -1% in the first 30 seconds.
That's normal noise. They then bounce to +3-9%. FLOOR_SL kills them
before they get the chance.

## THE FIX — ONE LINE CHANGE

Find this EXACT code (around line 5920):
    if p.pct_change <= -0.5:
        exit_reason = f"FLOOR_SL({p.pct_change:+.1f}%)"

Change -0.5 to -2.0:
    if p.pct_change <= -2.0:
        exit_reason = f"FLOOR_SL({p.pct_change:+.1f}%)"

That's it. One number. -0.5 becomes -2.0.

## WHY -2.0%?
- Normal meme coin noise: ±1-2% in first 30 seconds
- Our proven winners (ZEN, Community, MOON, Piece) all dip 0.5-1.5% before pumping
- -2.0% is still tight enough to catch real dumps (gem at -1.9% would barely survive)
- The strategy-specific exits (SCALP_MOM_EXIT, HEAT_DUMP) handle nuanced exits
- FLOOR_SL is just a safety net — it shouldn't be the primary exit mechanism

## ALSO: JTO × 5 DUPLICATES STILL HAPPENING
Bug 15 is not fixed. JTO has 5 open MOMENTUM positions. This wastes
2.5 SOL of capital on one token. Check the duplicate prevention code.

## DO NOT CHANGE
- NUCLEAR_TP at 5.0% (or whatever it's set to now)
- SCALP_TP tiers
- Grid trading
- HFT disable
- Anything in the SCALP elif block

## COMMIT
git add scanner.py && git commit -m "Fix FLOOR_SL: -0.5% to -2.0% — was killing proven winners (Community, MOON, LOL)"
