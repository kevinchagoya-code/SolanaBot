# UNIVERSAL PRICE LAYER — SEE EVERY TOKEN ON SOLANA

## THE VISION
The bot should be able to get the price of ANY Solana token instantly.
Right now it can only see:
1. Pump.fun bonding curve tokens (via getAccountInfo RPC)
2. Whatever DEXScreener has indexed (slow, 60s+ delay after graduation)

After this fix, it sees EVERYTHING through a priority chain of price sources.

## THE SOLUTION: Jupiter Price API V3 (FREE, covers ALL Solana tokens)

Jupiter is Solana's main DEX aggregator. It routes through Raydium, Orca,
PumpSwap, Meteora, Phoenix, Lifinity, and every other Solana DEX.
If a token is tradeable ANYWHERE on Solana, Jupiter has its price.

Endpoint: https://api.jup.ag/price/v2?ids={mint_address}
- FREE, no API key needed
- Returns price in USD for any Solana token by mint address
- Can batch up to 100 tokens per request
- Uses last swapped price across all DEXs
- Includes confidence/quality indicators

### Implementation: Add Jupiter as PRIMARY price source

```python
import aiohttp

JUPITER_PRICE_URL = "https://api.jup.ag/price/v2"

async def jupiter_get_price(session: aiohttp.ClientSession, mint: str) -> float:
    """Get price from Jupiter Price API — covers ALL Solana tokens."""
    try:
        url = f"{JUPITER_PRICE_URL}?ids={mint}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
            if r.status != 200: return 0.0
            data = await r.json(content_type=None)
            token_data = data.get("data", {}).get(mint, {})
            price_usd = float(token_data.get("price", 0) or 0)
            if price_usd > 0 and STATE.sol_price_usd > 0:
                return price_usd / STATE.sol_price_usd
            return 0.0
    except Exception as e:
        _dbg(f"Jupiter price error for {mint}: {e}")
        return 0.0

async def jupiter_get_prices_batch(session, mints: list) -> dict:
    """Batch price fetch — up to 100 mints at once."""
    try:
        ids = ",".join(mints[:100])
        url = f"{JUPITER_PRICE_URL}?ids={ids}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200: return {}
            data = await r.json(content_type=None)
            results = {}
            for mint in mints:
                token_data = data.get("data", {}).get(mint, {})
                price_usd = float(token_data.get("price", 0) or 0)
                if price_usd > 0 and STATE.sol_price_usd > 0:
                    results[mint] = price_usd / STATE.sol_price_usd
            return results
    except:
        return {}
```


### New Price Priority Chain

Replace the current price fetching logic with this priority chain:

```python
async def get_universal_price(session, mint: str, position=None) -> tuple:
    """Universal price fetcher — tries every source in priority order.
    Returns (price_sol, source_name) or (0.0, "NONE")
    """
    
    # 1. BONDING CURVE (fastest, ~50ms, only for active pump.fun tokens)
    if position and not position.graduated:
        price = await read_bonding_curve_price(session, mint)
        if price > 0:
            return (price, "BC")
    
    # 2. JUPITER PRICE API (covers ALL Solana DEXs, ~200ms, FREE)
    price = await jupiter_get_price(session, mint)
    if price > 0:
        return (price, "JUP")
    
    # 3. DEXSCREENER (backup, ~300ms, rate limited)
    price = await dexscreener_get_price(session, mint)
    if price > 0:
        return (price, "DEX")
    
    # 4. GECKOTERMINAL (second backup)
    price = await gecko_get_price(session, mint) if hasattr(get_universal_price, '_gecko') else 0.0
    if price > 0:
        return (price, "GECKO")
    
    return (0.0, "NONE")
```

### Wire it into the price check loop

In the main position monitoring loop (where prices are checked every 3s),
replace ALL direct bonding curve reads and DEXScreener calls with:

```python
price, source = await get_universal_price(session, p.mint, position=p)
if price > 0:
    p.current_price_sol = price
    p.price_source = source
else:
    p.price_fetch_failures += 1
```

This means:
- Bonding curve tokens still get fast BC reads
- Graduated tokens that DEXScreener hasn't indexed yet get Jupiter price
- Any Solana token on any DEX gets Jupiter price
- FETCH_FAIL only happens if ALL sources fail (truly dead token)

