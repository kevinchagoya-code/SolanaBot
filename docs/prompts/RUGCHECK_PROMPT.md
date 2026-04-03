# SCAM FILTER — RESEARCH-BACKED, USING EXISTING TOOLS

## READ ERROR_LOG.md FIRST — all 15 rules apply

## THE PROBLEM
CLAWBS [SCALP] lost -80.7% in 1 second. That's a rug pull / scam token. 
The loss cap at 0.05 SOL worked (saved $72) but we shouldn't enter at all.

## WHAT THE RESEARCH SAYS (not guessing)

### Best approach: RugCheck.xyz API (Python wrapper exists on PyPI)
- `pip install rugcheck` — unofficial but proven Python wrapper
- Returns: risk score, rugged status, total liquidity, top holder 
  concentration, mint/freeze authority, insider detection, risk list
- Free, millisecond responses, covers ALL Solana tokens
- API: GET https://api.rugcheck.xyz/v1/tokens/{mint}/report
- Already partially integrated — rugcheck_status exists in SimPosition

### What RugCheck catches that we don't:
1. Mint authority active (can mint infinite tokens = instant dilution)
2. Freeze authority active (can freeze your wallet = can't sell)  
3. Top 10 holders > 30% (concentrated = one whale dumps it all)
4. LP not locked/burned (dev can pull all liquidity)
5. Bundled buys detected (fake volume from same wallet cluster)
6. High transfer fees (hidden tax on every trade)
7. Known scam deployer address (serial rugger)

### The 3-tier safety architecture (from RugWatch open source bot):
**Tier 1 — FAST (before entry, <50ms):** On-chain authority check via 
  Helius DAS getAsset. Already built. Check mint/freeze authority.
**Tier 2 — MEDIUM (before entry, <200ms):** RugCheck API call. Get risk 
  score + liquidity + top holders. Skip if score > danger threshold.
**Tier 3 — SLOW (first 3 seconds after entry):** Price sanity check. 
  If price drops >10% in first 3 seconds, exit immediately as RUG_EXIT.

## IMPLEMENTATION

### Option A: Use the rugcheck Python package (easiest)
```python
# pip install rugcheck
# In the SCALP/TRENDING entry path:

async def check_rugcheck_safety(mint: str) -> dict:
    """Check token safety via RugCheck API. Returns {safe, score, reason}."""
    try:
        import aiohttp
        url = f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as r:
                if r.status != 200:
                    return {"safe": True, "score": 0, "reason": "rugcheck_unavailable"}
                data = await r.json()
                
                score = data.get("score", 0)
                risks = data.get("risks", [])
                total_liq = data.get("totalMarketLiquidity", 0)
                
                # SKIP if RugCheck says "Danger" or score > 5000
                if data.get("result") == "Danger" or score > 5000:
                    return {"safe": False, "score": score, 
                            "reason": f"RC_DANGER(score={score})"}
                
                # SKIP if total liquidity < $5,000
                if total_liq < 5000:
                    return {"safe": False, "score": score,
                            "reason": f"RC_LOW_LIQ(${total_liq:.0f})"}
                
                # SKIP if any "danger" level risk
                for risk in risks:
                    if risk.get("level") == "danger":
                        name = risk.get("name", "unknown")
                        return {"safe": False, "score": score,
                                "reason": f"RC_RISK({name})"}
                
                return {"safe": True, "score": score, "reason": "RC_OK"}
    except Exception as e:
        # If RugCheck is down, fall through (don't block trading)
        return {"safe": True, "score": 0, "reason": f"rc_error:{e}"}
```

### Where to add the check:
In EVERY entry path (SCALP, TRENDING, GRAD_SNIPE), BEFORE opening position:
```python
# Before opening any non-HFT position:
rc = await check_rugcheck_safety(mint)
if not rc["safe"]:
    _dbg(f"RUGCHECK_SKIP: {symbol} — {rc['reason']}")
    return
```

For HFT (pump.fun bonding curve tokens), the existing safety check 
via Helius DAS is sufficient — RugCheck may not have data on brand-new 
tokens. But add the Tier 3 price sanity check:

### Tier 3: Post-entry price sanity (catches what slips through)
```python
# In the position monitoring loop, for positions held < 5 seconds:
if hold_sec < 5 and p.pct_change < -10:
    exit_reason = f"RUG_EXIT({p.pct_change:+.0f}%@{hold_sec:.0f}s)"
    # This catches tokens that crash >10% in first 5 seconds
```

## ALSO: Lower SCALP loss cap from 0.05 to 0.03 SOL
A SCALP trade at 0.25 SOL entry should never lose more than 0.03 SOL.
-80% on a 0.25 position = capped at -0.03 instead of -0.20.

## DO NOT CHANGE
- HFT safety check (already uses Helius DAS, fast enough)
- Proactive TP tiers (SCALP_TP, TP2, TP3 — working great)
- Grid trading engine
- Jupiter price integration
- Dashboard

## EXPECTED IMPACT
CLAWBS would have been caught by RugCheck "Danger" score before entry.
Zero loss instead of -0.05 SOL. Every future scam token gets filtered.

## COMMIT
git add -A && git commit -m "Add RugCheck API scam filter for SCALP/TRENDING entries — research-backed 3-tier safety"
