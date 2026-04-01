# V8 Research — Rich UI Enhancement + Swing Polish

## Libraries
- Rich (already installed): Panel, Table, Text, Layout, Live, box
- pandas-ta: RSI calculation for swing patterns (installed)

## UI Architecture
- Dashboard uses Rich.Live with screen=True (full terminal)
- 10+ panels in hierarchical Layout
- Refresh rate: 4/sec (upgraded from 2/sec)
- Windows keyboard via msvcrt.getch()

## Dashboard Enhancements Applied
1. Header: market state color background + daily loss progress bar
2. Results: exit type icons (^ v - T * ! G S) + strategy badge
3. Log panel: color coded by event type (green=win, red=loss, cyan=grad)
4. Keyboard: +/- to adjust min score on the fly
5. Positions: heat bars, momentum lock, pyramid count

## Swing Strategy (already existed)
- Watchlist builder: DEXScreener scan every 30min
- Pattern scanner: BREAKOUT, BOUNCE, CONTINUATION, VOL_SURGE
- Exit logic: -8% SL, +15% TP (50% partial), trailing, 2hr max
- SWING_LOG_CSV for separate tracking

## API Endpoints
- DEXScreener search: https://api.dexscreener.com/latest/dex/search?q=pump.fun
- DEXScreener tokens: https://api.dexscreener.com/latest/dex/tokens/{mint}
- DEXScreener boosts: https://api.dexscreener.com/token-boosts/top/v1
- GeckoTerminal OHLCV: https://api.geckoterminal.com/api/v2/networks/solana/pools/{pair}/ohlcv/minute

## Known Issues
- GeckoTerminal rate limit: 30 req/min
- DEXScreener may not index all PumpSwap pools immediately
- Unicode chars may not render on all Windows terminals