### Wire it into TRENDING/SCALP entry

Before opening ANY TRENDING or SCALP position:
```python
price, source = await get_universal_price(session, mint)
if price <= 0:
    _dbg(f"SKIP: {symbol} — no price from any source")
    return
```

This eliminates 100% of the "FORCE_EXIT_STUCK(fails=5)" errors because
we verify price exists BEFORE entering.


### Jupiter Token Discovery — Find What's Moving

Jupiter also has a token list API that shows ALL tradeable Solana tokens.
Use this to discover what's moving across the entire ecosystem:

```python
async def jupiter_scan_movers(session) -> list:
    """Scan Jupiter for tokens with recent price movement.
    This replaces the DEXScreener-only scanner for broader coverage."""
    
    # Jupiter doesn't have a direct "gainers" endpoint, but we can:
    # 1. Use DEXScreener for discovery (trending/boosted)
    # 2. Use Jupiter for PRICING (universal coverage)
    # 3. Combine for best of both worlds
    
    # The key change: when DEXScreener finds a trending token,
    # verify its price via Jupiter (not DEXScreener) before entering.
    # This eliminates the FETCH_FAIL problem entirely.
    pass
```

### Batch Price Updates for Open Positions

Instead of fetching prices one by one, batch all open position mints
into a single Jupiter API call every 3 seconds:

```python
# In the main monitoring loop:
open_mints = [p.mint for p in STATE.sim_positions.values() 
              if not p.graduated]  # BC tokens handled separately
graduated_mints = [p.mint for p in STATE.sim_positions.values()
                   if p.graduated or p.strategy in ("SCALP", "TRENDING")]

if graduated_mints:
    # One API call for ALL graduated/DEX tokens
    prices = await jupiter_get_prices_batch(session, graduated_mints)
    for mint, price in prices.items():
        if mint in STATE.sim_positions:
            STATE.sim_positions[mint].current_price_sol = price
            STATE.sim_positions[mint].price_source = "JUP"
```

This reduces API calls from N (one per position) to 1 (batch), and
covers every token on every Solana DEX.

## THE COMPLETE PRICE ARCHITECTURE

```
                    ┌─────────────────────┐
                    │   Price Request      │
                    │   for any token      │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ 1. Bonding Curve?    │ ~50ms
                    │ (pump.fun active)    │ On-chain RPC
                    └──────────┬──────────┘
                          No   │   Yes → return BC price
                    ┌──────────▼──────────┐
                    │ 2. Jupiter Price V2  │ ~200ms
                    │ (ALL Solana DEXs)    │ FREE, no key
                    └──────────┬──────────┘
                          No   │   Yes → return JUP price
                    ┌──────────▼──────────┐
                    │ 3. DEXScreener       │ ~300ms
                    │ (backup)             │ Rate limited
                    └──────────┬──────────┘
                          No   │   Yes → return DEX price
                    ┌──────────▼──────────┐
                    │ 4. NONE              │
                    │ Token truly dead     │ Don't enter
                    └─────────────────────┘
```

## WHAT THIS UNLOCKS

- Bot can trade ANY token on ANY Solana DEX (not just pump.fun)
- FETCH_FAIL errors drop to near zero (Jupiter covers everything)
- Graduated tokens get instant pricing (no 60s DEXScreener wait)
- SCALP/TRENDING strategies can enter tokens the moment they're tradeable
- Batch pricing reduces API overhead for monitoring open positions
- Price source shown on dashboard (BC, JUP, DEX) so you know where data comes from

## ALSO: Update Dashboard

Show the price source per position in the dashboard:
- "BC" = bonding curve (pump.fun, fastest)
- "JUP" = Jupiter (all DEXs, universal)
- "DEX" = DEXScreener (backup)

The dashboard already has a price_source column — just make sure
Jupiter shows as "JUP" when it's the source.

## DO NOT CHANGE
- Adaptive trailing stop system
- Moonbag exit logic
- Heat score calculation  
- HFT Geyser WebSocket detection
- Groq AI engine

## COMMIT
git add -A && git commit -m "Universal price layer: Jupiter V2 API for all Solana tokens, batch pricing, price priority chain"
