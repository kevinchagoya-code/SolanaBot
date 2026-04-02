"""
Solana Pump.fun Meme Coin Sniper + Rug Surf Simulator + Pre-Fire Intelligence
Controls: SPACE = start/stop execution   Q = quit

v4: Geyser WebSocket, parallel RPC, connection pooling, latency benchmarks,
    pre-warmed tx pool, memory-cached wallet sets, uvloop.
"""
# ── stdlib ────────────────────────────────────────────────────────────────────
import asyncio, base64, csv, json, math, os, re, struct, sys, time, threading
from collections import deque, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

# ── uvloop (2-4x faster event loop on Linux/Mac) ─────────────────────────────
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    _UVLOOP = True
except ImportError:
    _UVLOOP = False  # Windows: falls back to default ProactorEventLoop

# ── third-party ───────────────────────────────────────────────────────────────
import aiohttp, websockets
from dotenv import load_dotenv
from rich import box
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
HELIUS_RPC_URL       = os.getenv("HELIUS_RPC_URL", "")
HELIUS_WS_URL        = os.getenv("HELIUS_WS_URL", "")
WALLET_ADDRESS       = os.getenv("WALLET_ADDRESS", "")
PRIVATE_KEY          = os.getenv("PRIVATE_KEY", "")
EXECUTE_TRADES       = os.getenv("EXECUTE_TRADES", "false").lower() == "true"
MIN_PROFIT_SOL       = float(os.getenv("MIN_PROFIT_SOL", "0.01"))
TRADE_SIZE_SOL       = float(os.getenv("TRADE_SIZE_SOL", "1.0"))
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")
BITQUERY_API_KEY     = os.getenv("BITQUERY_API_KEY", "")
JITO_TIP_LAMPORTS    = int(os.getenv("JITO_TIP_LAMPORTS", "10000"))
WATCH_WALLETS        = [w.strip() for w in os.getenv("WATCH_WALLETS", "").split(",") if w.strip()]
HELIUS_RPC_URL_2     = os.getenv("HELIUS_RPC_URL_2", "")
HELIUS_RPC_URL_3     = os.getenv("HELIUS_RPC_URL_3", "")
HFT_MODE             = os.getenv("HFT_MODE", "false").lower() == "true"  # from .env — set to true to enable pump.fun sniping
OVERNIGHT_MODE       = os.getenv("OVERNIGHT_MODE", "false").lower() == "true"

# ── Groq AI Decision Engine ──────────────────────────────────────────────────
GROQ_API_KEY         = os.getenv("GROQ_API_KEY", "")
AI_DECISION_ENGINE   = os.getenv("AI_DECISION_ENGINE", "true").lower() == "true"
AI_ENTRY_ENABLED     = os.getenv("AI_ENTRY_ENABLED", "true").lower() == "true"
AI_EXIT_ENABLED      = os.getenv("AI_EXIT_ENABLED", "true").lower() == "true"
AI_MAX_CALLS_DAY     = 14400
AI_LOG_CSV           = ""  # set after _BASE

# ── Email alerts ──────────────────────────────────────────────────────────────
ALERT_EMAIL          = os.getenv("ALERT_EMAIL", "")
ALERT_EMAIL_FROM     = os.getenv("ALERT_EMAIL_FROM", "")
GMAIL_APP_PASSWORD   = os.getenv("GMAIL_APP_PASSWORD", "")
DAILY_LOSS_LIMIT_SOL = 10.0      # sim mode: halt at 10 SOL loss
STARTING_BALANCE_SOL = 100.0     # starting capital — always reset to this on every restart
EMAIL_CHECK_INTERVAL = 60        # check inbox for replies every 60s
STOP_LOSS_REPLY_TIMEOUT = 600    # 10 minutes to reply before auto-stop

# ── HFT thresholds ───────────────────────────────────────────────────────────
HFT_STOP_LOSS_PCT    = -15.0      # -15% on 18 SOL = -2.7 SOL (~$224) max loss per trade
HFT_MEGA_STOP_LOSS_PCT = -10.0   # tighter SL for score 130+ — at $2,500 position, -10% = $250
HFT_TRAIL_ACTIVATE   = 8.0        # trailing stop activates at +8% (let winners run)
HFT_TRAIL_PCT        = 5.0        # once active, exit if price drops 5% from peak
HFT_FLAT_EXIT_SEC    = 60         # if still between -2% and +2% at 60s: dead token, close
HFT_FLAT_RANGE_PCT   = 2.0        # ±2% = "flat" = dead, free up capital
HFT_MAX_HOLD_SEC     = 60         # 60s max hold — winners avg 107s but 4 TP exits all under 72s. Losers sat 265s wasting slots.
HFT_MIN_BC_VELOCITY  = 5.0        # lowered from 25 — 2s window too short for 25%/min, most tokens show 0
HFT_MIN_BC_PROGRESS  = 0.5        # minimal BC activity — price momentum is the real filter
HFT_PRICE_CHECK_SEC  = 2          # was 10 — too slow, 2s enough to confirm momentum
HFT_MIN_PRICE_MOVE   = 0.0        # allow any non-negative move — BC velocity catches dumps, exits handle the rest
HFT_MIN_BUYERS       = 3          # minimum unique buyers in recent trades
HFT_ENTRY_SOL        = 0.5         # sim mode: 0.5 SOL per HFT trade (GRID_STRATEGY_PROMPT)
HFT_MEGA_ENTRY_SOL   = 1.0        # sim mode: slightly larger for high-score
# ── Dynamic position sizing ($1,500 minimum per position) ────────────────────
MAX_LOSS_PER_TRADE   = 1.0        # sim mode: cap per trade
MAX_LOSS_PER_HOUR    = 5.0        # sim mode: pause if hit
MAX_LOSS_PER_DAY     = 10.0       # sim mode: stop for the day
HFT_MIN_SCORE        = 90         # score 80-89 had 0% WR across 15 trades — pure drag
HFT_HEADERS          = ["session_id","timestamp","symbol","score","entry","exit",
                         "profit_sol","profit_usd","hold_seconds","exit_reason","strategy"]
# ── Multi-strategy constants ─────────────────────────────────────────────────
MAX_PER_STRATEGY      = 5       # sim mode: more positions to test more tokens
MAX_TOTAL_POSITIONS   = 15      # sim mode: 15 x 1-2 SOL = 15-30 SOL, leaves 70+ SOL reserve
GRAD_ENTRY_SOL        = 0.5     # sim mode: 0.5 SOL per GRAD trade (GRID_STRATEGY_PROMPT)
NEAR_GRAD_ENTRY_SOL   = 18.0    # ~$1,500 — pre-graduation
TRENDING_ENTRY_SOL    = 1.0     # sim mode: small bets on unproven tokens
TRENDING_MIN_HEAT     = 55      # minimum heat to enter — heat 36 COLD = garbage
REDDIT_ENTRY_SOL      = 1.0     # sim mode
GRAD_SL_PCT           = -15.0    # tightened from -30 — OpenCla proved grads can dump fast
GRAD_MAX_HOLD_SEC     = 1800    # 30 min moonbag
# Pyramiding (GRAD_SNIPE only — 30min hold gives enough time)
PYRAMID_LEVELS        = [3.0, 8.0, 15.0]   # add at +3%, +8%, +15% (lowered to catch winners earlier)
PYRAMID_ADD_RATIOS    = [0.50, 1.00, 0.50] # 50%, 100%, 50% of original
PYRAMID_MAX_ADDS      = 3
MOMENTUM_LOCK_PCT     = 3.0     # if position hits +3%, disable flat exit
# ── Swing trading constants ───────────────────────────────────────────────────
SWING_ENTRY_SOL       = 1.0     # sim mode
SWING_SL_PCT          = -8.0    # tighter SL
SWING_TP_PCT          = 15.0    # first take profit
SWING_MAX_HOLD_SEC    = 7200    # 2 hours
SWING_WATCHLIST_SIZE  = 20
SWING_SCAN_INTERVAL   = 30      # pattern check every 30s
SWING_WATCHLIST_FILE  = ""  # set after _BASE is defined
SWING_LOG_CSV         = ""  # set after _BASE is defined
# ── Scalp trading constants ───────────────────────────────────────────────────
SCALP_ENTRY_SOL       = 0.5     # sim mode: 0.5 SOL per SCALP trade (GRID_STRATEGY_PROMPT)
SCALP_TRAIL_ACTIVATE  = 0.5     # activate trailing stop at +0.5%
SCALP_TRAIL_MULT      = 0.40    # trail = 40% of peak gain (exit at 60% of peak)
SCALP_TRAIL_FLOOR     = 0.3     # minimum exit at +0.3% profit
SCALP_HARD_TP_PCT     = 3.0     # hard cap — exit at +3% ($45 profit on $1,500)
SCALP_SL_PCT          = -2.0    # SL -2% ($30 loss on $1,500)
SCALP_WEAK_SL_PCT     = -1.0    # exit early if losing AND heat dying ($15 loss)
SCALP_TIME_STOP_SEC   = 20      # exit flat tokens
SCALP_MAX_HOLD_SEC    = 30      # absolute max hold
SCALP_MAX_POSITIONS   = 5       # sim mode: more slots to find winners
SCALP_MIN_SCORE       = 70
SCALP_MIN_HEAT        = 55
SCALP_WATCH_INTERVAL  = 15       # 15s between scans to avoid DEXScreener rate limits
SCALP_SIM_THRESHOLD   = 0.6     # token name similarity threshold
SCALP_MAX_MCAP        = 10_000_000  # $10M max — bigger tokens don't move enough for scalp
SCALP_MIN_MCAP        = 50_000      # $50K min — avoid dust/dead tokens
SCALP_MIN_5M_CHANGE   = 1.0         # must have moved +1% in last 5 min
SCALP_BLACKLIST       = {
    "USDC", "USDT",  # stablecoins only — everything else is tradeable
}
SCALP_LOG_CSV         = ""      # set after _BASE defined
NEAR_GRAD_SL_PCT      = -20.0
NEAR_GRAD_MAX_HOLD_SEC = 600   # 10 min or graduation
TRENDING_SL_PCT       = -25.0
TRENDING_MAX_HOLD_SEC = 300     # 5 min
REDDIT_SL_PCT         = -20.0
REDDIT_MAX_HOLD_SEC   = 300     # 5 min
RPC_ENDPOINTS        = [u for u in [HELIUS_RPC_URL, HELIUS_RPC_URL_2, HELIUS_RPC_URL_3] if u]

# ── Helius Developer APIs ────────────────────────────────────────────────────
HELIUS_API_KEY       = HELIUS_RPC_URL.split("api-key=")[-1] if "api-key=" in HELIUS_RPC_URL else ""
HELIUS_API_BASE      = "https://api.helius.xyz/v0"
HELIUS_WEBHOOK_URL   = f"{HELIUS_API_BASE}/webhooks?api-key={HELIUS_API_KEY}"
HELIUS_ENHANCED_TX   = f"{HELIUS_API_BASE}/addresses"

# ── Geyser / Enhanced WebSocket ───────────────────────────────────────────────
# Helius Enhanced WebSocket supports transactionSubscribe on the standard endpoint.
# atlas-mainnet requires Business tier; standard endpoint works on Developer tier.
# Try standard endpoint first (works on all Helius tiers that support Enhanced WS)
GEYSER_WS_URL  = HELIUS_WS_URL  # same as standard WS — transactionSubscribe is the differentiator
GEYSER_WS_ATLAS = f"wss://atlas-mainnet.helius-rpc.com?api-key={HELIUS_API_KEY}" if HELIUS_API_KEY else ""

# ── Jito ──────────────────────────────────────────────────────────────────────
JITO_TIP_ACCOUNT = "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5"
JITO_BLOCK_ENGINE = "https://mainnet.block-engine.jito.wtf/api/v1/bundles"

# ── Bitquery ──────────────────────────────────────────────────────────────────
BITQUERY_URL = "https://streaming.bitquery.io/graphql"
BITQUERY_INTERVAL = 30  # seconds

# ── pump.fun constants (from nirholas/pump-fun-sdk + 1fge/pump-fun-sniper-bot) ─
PUMP_PROGRAM_ID      = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMP_AMM_PROGRAM_ID  = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"    # graduated pools
PUMP_MIGRATION_PROG  = "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg"    # migration wrapper (emits Migrate events)
PUMP_FEE_PROGRAM_ID  = "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"    # fee sharing
PUMP_MAYHEM_ID       = "MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e"    # mayhem mode
PUMP_MINT_AUTH       = "TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM"     # token mint authority
PUMP_FEE_BPS         = 100           # 1% = 100 bps (actual fee is tiered by MC)
SOL_TX_FEE           = 0.000005
LAMPORTS_PER_SOL     = 1_000_000_000

# Bonding curve constants (from 1fge + nirholas/pump-fun-sdk)
PUMP_INITIAL_REAL_TOKEN_RESERVES = 793_100_000_000_000   # 793.1T raw (6 decimals)
PUMP_TOKEN_TOTAL_SUPPLY          = 1_000_000_000_000_000  # 1B raw (6 decimals)
PUMP_INITIAL_VIRTUAL_SOL         = 30_000_000_000         # 30 SOL in lamports
PUMP_GRADUATION_SOL              = 85.0                    # ~85 SOL virtual reserves

# Anchor instruction discriminators (SHA-256 first 8 bytes of "global:<name>")
PUMP_IX_CREATE   = bytes([24, 30, 200, 40, 5, 28, 7, 119])
PUMP_IX_BUY      = bytes([102, 6, 61, 18, 1, 218, 235, 234])
PUMP_IX_SELL     = bytes([51, 230, 133, 164, 1, 127, 131, 173])

# Bonding curve account data layout (151 bytes, from nirholas/pump-fun-sdk)
# Offset 0-7:   IDL signature
# Offset 8-15:  virtualTokenReserves (u64 LE)
# Offset 16-23: virtualSolReserves (u64 LE)
# Offset 24-31: realTokenReserves (u64 LE)
# Offset 32-39: realSolReserves (u64 LE)
# Offset 40-47: tokenTotalSupply (u64 LE)
# Offset 48:    complete (bool)
# Offset 49-80: creator (PublicKey, 32 bytes)
# Offset 81:    isMayhemMode (bool)
BC_SIZE = 49  # minimum: 8 discriminator + 5*8 reserves + 1 complete (pump.fun added new fields, old 151 breaks)

# ── RugCheck.xyz ──────────────────────────────────────────────────────────────
RUGCHECK_API = "https://api.rugcheck.xyz/v1/tokens"

# ── Thresholds ────────────────────────────────────────────────────────────────
MIN_TOKEN_AGE_SEC    = 30
SIM_ENTRY_SOL        = TRADE_SIZE_SOL
STOP_LOSS_PCT        = -60.0
# Tiered exits (research: earlier exits outperform)
TAKE_PROFIT_2X       = 100.0    # take 50% at 2x
TAKE_PROFIT_3X       = 200.0    # take 75% remainder at 3x
HARD_EXIT_30MIN_MIN  = 50.0     # hard exit at 30min if under 1.5x (50% gain)
HARD_EXIT_30MIN_SEC  = 1800     # 30 minutes
DEV_SELL_THRESHOLD   = 0.20
MAX_HOLD_HOURS       = 24
PRICE_CHECK_INTERVAL = 3           # was 10 — too slow, tokens gap past stop loss
POLL_INTERVAL        = 30
SLIPPAGE_BPS         = 1500

# Bonding curve velocity
BC_VELOCITY_ALERT    = 10.0     # 10% jump in 60s = graduation predictor
BC_THRESHOLD_75      = 75.0
BC_THRESHOLD_85      = 85.0
BC_THRESHOLD_95      = 95.0

# Bundle detection
BUNDLE_SAME_BLOCK_BUYS = 3     # 3+ buys in same slot = bundled
BOT_CLUSTER_THRESHOLD  = 0.60  # 60% of early trades from same cluster = skip

# ── Intelligence intervals ────────────────────────────────────────────────────
REDDIT_POLL_INTERVAL    = 30   # Reddit JSON poll every 30s
TWIKIT_POLL_INTERVAL    = 60   # Twikit search every 60s
WALLET_CHECK_INTERVAL   = 300
WATCH_WALLET_INTERVAL   = 15   # seconds for copy-trade wallet scanning
WHALE_ENTRY_SOL         = 2.0   # sim mode
WHALE_SCORE_BOOST       = 60   # score boost for whale-bought token
WHALE_MULTI_BOOST       = 80   # multiple whales bought same token
PATTERN_MIN_CLOSED      = 100
TWIT_VEL_MIN_MENTIONS   = 3    # 3+ mentions of same ticker in window
TWIT_VEL_WINDOW_SEC     = 300  # 5 minute window
TWIT_VEL_SCORE_BOOST    = 40   # score boost for ticker velocity
VIRAL_WINDOW_SEC        = 600
VIRAL_MIN_ACCOUNTS      = 3

# ── File paths ────────────────────────────────────────────────────────────────
_BASE = r"C:\Users\kevin\SolanaBot"
SNIPE_LOG_CSV    = os.path.join(_BASE, "snipe_log.csv")
NEW_TOKENS_CSV   = os.path.join(_BASE, "new_tokens_log.csv")
INTELLIGENCE_CSV = os.path.join(_BASE, "intelligence_log.csv")
DEBUG_LOG        = os.path.join(_BASE, "debug.log")
PREFIRE_JSON     = os.path.join(_BASE, "prefirelist.json")
WALLETS_JSON     = os.path.join(_BASE, "successful_wallets.json")
PATTERNS_JSON    = os.path.join(_BASE, "patterns.json")
PERF_LOG_CSV     = os.path.join(_BASE, "performance_log.csv")
HFT_LOG_CSV      = os.path.join(_BASE, "hft_log.csv")
WHALE_LOG_CSV    = os.path.join(_BASE, "whale_log.csv")
MOONBAG_LOG_CSV  = os.path.join(_BASE, "moonbag_log.csv")
SWING_WATCHLIST_FILE = os.path.join(_BASE, "watchlist.json")
SWING_LOG_CSV    = os.path.join(_BASE, "swing_log.csv")
SCALP_LOG_CSV    = os.path.join(_BASE, "scalp_log.csv")
AI_LOG_CSV       = os.path.join(_BASE, "ai_decisions.csv")
EMAIL_LOG        = os.path.join(_BASE, "email_log.txt")
STATE_JSON       = os.path.join(_BASE, "state.json")
MORNING_REPORT   = os.path.join(_BASE, "morning_report.txt")
DASHBOARD_JSON   = os.path.join(_BASE, "dashboard_data.json")

WHALE_HEADERS    = ["session_id", "timestamp", "wallet_address", "token_mint",
                    "token_symbol", "whale_buy_amount_sol", "our_entry_price",
                    "peak_price", "exit_price", "profit_sol", "profit_usd"]
SESSIONS_LOG     = os.path.join(_BASE, "sessions_log.txt")

# Session ID: timestamp of this startup (persists across entire run)
SESSION_ID = datetime.now().strftime("%Y%m%d_%H%M%S")

PERF_HEADERS = [
    "timestamp", "mint", "symbol", "detect_ms", "rugcheck_ms",
    "safety_ms", "open_ms", "total_ms", "source",
]

SNIPE_HEADERS = [
    "session_id", "timestamp", "mint", "symbol", "score", "category",
    "entry_price_sol", "exit_price_sol", "profit_sol", "profit_usd",
    "hold_time_seconds", "exit_reason", "had_social_links", "dev_sold",
    "peak_price_sol", "bc_progress_at_exit", "rugcheck_status", "strategy",
    "pyramid_count", "heat_at_entry", "heat_at_exit", "peak_pct", "price_source",
]
NEW_TOKEN_HEADERS = [
    "timestamp", "mint", "symbol", "score", "category",
    "initial_liquidity_sol", "market_cap", "social_links", "description",
    "rugcheck_status", "narrative_score", "timing_window",
]
INTEL_HEADERS = [
    "timestamp", "signal_type", "search_term", "token_name", "ticker",
    "mint", "tweet_id", "author", "followers", "likes", "retweets",
    "signal_score", "source",
]

# ── Reddit feeds (free, no API key) ──────────────────────────────────────────
REDDIT_FEEDS = [
    "https://www.reddit.com/r/solana/new.json?limit=25",
    "https://www.reddit.com/r/cryptomoonshots/new.json?limit=25",
    "https://www.reddit.com/r/SolanaMemeCoins/new.json?limit=25",
    "https://www.reddit.com/r/memecoin/new.json?limit=25",
    "https://www.reddit.com/r/CryptoMoonShots/new.json?limit=25",
]
REDDIT_HIGH_SIGNAL_SUBS = {"solanamemecoins", "cryptomoonshots"}

# ── Twikit Twitter scraping (no API key) ─────────────────────────────────────
TWITTER_USERNAME    = os.getenv("TWITTER_USERNAME", "")
TWITTER_PASSWORD    = os.getenv("TWITTER_PASSWORD", "")
TWITTER_ENABLED     = os.getenv("TWITTER_ENABLED", "false").lower() == "true"  # disabled: KEY_BYTE error
TWIKIT_COOKIES_PATH = os.path.join(_BASE, "twitter_cookies.json")
TWIKIT_SEARCH_TERMS = [
    "pump.fun CA",
    "just launched solana",
    "stealth launch solana",
    "about to graduate pump.fun",
    "bonding curve solana",
]
TWIKIT_ACCOUNTS = [
    "elonmusk", "breaking911", "unusual_whales",
    "pumpdotfun", "disclosetv", "wsbchairman",
]

SIGNAL_KEYWORDS = {"ca", "just launched", "stealth", "pump.fun", "graduating",
                   "bonding curve", "graduated", "migrating", "king of the hill"}

# Legacy — unused
TWITTER_SEARCH_TERMS = []

_DEFAULT_TERM_WEIGHT = 1.0
_MINT_RE = re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b')

# ── Narrative keywords (current metas) ───────────────────────────────────────
_NARRATIVE_AI      = {"ai", "agent", "gpt", "llm", "neural", "cognitive", "sentient", "bot"}
_NARRATIVE_POLITIC = {"trump", "biden", "election", "congress", "maga", "politics",
                      "elon", "musk", "sec", "regulation"}
_NARRATIVE_ANIMAL  = {"cat", "dog", "frog", "pepe", "shiba", "doge", "penguin",
                      "hamster", "monkey", "ape", "bear", "bull", "whale"}
_NARRATIVE_CELEB   = {"drake", "kanye", "taylor", "rihanna", "beyonce", "snoop",
                      "lebron", "ronaldo", "messi", "pewdiepie", "mrbeast"}
_NARRATIVE_ABSURD  = {"fart", "poop", "butt", "69", "420", "bruh", "rizz",
                      "skibidi", "sigma", "goat", "chad"}
_NARRATIVE_GENERIC = {"moon", "rocket", "gem", "cash", "rich", "lambo",
                      "diamond", "gold", "king", "queen"}


# ── Debug logging ─────────────────────────────────────────────────────────────
def _dbg(msg: str):
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except: pass
    # Surface errors/warnings to web dashboard
    if any(kw in msg for kw in ("ERROR", "FAIL", "HALT", "PAUSE", "FORCE_EXIT", "CRASH")):
        try:
            STATE.errors_last_hour.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg[:120]}")
        except: pass


def _init_csv(path, headers):
    """Create CSV with headers only if file doesn't exist. Never overwrites."""
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(headers)

def _write_session_header(path):
    """Append a session separator row so you can filter by session in Excel."""
    try:
        with open(path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                f"--- SESSION {SESSION_ID}",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "v4", f"HFT={'ON' if HFT_MODE else 'OFF'}",
                f"min_score={HFT_MIN_SCORE}", f"bc_min={HFT_MIN_BC_PROGRESS}",
            ])
    except: pass

def _count_previous_sessions() -> int:
    """Count how many sessions are recorded in sessions_log.txt."""
    try:
        if os.path.exists(SESSIONS_LOG):
            with open(SESSIONS_LOG, "r", encoding="utf-8") as f:
                return sum(1 for line in f if line.startswith("SESSION "))
    except: pass
    return 0

def _log_session_start():
    """Record session start to sessions_log.txt."""
    try:
        with open(SESSIONS_LOG, "a", encoding="utf-8") as f:
            f.write(f"SESSION {SESSION_ID}\n")
            f.write(f"  Start:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"  HFT:       {'ON' if HFT_MODE else 'OFF'}\n")
            f.write(f"  Min score: {HFT_MIN_SCORE}\n")
            f.write(f"  BC min:    {HFT_MIN_BC_PROGRESS}%\n")
            f.write(f"  Timeout:   {HFT_MAX_HOLD_SEC}s\n")
            f.write(f"  SL:        {HFT_STOP_LOSS_PCT}%\n")
            f.write(f"  TP:        {HFT_TAKE_PROFIT_PCT}%\n")
            f.write(f"  Entry:     {HFT_ENTRY_SOL} SOL\n")
    except: pass

def _log_session_end():
    """Append session end stats to sessions_log.txt."""
    try:
        with open(SESSIONS_LOG, "a", encoding="utf-8") as f:
            f.write(f"  End:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"  Trades:    {STATE.total_opened}\n")
            f.write(f"  Wins:      {STATE.total_wins}\n")
            f.write(f"  Losses:    {STATE.total_losses}\n")
            f.write(f"  P&L:       {STATE.total_pnl_sol:+.6f} SOL\n")
            f.write(f"  HFT TP/SL/TO/FL: {STATE.hft_tp_count}/{STATE.hft_sl_count}/"
                    f"{STATE.hft_timeout_count}/{STATE.hft_flat_count}\n")
            f.write(f"---\n")
    except: pass

def init_csvs():
    """Initialize CSVs (create if missing, never overwrite) and write session headers."""
    _init_csv(SNIPE_LOG_CSV, SNIPE_HEADERS)
    _init_csv(NEW_TOKENS_CSV, NEW_TOKEN_HEADERS)
    _init_csv(INTELLIGENCE_CSV, INTEL_HEADERS)
    _init_csv(PERF_LOG_CSV, PERF_HEADERS)
    _init_csv(HFT_LOG_CSV, HFT_HEADERS)
    _init_csv(WHALE_LOG_CSV, WHALE_HEADERS)
    # Write session separator to trade CSVs
    _write_session_header(SNIPE_LOG_CSV)
    _write_session_header(HFT_LOG_CSV)
    # Record session start
    _log_session_start()

def _load_json(path):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: pass
    return {}

def _save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e: _dbg(f"JSON save error {path}: {e}")

def _safe_int(val, default=0):
    if isinstance(val, int): return val
    if isinstance(val, str):
        try: return int(val)
        except: return default
    return default


# ── Dataclasses ───────────────────────────────────────────────────────────────
@dataclass
class SafetyCheck:
    has_social_links:        Optional[bool] = None   # +15
    low_holder_conc:         Optional[bool] = None   # +15
    dev_not_sold:            Optional[bool] = None   # +15
    liquidity_over_10:       Optional[bool] = None   # +15
    age_over_2min:           Optional[bool] = None   # +10
    mint_authority_revoked:  Optional[bool] = None   # +20 (critical)
    freeze_authority_revoked:Optional[bool] = None   # +20 (critical)
    not_bundled:             Optional[bool] = None   # bundled = -40
    dev_holds_under_5:       Optional[bool] = None   # +15
    bc_progress_fast:        Optional[bool] = None   # 50%+ in 1hr = +20
    holder_growth_organic:   Optional[bool] = None   # +15
    rugcheck_ok:             Optional[bool] = None   # DANGER = skip, WARN = -20
    rugcheck_status:         str = ""                 # "Good","Warn","Danger"
    narrative_score:         int = 0                  # -10 to +25
    timing_score:            int = 0                  # -5 to +10
    bot_dominated:           bool = False             # skip entirely if True
    score:    int = 0
    category: str = "UNKNOWN"
    twitter:    str = ""
    telegram:   str = ""
    website:    str = ""
    top_holder_pct: float = 0.0
    dev_sold_pct:   float = 0.0
    dev_hold_pct:   float = 0.0
    liquidity_sol:  float = 0.0
    market_cap_usd: float = 0.0
    description:    str = ""


@dataclass
class SimPosition:
    symbol:           str
    name:             str
    mint:             str
    category:         str
    score:            int
    entry_time:       float
    entry_ts:         str
    entry_price_sol:  float
    entry_sol:        float = SIM_ENTRY_SOL
    current_price_sol:float = 0.0
    pct_change:       float = 0.0
    peak_price_sol:   float = 0.0
    trough_price_sol: float = 0.0
    initial_liq_sol:  float = 0.0
    market_cap_usd:   float = 0.0
    dev_sold:         bool  = False
    dev_sold_pct:     float = 0.0
    graduated:        bool  = False
    had_social:       bool  = False
    prefire_source:   str   = ""
    creator_wallet:   str   = ""
    rugcheck_status:  str   = ""
    whale_wallet:     str   = ""       # which whale triggered this entry
    whale_buy_sol:    float = 0.0      # how much the whale bought
    # Bonding curve tracking
    bc_progress:      float = 0.0      # 0-100%
    bc_velocity:      float = 0.0      # %/min
    bc_history:       list  = field(default_factory=list)  # [(time, progress%)]
    bc_alerted_75:    bool  = False
    bc_alerted_85:    bool  = False
    bc_alerted_95:    bool  = False
    # Trailing stop
    peak_pct:         float = 0.0      # highest P&L% reached
    trail_active:     bool  = False    # trailing stop activated
    # Tiered exits
    partial_exit_2x:  bool  = False    # took 50% at 2x
    partial_exit_3x:  bool  = False    # took 75% at 3x
    remaining_sol:    float = 0.0      # how much sim SOL still in position
    is_moonbag:       bool  = False    # 25% remainder after trailing stop exit
    moonbag_peak_pct: float = 0.0      # peak % for moonbag (tracks from conversion)
    price_source:     str   = "BC"     # BC, DEX, RPC — where current price comes from
    # Heat score (live momentum analysis)
    heat_score:       float = 0.0      # 0-100 composite momentum score
    heat_pattern:     str   = ""       # ROCKET/HEATING/WARM/COLD/DUMP
    scalp_trail_active: bool = False   # trailing micro-profit activated
    scalp_peak_pct:   float = 0.0     # peak P&L% reached during scalp hold
    heat_at_entry:    float = 0.0     # heat when position opened
    price_history:    list  = field(default_factory=list)  # [(monotonic_time, price)] last 15s
    sol_volume_history: list = field(default_factory=list)  # [(time, sol_delta)] from BC changes
    # Price momentum (direction + speed of current price movement)
    price_momentum:    float = 0.0      # avg % change per tick (positive=rising, negative=falling)
    price_direction:   str   = "FLAT"   # UP / DOWN / FLAT
    price_accelerating: bool = False    # is momentum increasing?
    consecutive_up:    int   = 0        # consecutive up ticks
    consecutive_down:  int   = 0        # consecutive down ticks
    prev_direction:    str   = "FLAT"   # previous direction (for reversal detection)
    # Standard
    signals:     list  = field(default_factory=list)
    alert_level: str   = "OK"
    status:      str   = "OPEN"
    exit_time:   float = 0.0
    exit_price_sol: float = 0.0
    exit_reason:    str   = ""
    profit_sol:     float = 0.0
    profit_usd:     float = 0.0
    price_fetch_failures: int = 0   # consecutive BC fetch failures
    strategy:       str   = "HFT"   # HFT, GRAD_SNIPE, NEAR_GRAD, TRENDING, REDDIT
    confidence:     str   = "LOW"   # LOW, MED, HIGH, MAX
    size_reason:    str   = ""      # why this size was chosen (SC116, GRAD+TREND, etc)
    pyramid_count:  int   = 0      # how many times we've added to this position
    pyramid_levels: list  = field(default_factory=list)  # pct levels where we added


@dataclass
class PreFireSignal:
    token_name:     str = ""
    ticker:         str = ""
    mint:           str = ""
    signal_score:   int = 0
    sources:        list = field(default_factory=list)
    search_terms:   list = field(default_factory=list)
    first_seen:     float = 0.0
    tweet_authors:  list = field(default_factory=list)
    follower_reach: int  = 0
    tweet_count:    int  = 0
    like_count:     int  = 0
    rt_count:       int  = 0
    is_viral:       bool = False
    whale_wallet:   str  = ""
    mint_confirmed: bool = False
    last_updated:   float = 0.0


# ── Shared state ──────────────────────────────────────────────────────────────
class State:
    def __init__(self):
        self.running = False; self.should_exit = False
        self.slot = 0; self.sol_price_usd = 0.0; self.last_ms = 0.0
        self.start_time: Optional[float] = None
        self.status_msg = "Press SPACE to start"
        self.tokens_found = 0; self.last_disc_time = "---"
        self.seen_mints: set = set(); self.skipped_bots = 0
        self.sim_positions: dict[str, SimPosition] = {}
        self.sim_closed: deque[SimPosition] = deque(maxlen=50)
        self.total_opened = 0; self.total_wins = 0; self.total_losses = 0
        self.total_pnl_sol = 0.0; self.best_trade_sol = 0.0
        self.balance_sol = STARTING_BALANCE_SOL  # available capital
        self.worst_trade_sol = 0.0; self.worst_set = False
        self.loss_today_sol:    float = 0.0    # accumulated losses today
        self.loss_hour_sol:     float = 0.0    # losses in current hour
        self.loss_hour_start:   float = time.monotonic()
        self.daily_halted:      bool  = False  # daily loss limit hit
        self.hourly_paused_until: float = 0.0  # pause trading until this time
        self.prefire_list: dict[str, PreFireSignal] = {}
        self.successful_wallets: dict = {}
        self.patterns: dict = {}; self.term_weights: dict = {}
        self.twitter_last_search = 0.0; self.twitter_signals_count = 0
        self.reddit_signals_count = 0
        self.twikit_status = "INIT"  # INIT, OK, FAIL
        self.whale_alerts_count = 0; self.viral_alerts_count = 0
        self.recent_activity: deque[str] = deque(maxlen=12)
        self.ws_connected = False
        self.geyser_connected = False
        self.rate_limited_until: float = 0  # monotonic time when rate limit expires
        # Adaptive market state
        self.market_state:      str   = "WARM"  # HOT, WARM, SLOW, DEAD
        self.adaptive_score:    int   = 88
        self.adaptive_mom:      float = 0.5
        self.adaptive_bc:       float = 0.0
        self.adaptive_size_mult:float = 1.0
        self.recent_velocities: deque = deque(maxlen=50)
        self.recent_scores:     deque = deque(maxlen=50)
        self.tokens_per_min:    float = 0.0
        self.rolling_win_rate:  float = 0.0
        self.wr_trend:          str   = "→"  # ↑ ↓ →
        self.swing_watchlist:   list  = []  # [{mint, symbol, vol_sol, ...}]
        # Creator reputation
        self.creator_stats:    dict  = {}  # wallet → {launches, wins, rugs, avg_peak}
        self.scalp_token_names: list = []  # recent token names for similarity check
        # AI engine
        self.ai_calls_today:   int  = 0
        self.ai_last_latency:  float = 0
        self.ai_status:        str  = "INIT"  # INIT, OK, FAIL, LIMIT
        # Scalp tracking
        self.scalp_enabled:    bool  = True
        self.scalp_trades_today: int = 0
        self.scalp_pnl_today:  float = 0.0
        self.scalp_trade_times: deque = deque(maxlen=200)  # timestamps for trades/min calc
        # Helius integrations
        self.webhook_active:    bool  = False
        self.das_active:        bool  = False
        self.priority_fee:      float = 0.0   # recommended fee in microlamports
        # Latency tracking
        self.latency_detect_ms:  float = 0.0   # token creation → our detection
        self.latency_safety_ms:  float = 0.0   # detection → safety check complete
        self.latency_open_ms:    float = 0.0   # safety → position opened
        self.latency_total_ms:   float = 0.0   # creation → position opened
        self.latency_samples:    deque = deque(maxlen=20)  # last 20 measurements
        # Memory-cached wallet sets (O(1) lookup)
        self.known_rug_wallets:  set = set()
        self.known_good_wallets: set = set()
        # HFT tracking
        self.hft_enabled:       bool = HFT_MODE
        self.hft_trades_hour:   int  = 0
        self.hft_hour_start:    float = time.monotonic()
        self.hft_profits:       deque = deque(maxlen=100)  # (profit_sol, hold_sec)
        self.hft_tp_count:      int  = 0    # take profit exits today
        self.hft_sl_count:      int  = 0    # stop loss exits today
        self.hft_timeout_count: int  = 0    # timeout exits today
        self.hft_flat_count:    int  = 0    # flat early exits today
        self.hft_skip_vel:      int  = 0    # skipped low velocity
        # Whale tracking
        self.whale_buys_today:  int  = 0
        self.whale_tokens:      deque = deque(maxlen=20)  # (time, wallet, mint, symbol, sol_amount)
        self.whale_best_pct:    float = 0.0
        self.whale_best_sym:    str   = ""
        self.wallet_status:     dict  = {}  # wallet -> {"active": bool, "last_trade": float, "checked": float}
        # Email alerts
        self.email_enabled:     bool  = bool(ALERT_EMAIL and GMAIL_APP_PASSWORD)
        self.stop_loss_pending: bool  = False  # waiting for reply
        self.stop_loss_sent_at: float = 0.0
        self.trading_halted:    bool  = False  # STOP reply received
        self.position_size_mult:float = 1.0    # REDUCE halves this
        self.last_hourly_email: float = 0.0
        self.warning_sent:      bool  = False  # 50% loss warning sent
        # Overnight mode
        self.overnight_active:  bool  = False  # True = off-hours watch only
        self.morning_report_sent: bool = False
        self.peak_start_sent:   bool  = False
        self.last_state_save:   float = 0.0
        self.overnight_tokens:  list  = []     # tokens seen during off-hours
        self.hft_skip_bc:       int  = 0    # skipped low BC progress
        self.hft_skip_mom:      int  = 0    # skipped no price momentum
        self.hft_skip_buyers:   int  = 0    # skipped few buyers
        self.session_number:    int  = 0    # which session this is
        # Scroll state
        self.scroll_offset:     int = 0
        self.scroll_selected:   int = 0
        # P&L chart (1-minute samples for last 60 minutes)
        self.pnl_history:       deque = deque(maxlen=60)   # (timestamp, total_pnl_sol)
        # Web dashboard
        self.balance_history:   list  = []   # [{"time": "HH:MM", "balance": 5.123}] — last 500 pts
        self.errors_last_hour:  deque = deque(maxlen=20)   # recent error messages for dashboard
        self._last_balance_log: float = 0.0  # monotonic time of last balance snapshot

STATE = State()
_reddit_open_queue: asyncio.Queue = asyncio.Queue()

def _strategy_count(strategy: str) -> int:
    return sum(1 for p in STATE.sim_positions.values()
               if p.status == "OPEN" and p.strategy == strategy)

def _can_open_strategy(strategy: str, entry_sol: float) -> bool:
    if _strategy_count(strategy) >= MAX_PER_STRATEGY: return False
    open_total = sum(1 for p in STATE.sim_positions.values() if p.status == "OPEN")
    if open_total >= MAX_TOTAL_POSITIONS: return False
    if STATE.balance_sol < entry_sol: return False
    return True

STRAT_COLORS = {"HFT": "yellow", "GRAD_SNIPE": "green", "NEAR_GRAD": "cyan",
                "TRENDING": "magenta", "REDDIT": "blue", "SWING": "bold cyan",
                "SCALP": "bright_white", "MOMENTUM": "bold magenta", "GRID": "bold cyan"}

def calc_hft_size(score: int, has_reddit: bool = False) -> tuple:
    """Dynamic HFT sizing. Sim mode: 0.5-1.5 SOL (GRID_STRATEGY_PROMPT capital allocation)."""
    if score >= 131 and has_reddit:
        return 1.5, "MAX", f"SC{score}+REDDIT"
    elif score >= 131:
        return 1.2, "MAX", f"SC{score}"
    elif score >= 116:
        return 1.0, "HIGH", f"SC{score}"
    elif score >= 100:
        return 0.7, "MED", f"SC{score}"
    else:
        return 0.5, "LOW", f"SC{score}"

def calc_grad_size(mint: str) -> tuple:
    """Dynamic GRAD_SNIPE sizing based on signal stack. Returns (sol, confidence, reason)."""
    signals = []
    has_trending = False
    has_reddit = False
    has_whale = False

    # Check if token is trending on dexscreener
    if mint in STATE.sim_positions:
        p = STATE.sim_positions[mint]
        has_trending = "TRENDING" in p.signals
    # Check prefire list for reddit/whale
    pf = STATE.prefire_list.get(mint)
    if pf:
        has_reddit = "REDDIT" in pf.sources or "NITTER" in pf.sources
        has_whale = bool(pf.whale_wallet)

    reason = "GRAD"
    if has_trending: reason += "+TREND"; signals.append("TREND")
    if has_reddit: reason += "+REDDIT"; signals.append("REDDIT")
    if has_whale: reason += "+WHALE"; signals.append("WHALE")

    n = len(signals)
    if n >= 3:
        return 0.30, "MAX", reason
    elif n >= 2:
        return 0.20, "HIGH", reason
    elif n >= 1:
        return 0.15, "MED", reason
    else:
        return 0.10, "LOW", reason

def _check_loss_limits() -> bool:
    """Check if trading should be paused/halted. Returns True if OK to trade."""
    now = time.monotonic()
    # Reset hourly counter
    if now - STATE.loss_hour_start >= 3600:
        STATE.loss_hour_sol = 0.0
        STATE.loss_hour_start = now
        if STATE.hourly_paused_until > 0 and now >= STATE.hourly_paused_until:
            STATE.hourly_paused_until = 0

    if STATE.daily_halted:
        return False
    if STATE.hourly_paused_until > 0 and now < STATE.hourly_paused_until:
        return False
    return True

async def _wait_if_rate_limited():
    """Check if we're rate limited and wait if so. Returns True if was limited."""
    if STATE.rate_limited_until > 0 and time.monotonic() < STATE.rate_limited_until:
        remain = STATE.rate_limited_until - time.monotonic()
        await asyncio.sleep(remain)
        return True
    return False

def _set_rate_limited(seconds: int = 120):
    """Set global rate limit backoff."""
    STATE.rate_limited_until = time.monotonic() + seconds
    STATE.status_msg = f"RATE LIMITED ({seconds}s)"
    _dbg(f"GLOBAL RATE LIMIT: backing off {seconds}s")
    STATE.recent_activity.append(f"Rate limited: pausing {seconds}s")

def _is_similar_token(name: str) -> bool:
    """Check if token name is too similar to one we already hold or recently lost on."""
    import difflib
    name_lower = name.lower()
    for existing in STATE.scalp_token_names[-50:]:
        sim = difflib.SequenceMatcher(None, existing.lower(), name_lower).ratio()
        if sim >= SCALP_SIM_THRESHOLD:
            return True
    # Also check open positions
    for p in STATE.sim_positions.values():
        if p.status == "OPEN":
            sim = difflib.SequenceMatcher(None, p.symbol.lower(), name_lower).ratio()
            if sim >= SCALP_SIM_THRESHOLD:
                return True
    return False

def _track_creator(creator: str, symbol: str, pct_change: float, graduated: bool):
    """Track creator wallet performance for reputation scoring."""
    if not creator or len(creator) < 20: return
    if creator not in STATE.creator_stats:
        STATE.creator_stats[creator] = {"launches": 0, "wins": 0, "rugs": 0, "avg_peak": 0}
    cs = STATE.creator_stats[creator]
    cs["launches"] += 1
    if pct_change > 10: cs["wins"] += 1
    if pct_change < -80: cs["rugs"] += 1
    cs["avg_peak"] = (cs["avg_peak"] * (cs["launches"] - 1) + max(0, pct_change)) / cs["launches"]

def _creator_score(creator: str) -> int:
    """Score a creator 0-100 based on track record."""
    cs = STATE.creator_stats.get(creator)
    if not cs or cs["launches"] < 2: return 50  # unknown = neutral
    trust = cs["wins"] / cs["launches"] * 100 if cs["launches"] > 0 else 0
    rug_penalty = cs["rugs"] * 20
    return max(0, min(100, int(trust - rug_penalty)))

# ── Groq AI Decision Functions ────────────────────────────────────────────────

async def ai_should_enter(token_data: dict) -> dict:
    """Ask Groq whether to enter a SCALP position. Returns {action, amount_sol, confidence, reason}."""
    if not GROQ_API_KEY or not AI_DECISION_ENGINE or not AI_ENTRY_ENABLED:
        return {"action": "FALLBACK", "amount_sol": SCALP_ENTRY_SOL, "confidence": 50, "reason": "AI disabled"}
    if STATE.ai_calls_today >= AI_MAX_CALLS_DAY:
        STATE.ai_status = "LIMIT"
        return {"action": "FALLBACK", "amount_sol": SCALP_ENTRY_SOL, "confidence": 50, "reason": "daily limit"}

    try:
        from groq import Groq
        import json as _j
        client = Groq(api_key=GROQ_API_KEY)
        t0 = time.monotonic()

        w = STATE.total_wins; l = STATE.total_losses
        wr = w / (w + l) * 100 if w + l else 0
        open_count = sum(1 for p in STATE.sim_positions.values() if p.status == "OPEN")

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=150,
            messages=[
                {"role": "system", "content": "Solana token scalp trader. Sim mode. Respond JSON only: {\"action\":\"BUY\"|\"SKIP\",\"amount_sol\":0.5-2.0,\"confidence\":0-100,\"reason\":\"one sentence\"}. Default 1.0 SOL. Only BUY tokens with confirmed upward momentum. SKIP flat tokens, falling prices, heat<55. Be selective."},
                {"role": "user", "content": f"Token:{token_data.get('symbol','?')} heat:{token_data.get('heat',0):.0f} price_dir:{token_data.get('price_direction','?')} momentum:{token_data.get('price_momentum',0):+.2f}%/tick consec_up:{token_data.get('consecutive_up',0)} chg5m:{token_data.get('chg_m5',0):+.1f}% vol:${token_data.get('vol',0):.0f} liq:${token_data.get('liq',0):.0f} buys:{token_data.get('buys',0)} sells:{token_data.get('sells',0)} market:{STATE.market_state} open:{open_count} pnl:{STATE.total_pnl_sol:+.3f}SOL wr:{wr:.0f}%"}
            ]
        )
        latency = (time.monotonic() - t0) * 1000
        STATE.ai_last_latency = latency
        STATE.ai_calls_today += 1
        STATE.ai_status = "OK"

        result = _j.loads(response.choices[0].message.content)
        result["amount_sol"] = max(0.5, min(2.0, float(result.get("amount_sol", 1.0))))

        # Log decision
        try:
            with open(AI_LOG_CSV, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    token_data.get("symbol", "?"), "ENTRY",
                    result.get("action"), f"{result['amount_sol']:.3f}",
                    result.get("confidence", 0), result.get("reason", ""),
                    f"{latency:.0f}"])
        except: pass

        _dbg(f"AI_ENTER: {token_data.get('symbol','?')} → {result.get('action')} "
             f"${result['amount_sol']:.3f} conf={result.get('confidence',0)} "
             f"({latency:.0f}ms) {result.get('reason','')}")
        return result
    except Exception as e:
        STATE.ai_status = "FAIL"
        _dbg(f"AI entry error: {type(e).__name__}: {e}")
        return {"action": "FALLBACK", "amount_sol": SCALP_ENTRY_SOL, "confidence": 50, "reason": str(e)[:50]}


async def ai_should_exit(position_data: dict) -> dict:
    """Ask Groq whether to exit a SCALP position. Returns {action, confidence, reason}."""
    if not GROQ_API_KEY or not AI_DECISION_ENGINE or not AI_EXIT_ENABLED:
        return {"action": "FALLBACK", "confidence": 50, "reason": "AI disabled"}
    if STATE.ai_calls_today >= AI_MAX_CALLS_DAY:
        return {"action": "FALLBACK", "confidence": 50, "reason": "daily limit"}

    try:
        from groq import Groq
        import json as _j
        client = Groq(api_key=GROQ_API_KEY)
        t0 = time.monotonic()

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=100,
            messages=[
                {"role": "system", "content": "Solana token exit advisor. Respond JSON: {\"action\":\"HOLD\"|\"SELL_HALF\"|\"SELL_ALL\",\"confidence\":0-100,\"reason\":\"one sentence\"}. You receive ATR (avg % move per tick) — this measures the token's volatility. Low ATR (<2%) = slow mover, tighter exits. High ATR (>8%) = wild swings, give more room. MOMENTUM RULES: If UP and accelerating: HOLD. If UP→DOWN flip: SELL_ALL or SELL_HALF. If DOWN 3+ ticks: SELL_ALL. If FLAT 30s: SELL_ALL. Winners show fast (avg 107s). PROFIT RULES: take profit if up 0.3%+ and heat dropping. Sell half if up 0.5%+ with strong heat. Cut losses if heat under 30."},
                {"role": "user", "content": f"Token:{position_data.get('symbol','?')} pnl:{position_data.get('pnl_pct',0):+.1f}% peak:{position_data.get('peak_pct',0):.1f}% heat:{position_data.get('heat',0):.0f} atr:{position_data.get('atr',5.0):.1f}%/tick price_dir:{position_data.get('price_direction','FLAT')} momentum:{position_data.get('price_momentum',0):+.2f}%/tick consec_up:{position_data.get('consecutive_up',0)} consec_down:{position_data.get('consecutive_down',0)} accel:{position_data.get('accelerating',False)} held:{position_data.get('hold_sec',0):.0f}s size:{position_data.get('entry_sol',0):.3f}SOL market:{STATE.market_state}"}
            ]
        )
        latency = (time.monotonic() - t0) * 1000
        STATE.ai_last_latency = latency
        STATE.ai_calls_today += 1

        result = _j.loads(response.choices[0].message.content)

        try:
            with open(AI_LOG_CSV, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    position_data.get("symbol", "?"), "EXIT",
                    result.get("action"), "",
                    result.get("confidence", 0), result.get("reason", ""),
                    f"{latency:.0f}"])
        except: pass

        _dbg(f"AI_EXIT: {position_data.get('symbol','?')} → {result.get('action')} "
             f"conf={result.get('confidence',0)} ({latency:.0f}ms)")
        return result
    except Exception as e:
        _dbg(f"AI exit error: {type(e).__name__}: {e}")
        return {"action": "FALLBACK", "confidence": 50, "reason": str(e)[:50]}


def _cap_position_size(entry_sol: float) -> float:
    """Apply adaptive size multiplier. Sim mode: cap at 3 SOL."""
    sized = entry_sol * STATE.adaptive_size_mult
    return min(sized, 3.0)

def update_market_state():
    """Classify market as HOT/WARM/SLOW/DEAD and adjust thresholds.
    Called every 5 minutes from update_sim_positions."""
    # Calculate metrics
    avg_vel = sum(STATE.recent_velocities) / len(STATE.recent_velocities) if STATE.recent_velocities else 0
    avg_score = sum(STATE.recent_scores) / len(STATE.recent_scores) if STATE.recent_scores else 0
    tpm = STATE.tokens_per_min

    # Rolling 20-trade win rate
    recent_closed = list(STATE.sim_closed)[:20]
    if len(recent_closed) >= 5:
        wins = sum(1 for p in recent_closed if p.profit_sol > 0)
        new_wr = wins / len(recent_closed) * 100
        old_wr = STATE.rolling_win_rate
        STATE.rolling_win_rate = new_wr
        STATE.wr_trend = "↑" if new_wr > old_wr + 2 else "↓" if new_wr < old_wr - 2 else "→"

    # Classify market state
    if tpm >= 3 and avg_vel >= 5:
        state = "HOT"
    elif tpm >= 1.5 or avg_vel >= 2:
        state = "WARM"
    elif tpm >= 0.5:
        state = "SLOW"
    else:
        state = "DEAD"

    old_state = STATE.market_state
    STATE.market_state = state

    # Set adaptive thresholds (floors raised: score<90 = 0% WR in 15 trades)
    if state == "HOT":
        STATE.adaptive_score = 95
        STATE.adaptive_mom = 2.0
        STATE.adaptive_bc = 10.0
        STATE.adaptive_size_mult = 1.0
    elif state == "WARM":
        STATE.adaptive_score = 90       # was 88 — score 80-89 is dead weight
        STATE.adaptive_mom = 1.0
        STATE.adaptive_bc = 5.0
        STATE.adaptive_size_mult = 1.0
    elif state == "SLOW":
        STATE.adaptive_score = 90       # was 80 — never go below 90
        STATE.adaptive_mom = 0.5
        STATE.adaptive_bc = 0.0
        STATE.adaptive_size_mult = 0.5
    else:  # DEAD
        STATE.adaptive_score = 90       # was 75 — even in dead markets, sub-90 never wins
        STATE.adaptive_mom = 0.1
        STATE.adaptive_bc = 0.0
        STATE.adaptive_size_mult = 0.25

    # Win rate adjustment (floor=90: sub-90 scores have 0% WR empirically)
    if STATE.rolling_win_rate > 40 and len(recent_closed) >= 10:
        STATE.adaptive_score = max(90, STATE.adaptive_score - 10)
    elif STATE.rolling_win_rate < 20 and len(recent_closed) >= 10:
        STATE.adaptive_score = min(120, STATE.adaptive_score + 20)

    if state != old_state:
        _dbg(f"MARKET_STATE: {old_state} -> {state} | vel={avg_vel:.1f} "
             f"tpm={tpm:.1f} sc={STATE.adaptive_score} mom={STATE.adaptive_mom}%")
        STATE.recent_activity.append(f"Market: {state} SC:{STATE.adaptive_score} MOM:{STATE.adaptive_mom}%")


def calc_heat_score(p) -> tuple:
    """Calculate heat score from price history and BC velocity.
    Returns (heat_score, pattern_name).
    Heat = buy_ratio(40%) + volume_accel(30%) + price_momentum(20%) + consec_buys(10%)"""
    now = time.monotonic()
    ph = p.price_history
    vh = p.sol_volume_history

    # Not enough data yet
    if len(ph) < 3:
        return 0.0, ""

    # Price momentum: (last - first) / first over available history
    first_price = ph[0][1]
    last_price = ph[-1][1]
    price_mom = ((last_price - first_price) / first_price * 100) if first_price > 0 else 0

    # Volume acceleration: compare last half vs first half of volume history
    if len(vh) >= 4:
        mid = len(vh) // 2
        first_half_vol = sum(abs(v[1]) for v in vh[:mid]) or 0.001
        second_half_vol = sum(abs(v[1]) for v in vh[mid:]) or 0.001
        vol_accel = second_half_vol / first_half_vol
    else:
        vol_accel = 1.0

    # Buy ratio: positive price changes = buys, negative = sells
    buys = 0; sells = 0
    for i in range(1, len(ph)):
        if ph[i][1] > ph[i-1][1]:
            buys += 1
        elif ph[i][1] < ph[i-1][1]:
            sells += 1
    total = buys + sells
    buy_ratio = buys / total if total > 0 else 0.5

    # Consecutive buys (longest streak of price increases)
    consec = 0; max_consec = 0
    for i in range(1, len(ph)):
        if ph[i][1] >= ph[i-1][1]:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0

    # BC velocity as additional signal
    bc_vel_bonus = min(10, max(0, p.bc_velocity)) if p.bc_velocity > 0 else 0

    # Composite heat score
    heat = (
        buy_ratio * 40 +
        min(vol_accel, 5.0) / 5.0 * 30 +  # cap at 5x acceleration
        min(max(price_mom, 0), 10) / 10 * 20 +  # cap at 10% momentum
        min(max_consec, 5) / 5 * 10 +  # cap at 5 consecutive
        bc_vel_bonus
    )
    heat = min(100, max(0, heat))

    # Pattern classification
    if buy_ratio < 0.3:
        pattern = "DUMP"
    elif heat >= 80:
        pattern = "ROCKET"
    elif heat >= 60:
        pattern = "HEATING"
    elif heat >= 40:
        pattern = "WARM"
    else:
        pattern = "COLD"

    return heat, pattern


def calc_position_atr(p) -> float:
    """Calculate Average True Range from position's price history.
    Returns the average absolute % move per tick for this specific token."""
    if len(p.price_history) < 3:
        return 5.0  # default 5% if not enough data
    moves = []
    for i in range(1, len(p.price_history)):
        prev_price = p.price_history[i - 1][1]
        curr_price = p.price_history[i][1]
        if prev_price > 0:
            moves.append(abs((curr_price - prev_price) / prev_price * 100))
    if not moves:
        return 5.0
    return max(0.5, min(sum(moves) / len(moves), 50.0))


def calc_adaptive_trail(p, atr: float) -> float:
    """Calculate how much of peak to keep, adaptive to this token's volatility.
    Returns a multiplier (0.30–0.85) where 0.70 = keep 70% of peak gains.
    Low volatility → tight trail (keep more). High volatility → wide trail (give room)."""
    # Base trail from ATR
    if atr < 1.0:
        base_keep = 0.75   # very slow mover — tight
    elif atr < 3.0:
        base_keep = 0.65   # normal volatility
    elif atr < 8.0:
        base_keep = 0.55   # high volatility (new meme)
    elif atr < 15.0:
        base_keep = 0.45   # very high (viral meme, whale pump)
    else:
        base_keep = 0.35   # extreme (>15%/tick)

    # Momentum direction adjustment
    if p.price_direction == "UP" and p.consecutive_up >= 2:
        base_keep -= 0.05  # still rising — give room
    elif p.price_direction == "DOWN" and p.consecutive_down >= 3:
        base_keep += 0.10  # confirmed drop — tighten

    # Heat adjustment
    if p.heat_score >= 70:
        base_keep -= 0.05  # strong buying — let it run
    elif p.heat_score <= 30:
        base_keep += 0.10  # dump — protect gains

    # Hold time adjustment (longer = tighter)
    hold_sec = time.monotonic() - p.entry_time
    if hold_sec > 120:
        base_keep += 0.05
    if hold_sec > 300:
        base_keep += 0.05

    # Strategy adjustment
    if p.strategy == "GRAD_SNIPE":
        base_keep += 0.05  # graduated tokens more predictable
    elif p.strategy == "SCALP":
        base_keep += 0.10  # scalps should be tight
    elif p.strategy == "MOMENTUM":
        base_keep += 0.05  # moderate trailing for established tokens

    return max(0.30, min(base_keep, 0.85))


def update_price_momentum(p):
    """Calculate price momentum from price_history. Call after every price update.
    Uses the last 5 price readings to determine direction, speed, and acceleration."""
    ph = p.price_history  # [(monotonic_time, price)]
    if len(ph) < 3:
        p.price_momentum = 0.0
        p.price_direction = "FLAT"
        p.consecutive_up = 0
        p.consecutive_down = 0
        return

    # Use last 5 readings max
    recent = ph[-5:]
    prices = [pt[1] for pt in recent]

    # Per-tick % changes
    changes = []
    for i in range(1, len(prices)):
        if prices[i - 1] > 0:
            changes.append((prices[i] - prices[i - 1]) / prices[i - 1] * 100)

    if not changes:
        return

    # Average momentum (% per tick)
    p.price_momentum = sum(changes) / len(changes)

    # Direction (0.05% threshold to filter noise)
    old_dir = p.price_direction
    if p.price_momentum > 0.05:
        p.price_direction = "UP"
    elif p.price_momentum < -0.05:
        p.price_direction = "DOWN"
    else:
        p.price_direction = "FLAT"

    # Track previous direction for reversal detection
    if old_dir != p.price_direction and old_dir != "FLAT":
        p.prev_direction = old_dir

    # Acceleration: is the most recent change stronger than the one before?
    if len(changes) >= 2:
        p.price_accelerating = abs(changes[-1]) > abs(changes[-2]) and \
                               (changes[-1] > 0) == (changes[-2] > 0)
    else:
        p.price_accelerating = False

    # Consecutive up/down ticks (count from most recent backwards)
    p.consecutive_up = 0
    p.consecutive_down = 0
    for c in reversed(changes):
        if c > 0:
            p.consecutive_up += 1
        else:
            break
    for c in reversed(changes):
        if c < 0:
            p.consecutive_down += 1
        else:
            break


# ── Latency helpers ───────────────────────────────────────────────────────────
_t = time.perf_counter_ns  # nanosecond precision timer

def _ms_since(ns_start: int) -> float:
    """Milliseconds elapsed since ns_start (from _t())."""
    return (time.perf_counter_ns() - ns_start) / 1_000_000

def log_perf(mint, symbol, detect_ms, rugcheck_ms, safety_ms, open_ms, total_ms, source):
    try:
        with open(PERF_LOG_CSV, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:23],
                mint, symbol, f"{detect_ms:.1f}", f"{rugcheck_ms:.1f}",
                f"{safety_ms:.1f}", f"{open_ms:.1f}", f"{total_ms:.1f}", source])
    except: pass


# ── RPC helpers (parallel submission, connection pooling) ─────────────────────
async def rpc_call(session, method, params=None):
    try:
        async with session.post(HELIUS_RPC_URL, json={
            "jsonrpc":"2.0","id":1,"method":method,"params":params or[]}) as r:
            return (await r.json(content_type=None)).get("result")
    except Exception as e: _dbg(f"RPC {method}: {e}"); return None

async def rpc_batch(session, calls):
    if not calls: return []
    batch = [{"jsonrpc":"2.0","id":i,"method":c["method"],
              "params":c.get("params",[])} for i,c in enumerate(calls)]
    try:
        async with session.post(HELIUS_RPC_URL, json=batch) as r:
            data = await r.json(content_type=None)
        if isinstance(data, list):
            data.sort(key=lambda x: x.get("id",0))
            return [x.get("result") for x in data]
        return [None]*len(calls)
    except: return [None]*len(calls)


async def rpc_call_to(session, url, method, params=None):
    """RPC call to a specific endpoint URL."""
    try:
        async with session.post(url, json={
            "jsonrpc":"2.0","id":1,"method":method,"params":params or[]}) as r:
            return (await r.json(content_type=None)).get("result")
    except: return None


async def parallel_rpc_call(session, method, params=None):
    """Submit same RPC call to all endpoints in parallel. First result wins."""
    if len(RPC_ENDPOINTS) <= 1:
        return await rpc_call(session, method, params)
    tasks = [rpc_call_to(session, url, method, params) for url in RPC_ENDPOINTS]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    for t in done:
        result = t.result()
        if result is not None:
            return result
    return None


async def parallel_submit_tx(session, signed_tx_b64: str) -> Optional[str]:
    """Submit a signed transaction to all RPC endpoints in parallel.
    Returns first confirmed signature."""
    params = [signed_tx_b64, {"encoding": "base64", "skipPreflight": True,
                               "preflightCommitment": "processed",
                               "maxRetries": 3}]
    tasks = [rpc_call_to(session, url, "sendTransaction", params)
             for url in RPC_ENDPOINTS]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending: t.cancel()
    for t in done:
        result = t.result()
        if result: return result
    return None


# ── Connection pool factory ───────────────────────────────────────────────────
def create_pooled_session() -> aiohttp.ClientSession:
    """Create aiohttp session with persistent connection pooling.
    Pre-connects to all API endpoints. No new connections during trading."""
    conn = aiohttp.TCPConnector(
        limit=100,              # max simultaneous connections
        limit_per_host=30,      # per-host connection limit
        keepalive_timeout=300,  # 5 min keep-alive
        enable_cleanup_closed=True,
        force_close=False,      # reuse connections
    )
    timeout = aiohttp.ClientTimeout(total=15, connect=5)
    return aiohttp.ClientSession(connector=conn, timeout=timeout)


# ── Pre-warmed transaction pool ───────────────────────────────────────────────
class TxPool:
    """Pre-build buy transaction templates at startup.
    When a token is detected, just fill in the mint address and submit."""
    def __init__(self):
        self.templates: list[dict] = []
        self.ready = False

    def warm(self):
        """Pre-build 10 buy transaction templates."""
        if not EXECUTE_TRADES or not PRIVATE_KEY or PRIVATE_KEY == "YOUR_PRIVATE_KEY":
            return
        try:
            from solders.pubkey import Pubkey
            from solders.keypair import Keypair

            for i in range(10):
                self.templates.append({
                    "ix_discriminator": PUMP_IX_BUY,
                    "sol_amount": int(TRADE_SIZE_SOL * LAMPORTS_PER_SOL),
                    "slippage_bps": SLIPPAGE_BPS,
                    "jito_tip": JITO_TIP_LAMPORTS,
                    "compute_units": 70_000,      # tight CU limit (from 1fge)
                    "priority_fee": 200_000,       # micro-lamports (from 1fge)
                    "index": i,
                })
            self.ready = True
            _dbg(f"TxPool: {len(self.templates)} templates warmed")
        except Exception as e:
            _dbg(f"TxPool warm error: {e}")

    def get_template(self) -> Optional[dict]:
        """Pop a pre-warmed template. Returns None if empty."""
        if self.templates:
            return self.templates.pop(0)
        return None

    def fill_and_submit(self, template: dict, mint: str) -> dict:
        """Fill in the mint address for a pre-warmed template.
        Returns instruction data ready for transaction building."""
        template["mint"] = mint
        template["filled_at"] = time.perf_counter_ns()
        return template

TX_POOL = TxPool()


# ── Memory-cached wallet sets ─────────────────────────────────────────────────
def _load_wallet_sets():
    """Pre-load successful and rug wallets into memory for O(1) lookup."""
    # Successful wallets
    data = _load_json(WALLETS_JSON)
    STATE.known_good_wallets = set(data.keys())
    _dbg(f"Loaded {len(STATE.known_good_wallets)} good wallets into memory")

    # Build rug wallet set from closed positions with negative P&L
    patterns = _load_json(PATTERNS_JSON)
    rug_wallets = set()
    for pos in patterns.get("closed_positions", []):
        if pos.get("exit_reason", "").startswith(("STOP_LOSS", "DEV_DUMP")):
            # These are rug patterns — we'd need creator wallet which we don't
            # always have in pattern data. Just count what we can.
            pass
    STATE.known_rug_wallets = rug_wallets
    _dbg(f"Loaded {len(STATE.known_rug_wallets)} rug wallets into memory")


# ── On-chain data (pure RPC — no web APIs for pump.fun) ──────────────────────

async def fetch_asset_metadata(session, mint: str) -> dict:
    """Fetch token metadata via Helius DAS getAsset.
    Returns {name, symbol, description, creator, links...} or {}."""
    try:
        result = await rpc_call(session, "getAsset", {"id": mint})
        if not result:
            return {}
        content   = result.get("content", {})
        meta      = content.get("metadata", {})
        links     = content.get("links", {})
        authority = result.get("authorities", [])
        creators  = result.get("creators", [])
        creator   = creators[0].get("address", "") if creators else ""
        if not creator and authority:
            creator = authority[0].get("address", "")
        return {
            "name":     meta.get("name", ""),
            "symbol":   meta.get("symbol", ""),
            "description": meta.get("description", ""),
            "image":    links.get("image", ""),
            "twitter":  "",   # DAS doesn't carry socials — will be empty
            "telegram": "",
            "website":  links.get("external_url", ""),
            "creator":  creator,
        }
    except Exception as e:
        _dbg(f"getAsset error {mint[:12]}: {e}")
        return {}


async def fetch_pump_coin(session, mint: str) -> Optional[dict]:
    """Build a coin dict entirely from on-chain RPC data.
    Combines bonding curve account data + Helius DAS metadata.
    Returns a dict compatible with all existing callers, or None."""
    # Fetch bonding curve and metadata in parallel
    bc_task   = fetch_bc_direct(session, mint)
    meta_task = fetch_asset_metadata(session, mint)
    bc, meta  = await asyncio.gather(bc_task, meta_task)

    if not bc:
        return None  # no bonding curve = not a pump.fun token

    # Build the coin dict that all callers expect
    vsolr = bc.get("virtualSolReserves", 0)
    vtokr = bc.get("virtualTokenReserves", 0)
    rtr   = bc.get("realTokenReserves", 0)
    rsr   = bc.get("realSolReserves", 0)
    supply = bc.get("tokenTotalSupply", PUMP_TOKEN_TOTAL_SUPPLY)
    creator_bytes = bc.get("creator", b"")

    # Derive creator pubkey from bonding curve data
    creator = ""
    if isinstance(creator_bytes, bytes) and len(creator_bytes) == 32:
        try:
            from solders.pubkey import Pubkey
            creator = str(Pubkey.from_bytes(creator_bytes))
        except:
            pass
    if not creator and meta:
        creator = meta.get("creator", "")

    # Estimate market cap: price_per_token * total_supply_in_tokens
    price_sol = (vsolr / LAMPORTS_PER_SOL) / (vtokr / 1e6) if vtokr else 0.0
    mc_usd = price_sol * (supply / 1e6) * STATE.sol_price_usd if price_sol else 0.0

    return {
        "mint":                    mint,
        "symbol":                  meta.get("symbol", "") or f"T_{mint[2:7]}",
        "name":                    meta.get("name", "") or meta.get("symbol", ""),
        "description":             meta.get("description", ""),
        "creator":                 creator,
        "virtual_sol_reserves":    vsolr,
        "virtual_token_reserves":  vtokr,
        "real_token_reserves":     rtr,
        "real_sol_reserves":       rsr,
        "total_supply":            supply,
        "twitter":                 meta.get("twitter", ""),
        "telegram":                meta.get("telegram", ""),
        "website":                 meta.get("website", ""),
        "usd_market_cap":          mc_usd,
        "created_timestamp":       int(time.time() * 1000),  # approximate — we just found it
        "raydium_pool":            bc.get("complete", False),  # graduated = has raydium pool
        "complete":                bc.get("complete", False),
    }


async def fetch_pump_holders(session, mint: str) -> list:
    """Approximate holder data from bonding curve reserves.
    Real holder enumeration would require getProgramAccounts (expensive).
    We return a synthetic list for compatibility with safety checks."""
    bc = await fetch_bc_direct(session, mint)
    if not bc:
        return []
    # The bonding curve itself holds the majority of tokens initially.
    # As tokens are bought, realTokenReserves decreases.
    rtr = bc.get("realTokenReserves", PUMP_INITIAL_REAL_TOKEN_RESERVES)
    supply = bc.get("tokenTotalSupply", PUMP_TOKEN_TOTAL_SUPPLY)
    if supply <= 0:
        return []
    # BC holds = rtr / supply, the rest is distributed to buyers
    bc_pct = (rtr / supply) * 100
    buyer_pct = 100 - bc_pct
    # Return synthetic holder list — top "holder" is the aggregate of all buyers
    return [{"percentage": buyer_pct, "address": "aggregate_buyers"}]


async def fetch_pump_trades(session, mint: str, limit: int = 50) -> list:
    """Fetch recent transaction signatures for the bonding curve PDA.
    Returns a list of signature info dicts (not full trade details)."""
    try:
        from solders.pubkey import Pubkey
        bc_pda, _ = Pubkey.find_program_address(
            [b"bonding-curve", bytes(Pubkey.from_string(mint))],
            Pubkey.from_string(PUMP_PROGRAM_ID))
        result = await rpc_call(session, "getSignaturesForAddress", [
            str(bc_pda),
            {"limit": limit, "commitment": "confirmed"},
        ])
        if result and isinstance(result, list):
            # Convert to format compatible with existing callers
            # Callers check t.get("user"), t.get("is_buy"), t.get("token_amount")
            # We can't determine buy/sell from signatures alone — return empty
            # This disables dev-sell detection from trades, but BC creator check
            # in safety scoring still works via getAsset
            return []
        return []
    except:
        return []


async def fetch_sol_price(session):
    try:
        async with session.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
            timeout=aiohttp.ClientTimeout(total=10)) as r:
            return float((await r.json(content_type=None)).get("solana",{}).get("usd",0))
    except: return STATE.sol_price_usd or 0.0


# ══════════════════════════════════════════════════════════════════════════════
# ██  RUGCHECK.XYZ API  ████████████████████████████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════

async def fetch_rugcheck(session, mint: str) -> dict:
    """Query RugCheck.xyz for token risk report."""
    try:
        url = f"{RUGCHECK_API}/{mint}/report"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as r:
            if r.status == 200:
                return await r.json(content_type=None)
            return {}
    except Exception as e:
        _dbg(f"RugCheck error {mint[:8]}: {e}")
        return {}

def parse_rugcheck(report: dict) -> tuple[str, list[str]]:
    """Parse RugCheck report into (status, warnings).
    status: 'Good', 'Warn', 'Danger', or '' if unavailable."""
    if not report:
        return "", []
    # RugCheck returns risks array and overall score
    risks = report.get("risks", [])
    warnings = [r.get("name", "") for r in risks if r.get("name")]
    score = report.get("score", 0)
    # score >= 700 = Good, 400-699 = Warn, <400 = Danger (approximate)
    if score >= 700: return "Good", warnings
    if score >= 400: return "Warn", warnings
    if score > 0:   return "Danger", warnings
    # Fallback: check if any risk is marked critical
    for r in risks:
        if r.get("level") in ("critical", "danger", "high"):
            return "Danger", warnings
    return "Warn" if risks else "", warnings


# ══════════════════════════════════════════════════════════════════════════════
# ██  BONDING CURVE  ███████████████████████████████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════

def calc_bc_progress(coin: dict) -> float:
    """Calculate bonding curve completion percentage (0-100).
    Correct formula from nirholas/pump-fun-sdk:
    progress = 1 - (realTokenReserves / INITIAL_REAL_TOKEN_RESERVES)
    When realTokenReserves reaches 0, curve is 100% complete."""
    # Try realTokenReserves first (accurate formula from pump-fun-sdk)
    rtr = _safe_int(coin.get("real_token_reserves", 0))
    if rtr > 0:
        progress = (1.0 - rtr / PUMP_INITIAL_REAL_TOKEN_RESERVES) * 100.0
        return min(100.0, max(0.0, progress))
    # Fallback to virtual_sol_reserves approximation
    vsolr = _safe_int(coin.get("virtual_sol_reserves", 0))
    sol = vsolr / LAMPORTS_PER_SOL if vsolr else 0.0
    if sol <= 30.0: return 0.0
    return min(100.0, (sol - 30.0) / (PUMP_GRADUATION_SOL - 30.0) * 100.0)


def parse_bc_account_data(data: bytes) -> Optional[dict]:
    """Parse raw bonding curve account data flexibly — handles old (151 bytes)
    and new formats (pump.fun added volume accumulators, v2, cashback fields).
    Uses slice notation so extra trailing bytes are ignored."""
    if not data or len(data) < BC_SIZE:
        return None
    try:
        # Handle variable response formats (base64 list, string, or raw bytes)
        if isinstance(data, (list, tuple)) and len(data) >= 2:
            data = base64.b64decode(data[0])
        elif isinstance(data, str):
            data = base64.b64decode(data)
        # Now data is bytes — read only the fields we need via slicing
        return {
            "virtualTokenReserves": int.from_bytes(data[8:16], "little"),
            "virtualSolReserves":   int.from_bytes(data[16:24], "little"),
            "realTokenReserves":    int.from_bytes(data[24:32], "little"),
            "realSolReserves":      int.from_bytes(data[32:40], "little"),
            "tokenTotalSupply":     int.from_bytes(data[40:48], "little"),
            "complete":             bool(data[48]),
            "creator":              data[49:81] if len(data) > 81 else b"",
            "isMayhemMode":         bool(data[81]) if len(data) > 81 else False,
        }
    except (ValueError, struct.error, IndexError, KeyError) as e:
        _dbg(f"BC parse error: {type(e).__name__}: {e} (data len={len(data)})")
        return None


async def fetch_bc_direct(session, mint: str) -> Optional[dict]:
    """Fetch bonding curve data directly from RPC with multi-endpoint failover.
    Tries all RPC endpoints, then falls back to DEXScreener for graduated tokens."""
    try:
        import base64
        from solders.pubkey import Pubkey
        bc_pda, _ = Pubkey.find_program_address(
            [b"bonding-curve", bytes(Pubkey.from_string(mint))],
            Pubkey.from_string(PUMP_PROGRAM_ID))
        params = [str(bc_pda), {"encoding": "base64", "commitment": "processed"}]

        # Try each RPC endpoint with 2s wait between retries
        for endpoint in RPC_ENDPOINTS:
            try:
                result = await rpc_call_to(session, endpoint, "getAccountInfo", params)
                if result and result.get("value"):
                    data_b64 = result["value"]["data"]
                    if isinstance(data_b64, list):
                        data_b64 = data_b64[0]
                    elif isinstance(data_b64, str):
                        pass  # already a string, decode below
                    elif isinstance(data_b64, bytes):
                        return parse_bc_account_data(data_b64)
                    raw = base64.b64decode(data_b64)
                    return parse_bc_account_data(raw)
            except (ValueError, struct.error) as e:
                _dbg(f"BC parse {mint[:8]} endpoint {endpoint[:30]}: {type(e).__name__}: {e}")
                # Parse error = data format changed, don't retry same bad data on other endpoints
                # Return a "complete" marker so caller knows to use DEXScreener
                return {"complete": True, "virtualSolReserves": 0, "virtualTokenReserves": 0,
                        "realTokenReserves": 0, "realSolReserves": 0, "tokenTotalSupply": 0,
                        "_parse_error": True}
            except Exception as e:
                _dbg(f"BC fetch {mint[:8]} endpoint {endpoint[:30]}: {e}")
            await asyncio.sleep(2)  # flat 2s between endpoint retries

        return None
    except Exception as e:
        _dbg(f"BC direct fetch {mint[:8]}: {e}")
        return None


def calc_bc_progress_from_raw(bc: dict) -> float:
    """Calculate progress from parsed bonding curve data."""
    if bc.get("complete"):
        return 100.0
    rtr = bc.get("realTokenReserves", PUMP_INITIAL_REAL_TOKEN_RESERVES)
    return min(100.0, max(0.0,
        (1.0 - rtr / PUMP_INITIAL_REAL_TOKEN_RESERVES) * 100.0))

def calc_bc_velocity(history: list) -> float:
    """Calculate bonding curve velocity in %/minute from history [(mono_time, pct)]."""
    if len(history) < 2: return 0.0
    recent = history[-1]
    # Find entry from ~60s ago
    target_t = recent[0] - 60.0
    prev = history[0]
    for h in history:
        if h[0] <= target_t:
            prev = h
        else:
            break
    dt = recent[0] - prev[0]
    if dt < 5: return 0.0  # need at least 5s of data
    dpct = recent[1] - prev[1]
    return dpct / (dt / 60.0)  # %/minute


# ══════════════════════════════════════════════════════════════════════════════
# ██  NARRATIVE / META DETECTION  ██████████████████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════

def score_narrative(name: str, description: str) -> int:
    """Score token name + description against trending metas."""
    text = (name + " " + description).lower()
    words = set(re.findall(r'[a-z]+', text))
    s = 0
    if words & _NARRATIVE_AI:      s += 25
    if words & _NARRATIVE_POLITIC: s += 20
    if words & _NARRATIVE_ANIMAL:  s += 20
    if words & _NARRATIVE_CELEB:   s += 15
    if words & _NARRATIVE_ABSURD:  s += 10
    if words & _NARRATIVE_GENERIC: s -= 10
    return s


# ══════════════════════════════════════════════════════════════════════════════
# ██  TIMING FILTER  ███████████████████████████████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════

def get_timing_score() -> tuple[int, str]:
    """Score based on current EST time window.
    Returns (score_adjustment, window_label)."""
    now_utc = datetime.now(timezone.utc)
    est = now_utc - timedelta(hours=5)
    h = est.hour
    if 12 <= h < 16:       return 10, "PEAK"       # 12PM-4PM EST
    if 8 <= h < 12:        return 5,  "ACTIVE"      # 8AM-12PM
    if 16 <= h < 20:       return 5,  "ACTIVE"      # 4PM-8PM
    if 20 <= h or h < 2:   return 0,  "DEGEN"       # 8PM-2AM
    return -10, "LOW"                                  # 2AM-8AM (dead hours)


# ══════════════════════════════════════════════════════════════════════════════
# ██  AUTHORITY & BUNDLE CHECKS  ███████████████████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════

async def check_mint_freeze_authority(session, mint: str) -> tuple[bool, bool]:
    """Check if mint and freeze authorities are revoked via getAccountInfo.
    Returns (mint_revoked, freeze_revoked)."""
    try:
        result = await rpc_call(session, "getAccountInfo", [
            mint, {"encoding": "jsonParsed"}
        ])
        if not result or not result.get("value"):
            return False, False
        parsed = result["value"].get("data", {}).get("parsed", {})
        info = parsed.get("info", {})
        mint_auth   = info.get("mintAuthority")
        freeze_auth = info.get("freezeAuthority")
        return (mint_auth is None, freeze_auth is None)
    except Exception as e:
        _dbg(f"Auth check error {mint[:8]}: {e}")
        return False, False


def detect_bundle(trades: list) -> bool:
    """Detect if launch was bundled: multiple buys in the same slot."""
    if not trades: return False
    # Get the earliest trades (last in the list since sorted desc)
    early = trades[-min(20, len(trades)):]
    slot_counts: dict = defaultdict(int)
    for t in early:
        if t.get("is_buy") is True:
            slot = t.get("slot", 0)
            if slot: slot_counts[slot] += 1
    # If any single slot has 3+ buys, it's bundled
    return any(c >= BUNDLE_SAME_BLOCK_BUYS for c in slot_counts.values())


def detect_bot_cluster(trades: list) -> bool:
    """If >60% of early trades are from same wallet cluster, skip."""
    if not trades or len(trades) < 5: return False
    early = trades[-min(30, len(trades)):]
    buy_wallets = [t.get("user", "") for t in early if t.get("is_buy") is True]
    if len(buy_wallets) < 3: return False
    wallet_counts = defaultdict(int)
    for w in buy_wallets: wallet_counts[w] += 1
    top_wallet_count = max(wallet_counts.values()) if wallet_counts else 0
    return top_wallet_count / len(buy_wallets) >= BOT_CLUSTER_THRESHOLD


async def check_serial_deployer(session, creator: str) -> bool:
    """Check if creator has launched 10+ tokens (serial deployer)."""
    if not creator: return False
    try:
        result = await rpc_call(session, "getSignaturesForAddress", [
            creator, {"limit": 50, "commitment": "confirmed"}
        ])
        if not result: return False
        # Count transactions — serial deployers have many
        return len(result) >= 50  # rough proxy: 50+ recent txs
    except: return False


# ══════════════════════════════════════════════════════════════════════════════
# ██  SAFETY SCORING  ██████████████████████████████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════

def _calc_score(sc: SafetyCheck) -> int:
    s = 0
    # Authority checks (critical)
    if sc.mint_authority_revoked  is True: s += 20
    if sc.freeze_authority_revoked is True: s += 20
    # Standard checks
    if sc.has_social_links  is True: s += 15
    if sc.low_holder_conc   is True: s += 15
    if sc.dev_not_sold      is True: s += 15
    if sc.liquidity_over_10 is True: s += 15
    if sc.age_over_2min     is True: s += 10
    if sc.dev_holds_under_5 is True: s += 15
    if sc.bc_progress_fast  is True: s += 20
    if sc.holder_growth_organic is True: s += 15
    # Penalties
    if sc.not_bundled is False: s -= 40          # bundled = insider holds
    if sc.rugcheck_status == "Warn":   s -= 20
    if sc.rugcheck_status == "Danger": s -= 60   # near-skip territory
    # Narrative & timing
    s += sc.narrative_score
    s += sc.timing_score
    return max(0, min(200, s))  # cap at 200 for boosted tokens

def _categorize(score: int) -> str:
    if score >= 70: return "SAFE"
    if score >= 40: return "WATCH"
    return "RISKY"


async def run_safety_check(session, coin: dict) -> SafetyCheck:
    sc = SafetyCheck()
    mint = coin.get("mint", "")
    creator = coin.get("creator", "")

    # Social
    sc.twitter  = coin.get("twitter", "") or ""
    sc.telegram = coin.get("telegram", "") or ""
    sc.website  = coin.get("website", "") or ""
    sc.has_social_links = bool(sc.twitter or sc.telegram or sc.website)

    # Liquidity
    vsolr = _safe_int(coin.get("virtual_sol_reserves", 0))
    sc.liquidity_sol = vsolr / LAMPORTS_PER_SOL if vsolr else 0.0
    sc.liquidity_over_10 = sc.liquidity_sol >= 10.0

    # Market cap
    mc = coin.get("usd_market_cap", 0)
    try: sc.market_cap_usd = float(mc) if mc else 0.0
    except: sc.market_cap_usd = 0.0

    sc.description = (coin.get("description", "") or "")[:200]

    # Age
    created_ts = coin.get("created_timestamp")
    if created_ts:
        try:
            created = created_ts / 1000.0 if created_ts > 1e12 else float(created_ts)
            age = time.time() - created
            sc.age_over_2min = age >= 120
            sc.bc_progress_fast = (calc_bc_progress(coin) >= 50.0 and age <= 3600)
        except: pass

    # Narrative scoring
    name = coin.get("name", "") or coin.get("symbol", "") or ""
    sc.narrative_score = score_narrative(name, sc.description)

    # Timing
    sc.timing_score, _ = get_timing_score()

    # ── Parallel checks with 3s timeout each (was 10s+ bottleneck) ─────
    async def _timed(coro, default, label=""):
        try:
            return await asyncio.wait_for(coro, timeout=3.0)
        except asyncio.TimeoutError:
            _dbg(f"SAFETY_TIMEOUT: {label} for {mint[:12]}")
            return default
        except: return default

    async def _default_tuple(): return (False, False)
    async def _default_dict(): return {}
    async def _default_list(): return []
    async def _default_false(): return False

    if STATE.hft_enabled:
        # HFT mode: single DAS getAsset call — gets authorities + metadata in ~50ms
        mint_rev = False; freeze_rev = False
        rugcheck_report = {}; holders = []; trades = []; is_serial = False
        if mint:
            try:
                das = await _timed(rpc_call(session, "getAsset", {"id": mint}),
                                   None, "DAS")
                if das:
                    STATE.das_active = True
                    auths = das.get("authorities", [])
                    for a in auths:
                        scopes = a.get("scopes", [])
                        if "full" not in scopes:
                            mint_rev = True
                    freeze = das.get("ownership", {}).get("frozen", False)
                    freeze_rev = not freeze
                    # Extract creator from DAS
                    for a in auths:
                        if "full" in a.get("scopes", []):
                            creator = a.get("address", creator)
                            break
            except: pass
    else:
        auth_task   = _timed(check_mint_freeze_authority(session, mint), (False, False), "auth") if mint else _default_tuple()
        rug_task    = _timed(fetch_rugcheck(session, mint), {}, "rugcheck") if mint else _default_dict()
        holder_task = _timed(fetch_pump_holders(session, mint), [], "holders") if mint else _default_list()
        trades_task = _timed(fetch_pump_trades(session, mint, limit=50), [], "trades") if mint else _default_list()
        serial_task = _timed(check_serial_deployer(session, creator), False, "serial") if creator else _default_false()
        (mint_rev, freeze_rev), rugcheck_report, holders, trades, is_serial = \
            await asyncio.gather(auth_task, rug_task, holder_task, trades_task, serial_task)

    # Authority
    sc.mint_authority_revoked = mint_rev
    sc.freeze_authority_revoked = freeze_rev

    # RugCheck
    rc_status, rc_warnings = parse_rugcheck(rugcheck_report)
    sc.rugcheck_status = rc_status
    sc.rugcheck_ok = rc_status in ("Good", "")

    # Holders
    try:
        if holders and isinstance(holders, list) and len(holders) > 0:
            top = holders[0] if isinstance(holders[0], dict) else {}
            sc.top_holder_pct = float(top.get("percentage", 0))
            sc.low_holder_conc = sc.top_holder_pct < 50.0
            # Check holder diversity (organic growth proxy)
            if len(holders) >= 5:
                sc.holder_growth_organic = True
    except: pass

    # Trades — dev selling, bundle detection, bot cluster
    sc.dev_not_sold = True; sc.dev_sold_pct = 0.0
    if trades and isinstance(trades, list):
        total_supply = _safe_int(coin.get("total_supply", 0))
        if not total_supply: total_supply = 1_000_000_000_000_000

        # Dev selling
        if creator:
            dev_sold_amount = sum(
                _safe_int(t.get("token_amount", 0))
                for t in trades
                if t.get("user", "") == creator and t.get("is_buy") is False)
            if total_supply > 0:
                sc.dev_sold_pct = dev_sold_amount / total_supply
            sc.dev_not_sold = sc.dev_sold_pct < 0.01

            # Dev holdings
            dev_bought = sum(
                _safe_int(t.get("token_amount", 0))
                for t in trades
                if t.get("user", "") == creator and t.get("is_buy") is True)
            dev_net = dev_bought - (dev_sold_amount if dev_sold_amount else 0)
            if total_supply > 0:
                sc.dev_hold_pct = max(0, dev_net / total_supply)
            sc.dev_holds_under_5 = sc.dev_hold_pct < 0.05

        # Bundle detection
        sc.not_bundled = not detect_bundle(trades)

        # Bot cluster detection
        sc.bot_dominated = detect_bot_cluster(trades)

    # Serial deployer penalty (applied in scoring via pattern, not a field)
    # Just log it
    if is_serial:
        _dbg(f"Serial deployer detected: {creator[:8]}")

    sc.score    = _calc_score(sc)
    sc.category = _categorize(sc.score)
    return sc


# ── Price & P&L ───────────────────────────────────────────────────────────────
def calc_token_price_sol(coin):
    vsolr = _safe_int(coin.get("virtual_sol_reserves", 0))
    vtokr = _safe_int(coin.get("virtual_token_reserves", 0))
    if not vsolr or not vtokr: return 0.0
    return (vsolr / LAMPORTS_PER_SOL) / (vtokr / 1e6) if vtokr else 0.0

def calc_price_impact(trade_sol, liq_sol):
    if liq_sol <= 0:
        return 0.02  # default 2% impact when liquidity unknown (was 100%!)
    return min(0.10, trade_sol / (liq_sol + trade_sol))  # cap at 10%


def pump_buy_quote(sol_amount_lamports: int, vsolr: int, vtokr: int,
                    fee_bps: int = PUMP_FEE_BPS) -> int:
    """Exact pump.fun buy quote with fees (from nirholas/pump-fun-sdk).
    Returns tokens received after fees."""
    if not vsolr or not vtokr or sol_amount_lamports <= 0:
        return 0
    # Subtract fee from input
    input_amount = (sol_amount_lamports - 1) * 10000 // (fee_bps + 10000)
    # Constant product AMM
    tokens = input_amount * vtokr // (vsolr + input_amount)
    return tokens


def pump_sell_quote(token_amount: int, vsolr: int, vtokr: int,
                     fee_bps: int = PUMP_FEE_BPS) -> int:
    """Exact pump.fun sell quote with fees (from nirholas/pump-fun-sdk).
    Returns lamports received after fees."""
    if not vsolr or not vtokr or token_amount <= 0:
        return 0
    # Constant product AMM
    sol_cost = token_amount * vsolr // (vtokr + token_amount)
    # Subtract fees from output
    fee = (sol_cost * fee_bps + 9999) // 10000  # ceil division
    return max(0, sol_cost - fee)


def calc_sim_pnl(entry_price, exit_price, entry_sol, liq_sol):
    """P&L with realistic fee model based on actual 2026 Solana DEX costs.
    Liquid tokens via Jupiter/Raydium: 25 bps per side + ~2 bps slippage = ~55 bps round trip.
    Pump.fun bonding curve: 100 bps per side + AMM price impact."""
    if entry_price <= 0: return 0.0, 0.0
    tokens = entry_sol / entry_price
    if liq_sol >= 100:
        # Established tokens: Raydium 0.25% pool fee + negligible slippage
        fee_rate = 25  # 25 bps = 0.25% (Raydium standard)
        impact = 0.0001  # 0.01% — negligible for $100-200 trades on millions in liquidity
    else:
        # Pump.fun / low-liquidity: 1% fee + AMM price impact
        fee_rate = PUMP_FEE_BPS  # 100 bps = 1%
        impact = calc_price_impact(entry_sol, liq_sol)
    entry_cost = entry_sol * (fee_rate / 10000) + SOL_TX_FEE
    gross = tokens * exit_price
    exit_cost = gross * (fee_rate / 10000) + SOL_TX_FEE + gross * impact
    return gross - exit_cost - entry_sol - entry_cost, gross - exit_cost


# ── CSV logging ───────────────────────────────────────────────────────────────
def log_new_token_csv(mint, symbol, sc):
    try:
        social = ",".join(filter(None, [sc.twitter, sc.telegram, sc.website]))
        _, timing_label = get_timing_score()
        with open(NEW_TOKENS_CSV, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                mint, symbol, sc.score, sc.category,
                f"{sc.liquidity_sol:.2f}", f"{sc.market_cap_usd:.0f}",
                social, sc.description[:100],
                sc.rugcheck_status, sc.narrative_score, timing_label])
    except: pass

def log_snipe_csv(p: SimPosition):
    try:
        hs = (p.exit_time - p.entry_time) if p.exit_time else 0
        with open(SNIPE_LOG_CSV, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                SESSION_ID,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                p.mint, p.symbol, p.score, p.category,
                f"{p.entry_price_sol:.10f}", f"{p.exit_price_sol:.10f}",
                f"{p.profit_sol:.6f}", f"{p.profit_usd:.2f}",
                f"{hs:.0f}", p.exit_reason, p.had_social, p.dev_sold,
                f"{p.peak_price_sol:.10f}", f"{p.bc_progress:.1f}",
                p.rugcheck_status, p.strategy, p.pyramid_count,
                f"{p.heat_at_entry:.1f}", f"{p.heat_score:.1f}",
                f"{p.peak_pct:.1f}", p.price_source])
    except: pass

def _log_partial_exit(p, reason: str, sold_sol: float, profit_sol: float):
    try:
        hs = time.monotonic() - p.entry_time
        with open(SNIPE_LOG_CSV, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                SESSION_ID,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                p.mint, p.symbol, p.score, p.category,
                f"{p.entry_price_sol:.10f}", f"{p.current_price_sol:.10f}",
                f"{profit_sol:.6f}", f"{profit_sol * STATE.sol_price_usd:.2f}",
                f"{hs:.0f}", reason, p.had_social, p.dev_sold,
                f"{p.peak_price_sol:.10f}", f"{p.bc_progress:.1f}",
                p.rugcheck_status, p.strategy, p.pyramid_count])
    except: pass

def log_intel_csv(signal_type, search_term, token_name, ticker, mint,
                  tweet_id, author, followers, likes, rts, score, source):
    try:
        with open(INTELLIGENCE_CSV, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                signal_type, search_term, token_name, ticker, mint,
                tweet_id, author, followers, likes, rts, score, source])
    except: pass


def log_hft_csv(symbol, score, entry, exit_p, profit_sol, profit_usd, hold_sec, reason, strategy="HFT"):
    try:
        with open(HFT_LOG_CSV, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                SESSION_ID,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                symbol, score, f"{entry:.10f}", f"{exit_p:.10f}",
                f"{profit_sol:.6f}", f"{profit_usd:.2f}",
                f"{hold_sec:.0f}", reason, strategy])
    except: pass


def log_whale_csv(p: SimPosition):
    try:
        with open(WHALE_LOG_CSV, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                SESSION_ID, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                p.whale_wallet, p.mint, p.symbol, f"{p.whale_buy_sol:.4f}",
                f"{p.entry_price_sol:.10f}", f"{p.peak_price_sol:.10f}",
                f"{p.exit_price_sol:.10f}", f"{p.profit_sol:.6f}",
                f"{p.profit_usd:.2f}"])
    except: pass


# ── Web Dashboard data writer ─────────────────────────────────────────────────

def write_dashboard_data():
    """Write current bot state to dashboard_data.json for the web dashboard.
    Called every ~3 seconds from update_sim_positions."""
    try:
        now_m = time.monotonic()
        open_pos = [p for p in STATE.sim_positions.values() if p.status == "OPEN"]
        open_pnl = sum(p.profit_sol for p in open_pos)

        # Balance history (every 30s)
        if now_m - STATE._last_balance_log >= 30:
            STATE.balance_history.append({
                "time": datetime.now().strftime("%H:%M"),
                "balance": round(STATE.balance_sol, 4)
            })
            STATE.balance_history = STATE.balance_history[-500:]
            STATE._last_balance_log = now_m

        # Strategy breakdown
        strats = {}
        for sname in ("HFT", "SCALP", "GRAD_SNIPE", "SWING", "ESTAB", "MOONBAG"):
            s_open = [p for p in open_pos if p.strategy == sname]
            s_closed = [p for p in STATE.sim_closed if p.strategy == sname]
            s_wins = sum(1 for p in s_closed if p.profit_sol > 0)
            s_total = len(s_closed)
            strats[sname] = {
                "open": len(s_open),
                "trades": s_total,
                "wr": round(s_wins / max(1, s_total) * 100, 1),
                "pnl": round(sum(p.profit_sol for p in s_closed), 4),
            }

        # Uptime
        if STATE.start_time:
            up_s = now_m - STATE.start_time
            h, rem = divmod(int(up_s), 3600)
            m, s = divmod(rem, 60)
            uptime = f"{h}:{m:02d}:{s:02d}"
        else:
            uptime = "stopped"

        # Trades per hour
        total_trades = STATE.total_wins + STATE.total_losses
        up_hrs = (now_m - STATE.start_time) / 3600 if STATE.start_time and now_m > STATE.start_time else 1
        tph = total_trades / max(0.01, up_hrs)

        # Hourly rate from pnl_history
        rate_sol_hr = 0.0
        if len(STATE.pnl_history) >= 2:
            oldest, newest = STATE.pnl_history[0], STATE.pnl_history[-1]
            dt_hr = (newest[0] - oldest[0]) / 3600
            if dt_hr > 0.01:
                rate_sol_hr = (newest[1] - oldest[1]) / dt_hr

        data = {
            "timestamp": datetime.now().isoformat(),
            "balance": round(STATE.balance_sol, 4),
            "starting_balance": STARTING_BALANCE_SOL,
            "pnl_sol": round(STATE.total_pnl_sol + open_pnl, 4),
            "pnl_usd": round((STATE.total_pnl_sol + open_pnl) * STATE.sol_price_usd, 2),
            "sol_price": round(STATE.sol_price_usd, 2),
            "market_state": STATE.market_state,
            "uptime": uptime,
            "mode": "LIVE" if EXECUTE_TRADES else "SIM",
            "rate_sol_hr": round(rate_sol_hr, 4),
            "trades_per_hour": round(tph, 1),

            "trades_today": {
                "wins": STATE.total_wins,
                "losses": STATE.total_losses,
                "total": total_trades,
                "win_rate": round(STATE.total_wins / max(1, total_trades) * 100, 1),
            },

            "positions": [
                {
                    "name": p.symbol or p.mint[:8],
                    "strategy": p.strategy,
                    "pnl_pct": round(p.pct_change, 1),
                    "heat": round(p.heat_score, 1),
                    "heat_label": p.heat_pattern,
                    "held_seconds": round(now_m - p.entry_time, 0),
                    "entry_amount": round(p.remaining_sol, 4),
                    "price_source": p.price_source,
                    "score": p.score,
                    "ai_confidence": 0,
                    "peak_pct": round(p.peak_pct, 1),
                    "price_direction": p.price_direction,
                    "price_momentum": round(p.price_momentum, 3),
                    "consecutive_up": p.consecutive_up,
                    "consecutive_down": p.consecutive_down,
                    "accelerating": p.price_accelerating,
                    "atr": round(calc_position_atr(p), 1),
                    "trail_pct": round(calc_adaptive_trail(p, calc_position_atr(p)) * 100),
                }
                for p in sorted(open_pos, key=lambda x: -x.pct_change)
            ],

            "recent_trades": [
                {
                    "name": t.symbol or "?",
                    "pnl": round(t.profit_sol, 4),
                    "pnl_pct": round(t.pct_change if hasattr(t, 'pct_change') else 0, 1),
                    "exit_reason": t.exit_reason[:30],
                    "strategy": t.strategy,
                    "held": round(t.exit_time - t.entry_time, 0) if t.exit_time else 0,
                }
                for t in list(STATE.sim_closed)[:20]
            ],

            "strategies": strats,

            "ai_status": {
                "engine": "Groq" if GROQ_API_KEY else "none",
                "status": STATE.ai_status,
                "calls_today": STATE.ai_calls_today,
                "calls_limit": AI_MAX_CALLS_DAY,
                "last_decision": "",
                "last_latency_ms": round(STATE.ai_last_latency, 0),
            },

            "errors_last_hour": list(STATE.errors_last_hour),
            "balance_history": STATE.balance_history,
            "daily_loss_used": round(STATE.loss_today_sol, 4),
            "daily_loss_limit": MAX_LOSS_PER_DAY,
            "tokens_found": STATE.tokens_found,
            "session_number": STATE.session_number,
        }

        with open(DASHBOARD_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, default=str)
    except Exception as e:
        pass  # never let dashboard crash the bot


# ══════════════════════════════════════════════════════════════════════════════
# ██  REDDIT + TWIKIT INTELLIGENCE  ███████████████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════

def _extract_tickers_and_mints(text):
    tickers = re.findall(r'\$([A-Z]{2,10})', text)
    mints = [m for m in _MINT_RE.findall(text)
             if len(m) >= 32 and m != PUMP_PROGRAM_ID and not m.startswith("1111")]
    return tickers, mints

def _score_signal(text: str, source: str, subreddit: str = "",
                  upvotes: int = 0, username: str = "") -> int:
    """Universal scoring for Reddit and Twitter signals."""
    s = 0
    lower = text.lower()

    # Contract address = high signal
    if _MINT_RE.search(text): s += 40

    # pump.fun mention
    if "pump.fun" in lower: s += 20

    # Graduating / bonding curve keywords
    if any(kw in lower for kw in ("graduating", "bonding curve", "about to graduate")):
        s += 25

    # Other signal keywords
    if any(kw in lower for kw in SIGNAL_KEYWORDS): s += 10

    # Ticker present
    if re.search(r'\$[A-Z]{2,10}', text): s += 15

    # Hype
    if any(w in lower for w in ("lfg", "send it", "aping", "aped", "100x")): s += 10

    # Source-specific boosts
    if source == "REDDIT":
        if subreddit.lower() in REDDIT_HIGH_SIGNAL_SUBS: s += 15
        if upvotes >= 10: s += 20
        if upvotes >= 50: s += 15
    elif source == "TWITTER":
        # Known high-signal accounts
        uname = username.lower()
        if uname in ("elonmusk", "unusual_whales"): s += 30
        elif uname in ("pumpdotfun", "breaking911"): s += 20
        elif uname in ("disclosetv", "wsbchairman"): s += 15

    return s

def _ingest_signal(text: str, source: str, username: str, link: str,
                    search_term: str = "", upvotes: int = 0, subreddit: str = ""):
    """Ingest a signal from any source into the prefire system."""
    score = _score_signal(text, source, subreddit, upvotes, username)
    if score < 10: return

    tickers, mints = _extract_tickers_and_mints(text)
    if not tickers and not mints: return

    for ticker in tickers:
        key = ticker.upper()
        if key in STATE.prefire_list:
            sig = STATE.prefire_list[key]
            sig.signal_score = max(sig.signal_score, score)
            sig.tweet_count += 1
            if username and username not in sig.tweet_authors:
                sig.tweet_authors.append(username)
            if source not in sig.sources: sig.sources.append(source)
            if search_term and search_term not in sig.search_terms:
                sig.search_terms.append(search_term)
            sig.last_updated = time.time()
        else:
            STATE.prefire_list[key] = PreFireSignal(
                ticker=key, signal_score=score, sources=[source],
                search_terms=[search_term] if search_term else [],
                first_seen=time.time(),
                tweet_authors=[username] if username else [],
                tweet_count=1, last_updated=time.time())
        if mints and not STATE.prefire_list[key].mint:
            STATE.prefire_list[key].mint = mints[0]
            STATE.prefire_list[key].mint_confirmed = True

    for mint in mints:
        if mint not in STATE.prefire_list:
            STATE.prefire_list[mint] = PreFireSignal(
                mint=mint, signal_score=score, sources=[source],
                search_terms=[search_term] if search_term else [],
                first_seen=time.time(),
                tweet_authors=[username] if username else [],
                tweet_count=1, mint_confirmed=True, last_updated=time.time())

    log_intel_csv(source, search_term or subreddit, ",".join(tickers) or "?",
                  ",".join(tickers) or "?", ",".join(mints) or "",
                  link, username, 0, upvotes, 0, score, source.lower())

    if source == "REDDIT":
        STATE.reddit_signals_count += 1
        # Direct open for high-score Reddit signals with confirmed mints
        if score >= 60:
            for mint in mints:
                try: _reddit_open_queue.put_nowait(mint)
                except: pass
    else:
        STATE.twitter_signals_count += 1

def _detect_viral():
    now = time.time()
    for sig in STATE.prefire_list.values():
        # Ticker velocity: 3+ mentions within 5 minutes = hot token
        if (sig.tweet_count >= TWIT_VEL_MIN_MENTIONS and
                now - sig.first_seen <= TWIT_VEL_WINDOW_SEC and
                "TWIT_VEL" not in sig.sources):
            sig.sources.append("TWIT_VEL")
            sig.signal_score += TWIT_VEL_SCORE_BOOST
            label = sig.ticker or (sig.mint[:8] if sig.mint else '?')
            STATE.recent_activity.append(
                f"TWIT_VEL: ${label} {sig.tweet_count} mentions in "
                f"{now - sig.first_seen:.0f}s")
            _dbg(f"TWIT_VEL: {label} +{TWIT_VEL_SCORE_BOOST} "
                 f"({sig.tweet_count} mentions, {now - sig.first_seen:.0f}s)")

        if sig.is_viral: continue
        if now - sig.first_seen > VIRAL_WINDOW_SEC * 2: continue
        if (len(sig.tweet_authors) >= VIRAL_MIN_ACCOUNTS and
                now - sig.first_seen <= VIRAL_WINDOW_SEC):
            sig.is_viral = True; sig.signal_score = max(sig.signal_score, 95)
            if "VIRAL" not in sig.sources: sig.sources.append("VIRAL")
            STATE.viral_alerts_count += 1
            STATE.recent_activity.append(
                f"VIRAL: ${sig.ticker or (sig.mint[:8] if sig.mint else '?')}")
            if sig.signal_score >= 80:
                _dbg(f"*** ALERT *** VIRAL {sig.ticker} score={sig.signal_score}")


# ── Reddit Scanner ───────────────────────────────────────────────────────────
async def reddit_scanner(session):
    """Poll Reddit JSON feeds for Solana token signals."""
    _dbg("Reddit scanner started")
    STATE.recent_activity.append("Reddit: scanning")
    seen_ids: set = set()

    await asyncio.sleep(3)
    while not STATE.should_exit:
        try:
            for feed_url in REDDIT_FEEDS:
                if STATE.should_exit: return
                try:
                    async with session.get(feed_url,
                            timeout=aiohttp.ClientTimeout(total=10),
                            headers={"User-Agent": "SolanaBot/1.0"}) as r:
                        if r.status == 429:
                            _dbg("Reddit: rate limited, backing off")
                            await asyncio.sleep(60); break
                        if r.status != 200:
                            _dbg(f"Reddit: {r.status} for {feed_url[:50]}")
                            continue
                        data = await r.json(content_type=None)
                except Exception as e:
                    _dbg(f"Reddit fetch error: {e}"); continue

                posts = data.get("data", {}).get("children", [])
                subreddit = ""
                for post in posts:
                    pd = post.get("data", {})
                    post_id = pd.get("id", "")
                    if not post_id or post_id in seen_ids: continue
                    seen_ids.add(post_id)

                    title = pd.get("title", "")
                    body = pd.get("selftext", "")
                    subreddit = pd.get("subreddit", "")
                    author = pd.get("author", "")
                    ups = pd.get("ups", 0)
                    link = f"https://reddit.com{pd.get('permalink', '')}"

                    full_text = title + " " + body
                    _ingest_signal(full_text, "REDDIT", author, link,
                                   subreddit=subreddit, upvotes=ups)

                await asyncio.sleep(2)  # polite delay between feeds

            _detect_viral()
            _save_prefire_list()

            if len(seen_ids) > 5000:
                seen_ids = set(list(seen_ids)[-2000:])

        except Exception as e: _dbg(f"Reddit scanner error: {e}")
        await asyncio.sleep(REDDIT_POLL_INTERVAL)


# ── Twikit Twitter Scanner ──────────────────────────────────────────────────
async def twitter_scanner(session):
    """Scrape Twitter via twikit (no API key needed)."""
    if not TWITTER_ENABLED:
        _dbg("Twikit disabled: TWITTER_ENABLED=false in .env")
        STATE.twikit_status = "OFF"
        return
    if not TWITTER_USERNAME or not TWITTER_PASSWORD:
        _dbg("Twikit disabled: set TWITTER_USERNAME and TWITTER_PASSWORD in .env")
        STATE.twikit_status = "FAIL"
        STATE.recent_activity.append("Twikit: no credentials in .env")
        return

    try:
        from twikit import Client as TwikitClient
    except ImportError:
        _dbg("Twikit not installed: pip install twikit")
        STATE.twikit_status = "FAIL"
        return

    seen_ids: set = set()
    client = None

    # ── Authenticate ──────────────────────────────────────────────
    async def _login():
        nonlocal client
        # Always create fresh client to avoid stale state
        client = TwikitClient("en-US")

        # Try loading saved cookies first
        if os.path.exists(TWIKIT_COOKIES_PATH):
            try:
                client.load_cookies(TWIKIT_COOKIES_PATH)
                # Validate cookies by making a test call
                _dbg("Twikit: testing saved cookies...")
                await client.user()
                _dbg("Twikit: cookies valid")
                STATE.twikit_status = "OK"
                STATE.recent_activity.append("Twikit: cookies loaded")
                return True
            except Exception as e:
                _dbg(f"Twikit: saved cookies invalid ({type(e).__name__}: {e})")
                # Delete stale cookies
                try: os.remove(TWIKIT_COOKIES_PATH)
                except: pass
                client = TwikitClient("en-US")  # fresh client

        # Fresh login
        try:
            _dbg(f"Twikit: attempting login as {TWITTER_USERNAME}")
            await client.login(
                auth_info_1=TWITTER_USERNAME,
                password=TWITTER_PASSWORD,
            )
            client.save_cookies(TWIKIT_COOKIES_PATH)
            _dbg("Twikit: logged in and saved cookies")
            STATE.twikit_status = "OK"
            STATE.recent_activity.append("Twikit: authenticated")
            return True
        except Exception as e:
            err_str = f"{type(e).__name__}: {e}"
            _dbg(f"Twikit login FULL ERROR: {err_str}")

            # Detect specific failure modes
            err_lower = str(e).lower()
            if "captcha" in err_lower or "arkose" in err_lower:
                STATE.twikit_status = "CAPTCHA"
                _dbg("Twikit: Twitter requires CAPTCHA — cannot auto-login")
                STATE.recent_activity.append("Twikit: CAPTCHA required")
                return False
            elif "key_byte" in err_lower or "couldn't get" in err_lower:
                STATE.twikit_status = "FAIL"
                _dbg("Twikit: Twitter JS encryption changed — need twikit update")
                STATE.recent_activity.append("Twikit: needs update (pip install -U twikit)")
                return False
            elif "verification" in err_lower or "confirm" in err_lower:
                STATE.twikit_status = "VERIFY"
                _dbg("Twikit: Twitter wants email/phone verification")
                STATE.recent_activity.append("Twikit: verification required — login manually first")
                return False
            elif "locked" in err_lower or "suspended" in err_lower:
                STATE.twikit_status = "LOCKED"
                _dbg("Twikit: account locked/suspended")
                STATE.recent_activity.append("Twikit: account locked")
                return False
            else:
                STATE.twikit_status = "FAIL"
                STATE.recent_activity.append(f"Twikit: {err_str[:50]}")
                return False

    # Try updating twikit if KEY_BYTE error
    async def _try_update_and_login():
        _dbg("Twikit: attempting pip update before retry...")
        try:
            import subprocess
            subprocess.run(["pip", "install", "-U", "twikit"],
                          capture_output=True, timeout=30)
            _dbg("Twikit: updated via pip")
            # Reimport with fresh module
            import importlib
            import twikit as _tw
            importlib.reload(_tw)
        except Exception as e:
            _dbg(f"Twikit pip update failed: {e}")
        return await _login()

    if not await _login():
        # If KEY_BYTE error, try updating twikit
        if STATE.twikit_status == "FAIL" and "update" in (
                STATE.recent_activity[-1] if STATE.recent_activity else ""):
            if await _try_update_and_login():
                pass  # success after update
            else:
                # Permanent failures — don't retry forever
                if STATE.twikit_status in ("CAPTCHA", "LOCKED", "VERIFY"):
                    _dbg(f"Twikit: permanent failure ({STATE.twikit_status}), disabling")
                    return
        # Retry login every 5 minutes for transient failures
        retry_count = 0
        while not STATE.should_exit and retry_count < 5:
            await asyncio.sleep(300)
            retry_count += 1
            _dbg(f"Twikit: retry {retry_count}/5...")
            if await _login(): break
        if STATE.should_exit or not client: return
        if STATE.twikit_status != "OK":
            _dbg(f"Twikit: giving up after {retry_count} retries")
            return

    await asyncio.sleep(5)
    consecutive_failures = 0

    while not STATE.should_exit:
        try:
            # ── Search queries ────────────────────────────────────────
            for query in TWIKIT_SEARCH_TERMS:
                if STATE.should_exit: return
                try:
                    results = await client.search_tweet(query, product="Latest", count=10)
                    for tweet in results or []:
                        tid = str(tweet.id)
                        if tid in seen_ids: continue
                        seen_ids.add(tid)
                        text = tweet.text or ""
                        username = tweet.user.screen_name if tweet.user else "?"
                        link = f"https://x.com/{username}/status/{tid}"
                        _ingest_signal(text, "TWITTER", username, link,
                                       search_term=query)
                    consecutive_failures = 0
                except Exception as e:
                    _dbg(f"Twikit search error ({query[:20]}): {e}")
                    consecutive_failures += 1
                await asyncio.sleep(3)

            # ── Account timelines ─────────────────────────────────────
            for account in TWIKIT_ACCOUNTS:
                if STATE.should_exit: return
                try:
                    user = await client.get_user_by_screen_name(account)
                    if user:
                        tweets = await client.get_user_tweets(user.id, tweet_type="Tweets", count=5)
                        for tweet in tweets or []:
                            tid = str(tweet.id)
                            if tid in seen_ids: continue
                            seen_ids.add(tid)
                            text = tweet.text or ""
                            link = f"https://x.com/{account}/status/{tid}"
                            _ingest_signal(text, "TWITTER", account, link)
                    consecutive_failures = 0
                except Exception as e:
                    _dbg(f"Twikit timeline error ({account}): {e}")
                    consecutive_failures += 1
                await asyncio.sleep(3)

            STATE.twikit_status = "OK" if consecutive_failures < 5 else "FAIL"
            _detect_viral()
            _save_prefire_list()
            STATE.twitter_last_search = time.time()

            if len(seen_ids) > 5000:
                seen_ids = set(list(seen_ids)[-2000:])

            # If too many failures, re-login
            if consecutive_failures >= 10:
                _dbg("Twikit: too many failures, re-authenticating...")
                STATE.twikit_status = "FAIL"
                # Delete stale cookies and re-login
                if os.path.exists(TWIKIT_COOKIES_PATH):
                    os.remove(TWIKIT_COOKIES_PATH)
                if not await _login():
                    await asyncio.sleep(300)
                    continue
                consecutive_failures = 0

        except Exception as e:
            _dbg(f"Twikit scanner error: {e}")
            consecutive_failures += 1
        await asyncio.sleep(TWIKIT_POLL_INTERVAL)


# ══════════════════════════════════════════════════════════════════════════════
# ██  WALLET TRACKER  ██████████████████████████████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════

def load_wallets():
    STATE.successful_wallets = _load_json(WALLETS_JSON)
    # Load smart wallets from Dragon CLI output if available
    smart = _load_json(GMGN_SMART_WALLETS_FILE)
    if isinstance(smart, list) and smart:
        added = 0
        for w in smart[:30]:
            addr = w.get("address", "") if isinstance(w, dict) else ""
            if addr and addr not in WATCH_WALLETS:
                WATCH_WALLETS.append(addr)
                added += 1
        if added:
            _dbg(f"Loaded {added} smart wallets from Dragon (total watching: {len(WATCH_WALLETS)})")
def save_wallets(): _save_json(WALLETS_JSON, STATE.successful_wallets)

def record_successful_wallet(wallet, symbol, gain_pct):
    if not wallet: return
    wl = wallet.lower()
    if wl in STATE.successful_wallets:
        e = STATE.successful_wallets[wl]
        e["tokens"].append(symbol); e["wins"] += 1
        e["best_gain"] = max(e.get("best_gain", 0), gain_pct)
        e["last_win"] = datetime.now().isoformat()
    else:
        STATE.successful_wallets[wl] = {
            "wallet": wallet, "tokens": [symbol], "wins": 1,
            "best_gain": gain_pct, "first_seen": datetime.now().isoformat(),
            "last_win": datetime.now().isoformat()}
    save_wallets()
    STATE.recent_activity.append(f"WHALE: {wallet[:8]}.. ({symbol} +{gain_pct:.0f}%)")

async def check_wallet_activity(session):
    await asyncio.sleep(30)
    while not STATE.should_exit:
        try:
            for wa in list(STATE.successful_wallets.keys())[:20]:
                if STATE.should_exit: return
                try:
                    result = await rpc_call(session, "getSignaturesForAddress",
                                            [wa, {"limit": 5, "commitment": "confirmed"}])
                    if not result: continue
                    for si in result:
                        sig = si.get("signature", "")
                        if not sig: continue
                        tx = await rpc_call(session, "getTransaction",
                            [sig, {"encoding":"jsonParsed","maxSupportedTransactionVersion":0}])
                        if not tx: continue
                        accs = tx.get("transaction",{}).get("message",{}).get("accountKeys",[])
                        acc_strs = [a if isinstance(a,str) else a.get("pubkey","") for a in accs]
                        if PUMP_PROGRAM_ID in acc_strs:
                            for bal in tx.get("meta",{}).get("postTokenBalances",[]):
                                m = bal.get("mint","")
                                if m and m != "So11111111111111111111111111111111111111112" and m not in STATE.prefire_list:
                                    STATE.prefire_list[m] = PreFireSignal(
                                        mint=m, signal_score=90, sources=["WHALE_WALLET"],
                                        whale_wallet=wa, first_seen=time.time(),
                                        mint_confirmed=True, last_updated=time.time())
                                    STATE.whale_alerts_count += 1
                                    STATE.recent_activity.append(f"WHALE: {wa[:8]}.. pump.fun")
                                    break
                        await asyncio.sleep(0.5)
                except: continue
        except Exception as e: _dbg(f"Wallet tracker: {e}")
        await asyncio.sleep(WALLET_CHECK_INTERVAL)


# ══════════════════════════════════════════════════════════════════════════════
# ██  BITQUERY INTEGRATION  ████████████████████████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════

BITQUERY_PUMP_QUERY = """
{
  Solana {
    DEXTradeByTokens(
      where: {
        Trade: {
          Dex: {ProgramAddress: {is: "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"}}
          Side: {Currency: {MintAddress: {is: "So11111111111111111111111111111111111111112"}}}
        }
        Block: {Time: {after: "$SINCE$"}}
      }
      orderBy: {descendingByField: "volumeUsd"}
      limit: {count: 20}
    ) {
      Trade {
        Currency { MintAddress Symbol Name }
        Side { AmountInUSD }
      }
      volumeUsd: sum(of: Trade_Side_AmountInUSD)
    }
  }
}
"""

async def bitquery_scan(session):
    """Query Bitquery for pump.fun tokens with high recent volume (BC velocity proxy)."""
    if not BITQUERY_API_KEY:
        _dbg("Bitquery disabled: no API key")
        return
    await asyncio.sleep(20)
    _dbg(f"Bitquery scanner started")

    while not STATE.should_exit:
        try:
            since = (datetime.now(timezone.utc) - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
            query = BITQUERY_PUMP_QUERY.replace("$SINCE$", since)
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {BITQUERY_API_KEY}",
            }
            async with session.post(BITQUERY_URL, json={"query": query},
                                    headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    _dbg(f"Bitquery status {r.status}")
                    await asyncio.sleep(BITQUERY_INTERVAL)
                    continue
                data = await r.json(content_type=None)

            trades = (data.get("data", {}).get("Solana", {})
                      .get("DEXTradeByTokens", []))
            if not trades:
                await asyncio.sleep(BITQUERY_INTERVAL)
                continue

            for entry in trades:
                trade_info = entry.get("Trade", {}).get("Currency", {})
                mint = trade_info.get("MintAddress", "")
                symbol = trade_info.get("Symbol", "")
                vol = float(entry.get("volumeUsd", 0) or 0)

                if not mint or mint in STATE.prefire_list:
                    continue
                # High volume in 60s = bonding curve velocity signal
                if vol >= 500:  # $500+ volume in 60 seconds
                    sig = PreFireSignal(
                        ticker=symbol.upper() if symbol else "",
                        mint=mint,
                        signal_score=85,
                        sources=["BITQUERY"],
                        first_seen=time.time(),
                        mint_confirmed=True,
                        last_updated=time.time(),
                    )
                    STATE.prefire_list[mint] = sig
                    STATE.recent_activity.append(
                        f"BQ: {symbol or mint[:8]} vol=${vol:.0f}/60s")
                    _dbg(f"Bitquery signal: {symbol} {mint[:12]} vol=${vol:.0f}")
                    log_intel_csv("BITQUERY", "bc_velocity", "", symbol, mint,
                                  "", "", 0, 0, 0, 85, "bitquery")

        except Exception as e:
            _dbg(f"Bitquery error: {e}")

        await asyncio.sleep(BITQUERY_INTERVAL)


# ══════════════════════════════════════════════════════════════════════════════
# ██  JITO BUNDLE SUPPORT  █████████████████████████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════

async def send_jito_bundle(session, signed_txs: list[str]) -> Optional[str]:
    """Send transaction bundle to Jito block engine for priority inclusion.
    signed_txs: list of base58-encoded signed transactions.
    Returns bundle ID or None."""
    if not EXECUTE_TRADES:
        return None
    try:
        payload = {
            "jsonrpc": "2.0", "id": 1,
            "method": "sendBundle",
            "params": [signed_txs],
        }
        async with session.post(JITO_BLOCK_ENGINE, json=payload,
                                timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json(content_type=None)
            bundle_id = data.get("result")
            if bundle_id:
                _dbg(f"Jito bundle sent: {bundle_id}")
                STATE.recent_activity.append(f"Jito bundle: {bundle_id[:12]}...")
            return bundle_id
    except Exception as e:
        _dbg(f"Jito error: {e}")
        return None


def build_jito_tip_instruction() -> dict:
    """Build the tip instruction data for Jito.
    Returns instruction dict to add to transaction before signing."""
    return {
        "program_id": "11111111111111111111111111111111",  # System Program
        "accounts": [
            {"pubkey": WALLET_ADDRESS, "is_signer": True, "is_writable": True},
            {"pubkey": JITO_TIP_ACCOUNT, "is_signer": False, "is_writable": True},
        ],
        "data_lamports": JITO_TIP_LAMPORTS,
        "type": "transfer",
    }


# ══════════════════════════════════════════════════════════════════════════════
# ██  WATCH WALLET COPY TRADING  ███████████████████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════

async def _open_whale_position(session, coin, wallet: str,
                                buy_sol: float, score_boost: int):
    """Open a whale-signaled position. Bypasses HFT momentum filters.
    Uses larger position size (WHALE_ENTRY_SOL)."""
    mint = coin.get("mint", "")
    if mint in STATE.sim_positions or mint in STATE.seen_mints:
        return
    STATE.seen_mints.add(mint)
    symbol = coin.get("symbol", "?")[:12]
    price = calc_token_price_sol(coin)
    if price <= 0:
        return

    # Quick safety check (with 3s timeout, no RugCheck in HFT)
    sc = await run_safety_check(session, coin)
    bc_pct = calc_bc_progress(coin)

    entry_sol = WHALE_ENTRY_SOL
    p = SimPosition(
        symbol=symbol, name=coin.get("name", "")[:30], mint=mint,
        category=sc.category, score=min(sc.score + score_boost, 200),
        entry_time=time.monotonic(),
        entry_ts=datetime.now().strftime("%H:%M:%S"),
        entry_price_sol=price, entry_sol=entry_sol,
        current_price_sol=price, peak_price_sol=price, trough_price_sol=price,
        initial_liq_sol=sc.liquidity_sol, market_cap_usd=sc.market_cap_usd,
        had_social=sc.has_social_links or False,
        prefire_source="WHALE", creator_wallet=coin.get("creator", ""),
        rugcheck_status=sc.rugcheck_status,
        bc_progress=bc_pct, remaining_sol=entry_sol,
        whale_wallet=wallet, whale_buy_sol=buy_sol)
    p.bc_history.append((time.monotonic(), bc_pct))
    STATE.sim_positions[mint] = p
    STATE.total_opened += 1
    STATE.recent_activity.append(
        f"WHALE OPEN {symbol} s={p.score} whale={wallet[:6]}.. "
        f"{buy_sol:.1f}SOL bc={bc_pct:.0f}%")
    _dbg(f"WHALE_OPEN: {symbol} {mint[:16]} score={p.score} "
         f"whale={wallet[:8]} buy={buy_sol:.2f}SOL")
    # Send whale alert email
    if STATE.email_enabled:
        send_whale_alert(symbol, wallet, buy_sol, sc.market_cap_usd)


async def watch_wallets_scanner(session):
    """Monitor WATCH_WALLETS via WebSocket onLogs subscription (real-time).
    Pattern from DracoR22/handi-cat_wallet-tracker: subscribe to logs per wallet,
    filter by pump.fun program ID, parse on match. ~200ms latency vs 15s polling."""
    if not WATCH_WALLETS:
        _dbg("Watch wallets disabled: no WATCH_WALLETS in .env")
        return
    await asyncio.sleep(5)
    _dbg(f"Watch wallets: subscribing to {len(WATCH_WALLETS)} wallets via onLogs")
    STATE.recent_activity.append(f"WS watch: {len(WATCH_WALLETS)} wallets")

    # Track pump.fun program IDs to filter (from handi-cat ValidTransactions)
    pump_programs = {PUMP_PROGRAM_ID, PUMP_AMM_PROGRAM_ID, PUMP_MINT_AUTH}

    while not STATE.should_exit:
        await _wait_if_rate_limited()
        try:
            async with websockets.connect(
                HELIUS_WS_URL, ping_interval=20, ping_timeout=30
            ) as ws:
                # Subscribe to each wallet's logs
                sub_ids = {}
                for i, wallet in enumerate(WATCH_WALLETS):
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0", "id": 100 + i,
                        "method": "logsSubscribe",
                        "params": [
                            {"mentions": [wallet]},
                            {"commitment": "confirmed"},
                        ],
                    }))
                    ack = json.loads(await ws.recv())
                    sub_id = ack.get("result")
                    if sub_id is not None:
                        sub_ids[sub_id] = wallet
                        _dbg(f"Watch wallet subscribed: {wallet[:8]}.. sub={sub_id}")

                if not sub_ids:
                    _dbg("No wallet subscriptions succeeded")
                    await asyncio.sleep(10)
                    continue

                STATE.recent_activity.append(
                    f"WS watching {len(sub_ids)} wallets live")

                async for raw in ws:
                    if STATE.should_exit:
                        return
                    try:
                        msg = json.loads(raw)
                        if msg.get("method") != "logsNotification":
                            continue
                        result = msg.get("params", {}).get("result", {})
                        sub = msg.get("params", {}).get("subscription")
                        wallet = sub_ids.get(sub, "")
                        if not wallet:
                            continue

                        value = result.get("value", {})
                        logs = value.get("logs", [])
                        sig = value.get("signature", "")

                        # Check if any log line mentions pump.fun programs
                        log_text = " ".join(logs)
                        if not any(pid in log_text for pid in pump_programs):
                            continue

                        # This wallet interacted with pump.fun — extract mint + buy amount
                        _dbg(f"WHALE HIT: {wallet[:8]}.. sig={sig[:12]}")
                        await asyncio.sleep(1)

                        tx = await rpc_call(session, "getTransaction", [
                            sig, {"encoding": "jsonParsed",
                                  "maxSupportedTransactionVersion": 0}
                        ])
                        if not tx:
                            continue

                        meta = tx.get("meta", {})

                        # Estimate buy amount from SOL balance change
                        pre_bals = meta.get("preBalances", [])
                        post_bals = meta.get("postBalances", [])
                        buy_sol = 0.0
                        if pre_bals and post_bals and len(pre_bals) > 0:
                            sol_spent = (pre_bals[0] - post_bals[0]) / LAMPORTS_PER_SOL
                            if sol_spent > 0.01:
                                buy_sol = sol_spent

                        for bal in meta.get("postTokenBalances", []):
                            mint = bal.get("mint", "")
                            if (mint and
                                mint != "So11111111111111111111111111111111111111112" and
                                mint not in STATE.sim_positions):

                                STATE.whale_buys_today += 1
                                STATE.whale_tokens.append((
                                    time.time(), wallet[:8], mint[:12],
                                    "", buy_sol))
                                _dbg(f"WHALE BUY: {wallet[:8]}.. → {mint[:12]} "
                                     f"{buy_sol:.2f} SOL")
                                STATE.recent_activity.append(
                                    f"WHALE: {wallet[:6]}.. {buy_sol:.1f}SOL → {mint[:8]}..")

                                # Check if multiple whales bought same token
                                same_mint_whales = sum(
                                    1 for t in STATE.whale_tokens
                                    if t[2] == mint[:12] and time.time() - t[0] < 300)
                                score_boost = WHALE_SCORE_BOOST
                                if same_mint_whales >= 2:
                                    score_boost = WHALE_MULTI_BOOST
                                    _dbg(f"MULTI-WHALE: {same_mint_whales} whales on {mint[:12]}")
                                if buy_sol >= 1.0:
                                    score_boost += 30

                                if mint not in STATE.prefire_list:
                                    STATE.prefire_list[mint] = PreFireSignal(
                                        mint=mint, signal_score=score_boost,
                                        sources=["WHALE"],
                                        whale_wallet=wallet,
                                        first_seen=time.time(),
                                        mint_confirmed=True,
                                        last_updated=time.time())

                                # Fetch coin and open with whale sizing
                                # Skip HFT momentum filter — whale IS the momentum
                                coin = await fetch_pump_coin(session, mint)
                                if coin:
                                    await _open_whale_position(
                                        session, coin, wallet, buy_sol, score_boost)

                                log_intel_csv("WHALE_BUY", "", "", "",
                                              mint, sig, wallet, 0,
                                              0, 0, score_boost, "watch_wallet")
                                break

                    except Exception as e:
                        _dbg(f"Watch wallet parse: {e}")

        except websockets.exceptions.ConnectionClosed as e:
            _dbg(f"Watch wallet WS disconnected: {e}")
            await asyncio.sleep(30)
        except Exception as e:
            _dbg(f"Watch wallets WS error: {type(e).__name__}: {e}")
            wait = 60 if "429" in str(e) else 30
            await asyncio.sleep(wait)


# ══════════════════════════════════════════════════════════════════════════════
# ██  EMAIL ALERTS + REPLY SYSTEM  █████████████████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════

import smtplib, imaplib, email as email_lib
from email.mime.text import MIMEText

def _log_email(msg: str):
    try:
        with open(EMAIL_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except: pass


def send_email(subject: str, body: str):
    """Send email via Gmail SMTP. Non-blocking (runs in thread)."""
    if not ALERT_EMAIL or not GMAIL_APP_PASSWORD:
        return
    def _send():
        try:
            msg = MIMEText(body, "plain")
            msg["Subject"] = subject
            msg["From"] = ALERT_EMAIL_FROM
            msg["To"] = ALERT_EMAIL
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as s:
                s.login(ALERT_EMAIL_FROM, GMAIL_APP_PASSWORD)
                s.send_message(msg)
            _log_email(f"SENT: {subject}")
            _dbg(f"EMAIL SENT: {subject}")
        except Exception as e:
            _log_email(f"SEND_ERROR: {e}")
            _dbg(f"Email error: {e}")
    threading.Thread(target=_send, daemon=True).start()


def check_email_replies() -> Optional[str]:
    """Check Gmail inbox for replies containing STOP/CONTINUE/REDUCE.
    Returns the command found, or None."""
    if not ALERT_EMAIL or not GMAIL_APP_PASSWORD:
        return None
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=10)
        mail.login(ALERT_EMAIL_FROM, GMAIL_APP_PASSWORD)
        mail.select("INBOX")
        # Search for recent unread emails from self (replies)
        _, data = mail.search(None, '(UNSEEN FROM "{}")'.format(ALERT_EMAIL))
        ids = data[0].split()
        for eid in ids[-5:]:  # check last 5 unread
            _, msg_data = mail.fetch(eid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw)
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        break
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
            body_upper = body.strip().upper()
            for cmd in ["STOP", "CONTINUE", "REDUCE"]:
                if cmd in body_upper:
                    mail.store(eid, "+FLAGS", "\\Seen")
                    mail.logout()
                    _log_email(f"REPLY: {cmd}")
                    return cmd
        mail.logout()
    except Exception as e:
        _log_email(f"CHECK_ERROR: {e}")
    return None


def send_stop_loss_alert():
    """Send stop loss warning email with reply instructions."""
    usd = STATE.sol_price_usd
    loss_sol = abs(STATE.total_pnl_sol)
    loss_usd = loss_sol * usd

    # Top losers
    losers = sorted(
        [p for p in STATE.sim_positions.values() if p.status == "OPEN"],
        key=lambda x: x.pct_change)[:5]
    loser_lines = "\n".join(
        f"  - {p.symbol}: {p.pct_change:+.1f}%" for p in losers)

    est = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%I:%M %p EST")

    body = f"""Current Loss: {STATE.total_pnl_sol:+.4f} SOL (-${loss_usd:.2f})
Loss Limit: {DAILY_LOSS_LIMIT_SOL} SOL
Time: {est}

Top losing positions:
{loser_lines}

REPLY "STOP" to halt all trading immediately
REPLY "CONTINUE" to allow trading to continue
REPLY "REDUCE" to cut position sizes in half

You have 10 minutes to reply before automatic stop loss triggers."""

    send_email("🚨 SOLANA BOT - STOP LOSS ALERT", body)
    STATE.stop_loss_pending = True
    STATE.stop_loss_sent_at = time.monotonic()
    _log_email(f"STOP_LOSS_ALERT: loss={loss_sol:.4f} SOL")


def send_warning_alert():
    """Send 50% loss warning."""
    usd = STATE.sol_price_usd
    body = f"""WARNING: Approaching daily loss limit

Current Loss: {STATE.total_pnl_sol:+.4f} SOL (${STATE.total_pnl_sol * usd:+.2f})
Loss Limit: {DAILY_LOSS_LIMIT_SOL} SOL
Currently at {abs(STATE.total_pnl_sol) / DAILY_LOSS_LIMIT_SOL * 100:.0f}% of limit

Trading continues. You will receive another alert if limit is reached."""
    send_email("⚠️ SOLANA BOT - LOSS WARNING", body)
    STATE.warning_sent = True


def send_whale_alert(symbol: str, wallet: str, buy_sol: float, mc_usd: float):
    """Send whale buy detection email."""
    body = f"""Whale wallet detected buying!

Wallet: {wallet}
Bought: {symbol} at ${mc_usd:,.0f} market cap
Amount: {buy_sol:.2f} SOL
Your position: {WHALE_ENTRY_SOL} SOL opened automatically

Monitor in dashboard for exit signals."""
    send_email(f"🐋 WHALE DETECTED - {symbol}", body)


def send_hourly_summary():
    """Send hourly P&L summary during peak hours."""
    usd = STATE.sol_price_usd
    w = STATE.total_wins; l = STATE.total_losses
    open_count = sum(1 for p in STATE.sim_positions.values() if p.status == "OPEN")

    # Find best trade this session
    best = max(list(STATE.sim_closed)[:20], key=lambda x: x.pct_change, default=None)
    best_str = f"{best.symbol} +{best.pct_change:.0f}%" if best else "none yet"

    body = f"""Hourly Bot Update

Trades this session: {w + l}
Winners: {w} | Losers: {l}
Win rate: {w/(w+l)*100:.0f}%

Total P&L: {STATE.total_pnl_sol:+.4f} SOL (${STATE.total_pnl_sol * usd:+.2f})
Best trade: {best_str}

Open positions: {open_count}
Watching: {len(WATCH_WALLETS)} whale wallets
Whale buys today: {STATE.whale_buys_today}

HFT mode: {'ON' if STATE.hft_enabled else 'OFF'}"""

    pnl_str = f"+${STATE.total_pnl_sol * usd:.2f}" if STATE.total_pnl_sol >= 0 else f"-${abs(STATE.total_pnl_sol * usd):.2f}"
    send_email(f"📊 Bot Update | {pnl_str}", body)
    STATE.last_hourly_email = time.monotonic()


def send_restart_alert():
    """Send notification that scanner restarted."""
    prev = _count_previous_sessions()
    body = f"""Scanner restarted

Session: #{prev + 1} ({SESSION_ID})
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
HFT Mode: {'ON' if HFT_MODE else 'OFF'}
Whale wallets: {len(WATCH_WALLETS)}
Previous sessions: {prev}"""
    send_email("🔄 SOLANA BOT - RESTARTED", body)


async def wallet_activity_checker(session):
    """Check WATCH_WALLETS activity via RPC getSignaturesForAddress.
    Marks wallets as ACTIVE/INACTIVE based on last 24h trade activity."""
    if not WATCH_WALLETS: return
    _dbg("Wallet activity checker started")
    while not STATE.should_exit:
        try:
            for wallet in WATCH_WALLETS:
                try:
                    sigs = await rpc_call(session, "getSignaturesForAddress", [
                        wallet, {"limit": 1, "commitment": "confirmed"}])
                    last_trade = 0
                    active = False
                    if sigs and isinstance(sigs, list) and len(sigs) > 0:
                        bt = sigs[0].get("blockTime", 0)
                        if bt:
                            last_trade = bt
                            active = (time.time() - bt) < 86400  # 24 hours
                    STATE.wallet_status[wallet] = {
                        "active": active,
                        "last_trade": last_trade,
                        "checked": time.time()
                    }
                    status = "ACTIVE" if active else "INACTIVE"
                    if not active:
                        age_h = (time.time() - last_trade) / 3600 if last_trade else 999
                        _dbg(f"WALLET: {wallet[:8]}.. {status} (last trade {age_h:.0f}h ago)")
                except Exception as e:
                    _dbg(f"Wallet check {wallet[:8]}: {e}")
                await asyncio.sleep(2)
        except Exception as e:
            _dbg(f"Wallet activity error: {e}")
        await asyncio.sleep(3600)  # check every hour


async def email_monitor_task(session):
    """Background task: check loss limits, send alerts, monitor replies."""
    if not STATE.email_enabled:
        _dbg("Email alerts disabled: no GMAIL_APP_PASSWORD")
        return

    send_restart_alert()
    _dbg("Email monitor started")

    while not STATE.should_exit:
        try:
            now = time.monotonic()

            # ── Loss limit checks ─────────────────────────────────────
            if STATE.total_pnl_sol < 0:
                loss = abs(STATE.total_pnl_sol)

                # 50% warning
                if (loss >= DAILY_LOSS_LIMIT_SOL * 0.5 and
                        not STATE.warning_sent and not STATE.stop_loss_pending):
                    send_warning_alert()

                # Full stop loss alert
                if loss >= DAILY_LOSS_LIMIT_SOL and not STATE.stop_loss_pending:
                    send_stop_loss_alert()

            # ── Check for email replies ───────────────────────────────
            if STATE.stop_loss_pending:
                reply = check_email_replies()
                if reply == "STOP":
                    STATE.trading_halted = True
                    STATE.stop_loss_pending = False
                    STATE.status_msg = "HALTED by email reply"
                    STATE.recent_activity.append("EMAIL: STOP received — trading halted")
                    _dbg("EMAIL STOP: trading halted by user reply")
                elif reply == "CONTINUE":
                    STATE.stop_loss_pending = False
                    STATE.warning_sent = False  # allow future warnings
                    STATE.status_msg = "CONTINUE — loss counter reset"
                    STATE.recent_activity.append("EMAIL: CONTINUE — trading resumes")
                    _dbg("EMAIL CONTINUE: user confirmed")
                elif reply == "REDUCE":
                    STATE.position_size_mult *= 0.5
                    STATE.stop_loss_pending = False
                    STATE.status_msg = f"REDUCED — sizes now {STATE.position_size_mult:.0%}"
                    STATE.recent_activity.append(
                        f"EMAIL: REDUCE — sizes now {STATE.position_size_mult:.0%}")
                    _dbg(f"EMAIL REDUCE: position sizes now {STATE.position_size_mult:.0%}")
                elif (now - STATE.stop_loss_sent_at >= STOP_LOSS_REPLY_TIMEOUT):
                    # No reply in 10 minutes — auto halt
                    STATE.trading_halted = True
                    STATE.stop_loss_pending = False
                    STATE.status_msg = "AUTO-HALTED: no reply in 10min"
                    STATE.recent_activity.append("EMAIL: auto-halt (no reply 10min)")
                    send_email("🛑 AUTO-HALTED", "No reply received within 10 minutes. "
                               "Trading has been automatically halted.")
                    _dbg("EMAIL: auto-halt — no reply in 10 minutes")

            # ── Hourly summary (during peak hours 12-4 PM EST) ────────
            est_hour = (datetime.now(timezone.utc) - timedelta(hours=5)).hour
            if (12 <= est_hour < 16 and
                    now - STATE.last_hourly_email >= 3600):
                send_hourly_summary()

        except Exception as e:
            _dbg(f"Email monitor error: {e}")

        await asyncio.sleep(EMAIL_CHECK_INTERVAL)


# ══════════════════════════════════════════════════════════════════════════════
# ██  OVERNIGHT MODE + STATE SAVING  ███████████████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════

def _est_hour() -> int:
    """Get current US Eastern hour, auto-adjusting for EST/EDT."""
    try:
        import zoneinfo
        return datetime.now(zoneinfo.ZoneInfo("America/New_York")).hour
    except Exception:
        # Fallback: EDT (UTC-4) Mar-Nov, EST (UTC-5) Nov-Mar
        now_utc = datetime.now(timezone.utc)
        month = now_utc.month
        offset = 4 if 3 <= month <= 10 else 5  # rough DST approximation
        return (now_utc - timedelta(hours=offset)).hour

def _is_off_hours() -> bool:
    """2AM-10AM Eastern = off hours (watch only, no trading)."""
    h = _est_hour()
    return 2 <= h < 10

def _is_peak_hours() -> bool:
    """10AM-2AM Eastern = peak hours (full trading)."""
    return not _is_off_hours()


def save_state():
    """Save current state to state.json for crash recovery."""
    try:
        positions = {}
        for mint, p in STATE.sim_positions.items():
            if p.status != "OPEN":
                continue
            positions[mint] = {
                "symbol": p.symbol, "name": p.name, "mint": p.mint,
                "category": p.category, "score": p.score,
                "entry_ts": p.entry_ts, "entry_price_sol": p.entry_price_sol,
                "entry_sol": p.entry_sol, "current_price_sol": p.current_price_sol,
                "pct_change": p.pct_change, "peak_price_sol": p.peak_price_sol,
                "initial_liq_sol": p.initial_liq_sol,
                "market_cap_usd": p.market_cap_usd,
                "prefire_source": p.prefire_source,
                "creator_wallet": p.creator_wallet,
                "whale_wallet": p.whale_wallet,
                "whale_buy_sol": p.whale_buy_sol,
                "bc_progress": p.bc_progress,
                "signals": p.signals,
                "strategy": p.strategy,
                "graduated": p.graduated,
            }
        state = {
            "session_id": SESSION_ID,
            "saved_at": datetime.now().isoformat(),
            "total_pnl_sol": STATE.total_pnl_sol,
            "balance_sol": STATE.balance_sol,
            "total_opened": STATE.total_opened,
            "total_wins": STATE.total_wins,
            "total_losses": STATE.total_losses,
            "tokens_found": STATE.tokens_found,
            "whale_buys_today": STATE.whale_buys_today,
            "hft_tp_count": STATE.hft_tp_count,
            "hft_sl_count": STATE.hft_sl_count,
            "hft_flat_count": STATE.hft_flat_count,
            "hft_timeout_count": STATE.hft_timeout_count,
            "seen_mints_count": len(STATE.seen_mints),
            "open_positions": positions,
            # Persist settings so they survive crashes
            "settings": {
                "hft_max_hold_sec": HFT_MAX_HOLD_SEC,
                "hft_min_score": HFT_MIN_SCORE,
                "hft_stop_loss_pct": HFT_STOP_LOSS_PCT,
                "hft_min_bc_progress": HFT_MIN_BC_PROGRESS,
                "hft_min_bc_velocity": HFT_MIN_BC_VELOCITY,
                "hft_entry_sol": HFT_ENTRY_SOL,
                "hft_mega_entry_sol": HFT_MEGA_ENTRY_SOL,
                "grad_sl_pct": GRAD_SL_PCT,
                "grad_entry_sol": GRAD_ENTRY_SOL,
                "position_size_mult": STATE.position_size_mult,
                "loss_today_sol": STATE.loss_today_sol,
                "daily_halted": STATE.daily_halted,
            },
        }
        _save_json(STATE_JSON, state)
    except Exception as e:
        _dbg(f"State save error: {e}")


def load_state():
    """CLEAN START: Only restore settings (tuning params) from state.json.
    Balance, P&L, positions, trade counts always start fresh at 100 SOL."""
    data = _load_json(STATE_JSON)
    if not data:
        _dbg(f"CLEAN START: {STARTING_BALANCE_SOL} SOL, zero P&L, no positions")
        return

    # ONLY restore settings so tuning persists across restarts
    settings = data.get("settings", {})
    if settings:
        global HFT_MAX_HOLD_SEC, HFT_MIN_SCORE, HFT_STOP_LOSS_PCT
        global HFT_MIN_BC_PROGRESS, HFT_MIN_BC_VELOCITY
        global HFT_ENTRY_SOL, HFT_MEGA_ENTRY_SOL, GRAD_SL_PCT, GRAD_ENTRY_SOL
        HFT_MAX_HOLD_SEC = settings.get("hft_max_hold_sec", HFT_MAX_HOLD_SEC)
        HFT_MIN_SCORE = settings.get("hft_min_score", HFT_MIN_SCORE)
        HFT_STOP_LOSS_PCT = settings.get("hft_stop_loss_pct", HFT_STOP_LOSS_PCT)
        HFT_MIN_BC_PROGRESS = settings.get("hft_min_bc_progress", HFT_MIN_BC_PROGRESS)
        HFT_MIN_BC_VELOCITY = settings.get("hft_min_bc_velocity", HFT_MIN_BC_VELOCITY)
        HFT_ENTRY_SOL = settings.get("hft_entry_sol", HFT_ENTRY_SOL)
        HFT_MEGA_ENTRY_SOL = settings.get("hft_mega_entry_sol", HFT_MEGA_ENTRY_SOL)
        GRAD_SL_PCT = settings.get("grad_sl_pct", GRAD_SL_PCT)
        GRAD_ENTRY_SOL = settings.get("grad_entry_sol", GRAD_ENTRY_SOL)
        STATE.position_size_mult = settings.get("position_size_mult", STATE.position_size_mult)
    _dbg(f"CLEAN START: {STARTING_BALANCE_SOL} SOL, zero P&L, no positions (settings restored)")


def generate_morning_report():
    """Generate morning report at 8AM EST."""
    usd = STATE.sol_price_usd
    est_now = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%Y-%m-%d %I:%M %p EST")

    # Top tokens seen overnight
    overnight = STATE.overnight_tokens[-50:]
    top_scored = sorted(overnight, key=lambda x: x.get("score", 0), reverse=True)[:10]

    lines = [
        f"MORNING REPORT — {est_now}",
        f"{'='*50}",
        f"",
        f"Tokens detected overnight: {len(overnight)}",
        f"Total P&L: {STATE.total_pnl_sol:+.4f} SOL (${STATE.total_pnl_sol * usd:+.2f})",
        f"Trades: {STATE.total_wins}W/{STATE.total_losses}L",
        f"Whale buys: {STATE.whale_buys_today}",
        f"",
        f"TOP 10 HIGHEST SCORING TOKENS SEEN:",
    ]
    for i, t in enumerate(top_scored, 1):
        lines.append(f"  {i}. {t.get('symbol','?')} — score {t.get('score',0)} "
                     f"bc={t.get('bc',0):.0f}% liq={t.get('liq',0):.1f}SOL")

    lines += [
        f"",
        f"WHALE ACTIVITY:",
    ]
    for wt in list(STATE.whale_tokens)[-5:]:
        lines.append(f"  {wt[1]}.. → {wt[2]}.. {wt[4]:.1f}SOL")

    lines += [
        f"",
        f"PEAK HOURS START: 10AM EST",
        f"Full HFT trading will resume automatically.",
    ]

    report = "\n".join(lines)

    try:
        with open(MORNING_REPORT, "w", encoding="utf-8") as f:
            f.write(report)
    except:
        pass

    # Email the report
    if STATE.email_enabled:
        send_email(f"🌅 Morning Report | {STATE.total_pnl_sol:+.4f} SOL", report)

    STATE.morning_report_sent = True
    _dbg("Morning report generated and emailed")
    return report


async def overnight_manager(session):
    """Manages overnight mode: off-hours watch, peak-hours trade, state saving,
    morning report, hourly emails."""
    if not OVERNIGHT_MODE:
        _dbg("Overnight mode disabled")
        return

    _dbg("Overnight manager started")

    while not STATE.should_exit:
        try:
            now = time.monotonic()
            h = _est_hour()

            # ── State save every 60 seconds ───────────────────────────
            if now - STATE.last_state_save >= 60:
                save_state()
                STATE.last_state_save = now

            # ── Off-hours: 2AM-10AM EST ───────────────────────────────
            if _is_off_hours():
                if not STATE.overnight_active:
                    STATE.overnight_active = True
                    STATE.status_msg = "OVERNIGHT: watch only"
                    STATE.recent_activity.append("Off-hours: watching only (2AM-10AM)")
                    _dbg("Entering off-hours mode")

                # Morning report at 8AM
                if h == 8 and not STATE.morning_report_sent:
                    generate_morning_report()

            # ── Peak hours: 10AM-2AM EST ──────────────────────────────
            elif _is_peak_hours():
                if STATE.overnight_active:
                    STATE.overnight_active = False
                    STATE.morning_report_sent = False
                    STATE.status_msg = "PEAK HOURS: full trading"
                    STATE.recent_activity.append("Peak hours: full trading resumed")
                    _dbg("Entering peak hours mode")
                    if STATE.email_enabled and not STATE.peak_start_sent:
                        send_email("🟢 PEAK HOURS STARTED",
                                   f"Trading resumed at {datetime.now().strftime('%I:%M %p EST')}\n"
                                   f"Current P&L: {STATE.total_pnl_sol:+.4f} SOL\n"
                                   f"Open positions: {sum(1 for p in STATE.sim_positions.values() if p.status=='OPEN')}")
                        STATE.peak_start_sent = True

                # Reset peak_start_sent at midnight for next day
                if h == 0:
                    STATE.peak_start_sent = False

            # ── Hourly email (all hours when overnight mode on) ───────
            if (STATE.email_enabled and
                    now - STATE.last_hourly_email >= 3600):
                send_hourly_summary()

        except Exception as e:
            _dbg(f"Overnight manager error: {e}")

        await asyncio.sleep(30)  # check every 30 seconds


# ══════════════════════════════════════════════════════════════════════════════
# ██  PATTERN LEARNING  ████████████████████████████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════

def load_patterns():
    STATE.patterns = _load_json(PATTERNS_JSON)
    _recalculate_term_weights()

def _recalculate_term_weights():
    ts = STATE.patterns.get("term_stats", {})
    if not ts or STATE.patterns.get("total_closed", 0) < PATTERN_MIN_CLOSED: return
    for term, s in ts.items():
        total = s.get("total", 0)
        if total < 3: continue
        wr = s.get("wins", 0) / total
        gf = max(-0.5, min(2.0, s.get("avg_gain_pct", 0) / 100.0))
        STATE.term_weights[term] = round(max(0.1, min(5.0,
            _DEFAULT_TERM_WEIGHT * (1 + wr) * (1 + gf))), 2)

def record_pattern(p: SimPosition):
    if "term_stats" not in STATE.patterns: STATE.patterns["term_stats"] = {}
    STATE.patterns["total_closed"] = STATE.patterns.get("total_closed", 0) + 1
    pf = STATE.prefire_list.get(p.symbol.upper()) or STATE.prefire_list.get(p.mint)
    terms = (pf.search_terms if pf else []) or ([p.prefire_source] if p.prefire_source else [])
    for term in terms:
        if term not in STATE.patterns["term_stats"]:
            STATE.patterns["term_stats"][term] = {
                "total":0,"wins":0,"losses":0,"total_gain_pct":0.0,"avg_gain_pct":0.0}
        s = STATE.patterns["term_stats"][term]
        s["total"] += 1
        if p.profit_sol > 0: s["wins"] += 1
        else: s["losses"] += 1
        s["total_gain_pct"] += p.pct_change
        s["avg_gain_pct"] = s["total_gain_pct"] / s["total"]
    if "closed_positions" not in STATE.patterns: STATE.patterns["closed_positions"] = []
    STATE.patterns["closed_positions"].append({
        "symbol": p.symbol, "mint": p.mint, "gain_pct": p.pct_change,
        "exit_reason": p.exit_reason, "terms": terms,
        "timestamp": datetime.now().isoformat()})
    STATE.patterns["closed_positions"] = STATE.patterns["closed_positions"][-500:]
    _save_json(PATTERNS_JSON, STATE.patterns)
    if STATE.patterns["total_closed"] % 25 == 0: _recalculate_term_weights()

def _save_prefire_list():
    out = {k: {"ticker":s.ticker,"mint":s.mint,"signal_score":s.signal_score,
               "sources":s.sources,"search_terms":s.search_terms,
               "first_seen":s.first_seen,"tweet_authors":s.tweet_authors[:20],
               "follower_reach":s.follower_reach,"tweet_count":s.tweet_count,
               "is_viral":s.is_viral,"whale_wallet":s.whale_wallet,
               "mint_confirmed":s.mint_confirmed,"last_updated":s.last_updated}
           for k,s in STATE.prefire_list.items()}
    _save_json(PREFIRE_JSON, out)

def _load_prefire_list():
    now = time.time()
    for k, d in _load_json(PREFIRE_JSON).items():
        if now - d.get("last_updated", 0) > 7200: continue
        STATE.prefire_list[k] = PreFireSignal(**{
            f: d.get(f, df) for f, df in [
                ("ticker",""),("mint",""),("signal_score",0),("sources",[]),
                ("search_terms",[]),("first_seen",0),("tweet_authors",[]),
                ("follower_reach",0),("tweet_count",0),("is_viral",False),
                ("whale_wallet",""),("mint_confirmed",False),("last_updated",0)]})


# ══════════════════════════════════════════════════════════════════════════════
# ██  POSITION MANAGEMENT  █████████████████████████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════

def close_position(p: SimPosition, reason: str, price: float):
    p.status = "CLOSED"; p.exit_time = time.monotonic()
    p.exit_price_sol = price; p.exit_reason = reason
    profit, _ = calc_sim_pnl(p.entry_price_sol, price,
                             p.remaining_sol or p.entry_sol, p.initial_liq_sol)
    p.profit_sol = profit; p.profit_usd = profit * STATE.sol_price_usd
    STATE.sim_closed.appendleft(p)
    STATE.total_pnl_sol += p.profit_sol
    STATE.balance_sol += p.remaining_sol + p.profit_sol  # return capital + profit
    if p.profit_sol > 0: STATE.total_wins += 1
    else:
        STATE.total_losses += 1
        loss = abs(p.profit_sol)
        STATE.loss_today_sol += loss
        STATE.loss_hour_sol += loss
        # Check limits
        if STATE.loss_today_sol >= MAX_LOSS_PER_DAY:
            STATE.daily_halted = True
            STATE.status_msg = f"DAILY LIMIT: -{STATE.loss_today_sol:.2f} SOL"
            _dbg(f"DAILY_HALT: lost {STATE.loss_today_sol:.3f} SOL, limit={MAX_LOSS_PER_DAY}")
            STATE.recent_activity.append(f"DAILY HALT: -{STATE.loss_today_sol:.2f} SOL")
        elif STATE.loss_hour_sol >= MAX_LOSS_PER_HOUR:
            STATE.hourly_paused_until = time.monotonic() + 3600
            _dbg(f"HOURLY_PAUSE: lost {STATE.loss_hour_sol:.3f} SOL, pausing 1h")
            STATE.recent_activity.append(f"HOURLY PAUSE: -{STATE.loss_hour_sol:.2f} SOL")
    STATE.best_trade_sol = max(STATE.best_trade_sol, p.profit_sol)
    if not STATE.worst_set or p.profit_sol < STATE.worst_trade_sol:
        STATE.worst_trade_sol = p.profit_sol; STATE.worst_set = True
    log_snipe_csv(p)
    STATE.recent_activity.append(f"CLOSE {p.symbol} {reason} {p.profit_sol:+.4f}")
    record_pattern(p)
    if p.pct_change >= 400 and p.creator_wallet:
        record_successful_wallet(p.creator_wallet, p.symbol, p.pct_change)
    # Log whale trades and track best whale call
    if p.whale_wallet:
        log_whale_csv(p)
        if p.pct_change > STATE.whale_best_pct:
            STATE.whale_best_pct = p.pct_change
            STATE.whale_best_sym = p.symbol


async def open_sim_position(session, coin, sc, prefire_source=""):
    # Block new positions if trading halted, off-hours, or HFT disabled
    if STATE.trading_halted or STATE.overnight_active:
        return
    if not STATE.hft_enabled:
        return  # HFT disabled via .env HFT_MODE=false
    mint = coin.get("mint", ""); symbol = coin.get("symbol", "?")[:12]
    name = coin.get("name", "")[:30]
    price = calc_token_price_sol(coin)
    if price <= 0: return

    # HFT mode: adaptive filters based on market state
    if STATE.hft_enabled:
        # Use adaptive thresholds (adjusted by market state engine)
        min_score = min(HFT_MIN_SCORE, STATE.adaptive_score)
        min_bc = max(HFT_MIN_BC_PROGRESS, STATE.adaptive_bc)
        if sc.score < min_score:
            if sc.score >= 70:  # only log near-misses, not total garbage
                _dbg(f"SKIP_SCORE: {symbol} sc={sc.score} need={min_score} [{STATE.market_state}]")
            return
        # Track for market state engine
        STATE.recent_scores.append(sc.score)
        _dbg(f"SCORE_PASS: {symbol} sc={sc.score} (need {min_score}) — checking momentum...")

        bc_pct = calc_bc_progress(coin)

        if bc_pct < min_bc:
            STATE.hft_skip_bc += 1
            _dbg(f"SKIP_LOW_BC: {symbol} bc={bc_pct:.0f}%")
            return

        price1 = price
        # BC velocity check — must show active liquidity inflow
        bc_vel = calc_bc_velocity([(time.monotonic(), bc_pct)])  # single point = 0
        # Get a second BC read to compute real velocity
        await asyncio.sleep(HFT_PRICE_CHECK_SEC)
        bc2 = await fetch_bc_direct(session, mint)
        if bc2:
            bc_pct2 = calc_bc_progress_from_raw(bc2)
            dt_sec = HFT_PRICE_CHECK_SEC
            if dt_sec > 0:
                bc_vel = (bc_pct2 - bc_pct) / (dt_sec / 60.0)  # %/min
            # BC velocity filter: skip only if actively DUMPING (negative velocity)
            # Zero velocity is normal for 2s window — price momentum check below catches flat tokens
            if bc_vel < -5.0:
                STATE.hft_skip_vel += 1
                _dbg(f"SKIP_NEG_VEL: {symbol} bc_vel={bc_vel:.1f}%/min (BC draining) [{STATE.market_state}]")
                return

            vsolr2 = bc2.get("virtualSolReserves", 0)
            vtokr2 = bc2.get("virtualTokenReserves", 0)
            if vsolr2 and vtokr2:
                price2 = (vsolr2 / LAMPORTS_PER_SOL) / (vtokr2 / 1e6)
                if price1 > 0 and price2 > 0:
                    move_pct = (price2 - price1) / price1 * 100
                    # Negative velocity = people selling = worst entry
                    if move_pct <= -5.0:
                        STATE.hft_skip_vel += 1
                        _dbg(f"SKIP_NEG_VEL: {symbol} move={move_pct:+.1f}% in {HFT_PRICE_CHECK_SEC}s")
                        return
                    # Only block actively falling prices — flat (0.0%) is OK to enter
                    if move_pct < 0:
                        STATE.hft_skip_mom += 1
                        _dbg(f"SKIP_NO_MOM: {symbol} sc={sc.score} bc={bc_pct:.0f}% "
                             f"move={move_pct:+.1f}% (falling) [{STATE.market_state}]")
                        return
                    STATE.recent_velocities.append(move_pct)
                    price = price2
                    _dbg(f"HFT_MOM_OK: {symbol} +{move_pct:.1f}% vel={bc_vel:.1f}%/min")

    # Loss limits check
    if not _check_loss_limits():
        _dbg(f"SKIP_LOSS_LIMIT: {symbol} daily={STATE.loss_today_sol:.2f} hourly={STATE.loss_hour_sol:.2f}")
        return

    # Dynamic position sizing based on score + signals
    if STATE.hft_enabled:
        has_reddit = bool(prefire_source and "REDDIT" in prefire_source)
        base_sol, confidence, size_reason = calc_hft_size(sc.score, has_reddit)
    else:
        base_sol = SIM_ENTRY_SOL; confidence = "MED"; size_reason = "SIM"
    entry_sol = _cap_position_size(base_sol * STATE.position_size_mult)

    # Capital check
    if STATE.balance_sol < entry_sol:
        _dbg(f"SKIP_NO_CAPITAL: {symbol} need={entry_sol:.3f} have={STATE.balance_sol:.3f}")
        return

    p = SimPosition(
        symbol=symbol, name=name, mint=mint, category=sc.category, score=sc.score,
        entry_time=time.monotonic(), entry_ts=datetime.now().strftime("%H:%M:%S"),
        entry_price_sol=price, entry_sol=entry_sol,
        current_price_sol=price, peak_price_sol=price, trough_price_sol=price,
        initial_liq_sol=sc.liquidity_sol, market_cap_usd=sc.market_cap_usd,
        had_social=sc.has_social_links or False, dev_sold_pct=sc.dev_sold_pct,
        prefire_source=prefire_source, creator_wallet=coin.get("creator",""),
        rugcheck_status=sc.rugcheck_status,
        bc_progress=calc_bc_progress(coin), remaining_sol=entry_sol,
        confidence=confidence, size_reason=size_reason)
    p.bc_history.append((time.monotonic(), p.bc_progress))
    STATE.balance_sol -= entry_sol  # reserve capital
    STATE.sim_positions[mint] = p; STATE.total_opened += 1
    STATE.recent_activity.append(
        f"OPEN {symbol} s={sc.score} {sc.category} bc={p.bc_progress:.0f}%")


# ── Strategy-specific entry functions ─────────────────────────────────────────

async def _get_pool_price_rpc(session, mint: str) -> float:
    """Get real price from PumpSwap pool via RPC.
    Finds pool via DexScreener, decodes pool account to get vault addresses,
    reads vault balances, calculates price = sol_balance / token_balance."""
    try:
        # Step 1: Find pool address via DexScreener
        data = await _dex_fetch_json(session,
            f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
        if not data: return 0.0
        pool_addr = None
        for pair in data.get("pairs") or []:
            if pair.get("chainId") != "solana": continue
            if "pumpswap" in (pair.get("dexId", "") or "").lower():
                pool_addr = pair.get("pairAddress", "")
                break
            # Fallback: any Solana pair
            if not pool_addr:
                pool_addr = pair.get("pairAddress", "")
        if not pool_addr: return 0.0

        # Step 2: Decode pool account to get vault addresses
        import base64, struct
        result = await rpc_call(session, "getAccountInfo", [
            pool_addr, {"encoding": "base64", "commitment": "confirmed"}])
        if not result or not result.get("value"): return 0.0
        raw_b64 = result["value"]["data"]
        if isinstance(raw_b64, list): raw_b64 = raw_b64[0]
        raw = base64.b64decode(raw_b64)
        if len(raw) < 211: return 0.0

        # Pool layout: skip 8 disc + 1 bump + 2 index + 32 creator + 32 base_mint + 32 quote_mint + 32 lp_mint
        # pool_base_token_account at offset 139, pool_quote_token_account at 171
        from solders.pubkey import Pubkey
        base_vault = str(Pubkey.from_bytes(raw[139:171]))
        quote_vault = str(Pubkey.from_bytes(raw[171:203]))

        # Step 3: Read vault balances via getMultipleAccounts
        result = await rpc_call(session, "getMultipleAccounts", [
            [base_vault, quote_vault],
            {"encoding": "base64", "commitment": "confirmed"}])
        if not result or not result.get("value"): return 0.0
        vals = result["value"]
        if len(vals) < 2 or not vals[0] or not vals[1]: return 0.0

        # SPL token amount is u64 at offset 64 in token account data
        base_data = base64.b64decode(vals[0]["data"][0] if isinstance(vals[0]["data"], list) else vals[0]["data"])
        quote_data = base64.b64decode(vals[1]["data"][0] if isinstance(vals[1]["data"], list) else vals[1]["data"])
        base_amount = struct.unpack_from("<Q", base_data, 64)[0]   # token amount (raw)
        quote_amount = struct.unpack_from("<Q", quote_data, 64)[0]  # SOL amount (lamports)

        if base_amount <= 0: return 0.0
        # price = SOL per token = (quote_lamports / 1e9) / (base_tokens / 1e6)
        price = (quote_amount / LAMPORTS_PER_SOL) / (base_amount / 1e6)
        _dbg(f"POOL_PRICE: base={base_amount} quote={quote_amount} price={price:.10f}")
        return price
    except (ValueError, struct.error, IndexError, KeyError, Exception) as e:
        _dbg(f"Pool price error: {type(e).__name__}: {e}")
        return 0.0

async def _get_pool_price_direct(session, mint: str) -> float:
    """Get price directly from on-chain pool by deriving pool PDA.
    Uses getProgramAccounts to find pool with this token as base_mint."""
    try:
        import base64, struct
        from solders.pubkey import Pubkey
        # Pool discriminator for PumpSwap AMM (first 8 bytes)
        # Search for pool accounts with base_mint matching our token
        mint_bytes = base64.b64encode(bytes(Pubkey.from_string(mint))).decode()
        result = await rpc_call(session, "getProgramAccounts", [
            PUMP_AMM_PROGRAM_ID, {
                "encoding": "base64",
                "filters": [
                    {"dataSize": 243},  # new pool size (or 211 for old)
                    {"memcmp": {"offset": 43, "bytes": mint_bytes}}  # base_mint at offset 43
                ],
                "commitment": "confirmed"
            }])
        if not result:
            # Try old pool size
            result = await rpc_call(session, "getProgramAccounts", [
                PUMP_AMM_PROGRAM_ID, {
                    "encoding": "base64",
                    "filters": [
                        {"dataSize": 211},
                        {"memcmp": {"offset": 43, "bytes": mint_bytes}}
                    ],
                    "commitment": "confirmed"
                }])
        if not result or not isinstance(result, list) or len(result) == 0:
            return 0.0

        # Decode first matching pool
        acc = result[0]
        raw_b64 = acc.get("account", {}).get("data", [])
        if isinstance(raw_b64, list): raw_b64 = raw_b64[0]
        raw = base64.b64decode(raw_b64)
        if len(raw) < 203: return 0.0

        base_vault = str(Pubkey.from_bytes(raw[139:171]))
        quote_vault = str(Pubkey.from_bytes(raw[171:203]))

        # Read vault balances
        vaults = await rpc_call(session, "getMultipleAccounts", [
            [base_vault, quote_vault],
            {"encoding": "base64", "commitment": "confirmed"}])
        if not vaults or not vaults.get("value"): return 0.0
        vals = vaults["value"]
        if len(vals) < 2 or not vals[0] or not vals[1]: return 0.0

        bd = base64.b64decode(vals[0]["data"][0] if isinstance(vals[0]["data"], list) else vals[0]["data"])
        qd = base64.b64decode(vals[1]["data"][0] if isinstance(vals[1]["data"], list) else vals[1]["data"])
        base_amt = struct.unpack_from("<Q", bd, 64)[0]
        quote_amt = struct.unpack_from("<Q", qd, 64)[0]

        if base_amt <= 0: return 0.0
        price = (quote_amt / LAMPORTS_PER_SOL) / (base_amt / 1e6)
        _dbg(f"POOL_DIRECT: base={base_amt} quote={quote_amt} price={price:.10f}")
        return price
    except (ValueError, struct.error, IndexError, KeyError, Exception) as e:
        _dbg(f"Pool direct error: {type(e).__name__}: {e}")
        return 0.0

async def _get_grad_price(session, mint: str, symbol: str) -> tuple:
    """Get real price for graduated token. Returns (price_sol, source_str).
    Pipeline: DEXScreener → Direct pool RPC → extended DEXScreener retry.
    Total wait: up to 30s before giving up."""
    # Step 1: DEXScreener (2 fast attempts, 3s apart)
    for attempt in range(2):
        dex_price = await dexscreener_get_price(session, mint)
        if dex_price > 0:
            _dbg(f"GRAD_PRICE_OK: {symbol} DEX={dex_price:.10f} (attempt {attempt+1})")
            return dex_price, "DEX"
        _dbg(f"GRAD_DEX_FAIL: {symbol} attempt {attempt+1} — no price")
        await asyncio.sleep(3)

    # Step 2: Direct pool price via getProgramAccounts (no DEXScreener needed)
    _dbg(f"GRAD_TRYING_RPC: {symbol} — DEXScreener failed, trying direct pool lookup")
    pool_price = await _get_pool_price_direct(session, mint)
    if pool_price > 0:
        _dbg(f"GRAD_PRICE_OK: {symbol} RPC={pool_price:.10f} (direct pool)")
        return pool_price, "RPC"

    # Step 3: Wait longer for DEXScreener indexing (up to 20s more)
    for attempt in range(4):
        await asyncio.sleep(5)
        dex_price = await dexscreener_get_price(session, mint)
        if dex_price > 0:
            _dbg(f"GRAD_PRICE_OK: {symbol} DEX={dex_price:.10f} (delayed attempt {attempt+1})")
            return dex_price, "DEX"
        # Try pool RPC again
        pool_price = await _get_pool_price_direct(session, mint)
        if pool_price > 0:
            _dbg(f"GRAD_PRICE_OK: {symbol} RPC={pool_price:.10f} (delayed)")
            return pool_price, "RPC"

    _dbg(f"GRAD_NO_PRICE: {symbol} {mint[:12]} all sources failed after 30s")
    return 0.0, ""

async def open_grad_snipe_position(session, mint: str, price: float):
    """Open a GRAD_SNIPE position when token graduates to AMM.
    MUST get real verified price — never uses estimates.
    Waits for DEXScreener to index (~60s) with 2 test fetches before entering."""
    if not _can_open_strategy("GRAD_SNIPE", GRAD_ENTRY_SOL):
        return
    if mint in STATE.sim_positions: return
    if not _check_loss_limits(): return
    symbol = "?"

    # Get symbol from pump API
    coin = await fetch_pump_coin(session, mint)
    if coin:
        symbol = coin.get("symbol", "?")[:12]

    # DEXScreener needs ~60s to index a newly graduated token.
    # Do 2 test price fetches 30s apart — only enter if BOTH succeed.
    _dbg(f"GRAD_WAIT: {symbol} {mint[:12]} — waiting for DEX indexing (test 1/2)...")
    await asyncio.sleep(30)
    test1 = await dexscreener_get_price(session, mint)
    if test1 <= 0:
        _dbg(f"GRAD_SKIP: {symbol} DEX test 1 failed — not indexed yet")
        return
    _dbg(f"GRAD_WAIT: {symbol} test 1 OK ({test1:.10f}) — waiting 30s for test 2...")
    await asyncio.sleep(30)
    test2 = await dexscreener_get_price(session, mint)
    if test2 <= 0:
        _dbg(f"GRAD_SKIP: {symbol} DEX test 2 failed — unstable indexing")
        return
    _dbg(f"GRAD_CONFIRMED: {symbol} both DEX tests passed ({test1:.10f} → {test2:.10f})")

    # Get verified price (DEXScreener → RPC fallback)
    price, price_src = await _get_grad_price(session, mint, symbol)
    if price <= 0:
        return  # GRAD_NO_PRICE already logged

    base_sol, confidence, size_reason = calc_grad_size(mint)
    entry_sol = _cap_position_size(base_sol * STATE.position_size_mult)
    if STATE.balance_sol < entry_sol: return
    # Validate price
    if price < 0.000000001:
        _dbg(f"GRAD_PRICE_TOO_SMALL: {symbol} {mint[:12]} price={price}")
        return

    p = SimPosition(
        symbol=symbol, name=symbol, mint=mint, category="GRAD", score=100,
        entry_time=time.monotonic(), entry_ts=datetime.now().strftime("%H:%M:%S"),
        entry_price_sol=price, entry_sol=entry_sol,
        current_price_sol=price, peak_price_sol=price, trough_price_sol=price,
        initial_liq_sol=PUMP_GRADUATION_SOL,  # ~85 SOL in graduated pools
        graduated=True, bc_progress=100.0, remaining_sol=entry_sol,
        strategy="GRAD_SNIPE", confidence=confidence, size_reason=size_reason,
        price_source=price_src)
    STATE.balance_sol -= entry_sol
    STATE.sim_positions[mint] = p; STATE.total_opened += 1
    STATE.recent_activity.append(f"GRAD: {symbol} {entry_sol:.2f}SOL @{price_src}")
    _dbg(f"GRAD_SNIPE: {symbol} {mint[:12]} price={price:.10f} src={price_src}")

async def open_near_grad_position(session, coin, sc):
    """DISABLED — lost 0.836 SOL. Pre-graduation is too risky."""
    return  # NEAR_GRAD disabled
    if not _can_open_strategy("NEAR_GRAD", NEAR_GRAD_ENTRY_SOL): return
    mint = coin.get("mint", "")
    if mint in STATE.sim_positions: return
    symbol = coin.get("symbol", "?")[:12]
    price = calc_token_price_sol(coin)
    if price <= 0: return
    entry_sol = NEAR_GRAD_ENTRY_SOL * STATE.position_size_mult
    if STATE.balance_sol < entry_sol: return
    p = SimPosition(
        symbol=symbol, name=coin.get("name","")[:30], mint=mint,
        category=sc.category if sc else "WATCH", score=sc.score + 50 if sc else 50,
        entry_time=time.monotonic(), entry_ts=datetime.now().strftime("%H:%M:%S"),
        entry_price_sol=price, entry_sol=entry_sol,
        current_price_sol=price, peak_price_sol=price, trough_price_sol=price,
        initial_liq_sol=sc.liquidity_sol if sc else 0,
        bc_progress=calc_bc_progress(coin), remaining_sol=entry_sol,
        strategy="NEAR_GRAD")
    p.bc_history.append((time.monotonic(), p.bc_progress))
    STATE.balance_sol -= entry_sol
    STATE.sim_positions[mint] = p; STATE.total_opened += 1
    STATE.recent_activity.append(f"NEAR_GRAD: {symbol} bc={p.bc_progress:.0f}% +50score")
    _dbg(f"NEAR_GRAD: {symbol} bc={p.bc_progress:.0f}% score={p.score}")

async def open_trending_position(session, mint: str, symbol: str, price_sol: float):
    """Open TRENDING position from DexScreener signal."""
    if not _can_open_strategy("TRENDING", TRENDING_ENTRY_SOL): return
    if mint in STATE.sim_positions: return
    if not _check_loss_limits(): return
    # Universal price verification — confirm price exists before entering
    verified_price, src = await get_universal_price(session, mint)
    if verified_price <= 0:
        _dbg(f"TREND_SKIP: {symbol} — no price from any source")
        return
    price_sol = verified_price  # use verified price, not the stale one passed in
    entry_sol = TRENDING_ENTRY_SOL * STATE.position_size_mult
    if STATE.balance_sol < entry_sol: return
    p = SimPosition(
        symbol=symbol, name=symbol, mint=mint, category="TRENDING", score=80,
        entry_time=time.monotonic(), entry_ts=datetime.now().strftime("%H:%M:%S"),
        entry_price_sol=price_sol, entry_sol=entry_sol,
        current_price_sol=price_sol, peak_price_sol=price_sol,
        trough_price_sol=price_sol, remaining_sol=entry_sol,
        prefire_source="DEXSCREENER", strategy="TRENDING")
    STATE.balance_sol -= entry_sol
    STATE.sim_positions[mint] = p; STATE.total_opened += 1
    STATE.recent_activity.append(f"TRENDING: {symbol} dexscreener")
    _dbg(f"TRENDING: {symbol} {mint[:12]} price={price_sol:.10f}")

async def open_reddit_position(session, mint: str):
    """Open REDDIT position from high-score Reddit signal."""
    if not _can_open_strategy("REDDIT", REDDIT_ENTRY_SOL): return
    if mint in STATE.sim_positions: return
    coin = await fetch_pump_coin(session, mint)
    if not coin: return
    symbol = coin.get("symbol", "?")[:12]
    price = calc_token_price_sol(coin)
    if price <= 0: return
    entry_sol = REDDIT_ENTRY_SOL * STATE.position_size_mult
    if STATE.balance_sol < entry_sol: return
    p = SimPosition(
        symbol=symbol, name=coin.get("name","")[:30], mint=mint,
        category="REDDIT", score=80,
        entry_time=time.monotonic(), entry_ts=datetime.now().strftime("%H:%M:%S"),
        entry_price_sol=price, entry_sol=entry_sol,
        current_price_sol=price, peak_price_sol=price, trough_price_sol=price,
        remaining_sol=entry_sol, prefire_source="REDDIT", strategy="REDDIT")
    STATE.balance_sol -= entry_sol
    STATE.sim_positions[mint] = p; STATE.total_opened += 1
    STATE.recent_activity.append(f"REDDIT: {symbol} social signal")
    _dbg(f"REDDIT: {symbol} {mint[:12]} price={price:.10f}")


# ── DexScreener Trending Scanner ─────────────────────────────────────────────
async def _dex_fetch_json(session, url):
    """Fetch JSON from DexScreener with rate limit handling."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 429: _dbg("DexScreener: rate limited"); return None
            if r.status != 200: return None
            return await r.json(content_type=None)
    except Exception as e:
        _dbg(f"DexScreener fetch: {e}"); return None

# ── Jupiter Price API V2 (universal Solana price source) ─────────────────────
JUPITER_PRICE_URL = "https://api.jup.ag/price/v2"
JUP_API_KEY       = os.getenv("JUP_API_KEY", "")  # free key from portal.jup.ag

def _jup_headers() -> dict:
    """Headers for Jupiter API — key required since 2026."""
    h = {"Accept": "application/json"}
    if JUP_API_KEY:
        h["x-api-key"] = JUP_API_KEY
    return h

async def jupiter_get_price(session, mint: str) -> float:
    """Get price from Jupiter Price API — covers ALL Solana tokens on any DEX."""
    try:
        async with session.get(f"{JUPITER_PRICE_URL}?ids={mint}",
                               headers=_jup_headers(),
                               timeout=aiohttp.ClientTimeout(total=5)) as r:
            if r.status == 401:
                # API key required — fall back to DEXScreener silently
                return 0.0
            if r.status != 200: return 0.0
            data = await r.json(content_type=None)
            token_data = data.get("data", {}).get(mint, {})
            price_usd = float(token_data.get("price", 0) or 0)
            if price_usd > 0 and STATE.sol_price_usd > 0:
                return price_usd / STATE.sol_price_usd
    except Exception as e:
        _dbg(f"Jupiter price error {mint[:12]}: {e}")
    return 0.0


async def jupiter_get_prices_batch(session, mints: list) -> dict:
    """Batch price fetch from Jupiter — up to 100 mints in one call."""
    if not mints: return {}
    try:
        ids = ",".join(mints[:100])
        async with session.get(f"{JUPITER_PRICE_URL}?ids={ids}",
                               headers=_jup_headers(),
                               timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200: return {}
            data = await r.json(content_type=None)
            results = {}
            for mint in mints:
                token_data = data.get("data", {}).get(mint, {})
                price_usd = float(token_data.get("price", 0) or 0)
                if price_usd > 0 and STATE.sol_price_usd > 0:
                    results[mint] = price_usd / STATE.sol_price_usd
            return results
    except Exception as e:
        _dbg(f"Jupiter batch error: {e}")
    return {}


async def get_universal_price(session, mint: str, position=None) -> tuple:
    """Universal price fetcher — tries every source in priority order.
    Returns (price_sol, source_name) or (0.0, 'NONE').
    BC → Jupiter → DEXScreener fallback chain."""
    # 1. Bonding curve (fastest, only for active pump.fun tokens)
    if position and not position.graduated and position.price_source == "BC":
        bc = await fetch_bc_direct(session, mint)
        if bc and not bc.get("_parse_error"):
            vsolr = bc.get("virtualSolReserves", 0)
            vtokr = bc.get("virtualTokenReserves", 0)
            if vsolr and vtokr:
                price = (vsolr / LAMPORTS_PER_SOL) / (vtokr / 1e6)
                if price > 0:
                    return (price, "BC")

    # 2. Jupiter Price API (covers ALL Solana DEXs, ~200ms, FREE)
    price = await jupiter_get_price(session, mint)
    if price > 0:
        return (price, "JUP")

    # 3. DEXScreener (backup, ~300ms, rate limited)
    price = await dexscreener_get_price(session, mint)
    if price > 0:
        return (price, "DEX")

    return (0.0, "NONE")


async def dexscreener_get_price(session, mint: str) -> float:
    """Get price in SOL from DexScreener for a specific token (backup price source)."""
    data = await _dex_fetch_json(session,
        f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
    if not data: return 0.0
    for pair in data.get("pairs") or []:
        # Accept any chain — we sim-track all prices in SOL equivalent
        price_usd = float(pair.get("priceUsd", 0) or 0)
        if price_usd > 0 and STATE.sol_price_usd > 0:
            return price_usd / STATE.sol_price_usd
    return 0.0

async def dexscreener_scanner(session):
    """Poll DexScreener trending + top boosts for Solana pump.fun tokens."""
    _dbg("DexScreener scanner started")
    seen_trending: set = set()
    await asyncio.sleep(15)
    while not STATE.should_exit:
        try:
            # ── Boosted tokens (top + latest) + Solana-wide search ──
            for url in [
                "https://api.dexscreener.com/token-boosts/top/v1",
                "https://api.dexscreener.com/token-boosts/latest/v1",
                "https://api.dexscreener.com/latest/dex/search?q=pump.fun",
                "https://api.dexscreener.com/latest/dex/search?q=solana%20trending",
                "https://api.dexscreener.com/latest/dex/search?q=raydium",
            ]:
                data = await _dex_fetch_json(session, url)
                if not data: continue

                # Boosts endpoints return list of tokens directly
                items = data if isinstance(data, list) else data.get("pairs", [])
                for item in items:
                    chain = item.get("chainId", "")
                    if chain != "solana": continue

                    mint = item.get("tokenAddress", "") or \
                           item.get("baseToken", {}).get("address", "")
                    if not mint or mint in seen_trending: continue

                    # Accept any Solana token — quality filters below do the real work
                    # (removed pump.fun-only filter that was blocking all non-pump tokens)

                    seen_trending.add(mint)

                    # Score boost for existing positions (GRAD + TRENDING = best signal)
                    if mint in STATE.sim_positions:
                        p = STATE.sim_positions[mint]
                        if "TRENDING" not in p.signals:
                            p.signals.append("TRENDING")
                            p.score += 50
                            STATE.recent_activity.append(
                                f"DEX_BOOST: {p.symbol} +50 (grad+trending)")
                            _dbg(f"DEX_BOOST: {p.symbol} trending on dexscreener +50")
                        # Moonbag sell trigger: trending = time to take profit
                        if p.is_moonbag and "DEX_MOON_SELL" not in p.signals:
                            p.signals.append("DEX_MOON_SELL")
                            STATE.recent_activity.append(
                                f"MOON_SELL: {p.symbol} trending on DEX — selling moonbag")
                            _dbg(f"MOON_SELL: {p.symbol} moonbag sell triggered by DEX trending")
                        continue

                    # ── Behavior-based quality filters (name-blind) ──
                    vol_h1 = item.get("volume", {}).get("h1", 0) if isinstance(item.get("volume"), dict) else 0
                    mcap = item.get("fdv", 0) or item.get("marketCap", 0) or 0
                    liq_usd = item.get("liquidity", {}).get("usd", 0) if isinstance(item.get("liquidity"), dict) else 0
                    chg_5m = item.get("priceChange", {}).get("m5", 0) if isinstance(item.get("priceChange"), dict) else 0
                    chg_1h = item.get("priceChange", {}).get("h1", 0) if isinstance(item.get("priceChange"), dict) else 0
                    txns = item.get("txns", {}).get("m5", {}) if isinstance(item.get("txns"), dict) else {}
                    buys = txns.get("buys", 0) or 0
                    sells = txns.get("sells", 0) or 0

                    # Must have real liquidity (scam tokens have $0-$500)
                    if liq_usd < 10000: continue
                    # Must have real trading volume
                    if vol_h1 < 5000: continue
                    # PRICE MUST BE GOING UP — trending doesn't mean buy
                    if (chg_5m or 0) < 1.0: continue  # need +1% in 5 min, not just "moving"
                    # Market cap sanity
                    if mcap < 50000 or mcap > 10000000: continue
                    # Heat proxy from buy/sell ratio
                    heat_proxy = (buys / (buys + sells) * 100) if (buys + sells) > 0 else 0
                    if heat_proxy < TRENDING_MIN_HEAT: continue
                    # Blacklist check
                    symbol = item.get("baseToken", {}).get("symbol", "") if "baseToken" in item else "?"
                    symbol = symbol[:12] if symbol else "?"
                    if symbol.upper() in SCALP_BLACKLIST: continue

                    # Get price
                    price_usd = float(item.get("priceUsd", 0) or 0)
                    if price_usd <= 0 or STATE.sol_price_usd <= 0: continue
                    price_sol = price_usd / STATE.sol_price_usd

                    _dbg(f"DEX_TREND: {symbol} mc=${mcap:.0f} liq=${liq_usd:.0f} "
                         f"5m={chg_5m:+.1f}% heat={heat_proxy:.0f} vol=${vol_h1:.0f}")
                    STATE.recent_activity.append(f"DEX: {symbol} mc=${mcap/1000:.0f}K h={heat_proxy:.0f}")
                    asyncio.create_task(
                        open_trending_position(session, mint, symbol, price_sol))
                await asyncio.sleep(3)

            if len(seen_trending) > 3000:
                seen_trending = set(list(seen_trending)[-1000:])
        except Exception as e: _dbg(f"DexScreener error: {e}")
        await asyncio.sleep(60)


# ── Helius DAS Trending Scanner ──────────────────────────────────────────────
async def helius_trending_scanner(session):
    """Use Helius getTokenAccounts to find tokens with high activity."""
    await asyncio.sleep(20)
    while not STATE.should_exit:
        try:
            # Use getSignaturesForAddress on pump.fun program to find hot tokens
            sigs = await rpc_call(session, "getSignaturesForAddress", [
                PUMP_PROGRAM_ID, {"limit": 20, "commitment": "confirmed"}])
            if sigs and isinstance(sigs, list):
                # Extract unique mints from recent pump.fun transactions
                recent_mints = set()
                for sig_info in sigs:
                    sig = sig_info.get("signature", "")
                    if not sig: continue
                    # Check if this token is already in prefire with score boost
                    memo = sig_info.get("memo", "")
                    if memo:
                        tickers, mints = _extract_tickers_and_mints(memo)
                        for m in mints:
                            if m in STATE.sim_positions:
                                p = STATE.sim_positions[m]
                                if "HELIUS_HOT" not in p.signals:
                                    p.signals.append("HELIUS_HOT")
                                    p.score += 30
                                    _dbg(f"HELIUS_HOT: {p.symbol} +30 (high on-chain activity)")
        except Exception as e:
            _dbg(f"Helius trending error: {e}")
        await asyncio.sleep(120)


# ── Reddit Catalyst Consumer ─────────────────────────────────────────────────
async def reddit_catalyst_consumer(session):
    """Drains reddit signal queue and opens positions for high-score mints."""
    _dbg("Reddit catalyst consumer started")
    while not STATE.should_exit:
        try:
            mint = await asyncio.wait_for(_reddit_open_queue.get(), timeout=5)
            if mint and mint not in STATE.sim_positions:
                await open_reddit_position(session, mint)
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            _dbg(f"Reddit catalyst error: {e}")


# ── Swing Trading System ─────────────────────────────────────────────────────

async def swing_watchlist_builder(session):
    """Every 30 min: scan DEXScreener for graduated pump.fun tokens to watch."""
    _dbg("Swing watchlist builder started")
    await asyncio.sleep(30)
    while not STATE.should_exit:
        try:
            watchlist = []
            data = await _dex_fetch_json(session,
                "https://api.dexscreener.com/latest/dex/search?q=pump.fun")
            if data:
                for pair in data.get("pairs") or []:
                    if pair.get("chainId") != "solana": continue
                    mint = pair.get("baseToken", {}).get("address", "")
                    if not mint: continue
                    # Age filter: 1-24 hours
                    created = pair.get("pairCreatedAt", 0)
                    if created:
                        age_h = (time.time() * 1000 - created) / 3600000
                        if age_h < 1 or age_h > 24: continue
                    # Volume filter
                    vol_h1 = pair.get("volume", {}).get("h1", 0) or 0
                    sol_price = STATE.sol_price_usd or 80
                    vol_sol = vol_h1 / sol_price if sol_price > 0 else 0
                    if vol_sol < 5: continue
                    # Must be on pumpswap
                    dex_id = (pair.get("dexId", "") or "").lower()
                    if "pump" not in dex_id and "raydium" not in dex_id: continue

                    symbol = pair.get("baseToken", {}).get("symbol", "?")[:12]
                    price_usd = float(pair.get("priceUsd", 0) or 0)
                    mcap = pair.get("fdv", 0) or 0
                    chg_h1 = pair.get("priceChange", {}).get("h1", 0) or 0
                    chg_h24 = pair.get("priceChange", {}).get("h24", 0) or 0

                    watchlist.append({
                        "mint": mint, "symbol": symbol,
                        "price_usd": price_usd, "vol_sol": vol_sol,
                        "mcap": mcap, "chg_h1": chg_h1, "chg_h24": chg_h24,
                        "dex_id": dex_id, "updated": time.time()
                    })

            # Sort by volume, keep top 20
            watchlist.sort(key=lambda x: -x["vol_sol"])
            watchlist = watchlist[:SWING_WATCHLIST_SIZE]
            STATE.swing_watchlist = watchlist

            # Save to file
            try:
                _save_json(SWING_WATCHLIST_FILE, watchlist)
            except: pass

            if watchlist:
                _dbg(f"SWING_WATCH: {len(watchlist)} tokens, "
                     f"top={watchlist[0]['symbol']} vol={watchlist[0]['vol_sol']:.1f}SOL")
        except Exception as e:
            _dbg(f"Swing watchlist error: {e}")
        await asyncio.sleep(1800)  # every 30 min


async def swing_pattern_scanner(session):
    """Every 30s: check watchlist tokens for entry patterns."""
    _dbg("Swing pattern scanner started")
    await asyncio.sleep(60)  # let watchlist build first
    # Price history per token: {mint: [(time, price_sol)]}
    price_cache: dict = {}

    while not STATE.should_exit:
        try:
            watchlist = getattr(STATE, 'swing_watchlist', [])
            if not watchlist:
                await asyncio.sleep(SWING_SCAN_INTERVAL); continue

            for token in watchlist[:10]:  # check top 10 by volume
                if STATE.should_exit: return
                mint = token["mint"]
                symbol = token["symbol"]
                if mint in STATE.sim_positions: continue

                # Fetch current price
                dex_price = await dexscreener_get_price(session, mint)
                if dex_price <= 0: continue

                # Build price history
                if mint not in price_cache:
                    price_cache[mint] = []
                price_cache[mint].append((time.time(), dex_price))
                # Keep last 20 entries (~10 min at 30s intervals)
                price_cache[mint] = price_cache[mint][-20:]
                ph = price_cache[mint]
                if len(ph) < 4: continue  # need at least 4 data points

                # Calculate pattern metrics
                prices = [p[1] for p in ph]
                recent_5 = prices[-5:] if len(prices) >= 5 else prices
                hi = max(recent_5); lo = min(recent_5)
                avg = sum(recent_5) / len(recent_5)
                price_range_pct = (hi - lo) / avg * 100 if avg > 0 else 0
                current = prices[-1]
                peak = max(prices)
                trough = min(prices)

                # Volume from DEX data
                vol_sol = token.get("vol_sol", 0)

                # Pattern detection
                signal = None; signal_score = 0

                # 1. CONSOLIDATION BREAKOUT
                if price_range_pct < 3.0 and len(prices) >= 6:
                    prev_range = prices[-6:-3]
                    curr_range = prices[-3:]
                    if max(curr_range) > max(prev_range) * 1.02:
                        signal = "BREAKOUT"
                        signal_score = 80

                # 2. SUPPORT BOUNCE
                if not signal and peak > 0:
                    drop_pct = (peak - trough) / peak * 100
                    bounce_pct = (current - trough) / trough * 100 if trough > 0 else 0
                    if 10 <= drop_pct <= 30 and bounce_pct >= 3:
                        signal = "BOUNCE"
                        signal_score = 70

                # 3. MOMENTUM CONTINUATION
                if not signal and len(prices) >= 6:
                    chg_total = (current - prices[0]) / prices[0] * 100 if prices[0] > 0 else 0
                    recent_dip = (current - min(prices[-3:])) / min(prices[-3:]) * 100 if min(prices[-3:]) > 0 else 0
                    if chg_total > 20 and recent_dip > 0 and recent_dip < 5:
                        signal = "CONTINUATION"
                        signal_score = 75

                # 4. VOLUME SURGE (use h1 change as proxy)
                if not signal and token.get("chg_h1", 0) > 10 and vol_sol > 10:
                    signal = "VOL_SURGE"
                    signal_score = 65

                if signal and signal_score >= 65:
                    if not _can_open_strategy("SWING", SWING_ENTRY_SOL): continue
                    if not _check_loss_limits(): continue

                    entry_sol = _cap_position_size(SWING_ENTRY_SOL * STATE.position_size_mult)
                    if STATE.balance_sol < entry_sol: continue
                    price_sol = dex_price

                    p = SimPosition(
                        symbol=symbol, name=symbol, mint=mint,
                        category="SWING", score=signal_score,
                        entry_time=time.monotonic(),
                        entry_ts=datetime.now().strftime("%H:%M:%S"),
                        entry_price_sol=price_sol, entry_sol=entry_sol,
                        current_price_sol=price_sol, peak_price_sol=price_sol,
                        trough_price_sol=price_sol, initial_liq_sol=PUMP_GRADUATION_SOL,
                        remaining_sol=entry_sol, strategy="SWING",
                        confidence="MED", size_reason=signal,
                        price_source="DEX", graduated=True)
                    STATE.balance_sol -= entry_sol
                    STATE.sim_positions[mint] = p; STATE.total_opened += 1
                    STATE.recent_activity.append(
                        f"SWING: {symbol} {signal} {entry_sol:.2f}SOL")
                    _dbg(f"SWING_OPEN: {symbol} {signal} score={signal_score} "
                         f"price={price_sol:.10f}")

                    # Log to swing CSV
                    try:
                        with open(SWING_LOG_CSV, "a", newline="", encoding="utf-8") as f:
                            csv.writer(f).writerow([
                                SESSION_ID, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                mint, symbol, signal, signal_score,
                                f"{price_sol:.10f}", f"{entry_sol:.4f}", "OPEN"])
                    except: pass

                await asyncio.sleep(2)  # polite delay

            # Clean old price cache
            cutoff = time.time() - 1800
            price_cache = {k: v for k, v in price_cache.items()
                          if v and v[-1][0] > cutoff}
        except Exception as e:
            _dbg(f"Swing pattern error: {e}")
        await asyncio.sleep(SWING_SCAN_INTERVAL)


# ── Scalp Strategy ────────────────────────────────────────────────────────────

async def open_scalp_position(session, coin, sc):
    """Open a SCALP position — tiny size, fast exit."""
    if not STATE.scalp_enabled: return
    if _strategy_count("SCALP") >= SCALP_MAX_POSITIONS: return
    mint = coin.get("mint", "")
    if not mint: return
    # Allow scalp + HFT on same token — check scalp-specific dedup
    scalp_key = f"SCALP_{mint}"
    if scalp_key in STATE.sim_positions: return
    if not _check_loss_limits(): return

    symbol = coin.get("symbol", "?")[:12]
    price = calc_token_price_sol(coin)
    if price <= 0: return

    entry_sol = SCALP_ENTRY_SOL  # flat 0.01, no multiplier
    if STATE.balance_sol < entry_sol: return

    p = SimPosition(
        symbol=symbol, name=coin.get("name", "")[:30], mint=mint,
        category=sc.category if sc else "SCALP", score=sc.score if sc else 70,
        entry_time=time.monotonic(), entry_ts=datetime.now().strftime("%H:%M:%S"),
        entry_price_sol=price, entry_sol=entry_sol,
        current_price_sol=price, peak_price_sol=price, trough_price_sol=price,
        initial_liq_sol=sc.liquidity_sol if sc else 30,
        remaining_sol=entry_sol, strategy="SCALP",
        confidence="LOW", size_reason="SCALP")
    STATE.balance_sol -= entry_sol
    STATE.sim_positions[scalp_key] = p; STATE.total_opened += 1
    STATE.scalp_trades_today += 1
    STATE.scalp_trade_times.append(time.time())
    _dbg(f"SCALP_OPEN: {symbol} price={price:.10f} score={sc.score if sc else 0}")


async def scalp_scanner(session):
    """Fast scalp entry scanner — checks every 2 seconds for quick-move tokens."""
    _dbg("Scalp scanner started")
    await asyncio.sleep(10)
    while not STATE.should_exit:
        try:
            if not STATE.scalp_enabled or not STATE.running:
                await asyncio.sleep(2); continue

            # Check all open HFT/other positions for scalp opportunities
            # Also check recently detected tokens from Geyser
            open_pos = [p for p in STATE.sim_positions.values()
                       if p.status == "OPEN" and p.strategy != "SCALP"]

            for p in open_pos:
                if STATE.should_exit: return
                mint = p.mint
                scalp_key = f"SCALP_{mint}"
                if scalp_key in STATE.sim_positions: continue

                # Scalp entry conditions from heat data
                if len(p.price_history) < 4: continue
                if p.heat_score < SCALP_MIN_HEAT: continue

                # Buy ratio check
                prices = [x[1] for x in p.price_history[-5:]]
                ups = sum(1 for i in range(1, len(prices)) if prices[i] > prices[i-1])
                buy_ratio = ups / (len(prices) - 1) if len(prices) > 1 else 0
                if buy_ratio < 0.6: continue

                # Price momentum: up 0.5%+ in recent history
                if len(prices) >= 3:
                    mom = (prices[-1] - prices[-3]) / prices[-3] * 100 if prices[-3] > 0 else 0
                    if mom < 0.5: continue

                # Score check (lower bar than HFT)
                if p.score < SCALP_MIN_SCORE: continue

                # All conditions met — open scalp position
                if (_strategy_count("SCALP") < SCALP_MAX_POSITIONS and
                        STATE.balance_sol >= SCALP_ENTRY_SOL):
                    sp = SimPosition(
                        symbol=p.symbol, name=p.name, mint=mint,
                        category="SCALP", score=p.score,
                        entry_time=time.monotonic(),
                        entry_ts=datetime.now().strftime("%H:%M:%S"),
                        entry_price_sol=p.current_price_sol,
                        entry_sol=SCALP_ENTRY_SOL,
                        current_price_sol=p.current_price_sol,
                        peak_price_sol=p.current_price_sol,
                        trough_price_sol=p.current_price_sol,
                        initial_liq_sol=p.initial_liq_sol or 30,
                        remaining_sol=SCALP_ENTRY_SOL, strategy="SCALP",
                        confidence="LOW", size_reason="SCALP",
                        heat_score=p.heat_score, heat_pattern=p.heat_pattern)
                    STATE.balance_sol -= SCALP_ENTRY_SOL
                    STATE.sim_positions[scalp_key] = sp
                    STATE.total_opened += 1
                    STATE.scalp_trades_today += 1
                    STATE.scalp_trade_times.append(time.time())
                    STATE.recent_activity.append(
                        f"SCALP: {p.symbol} heat={p.heat_score:.0f} @{p.current_price_sol:.10f}")
                    _dbg(f"SCALP_OPEN: {p.symbol} heat={p.heat_score:.0f} "
                         f"buy_ratio={buy_ratio:.0%} mom={mom:+.1f}%")

        except Exception as e:
            _dbg(f"Scalp scanner error: {e}")
        await asyncio.sleep(2)


# ── SCALP_WATCH: Independent DEXScreener bounce scanner ──────────────────────

_scalp_watch_blacklist: dict = {}  # mint → expiry timestamp

async def scalp_ai_monitor(session):
    """Every 2 min: AI reviews last 10 scalp exits and adjusts TP/heat thresholds."""
    global SCALP_MIN_HEAT, SCALP_HARD_TP_PCT
    _dbg("Scalp AI monitor started")
    await asyncio.sleep(120)  # wait for initial trades
    while not STATE.should_exit:
        try:
            if not STATE.scalp_enabled:
                await asyncio.sleep(120); continue

            # Collect last 10 scalp exits
            scalp_closed = [p for p in STATE.sim_closed if p.strategy == "SCALP"][-10:]
            if len(scalp_closed) < 5:
                await asyncio.sleep(120); continue

            tp_wins = sum(1 for p in scalp_closed if "TP" in p.exit_reason)
            heat_drops = sum(1 for p in scalp_closed if "HEAT" in p.exit_reason)
            dead_tokens = sum(1 for p in scalp_closed if "DEAD" in p.exit_reason or "NO_PRICE" in p.exit_reason)
            timeouts = sum(1 for p in scalp_closed if "FLAT" in p.exit_reason or "TIME" in p.exit_reason)
            avg_heat = sum(p.heat_score for p in scalp_closed) / len(scalp_closed) if scalp_closed else 0

            try:
                if not GROQ_API_KEY: raise ImportError("no key")
                from groq import Groq
                client = Groq(api_key=GROQ_API_KEY)
                response = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=100,
                    messages=[
                        {"role": "system", "content": "Trading bot optimizer. Return ONLY valid JSON: {\"action\":\"adjust_tp|adjust_min_heat|none\",\"new_tp\":float,\"new_min_heat\":int,\"reason\":\"string\"}"},
                        {"role": "user", "content":
                            f"Last 10 scalp exits: TP_wins:{tp_wins} heat_drops:{heat_drops} "
                            f"dead:{dead_tokens} timeouts:{timeouts} avg_entry_heat:{avg_heat:.0f} "
                            f"Current TP:{SCALP_HARD_TP_PCT}% min_heat:{SCALP_MIN_HEAT} market:{STATE.market_state}"}
                    ]
                )
                STATE.ai_calls_today += 1
                import json as _json
                text = response.choices[0].message.content.strip()
                decision = _json.loads(text)
                action = decision.get("action", "none")

                if action == "adjust_tp" and "new_tp" in decision:
                    new_tp = max(0.5, min(3.0, float(decision["new_tp"])))
                    old_tp = SCALP_HARD_TP_PCT
                    SCALP_HARD_TP_PCT = new_tp
                    _dbg(f"AI_2MIN: TP {old_tp}→{new_tp} reason: {decision.get('reason','')}")
                    STATE.recent_activity.append(f"AI: TP {old_tp}→{new_tp}")
                elif action == "adjust_min_heat" and "new_min_heat" in decision:
                    new_heat = max(40, min(80, int(decision["new_min_heat"])))
                    old_heat = SCALP_MIN_HEAT
                    SCALP_MIN_HEAT = new_heat
                    _dbg(f"AI_2MIN: heat_min {old_heat}→{new_heat} reason: {decision.get('reason','')}")
                    STATE.recent_activity.append(f"AI: heat_min {old_heat}→{new_heat}")
                else:
                    _dbg(f"AI_2MIN: no change — {decision.get('reason','optimal')}")

            except ImportError:
                _dbg("AI monitor: anthropic not installed")
            except Exception as e:
                _dbg(f"AI monitor error: {type(e).__name__}: {e}")

        except Exception as e:
            _dbg(f"Scalp AI error: {e}")
        await asyncio.sleep(120)


# ── Established Token Scalper (24/7 volume) ──────────────────────────────────
# ── Momentum trading tokens (high liquidity, any direction) ──────────────────
# 28 tokens across majors, DeFi, infra, DePIN, and memes.
# Deep liquidity on Jupiter/Raydium — zero slippage on $1,500 positions.
# No wash sale rule on crypto = harvest losses and re-enter freely.
# ── GRID TRADING (replaces MOMENTUM — research-backed) ───────────────────────
# Buy at grid levels below price, sell at grid levels above. Profit from oscillation.
# Breakeven: 0.55% round-trip (Rule 1). Grid spacing 1.5% → 0.95% profit per cycle.
GRID_TOKENS = {
    # Infrastructure — oscillate in ranges, deep liquidity (best for grid)
    "PYTH":     "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
    "ORCA":     "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
    "HNT":      "hntyVP6YFm1Hg25TN9WGLqM12b8TQmcknKrdu1oxWux",
    "W":        "85VBFQZC9TZkfaptBWjvUw7YbZjy52A6mjtPGjstQAmQ",
    "JUP":      "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "RAY":      "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "JTO":      "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
    # Mid-cap range-bound tokens
    "TNSR":     "TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6",
    "NOS":      "nosXBVoaCTtYdLvKY6Csb4AC8JCdQKKAaWYtx2ZMoo7",
    "MNDE":     "MNDEFzGvMt87ueuHvVU9VcTqsAP5b3fTGPsHuuPA5ey",
    "MOBILE":   "mb1eu7TzEc71KxDpsmsKoucSSuuoGLv1drys1oP2jh6",
    "DRIFT":    "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7",
    # EXCLUDED: wBTC/wETH/SOL (Rule 15 — SOL-denominated price issues)
    # EXCLUDED: BONK/WIF/PENGU/TRUMP (trend too hard — bad for grid)
    # EXCLUDED: USDC/USDT (stablecoins don't oscillate)
}
GRID_SPACING_PCT      = 1.5       # 1.5% between levels (0.95% profit per cycle after 0.55% fees)
GRID_LEVELS           = 5         # 5 buy + 5 sell = 10 levels per token
GRID_SOL_PER_LEVEL    = 0.5       # sim mode: 0.5 SOL per level (Rule 5)
GRID_RECENTER_PCT     = 5.0       # recenter grid if price drifts 5% from center
GRID_MAX_TOKENS       = 8         # max tokens with active grids
GRID_CHECK_SEC        = 10        # check every 10s (same as old MOMENTUM)
# Keep MOMENTUM constants for exit logic compatibility
MOMENTUM_TOKENS = GRID_TOKENS     # backwards compat
MOMENTUM_ENTRY_SOL    = GRID_SOL_PER_LEVEL
MOMENTUM_SL_PCT       = -3.0      # grid SL: -3% below entry (wider than momentum — grid expects oscillation)
MOMENTUM_TP_PCT       = GRID_SPACING_PCT  # grid TP = one grid level
MOMENTUM_MAX_HOLD_SEC = 3600      # 1 hour — grid holds until next level hit
MOMENTUM_CHECK_SEC    = GRID_CHECK_SEC
MOMENTUM_MAX_POSITIONS = GRID_MAX_TOKENS * GRID_LEVELS  # up to 40 grid fills across all tokens
ESTAB_TOKENS = GRID_TOKENS

# ── GMGN Smart Money Wallet Finder ────────────────────────────────────────────
GMGN_SMART_WALLETS_FILE = os.path.join(_BASE, "smart_wallets.json")

async def gmgn_wallet_finder(session):
    """Periodically scrape GMGN.ai for profitable wallets.
    NOTE: GMGN blocks non-browser requests. Needs tls_client for fingerprint spoofing.
    Currently disabled — run Dragon CLI separately to populate smart_wallets.json."""
    _dbg("GMGN wallet finder: requires tls_client (run Dragon CLI separately)")
    return  # GMGN blocks aiohttp — needs tls_client fingerprint spoofing
    _dbg("GMGN wallet finder started")
    await asyncio.sleep(60)
    while not STATE.should_exit:
        try:
            smart_wallets = []
            # Get top traders from soaring tokens
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
                       "Accept": "application/json"}
            # Soaring tokens
            url = ("https://gmgn.ai/defi/quotation/v1/rank/sol/pump/1h"
                   "?limit=10&orderby=market_cap_5m&direction=desc&soaring=true")
            try:
                async with session.get(url, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 200:
                        data = await r.json(content_type=None)
                        tokens = data.get("data", {}).get("rank", [])
                        for tok in tokens[:5]:
                            ca = tok.get("address", "")
                            if not ca: continue
                            # Get top traders for this token
                            turl = f"https://gmgn.ai/vas/api/v1/token_traders/sol/{ca}?orderby=realized_profit&direction=desc&limit=20"
                            try:
                                async with session.get(turl, headers=headers,
                                        timeout=aiohttp.ClientTimeout(total=10)) as r2:
                                    if r2.status == 200:
                                        td = await r2.json(content_type=None)
                                        for trader in (td.get("data", {}).get("items", []) or [])[:10]:
                                            wallet = trader.get("address", "")
                                            profit = trader.get("realized_profit", 0)
                                            if wallet and profit and float(profit) > 100:
                                                smart_wallets.append({
                                                    "address": wallet,
                                                    "profit": float(profit),
                                                    "source": "gmgn_soaring"
                                                })
                            except: pass
                            await asyncio.sleep(2)
                    else:
                        _dbg(f"GMGN: status {r.status}")
            except Exception as e:
                _dbg(f"GMGN soaring error: {e}")

            # Deduplicate by address, keep highest profit
            seen = {}
            for w in smart_wallets:
                addr = w["address"]
                if addr not in seen or w["profit"] > seen[addr]["profit"]:
                    seen[addr] = w
            unique = sorted(seen.values(), key=lambda x: -x["profit"])[:50]

            if unique:
                # Save to file
                _save_json(GMGN_SMART_WALLETS_FILE, unique)
                # Add top wallets to watch list if not already there
                new_added = 0
                for w in unique[:20]:
                    addr = w["address"]
                    if addr not in WATCH_WALLETS:
                        WATCH_WALLETS.append(addr)
                        new_added += 1
                if new_added:
                    _dbg(f"GMGN: added {new_added} smart wallets (total watching: {len(WATCH_WALLETS)})")
                    STATE.recent_activity.append(f"GMGN: +{new_added} smart wallets")
                STATE.creator_stats["_gmgn_count"] = {"launches": len(unique)}

        except Exception as e:
            _dbg(f"GMGN finder error: {e}")
        await asyncio.sleep(1800)  # every 30 minutes


# ── DEXScreener WebSocket Streaming ──────────────────────────────────────────

async def dexscreener_ws_stream(session):
    """Stream trending Solana pairs from DEXScreener WebSocket.
    NOTE: DEXScreener WS requires socket.io handshake — plain WS gets 403.
    Disabled — using HTTP polling instead (already working in scalp_watch_loop)."""
    _dbg("DEX WS: requires socket.io (using HTTP polling instead)")
    return  # DEXScreener blocks plain WebSocket — needs socket.io protocol
    _dbg("DEXScreener WS stream starting")
    await asyncio.sleep(15)

    while not STATE.should_exit:
        try:
            url = ("wss://io.dexscreener.com/dex/screener/pairs/h24/1"
                   "?rankBy[key]=trendingScoreH6&rankBy[order]=desc")
            extra_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Origin": "https://dexscreener.com",
            }
            async with websockets.connect(url, ping_interval=30, ping_timeout=15,
                    extra_headers=extra_headers) as ws:
                _dbg("DEXScreener WS connected")
                STATE.recent_activity.append("DEX WS: streaming")

                async for raw in ws:
                    if STATE.should_exit: return
                    try:
                        msg = json.loads(raw)
                        if msg.get("type") != "pairs": continue
                        pairs = msg.get("pairs", [])

                        for pair in pairs:
                            if pair.get("chainId") != "solana": continue
                            mint = pair.get("baseToken", {}).get("address", "")
                            if not mint: continue

                            chg_m5 = pair.get("priceChange", {}).get("m5", 0) or 0
                            txns = pair.get("txns", {}).get("m5", {})
                            buys = txns.get("buys", 0) or 0
                            sells = txns.get("sells", 0) or 0
                            liq = pair.get("liquidity", {}).get("usd", 0) or 0
                            vol_m5 = pair.get("volume", {}).get("m5", 0) or 0

                            # Check if this is a scalp opportunity
                            if chg_m5 < 0.3 or chg_m5 > 8: continue
                            if liq < 5000: continue
                            if buys + sells < 10: continue
                            if sells > 0 and buys < sells * 1.3: continue

                            scalp_key = f"SCALP_{mint}"
                            if scalp_key in STATE.sim_positions: continue
                            if mint in STATE.sim_positions: continue
                            if mint in _scalp_watch_blacklist: continue
                            if _strategy_count("SCALP") >= SCALP_MAX_POSITIONS: continue

                            heat = buys / (buys + sells) * 100 if buys + sells > 0 else 50
                            if heat < 50: continue

                            # Get price
                            price_usd = float(pair.get("priceUsd", 0) or 0)
                            if price_usd <= 0 or STATE.sol_price_usd <= 0: continue
                            price_sol = price_usd / STATE.sol_price_usd
                            symbol = pair.get("baseToken", {}).get("symbol", "?")[:12]

                            # Check balance + loss limits
                            if STATE.balance_sol < SCALP_ENTRY_SOL: continue
                            if not _check_loss_limits(): continue

                            # AI decision
                            ai_result = await ai_should_enter({
                                "symbol": symbol, "heat": heat, "chg_m5": chg_m5,
                                "vol": vol_m5, "liq": liq, "buys": buys, "sells": sells})
                            if ai_result.get("action") == "SKIP": continue
                            scalp_size = ai_result.get("amount_sol", SCALP_ENTRY_SOL)

                            sp = SimPosition(
                                symbol=symbol, name=symbol, mint=mint,
                                category="SCALP", score=75,
                                entry_time=time.monotonic(),
                                entry_ts=datetime.now().strftime("%H:%M:%S"),
                                entry_price_sol=price_sol, entry_sol=scalp_size,
                                current_price_sol=price_sol, peak_price_sol=price_sol,
                                trough_price_sol=price_sol,
                                initial_liq_sol=liq / STATE.sol_price_usd,
                                remaining_sol=scalp_size, strategy="SCALP",
                                confidence="MED", size_reason="DEX_WS",
                                price_source="DEX", graduated=True,
                                heat_score=heat,
                                heat_pattern="HEATING" if heat > 60 else "WARM",
                                heat_at_entry=heat)
                            STATE.balance_sol -= scalp_size
                            STATE.sim_positions[scalp_key] = sp
                            STATE.total_opened += 1
                            STATE.scalp_trades_today += 1
                            STATE.scalp_trade_times.append(time.time())
                            STATE.recent_activity.append(
                                f"DEX_WS: {symbol} +{chg_m5:.1f}% B:{buys}")
                            _dbg(f"DEX_WS_OPEN: {symbol} chg={chg_m5:+.1f}% "
                                 f"heat={heat:.0f} buys={buys}")

                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        _dbg(f"DEX WS parse: {e}")

        except Exception as e:
            _dbg(f"DEX WS error: {type(e).__name__}: {e}")
            await asyncio.sleep(10)


async def estab_token_scalper(session):
    """HIGH-FREQUENCY SWING TRADER on established tokens.
    Buys dips, sells bounces, repeats all day. No wash sale rule = unlimited cycles.
    27 tokens × 3-5 cycles/day = 80-135 trades. +1.5% avg win at 40% WR = profit.
    Uses 1-minute candle data built from 10s polls for pattern detection."""
    # GRID TRADING ENGINE — buy at grid levels below price, sell at levels above.
    # Profits from natural price oscillation. No need to predict direction.
    _dbg(f"GRID TRADER started — {len(GRID_TOKENS)} tokens, {GRID_LEVELS} levels, {GRID_SPACING_PCT}% spacing")
    _grid_state: dict = {}   # mint → {center, buy_levels, sell_targets, positions}
    _grid_candles: dict = {} # mint → [{"o","h","l","c","t"}, ...] for regime detection
    _grid_ticks: dict = {}   # mint → [(time, price)] buffer for candles
    _grid_last_min: dict = {}
    _grid_profit = 0.0
    _grid_cycles = 0

    await asyncio.sleep(15)
    while not STATE.should_exit:
        try:
            if not STATE.scalp_enabled:
                await asyncio.sleep(10); continue

            now = time.time()
            now_min = int(now // 60)

            # ── Batch price fetch (Rule 11: batch, don't spam) ──
            all_mints = list(GRID_TOKENS.values())
            prices = {}
            if JUP_API_KEY:
                prices = await jupiter_get_prices_batch(session, all_mints)
            if len(prices) < len(all_mints) // 2:
                dex_data = await _dex_fetch_json(session,
                    f"https://api.dexscreener.com/tokens/v1/solana/{','.join(all_mints[:30])}")
                if dex_data and isinstance(dex_data, list):
                    for pair in dex_data:
                        pm = pair.get("baseToken", {}).get("address", "")
                        pu = float(pair.get("priceUsd", 0) or 0)
                        if pm and pu > 0 and STATE.sol_price_usd > 0 and pm not in prices:
                            prices[pm] = pu / STATE.sol_price_usd

            # ── Build 1-minute candles for regime detection ──
            for name, mint in GRID_TOKENS.items():
                price_sol = prices.get(mint, 0)
                if price_sol <= 0: continue
                if mint not in _grid_ticks: _grid_ticks[mint] = []
                _grid_ticks[mint].append((now, price_sol))
                last_min = _grid_last_min.get(mint, 0)
                if now_min > last_min and len(_grid_ticks[mint]) >= 2:
                    ticks = _grid_ticks[mint]
                    candle = {"o": ticks[0][1], "h": max(t[1] for t in ticks),
                              "l": min(t[1] for t in ticks), "c": ticks[-1][1], "t": now_min}
                    if mint not in _grid_candles: _grid_candles[mint] = []
                    _grid_candles[mint].append(candle)
                    _grid_candles[mint] = _grid_candles[mint][-60:]
                    _grid_ticks[mint] = [(now, price_sol)]
                    _grid_last_min[mint] = now_min

            # ── Process each grid token ──
            active_grids = 0
            for name, mint in GRID_TOKENS.items():
                if STATE.should_exit: return
                price_sol = prices.get(mint, 0)
                if price_sol <= 0: continue  # Rule 10: never trade without verified price

                # Initialize grid for this token
                if mint not in _grid_state:
                    if active_grids >= GRID_MAX_TOKENS: continue
                    _grid_state[mint] = {
                        "symbol": name, "center": price_sol,
                        "positions": [],  # [{entry_price, sol, time, level_idx}]
                    }
                    # Calculate buy levels (below current price)
                    ratio = 1 + (GRID_SPACING_PCT / 100)
                    levels = []
                    for i in range(1, GRID_LEVELS + 1):
                        levels.append(round(price_sol / (ratio ** i), 12))
                    _grid_state[mint]["buy_levels"] = levels
                    _dbg(f"GRID_INIT: {name} center={price_sol:.8f} levels={GRID_LEVELS} spacing={GRID_SPACING_PCT}%")

                gs = _grid_state[mint]
                active_grids += 1

                # Regime check: skip grid if token is trending hard (>8% range in 20 candles)
                candles = _grid_candles.get(mint, [])
                if len(candles) >= 20:
                    c_prices = [c["c"] for c in candles[-20:]]
                    band = (max(c_prices) - min(c_prices)) / min(c_prices) * 100 if min(c_prices) > 0 else 0
                    if band > 8.0:
                        # Token is trending — don't open new grid levels, but keep existing
                        continue

                # ── Check BUY levels: price dropped to a grid level ──
                for i, level_price in enumerate(gs["buy_levels"]):
                    if price_sol <= level_price:
                        # Check we don't already have a position at this level
                        already_filled = any(p["level_idx"] == i for p in gs["positions"])
                        if already_filled: continue
                        # Capital check (Rule 10: verify before entering)
                        if STATE.balance_sol < GRID_SOL_PER_LEVEL: continue
                        if not _check_loss_limits(): continue

                        # Open grid position
                        grid_key = f"GRID_{mint}_{i}"
                        if grid_key in STATE.sim_positions: continue

                        sp = SimPosition(
                            symbol=name, name=f"{name}_G{i+1}", mint=mint,
                            category="GRID", score=80,
                            entry_time=time.monotonic(),
                            entry_ts=datetime.now().strftime("%H:%M:%S"),
                            entry_price_sol=price_sol, entry_sol=GRID_SOL_PER_LEVEL,
                            current_price_sol=price_sol, peak_price_sol=price_sol,
                            trough_price_sol=price_sol,
                            initial_liq_sol=1000, remaining_sol=GRID_SOL_PER_LEVEL,
                            strategy="MOMENTUM", confidence="HIGH", size_reason="GRID",
                            price_source="DEX", graduated=True,
                            heat_score=50, heat_pattern="WARM", heat_at_entry=50)
                        STATE.balance_sol -= GRID_SOL_PER_LEVEL
                        STATE.sim_positions[grid_key] = sp
                        STATE.total_opened += 1
                        gs["positions"].append({
                            "entry_price": price_sol, "sol": GRID_SOL_PER_LEVEL,
                            "time": now, "level_idx": i, "key": grid_key,
                        })
                        STATE.recent_activity.append(
                            f"GRID_BUY: {name} L{i+1} @{price_sol:.8f}")
                        _dbg(f"GRID_BUY: {name} level={i+1} price={price_sol:.10f}")

                # ── Check SELL: price rose grid_pct above any filled position ──
                for pos in list(gs["positions"]):
                    target = pos["entry_price"] * (1 + GRID_SPACING_PCT / 100)
                    if price_sol >= target:
                        grid_key = pos["key"]
                        if grid_key in STATE.sim_positions:
                            p = STATE.sim_positions[grid_key]
                            # Profit = grid spacing minus fees (Rule 1: verified > breakeven)
                            profit_pct = GRID_SPACING_PCT - 0.55  # net after 0.55% round-trip
                            close_position(p, f"GRID_SELL(+{GRID_SPACING_PCT}% L{pos['level_idx']+1})", price_sol)
                            _grid_profit += p.profit_sol
                            _grid_cycles += 1
                            STATE.recent_activity.append(
                                f"GRID_SELL: {name} L{pos['level_idx']+1} +{GRID_SPACING_PCT}% (cycle#{_grid_cycles})")
                            _dbg(f"GRID_SELL: {name} level={pos['level_idx']+1} "
                                 f"profit={p.profit_sol:+.4f} total_grid={_grid_profit:+.4f} cycles={_grid_cycles}")
                        gs["positions"].remove(pos)

                # ── Recenter grid if price drifted too far ──
                drift_pct = abs(price_sol - gs["center"]) / gs["center"] * 100 if gs["center"] > 0 else 0
                if drift_pct > GRID_RECENTER_PCT:
                    gs["center"] = price_sol
                    ratio = 1 + (GRID_SPACING_PCT / 100)
                    gs["buy_levels"] = [round(price_sol / (ratio ** i), 12) for i in range(1, GRID_LEVELS + 1)]
                    _dbg(f"GRID_RECENTER: {name} new_center={price_sol:.8f} drift={drift_pct:.1f}%")

        except Exception as e:
            _dbg(f"Grid trader error: {e}")
        await asyncio.sleep(GRID_CHECK_SEC)


async def scalp_watch_loop(session):
    """Scan DEXScreener every 10s for existing tokens bouncing up.
    Opens SCALP positions on tokens with confirmed upward momentum.
    Runs 24/7 including off-hours — this is where overnight scalp thrives."""
    _dbg("SCALP_WATCH started")
    STATE.recent_activity.append("SCALP_WATCH: scanning")
    backoff = 0
    watch_trades = 0

    await asyncio.sleep(15)
    while not STATE.should_exit:
        try:
            if not STATE.scalp_enabled:
                await asyncio.sleep(10); continue

            # Backoff on rate limit
            if backoff > 0:
                await asyncio.sleep(backoff)
                backoff = 0

            # Poll DEXScreener — boosts + Solana-wide search
            tokens_found = []
            for url in [
                "https://api.dexscreener.com/token-boosts/latest/v1",
                "https://api.dexscreener.com/token-boosts/top/v1",
            ]:
                data = await _dex_fetch_json(session, url)
                if data is None:
                    backoff = min(backoff + 30, 120)
                    continue
                if isinstance(data, list):
                    tokens_found.extend(data)
                await asyncio.sleep(1)

            # ── Solana-wide gainers scan (one query per cycle to avoid rate limits) ──
            _wide_queries = ["solana trending", "raydium sol", "pumpswap", "solana meme", "sol pump", "solana new"]
            _wide_idx = getattr(scalp_watch_loop, '_qidx', 0)
            search_q = _wide_queries[_wide_idx % len(_wide_queries)]
            scalp_watch_loop._qidx = _wide_idx + 1
            sdata = await _dex_fetch_json(session,
                f"https://api.dexscreener.com/latest/dex/search?q={search_q}")
            if sdata:
                for sp in sdata.get("pairs", []):
                    if sp.get("chainId") != "solana": continue
                    sm = sp.get("baseToken", {}).get("address", "")
                    if not sm: continue
                    tokens_found.append({
                        "chainId": "solana",
                        "tokenAddress": sm,
                        "baseToken": sp.get("baseToken", {}),
                        "priceUsd": sp.get("priceUsd", 0),
                        "priceChange": sp.get("priceChange", {}),
                        "volume": sp.get("volume", {}),
                        "liquidity": sp.get("liquidity", {}),
                        "txns": sp.get("txns", {}),
                        "fdv": sp.get("fdv", 0),
                        "marketCap": sp.get("marketCap", 0),
                    })

            # Clean expired blacklist entries
            now = time.time()
            expired = [m for m, exp in _scalp_watch_blacklist.items() if now > exp]
            for m in expired: del _scalp_watch_blacklist[m]

            # Determine thresholds based on market state
            if STATE.market_state == "HOT":
                min_chg = 1.0; min_vol_usd = 2.0 * STATE.sol_price_usd
            elif STATE.market_state in ("DEAD", "SLOW"):
                min_chg = 0.2; min_vol_usd = 0.3 * STATE.sol_price_usd
            else:
                min_chg = 0.3; min_vol_usd = 0.5 * STATE.sol_price_usd

            opened = 0
            for token in tokens_found:
                if STATE.should_exit: return
                if _strategy_count("SCALP") >= SCALP_MAX_POSITIONS: break
                if not STATE.scalp_enabled: break

                chain = token.get("chainId", "")
                if chain != "solana": continue

                mint = (token.get("tokenAddress", "") or
                        token.get("baseToken", {}).get("address", ""))
                if not mint: continue
                if mint in _scalp_watch_blacklist: continue

                # Check not already in any position
                scalp_key = f"SCALP_{mint}"
                if scalp_key in STATE.sim_positions: continue
                if mint in STATE.sim_positions: continue

                # Use inline pair data if available (from search results), else fetch
                if token.get("priceChange") or token.get("volume"):
                    pair = token  # search results already have pair data
                else:
                    # Boost tokens don't have pair data — use Jupiter for price instead
                    jup_price = await jupiter_get_price(session, mint)
                    if jup_price <= 0: continue
                    # Minimal pair stub — we have price, skip detailed DEX fetch
                    pair = {"priceUsd": str(jup_price * STATE.sol_price_usd),
                            "priceChange": {}, "volume": {}, "liquidity": {},
                            "txns": {"m5": {}}, "baseToken": token.get("baseToken", {})}

                # Filter conditions
                chg_m5 = pair.get("priceChange", {}).get("m5", 0) if isinstance(pair.get("priceChange"), dict) else 0
                chg_m5 = float(chg_m5 or 0)
                vol_m5 = pair.get("volume", {}).get("m5", 0) if isinstance(pair.get("volume"), dict) else 0
                vol_m5 = float(vol_m5 or 0)
                liq_usd = pair.get("liquidity", {}).get("usd", 0) if isinstance(pair.get("liquidity"), dict) else 0
                liq_usd = float(liq_usd or 0)
                txns = pair.get("txns", {}).get("m5", {}) if isinstance(pair.get("txns"), dict) else {}
                buys = int(txns.get("buys", 0) or 0)
                sells = int(txns.get("sells", 0) or 0)

                # All conditions must pass
                if chg_m5 < 1.0: continue  # MUST be going UP +1% in 5 min — no buying into flat/falling tokens
                if chg_m5 > 50.0: continue  # already pumped too much — chasing

                # Quality filters — at 3 max positions, keep it simple
                min_liq = 10000
                min_txns = 10
                min_heat_entry = 50

                if liq_usd < min_liq and liq_usd > 0: continue  # 0 = no data, let through
                if sells > 0 and buys > 0 and buys < sells * 1.2: continue  # slight buy pressure enough
                if buys + sells > 0 and buys + sells < min_txns: continue  # 0 = no data from boost tokens

                # Get price + symbol
                price_usd = float(pair.get("priceUsd", 0) or 0)
                if price_usd <= 0 or STATE.sol_price_usd <= 0: continue
                price_sol = price_usd / STATE.sol_price_usd
                symbol = pair.get("baseToken", {}).get("symbol", "?")[:12]

                # Skip blacklisted large-cap tokens that don't move enough
                if symbol.upper() in SCALP_BLACKLIST: continue

                # Skip tokens outside mcap range
                mcap = float(pair.get("marketCap", 0) or pair.get("fdv", 0) or 0)
                if mcap > SCALP_MAX_MCAP or mcap < SCALP_MIN_MCAP: continue

                # Skip tokens that haven't moved enough in 5 min
                if chg_m5 < SCALP_MIN_5M_CHANGE: continue

                # Capital check
                if STATE.balance_sol < SCALP_ENTRY_SOL: break
                if not _check_loss_limits(): break

                # Calculate heat proxy from buy/sell ratio
                heat_proxy = (buys / (buys + sells) * 100) if (buys + sells) > 0 else 50
                heat_pat = ("ROCKET" if heat_proxy >= 80 else "HEATING" if heat_proxy >= 60
                            else "WARM" if heat_proxy >= 40 else "COLD")
                if heat_proxy < min_heat_entry: continue

                # Token similarity check — avoid buying copycats
                if _is_similar_token(symbol):
                    continue

                # Verify price is trackable (Jupiter → DEXScreener fallback)
                verify_price, _vsrc = await get_universal_price(session, mint)
                if verify_price <= 0:
                    _scalp_watch_blacklist[mint] = time.time() + 300
                    continue
                price_sol = verify_price  # use verified universal price

                # AI decision on entry + sizing
                ai_result = await ai_should_enter({
                    "symbol": symbol, "heat": heat_proxy, "chg_m5": chg_m5,
                    "vol": vol_m5, "liq": liq_usd, "buys": buys, "sells": sells})
                if ai_result.get("action") == "SKIP":
                    continue  # AI says skip
                scalp_size = ai_result.get("amount_sol", SCALP_ENTRY_SOL)
                conf = "HIGH" if ai_result.get("confidence", 50) >= 80 else "MED" if ai_result.get("confidence", 50) >= 60 else "LOW"

                if STATE.balance_sol < scalp_size: break

                sp = SimPosition(
                    symbol=symbol, name=symbol, mint=mint,
                    category="SCALP", score=75,
                    entry_time=time.monotonic(),
                    entry_ts=datetime.now().strftime("%H:%M:%S"),
                    entry_price_sol=price_sol, entry_sol=scalp_size,
                    current_price_sol=price_sol, peak_price_sol=price_sol,
                    trough_price_sol=price_sol,
                    initial_liq_sol=liq_usd / STATE.sol_price_usd if STATE.sol_price_usd else 30,
                    remaining_sol=scalp_size, strategy="SCALP",
                    confidence=conf, size_reason="WATCH",
                    price_source="DEX", graduated=True,
                    heat_score=heat_proxy, heat_pattern=heat_pat,
                    heat_at_entry=heat_proxy)
                STATE.balance_sol -= scalp_size
                STATE.sim_positions[scalp_key] = sp
                STATE.total_opened += 1
                STATE.scalp_trades_today += 1
                STATE.scalp_trade_times.append(time.time())
                watch_trades += 1
                opened += 1

                STATE.recent_activity.append(
                    f"WATCH: {symbol} +{chg_m5:.1f}% B:{buys}/S:{sells}")
                _dbg(f"SCALP_WATCH_OPEN: {symbol} chg5m={chg_m5:+.1f}% "
                     f"buys={buys} sells={sells} vol=${vol_m5:.0f} "
                     f"price={price_sol:.10f}")

                await asyncio.sleep(1)  # stagger entries

            if opened:
                _dbg(f"SCALP_WATCH: opened {opened} positions this scan")

        except Exception as e:
            _dbg(f"SCALP_WATCH error: {e}")
        await asyncio.sleep(SCALP_WATCH_INTERVAL)  # 7s scan cycle


async def process_new_coin(session, coin, prefire_source=""):
    mint = coin.get("mint", "")
    if not mint or mint in STATE.seen_mints: return
    STATE.seen_mints.add(mint)
    created_ts = coin.get("created_timestamp")
    if created_ts:
        try:
            created = created_ts/1000.0 if created_ts > 1e12 else float(created_ts)
            if time.time() - created < MIN_TOKEN_AGE_SEC: return
        except: pass

    sc = await run_safety_check(session, coin)
    symbol = coin.get("symbol", "?")[:12]

    # Skip if RugCheck flags DANGER (bypassed in HFT — timeout is the protection)
    if sc.rugcheck_status == "Danger" and not STATE.hft_enabled:
        _dbg(f"SKIP {symbol}: RugCheck DANGER"); return

    # Skip if bot-dominated
    if sc.bot_dominated:
        STATE.skipped_bots += 1
        _dbg(f"SKIP {symbol}: bot-dominated trading"); return

    STATE.tokens_found += 1; STATE.last_disc_time = datetime.now().strftime("%H:%M:%S")
    log_new_token_csv(mint, symbol, sc)
    # Track for morning report
    if STATE.overnight_active:
        STATE.overnight_tokens.append({
            "symbol": symbol, "mint": mint, "score": sc.score,
            "bc": calc_bc_progress(coin) if coin else 0,
            "liq": sc.liquidity_sol, "time": datetime.now().isoformat()})
    if mint not in STATE.sim_positions:
        await open_sim_position(session, coin, sc, prefire_source=prefire_source)


# ══════════════════════════════════════════════════════════════════════════════
# ██  GEYSER WEBSOCKET (fastest detection: ~50ms from block)  ██████████████████
# ══════════════════════════════════════════════════════════════════════════════

async def _geyser_process_graduation(session, mint: str):
    """Handle a graduation event — convert NEAR_GRAD or open GRAD_SNIPE."""
    try:
        if mint in STATE.sim_positions:
            p = STATE.sim_positions[mint]
            if p.strategy == "NEAR_GRAD" and p.status == "OPEN":
                p.strategy = "GRAD_SNIPE"
                p.graduated = True
                p.signals.append("CONVERTED_GRAD")
                STATE.recent_activity.append(f"CONV: {p.symbol} NEAR_GRAD->GRAD_SNIPE")
                _dbg(f"GRAD_CONV: {p.symbol} NEAR_GRAD->GRAD_SNIPE")
                return
        await open_grad_snipe_position(session, mint, 0)
    except Exception as e:
        _dbg(f"GRAD_PROC_ERR: {mint[:16]} {e}")

async def _geyser_process_mint(session, mint: str, t_detect: int):
    """Process a single mint detected by Geyser. Runs as a background task
    so the Geyser loop doesn't block on RPC calls."""
    try:
        # Single attempt — no retries. BC data is on-chain, available immediately.
        coin = await fetch_pump_coin(session, mint)
        if not coin:
            _dbg(f"GEYSER_NOBC: {mint[:20]} no bonding curve")
            return
        _dbg(f"GEYSER_OK: {coin.get('symbol','?')} {mint[:20]} "
             f"vSOL={coin.get('virtual_sol_reserves',0)//LAMPORTS_PER_SOL}SOL")
        pf = STATE.prefire_list.get(mint)
        await process_new_coin_timed(
            session, coin,
            prefire_source=",".join(pf.sources) if pf else "",
            detect_start_ns=t_detect,
            source="GEYSER")
    except Exception as e:
        _dbg(f"GEYSER_PROC_ERR: {mint[:16]} {e}")


async def geyser_token_listener(session):
    """Subscribe to pump.fun via Helius Enhanced WebSocket (transactionSubscribe).
    Tries standard WS endpoint first (works on Developer tier), then atlas
    endpoint (Business tier). If both fail, logs and exits gracefully —
    the logsSubscribe fallback handles detection."""
    if not GEYSER_WS_URL:
        _dbg("Geyser disabled: no WS URL")
        return
    await asyncio.sleep(2)

    # Try endpoints in order: standard first, then atlas
    endpoints = [GEYSER_WS_URL]
    if GEYSER_WS_ATLAS and GEYSER_WS_ATLAS != GEYSER_WS_URL:
        endpoints.append(GEYSER_WS_ATLAS)

    geyser_failures = 0

    while not STATE.should_exit:
        await _wait_if_rate_limited()
        # Cycle through endpoints
        url = endpoints[geyser_failures % len(endpoints)]
        try:
            _dbg(f"Geyser trying {url[:50]}...")
            async with websockets.connect(
                url, ping_interval=20, ping_timeout=30,
                max_size=10_000_000
            ) as ws:
                # Helius Enhanced WebSocket: transactionSubscribe
                # Filters for pump.fun program at processed commitment (fastest)
                sub_msg = json.dumps({
                    "jsonrpc": "2.0", "id": 420,
                    "method": "transactionSubscribe",
                    "params": [{
                        "accountInclude": [PUMP_PROGRAM_ID],  # migration handled by dedicated listener
                        "failed": False,
                    }, {
                        "commitment": "processed",
                        "encoding": "jsonParsed",
                        "transactionDetails": "full",
                        "showRewards": False,
                        "maxSupportedTransactionVersion": 0,
                    }],
                })
                await ws.send(sub_msg)
                ack = json.loads(await ws.recv())
                if "error" in ack:
                    _dbg(f"Geyser sub error: {ack.get('error')}")
                    await asyncio.sleep(10)
                    continue

                STATE.geyser_connected = True
                _dbg("Geyser connected (transactionSubscribe)")
                STATE.recent_activity.append("Geyser connected (fast mode)")

                async for raw in ws:
                    if STATE.should_exit:
                        return
                    t_detect = _t()
                    try:
                        msg = json.loads(raw)
                        if msg.get("method") != "transactionNotification":
                            continue

                        params = msg.get("params", {})
                        result = params.get("result", {})
                        tx_data = result.get("transaction", {})
                        sig = result.get("signature", "")
                        slot = tx_data.get("slot", 0)
                        if slot:
                            STATE.slot = slot

                        # Check for Create instruction in the transaction
                        meta = tx_data.get("meta", {})
                        tx_msg = tx_data.get("transaction", {})
                        logs = meta.get("logMessages", [])

                        if STATE.tokens_found < 3:
                            meta_keys = list(meta.keys()) if meta else []
                            tx_keys = list(tx_msg.keys()) if isinstance(tx_msg, dict) else []
                            ptb = meta.get("postTokenBalances", [])
                            _dbg(f"GEYSER_DBG: meta_keys={meta_keys} "
                                 f"tx_keys={tx_keys} "
                                 f"postTokenBal={len(ptb)} "
                                 f"logs={len(logs)} "
                                 f"result_keys={list(result.keys())}")

                        # Extract mint from the transaction.
                        mint = None

                        # Try postTokenBalances first (present in most modes)
                        for bal in meta.get("postTokenBalances", []):
                            m = bal.get("mint", "")
                            if m and m != "So11111111111111111111111111111111111111112":
                                mint = m; break

                        # Fallback: parse account keys for non-program addresses
                        if not mint:
                            msg_data = tx_msg.get("message", {})
                            for acc in msg_data.get("accountKeys", []):
                                pk = acc if isinstance(acc, str) else acc.get("pubkey", "")
                                if (pk and len(pk) >= 32 and
                                    pk not in (PUMP_PROGRAM_ID, PUMP_AMM_PROGRAM_ID,
                                               PUMP_FEE_PROGRAM_ID, PUMP_MINT_AUTH,
                                               "11111111111111111111111111111111",
                                               "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
                                               "SysvarRent111111111111111111111111111111111",
                                               "So11111111111111111111111111111111111111112",
                                               "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
                                               JITO_TIP_ACCOUNT)):
                                    mint = pk; break

                        if not mint:
                            _dbg(f"GEYSER_NOMINT: sig={sig[:12]} ptb={len(meta.get('postTokenBalances',[]))}")
                            continue
                        if mint in STATE.seen_mints:
                            continue  # already tracked

                        STATE.seen_mints.add(mint)
                        detect_ms = _ms_since(t_detect)
                        STATE.latency_detect_ms = detect_ms
                        _dbg(f"GEYSER_NEW: {mint} in {detect_ms:.1f}ms")
                        STATE.recent_activity.append(
                            f"GEY: {mint[:8]}.. {detect_ms:.0f}ms")

                        # Fire-and-forget: process in background so Geyser loop
                        # continues receiving new tokens without blocking
                        asyncio.create_task(
                            _geyser_process_mint(session, mint, t_detect)
                        )

                    except Exception as e:
                        _dbg(f"Geyser parse: {e}")

        except websockets.exceptions.ConnectionClosed:
            STATE.geyser_connected = False
            geyser_failures += 1
            _dbg("Geyser disconnected, reconnecting...")
            await asyncio.sleep(3)
        except Exception as e:
            STATE.geyser_connected = False
            geyser_failures += 1
            err_str = str(e)
            _dbg(f"Geyser FULL ERROR ({geyser_failures}): {type(e).__name__}: {err_str}")
            STATE.status_msg = f"GEY:RETRY({geyser_failures})"

            if "429" in err_str:
                # Rate limited — set global backoff so ALL connections stop
                wait = min(30 * geyser_failures, 120)
                _set_rate_limited(wait)
                await asyncio.sleep(wait)
            elif "403" in err_str or "Method not found" in err_str:
                # Try next endpoint but never give up
                _dbg(f"Geyser: endpoint rejected, trying next in 30s")
                await asyncio.sleep(30)
            else:
                wait = min(10 * min(geyser_failures, 6), 60)
                await asyncio.sleep(wait)


async def process_new_coin_timed(session, coin, prefire_source="",
                                  detect_start_ns=0, source="WS"):
    """Process a coin with latency benchmarking. Caller handles dedup.
    No age filter here — Geyser tokens are brand new by definition."""
    mint = coin.get("mint", "")
    if not mint:
        return
    symbol = coin.get("symbol", "?")[:12]

    # Safety check with timing
    t_safety = _t()
    sc = await run_safety_check(session, coin)
    safety_ms = _ms_since(t_safety)
    STATE.latency_safety_ms = safety_ms

    if sc.rugcheck_status == "Danger" and not STATE.hft_enabled:
        _dbg(f"SKIP {symbol}: RugCheck DANGER ({safety_ms:.0f}ms)"); return
    if sc.bot_dominated:
        STATE.skipped_bots += 1; return

    STATE.tokens_found += 1
    STATE.last_disc_time = datetime.now().strftime("%H:%M:%S")
    log_new_token_csv(mint, symbol, sc)

    # Open position with timing — route to strategy by BC progress
    t_open = _t()
    if mint not in STATE.sim_positions:
        bc_at_entry = calc_bc_progress(coin)
        # NEAR_GRAD disabled — lost 0.836 SOL, too risky pre-graduation
        if False:  # was: bc_at_entry >= 75.0
            await open_near_grad_position(session, coin, sc)
        else:
            await open_sim_position(session, coin, sc, prefire_source=prefire_source)
    open_ms = _ms_since(t_open)
    STATE.latency_open_ms = open_ms

    # Total latency
    total_ms = _ms_since(detect_start_ns) if detect_start_ns else 0
    STATE.latency_total_ms = total_ms
    STATE.latency_samples.append({
        "detect": STATE.latency_detect_ms,
        "safety": safety_ms,
        "open": open_ms,
        "total": total_ms,
        "source": source,
    })

    # Log to performance CSV
    detect_ms = STATE.latency_detect_ms
    log_perf(mint, symbol, detect_ms, 0, safety_ms, open_ms, total_ms, source)

    _dbg(f"PERF {symbol}: detect={detect_ms:.0f}ms safety={safety_ms:.0f}ms "
         f"open={open_ms:.0f}ms total={total_ms:.0f}ms src={source}")


# ── Discovery (logsSubscribe fallback) ────────────────────────────────────────
async def ws_token_listener(session):
    while not STATE.should_exit:
        await _wait_if_rate_limited()
        try:
            async with websockets.connect(HELIUS_WS_URL, ping_interval=20, ping_timeout=30) as ws:
                await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"logsSubscribe",
                    "params":[{"mentions":[PUMP_PROGRAM_ID]},{"commitment":"confirmed"}]}))
                ack = json.loads(await ws.recv())
                if "error" in ack: await asyncio.sleep(10); continue
                STATE.ws_connected = True; STATE.recent_activity.append("WS connected")
                async for raw in ws:
                    if STATE.should_exit: return
                    try:
                        msg = json.loads(raw)
                        if msg.get("method") != "logsNotification": continue
                        result = msg["params"]["result"]
                        value = result.get("value",{}); logs = value.get("logs",[])
                        sig = value.get("signature","")
                        slot = result.get("context",{}).get("slot",0)
                        if slot: STATE.slot = slot
                        if not any("Create" in l and "Instruction" in l for l in logs): continue
                        mint = await _extract_mint_from_tx(session, sig)
                        if not mint or mint in STATE.seen_mints: continue
                        STATE.recent_activity.append(f"WS: {mint[:8]}..")
                        await asyncio.sleep(2)
                        coin = await fetch_pump_coin(session, mint)
                        if not coin: await asyncio.sleep(5); coin = await fetch_pump_coin(session, mint)
                        if coin:
                            pf = STATE.prefire_list.get(mint)
                            await process_new_coin(session, coin,
                                prefire_source=",".join(pf.sources) if pf else "")
                    except Exception as e: _dbg(f"WS parse: {e}")
        except Exception as e:
            STATE.ws_connected = False
            if "429" in str(e):
                _set_rate_limited(60)
            wait = 60 if "429" in str(e) else 15
            _dbg(f"WS fallback error: {type(e).__name__}: {e}, retry in {wait}s")
            await asyncio.sleep(wait)

async def _extract_mint_from_tx(session, signature):
    try:
        r = await rpc_call(session, "getTransaction",
            [signature, {"encoding":"jsonParsed","maxSupportedTransactionVersion":0}])
        if not r: return None
        for bal in r.get("meta",{}).get("postTokenBalances",[]):
            m = bal.get("mint","")
            if m and m != "So11111111111111111111111111111111111111112": return m
        return None
    except: return None


# ── Migration Listener (logsSubscribe on migration wrapper) ──────────────────
async def migration_listener(session):
    """Dedicated WebSocket listener for pump.fun -> PumpSwap migrations.
    Monitors the migration wrapper program for 'Instruction: Migrate' logs.
    From chainstacklabs/pumpfun-bonkfun-bot research."""
    _dbg("Migration listener started")
    seen_migrations: set = set()

    while not STATE.should_exit:
        await _wait_if_rate_limited()
        try:
            async with websockets.connect(HELIUS_WS_URL,
                    ping_interval=20, ping_timeout=30) as ws:
                # Subscribe to migration wrapper program
                await ws.send(json.dumps({
                    "jsonrpc": "2.0", "id": 1,
                    "method": "logsSubscribe",
                    "params": [
                        {"mentions": [PUMP_MIGRATION_PROG]},
                        {"commitment": "processed"}
                    ]
                }))
                ack = json.loads(await ws.recv())
                if "error" in ack:
                    _dbg(f"Migration WS error: {ack}")
                    await asyncio.sleep(10); continue
                _dbg("Migration listener connected")
                STATE.recent_activity.append("Migration WS: connected")

                async for raw in ws:
                    if STATE.should_exit: return
                    try:
                        msg = json.loads(raw)
                        if msg.get("method") != "logsNotification": continue
                        logs = msg.get("params", {}).get("result", {}).get(
                            "value", {}).get("logs", [])
                        sig = msg.get("params", {}).get("result", {}).get(
                            "value", {}).get("signature", "")

                        # Skip errors
                        if any("AnchorError" in l or "Error" in l for l in logs):
                            continue
                        # Must have migration instruction
                        if not any("Instruction: Migrate" in l for l in logs):
                            continue
                        # Skip already migrated
                        if any("already migrated" in l for l in logs):
                            continue

                        # Extract token mint from Program data or postTokenBalances
                        mint = None
                        for log in logs:
                            if log.startswith("Program data:"):
                                try:
                                    import base64
                                    data = base64.b64decode(log.split("Program data: ")[1])
                                    if len(data) >= 80:
                                        # Skip 8-byte discriminator + 8 timestamp + 2 index + 32 creator
                                        # baseMint starts at offset 50
                                        from solders.pubkey import Pubkey
                                        mint_bytes = data[50:82]
                                        mint = str(Pubkey.from_bytes(mint_bytes))
                                        # quoteAmountIn (SOL liquidity) at offset 115
                                        if len(data) >= 123:
                                            import struct
                                            sol_liq = struct.unpack_from("<Q", data, 115)[0] / LAMPORTS_PER_SOL
                                            _dbg(f"MIGRATE: {mint[:12]} liq={sol_liq:.1f}SOL")
                                except Exception as e:
                                    _dbg(f"Migration data parse: {e}")
                                break

                        # Fallback: get mint from transaction
                        if not mint and sig:
                            mint = await _extract_mint_from_tx(session, sig)

                        if not mint or mint in seen_migrations:
                            continue
                        seen_migrations.add(mint)

                        _dbg(f"MIGRATION_DETECTED: {mint}")
                        STATE.recent_activity.append(f"MIGRATE: {mint[:8]}.. detected")

                        # Open graduation snipe position
                        asyncio.create_task(
                            _geyser_process_graduation(session, mint))

                    except Exception as e:
                        _dbg(f"Migration parse: {e}")

        except Exception as e:
            _dbg(f"Migration WS disconnected: {type(e).__name__}: {e}")
            wait = 60 if "429" in str(e) else 10
            await asyncio.sleep(wait)

        # Cap seen set
        if len(seen_migrations) > 5000:
            seen_migrations = set(list(seen_migrations)[-2000:])


# api_token_poller removed — Geyser handles all detection at 0.1ms


# ── Sim updater with bonding curve velocity + tiered exits ────────────────────
async def update_sim_positions(session):
    _last_save = time.monotonic()
    _last_market_update = time.monotonic()
    _tokens_at_last_update = 0
    while not STATE.should_exit:
        try:
            # Save state every 60s
            now_save = time.monotonic()
            if now_save - _last_save >= 60:
                save_state()
                _last_save = now_save

            # Market state update every 5 minutes
            if now_save - _last_market_update >= 300:
                elapsed_min = (now_save - _last_market_update) / 60
                new_tokens = STATE.tokens_found - _tokens_at_last_update
                STATE.tokens_per_min = new_tokens / elapsed_min if elapsed_min > 0 else 0
                _tokens_at_last_update = STATE.tokens_found
                _last_market_update = now_save
                update_market_state()

            open_pos = [p for p in STATE.sim_positions.values() if p.status == "OPEN"]
            write_dashboard_data()  # update web dashboard every cycle
            if not open_pos: await asyncio.sleep(PRICE_CHECK_INTERVAL); continue
            now = time.monotonic()

            # Batch DEX price fetch for SCALP/GRAD positions (one call, all mints)
            _dex_batch_prices = {}
            scalp_mints = [p.mint for p in open_pos
                          if p.strategy in ("SCALP", "GRAD_SNIPE", "SWING")
                          or p.price_source == "DEX" or p.graduated]
            if scalp_mints:
                try:
                    # DEXScreener batch: split by Solana vs other chains
                    sol_mints = [m for m in scalp_mints if not m.startswith("0x")]
                    eth_mints = [m for m in scalp_mints if m.startswith("0x")]
                    batch_data = []
                    if sol_mints:
                        d = await _dex_fetch_json(session,
                            f"https://api.dexscreener.com/tokens/v1/solana/{','.join(sol_mints[:30])}")
                        if d and isinstance(d, list): batch_data.extend(d)
                    if eth_mints:
                        d = await _dex_fetch_json(session,
                            f"https://api.dexscreener.com/tokens/v1/ethereum/{','.join(eth_mints[:15])}")
                        if d and isinstance(d, list): batch_data.extend(d)
                        d = await _dex_fetch_json(session,
                            f"https://api.dexscreener.com/tokens/v1/base/{','.join(eth_mints[:15])}")
                        if d and isinstance(d, list): batch_data.extend(d)
                    if batch_data:
                        for pair in batch_data:
                            mint = pair.get("baseToken", {}).get("address", "")
                            if not mint: continue
                            pu = float(pair.get("priceUsd", 0) or 0)
                            txns = pair.get("txns", {}).get("m5", {})
                            _dex_batch_prices[mint] = {
                                "price_usd": pu,
                                "buys": txns.get("buys", 0) or 0,
                                "sells": txns.get("sells", 0) or 0,
                            }
                except Exception as e:
                    _dbg(f"DEX batch error: {e}")

            # Batch Jupiter price fetch for graduated/SCALP/TRENDING (one call, up to 100 mints)
            _jup_batch_prices = {}
            jup_mints = [p.mint for p in open_pos
                        if p.graduated or p.strategy in ("SCALP", "TRENDING", "SWING")
                        or p.price_source in ("JUP", "DEX")]
            if jup_mints:
                try:
                    _jup_batch_prices = await jupiter_get_prices_batch(session, jup_mints)
                    if _jup_batch_prices:
                        _dbg(f"JUP_BATCH: got prices for {len(_jup_batch_prices)}/{len(jup_mints)} tokens")
                except Exception as e:
                    _dbg(f"JUP batch error: {e}")

            # Batch BC reads in parallel for all open positions
            _dbg(f"SIM_UPDATE: {len(open_pos)} positions, batch BC read...")
            bc_tasks = [fetch_bc_direct(session, p.mint) for p in open_pos]
            bc_results = await asyncio.gather(*bc_tasks, return_exceptions=True)

            for i, p in enumerate(open_pos):
                try:
                    bc = bc_results[i] if not isinstance(bc_results[i], Exception) else None
                    # ESTAB tokens: always use DEX price, ignore BC failures
                    if p.size_reason == "ESTAB":
                        dp = await dexscreener_get_price(session, p.mint)
                        if dp > 0 and p.entry_price_sol > 0:
                            # Sanity: reject prices that differ >50x from entry (bug)
                            ratio = dp / p.entry_price_sol if p.entry_price_sol > 0 else 1
                            if ratio > 50 or ratio < 0.02:
                                _dbg(f"ESTAB_PRICE_BUG: {p.symbol} entry={p.entry_price_sol:.10f} "
                                     f"now={dp:.10f} ratio={ratio:.0f}x — skipping")
                            else:
                                p.current_price_sol = dp; p.price_fetch_failures = 0
                                p.peak_price_sol = max(p.peak_price_sol, dp)
                                p.trough_price_sol = min(p.trough_price_sol, dp)
                                p.pct_change = (dp - p.entry_price_sol) / p.entry_price_sol * 100
                                p.price_source = "DEX"
                                profit, _ = calc_sim_pnl(p.entry_price_sol, dp,
                                    p.remaining_sol, p.initial_liq_sol)
                                p.profit_sol = profit
                                p.profit_usd = profit * STATE.sol_price_usd
                        # Skip BC-dependent processing — set safe defaults
                        bc = {}; vsolr = 0; vtokr = 0
                    elif not bc:
                        # BC read failed — for non-graduated tokens, retry BC once more
                        # (new pump.fun tokens ONLY exist on BC, Jupiter/DEX won't have them)
                        if not p.graduated and p.price_source == "BC":
                            await asyncio.sleep(1)
                            bc_retry = await fetch_bc_direct(session, p.mint)
                            if bc_retry and not bc_retry.get("_parse_error"):
                                vr = bc_retry.get("virtualSolReserves", 0)
                                vt = bc_retry.get("virtualTokenReserves", 0)
                                if vr and vt:
                                    rp = (vr / LAMPORTS_PER_SOL) / (vt / 1e6)
                                    if rp > 0:
                                        p.price_fetch_failures = 0
                                        p.price_source = "BC"
                                        p.current_price_sol = rp
                                        p.peak_price_sol = max(p.peak_price_sol, rp)
                                        p.trough_price_sol = min(p.trough_price_sol, rp)
                                        if p.entry_price_sol > 0:
                                            p.pct_change = (rp - p.entry_price_sol) / p.entry_price_sol * 100
                                        bc = bc_retry  # set bc so we skip the fallback chain below

                        # If BC retry didn't work, try Jupiter → DEXScreener → pool
                        if not bc:
                            live_price = _jup_batch_prices.get(p.mint, 0)
                            src = "JUP"
                            if live_price <= 0:
                                live_price = await jupiter_get_price(session, p.mint)
                            if live_price <= 0:
                                live_price = await dexscreener_get_price(session, p.mint)
                                src = "DEX"
                            if live_price <= 0:
                                live_price = await _get_pool_price_direct(session, p.mint)
                                src = "POOL"
                            if live_price > 0:
                                p.price_fetch_failures = 0
                                p.current_price_sol = live_price
                                p.peak_price_sol = max(p.peak_price_sol, live_price)
                                p.trough_price_sol = min(p.trough_price_sol, live_price)
                                if p.entry_price_sol > 0:
                                    p.pct_change = (live_price - p.entry_price_sol) / p.entry_price_sol * 100
                                p.price_source = src
                                profit, _ = calc_sim_pnl(p.entry_price_sol, live_price,
                                    p.remaining_sol, p.initial_liq_sol)
                                p.profit_sol = profit
                                p.profit_usd = profit * STATE.sol_price_usd
                                STATE.recent_activity.append(f"PRICE_FALLBACK: {p.symbol} RPC→{src}")
                                _dbg(f"PRICE_FALLBACK: {p.symbol} RPC failed, got {src} price={live_price:.10f}")
                            else:
                                p.price_fetch_failures += 1
                        if p.price_fetch_failures > 0:
                            p.signals = list(set(p.signals) | {"API_GONE"})
                            _dbg(f"FETCH_FAIL: {p.symbol} consecutive={p.price_fetch_failures} (all sources failed)")
                        # Safety: 5 consecutive all-source failures = force exit
                        if p.price_fetch_failures >= 5:
                            last_price = p.current_price_sol if p.current_price_sol > 0 else p.entry_price_sol
                            pnl_pct = ((last_price - p.entry_price_sol) / p.entry_price_sol * 100) if p.entry_price_sol > 0 else 0
                            exit_reason = f"FORCE_EXIT_STUCK(fails={p.price_fetch_failures} pnl={pnl_pct:+.1f}%)"
                            close_price = last_price
                            _dbg(f"FORCE EXIT: {p.symbol} stuck {p.price_fetch_failures} fails, closing at {close_price:.10f} ({pnl_pct:+.1f}%)")
                            STATE.recent_activity.append(f"FORCE_EXIT: {p.symbol} stuck {p.price_fetch_failures} fails {pnl_pct:+.1f}%")
                            close_position(p, exit_reason, close_price)
                            if STATE.hft_enabled:
                                hold_sec = now - p.entry_time
                                STATE.hft_trades_hour += 1
                                STATE.hft_profits.append((p.profit_sol, hold_sec))
                                log_hft_csv(p.symbol, p.score, p.entry_price_sol,
                                           p.current_price_sol, p.profit_sol,
                                           p.profit_usd, hold_sec, exit_reason)
                        continue

                    # Detect parse errors from struct changes — treat as graduated
                    if bc.get("_parse_error"):
                        if not p.graduated:
                            p.graduated = True
                            p.price_source = "DEX"
                            p.signals.append("BC_PARSE_ERROR")
                            _dbg(f"BC_PARSE_ERROR: {p.symbol} — struct changed, switching to DEXScreener")
                            STATE.recent_activity.append(f"BC_PARSE: {p.symbol} → DEXScreener")

                    # Graduated tokens: Jupiter batch → Jupiter single → DEXScreener → pool RPC
                    if p.graduated or p.price_source in ("DEX", "JUP"):
                        # Try Jupiter batch first (already fetched above, free)
                        live_price = _jup_batch_prices.get(p.mint, 0)
                        src = "JUP"
                        # Fallback: individual Jupiter call
                        if live_price <= 0:
                            live_price = await jupiter_get_price(session, p.mint)
                        # Fallback: DEXScreener
                        if live_price <= 0:
                            live_price = await dexscreener_get_price(session, p.mint)
                            src = "DEX"
                        # Fallback: direct pool RPC
                        if live_price <= 0:
                            live_price = await _get_pool_price_direct(session, p.mint)
                            src = "POOL"
                        if live_price > 0:
                            p.price_fetch_failures = 0
                            p.price_source = src
                            p.current_price_sol = live_price
                            p.peak_price_sol = max(p.peak_price_sol, live_price)
                            p.trough_price_sol = min(p.trough_price_sol, live_price)
                            if p.entry_price_sol > 0:
                                p.pct_change = (live_price - p.entry_price_sol) / p.entry_price_sol * 100
                            profit, _ = calc_sim_pnl(p.entry_price_sol, live_price,
                                p.remaining_sol, p.initial_liq_sol)
                            p.profit_sol = profit
                            p.profit_usd = profit * STATE.sol_price_usd
                        else:
                            p.price_fetch_failures += 1
                            _dbg(f"FETCH_FAIL: {p.symbol} all sources failed (JUP+DEX+POOL)")
                    else:
                        # Price from BC reserves (no getAsset needed for updates)
                        vsolr = bc.get("virtualSolReserves", 0)
                        vtokr = bc.get("virtualTokenReserves", 0)
                        if vsolr and vtokr:
                            np = (vsolr / LAMPORTS_PER_SOL) / (vtokr / 1e6)
                            if np > 0:
                                p.price_fetch_failures = 0; p.price_source = "BC"
                                p.current_price_sol = np
                                p.peak_price_sol = max(p.peak_price_sol, np)
                                p.trough_price_sol = min(p.trough_price_sol, np)
                                if p.entry_price_sol > 0:
                                    p.pct_change = (np - p.entry_price_sol) / p.entry_price_sol * 100
                            else:
                                # BC returned but price calc'd to 0 — treat as fetch fail
                                p.price_fetch_failures += 1
                                _dbg(f"FETCH_FAIL: {p.symbol} price=0 from BC reserves")
                        else:
                            # BC returned but reserves empty — token graduated (BC drained) or rugged
                            if bc.get("complete") or (vsolr == 0 and vtokr == 0):
                                # Graduated! Switch to DEXScreener pricing
                                if not p.graduated:
                                    p.graduated = True
                                    p.price_source = "DEX"
                                    p.signals.append("GRADUATED")
                                    _dbg(f"GRADUATED: {p.symbol} reserves drained → switching to DEXScreener")
                                    STATE.recent_activity.append(f"GRADUATED: {p.symbol} → DEXScreener")
                                    if p.strategy == "NEAR_GRAD":
                                        p.strategy = "GRAD_SNIPE"
                                        STATE.recent_activity.append(f"CONV: {p.symbol} ->GRAD_SNIPE (drained)")
                                # Try DEXScreener immediately for this cycle
                                dex_price = await dexscreener_get_price(session, p.mint)
                                if dex_price > 0:
                                    p.price_fetch_failures = 0
                                    p.current_price_sol = dex_price
                                    p.peak_price_sol = max(p.peak_price_sol, dex_price)
                                    p.trough_price_sol = min(p.trough_price_sol, dex_price)
                                    if p.entry_price_sol > 0:
                                        p.pct_change = (dex_price - p.entry_price_sol) / p.entry_price_sol * 100
                                    p.price_source = "DEX"
                                # Don't increment failures for graduated tokens — DEXScreener may be slow
                            else:
                                p.price_fetch_failures += 1
                                _dbg(f"FETCH_FAIL: {p.symbol} reserves empty vsolr={vsolr} vtokr={vtokr}")

                    # Safety: 5 consecutive bad prices = force exit (was 10 — too slow, slots get stuck)
                    if p.price_fetch_failures >= 5 and p.status == "OPEN":
                        last_price = p.current_price_sol if p.current_price_sol > 0 else p.entry_price_sol
                        pnl_pct = ((last_price - p.entry_price_sol) / p.entry_price_sol * 100) if p.entry_price_sol > 0 else 0
                        exit_reason = f"PRICE_STALE(fails={p.price_fetch_failures} pnl={pnl_pct:+.1f}%)"
                        _dbg(f"FORCE EXIT: {p.symbol} {exit_reason} — closing at last known price {last_price:.10f}")
                        STATE.recent_activity.append(f"FORCE_EXIT: {p.symbol} {pnl_pct:+.1f}% (stale)")
                        close_position(p, exit_reason, last_price)
                        if STATE.hft_enabled:
                            hold_sec_f = now - p.entry_time
                            STATE.hft_trades_hour += 1
                            STATE.hft_profits.append((p.profit_sol, hold_sec_f))
                            log_hft_csv(p.symbol, p.score, p.entry_price_sol,
                                       p.current_price_sol, p.profit_sol,
                                       p.profit_usd, hold_sec_f, exit_reason)
                        continue

                    # Liquidity (vsolr only exists for BC-path tokens)
                    _vsolr = bc.get("virtualSolReserves", 0) if bc else 0
                    if _vsolr:
                        p.initial_liq_sol = _vsolr / LAMPORTS_PER_SOL
                    # Market cap from price * supply
                    supply = bc.get("tokenTotalSupply", PUMP_TOKEN_TOTAL_SUPPLY) if bc else PUMP_TOKEN_TOTAL_SUPPLY
                    if p.current_price_sol and STATE.sol_price_usd:
                        p.market_cap_usd = p.current_price_sol * (supply / 1e6) * STATE.sol_price_usd

                    # Bonding curve progress
                    new_bc = calc_bc_progress_from_raw(bc)
                    if bc.get("complete") and not p.graduated:
                        p.graduated = True; p.signals.append("GRADUATED")
                        STATE.recent_activity.append(f"{p.symbol} graduated!")
                    p.bc_progress = new_bc
                    p.bc_history.append((now, new_bc))
                    # Keep last 60 entries (~10 min at 10s intervals)
                    p.bc_history = p.bc_history[-60:]
                    p.bc_velocity = calc_bc_velocity(p.bc_history)

                    # Velocity alert: 10%+ jump in 60s
                    if p.bc_velocity >= BC_VELOCITY_ALERT and "BC_FAST" not in p.signals:
                        p.signals.append("BC_FAST")
                        p.score += 30  # boost
                        STATE.recent_activity.append(
                            f"BC FAST: {p.symbol} {p.bc_velocity:.1f}%/min")

                    # Threshold alerts
                    if new_bc >= BC_THRESHOLD_95 and not p.bc_alerted_95:
                        p.bc_alerted_95 = True; p.signals.append("BC_95%")
                        STATE.recent_activity.append(f"BC 95%: {p.symbol} imminent grad!")
                    elif new_bc >= BC_THRESHOLD_85 and not p.bc_alerted_85:
                        p.bc_alerted_85 = True; p.signals.append("BC_85%")
                    elif new_bc >= BC_THRESHOLD_75 and not p.bc_alerted_75:
                        p.bc_alerted_75 = True; p.signals.append("BC_75%")

                    # Dev sell detection: creator bytes from BC data
                    creator_bytes = bc.get("creator", b"")
                    if isinstance(creator_bytes, bytes) and len(creator_bytes) == 32:
                        try:
                            from solders.pubkey import Pubkey
                            p.creator_wallet = str(Pubkey.from_bytes(creator_bytes))
                        except: pass

                    # P&L
                    if p.entry_price_sol > 0 and p.current_price_sol > 0:
                        profit, _ = calc_sim_pnl(p.entry_price_sol, p.current_price_sol,
                                                 p.remaining_sol, p.initial_liq_sol)
                        p.profit_sol = profit
                        p.profit_usd = profit * STATE.sol_price_usd

                    # Alert level
                    n = len(p.signals)
                    p.alert_level = ("RED" if n>=3 else "ORANGE" if n>=2 else
                                     "YELLOW" if n>=1 else "OK")

                    # ── Heat score tracking ───────────────────────────
                    if not p.is_moonbag:
                        p.price_history.append((now, p.current_price_sol))
                        # Track SOL volume from BC reserve changes
                        if _vsolr:
                            sol_now = _vsolr / LAMPORTS_PER_SOL
                            if p.sol_volume_history:
                                delta = sol_now - p.sol_volume_history[-1][1]
                                p.sol_volume_history.append((now, delta))
                            else:
                                p.sol_volume_history.append((now, sol_now))
                        # Keep last 20 entries (~60s at 3s intervals)
                        p.price_history = p.price_history[-20:]
                        p.sol_volume_history = p.sol_volume_history[-20:]

                        # Update price momentum (direction + speed + acceleration)
                        update_price_momentum(p)

                        # SCALP/GRAD: update from batch DEX data (one call for all)
                        if p.mint in _dex_batch_prices:
                            bd = _dex_batch_prices[p.mint]
                            b = bd["buys"]; s = bd["sells"]
                            if b + s > 0:
                                p.heat_score = b / (b + s) * 100
                                p.heat_pattern = ("ROCKET" if p.heat_score >= 80
                                    else "HEATING" if p.heat_score >= 60
                                    else "WARM" if p.heat_score >= 40
                                    else "COLD" if p.heat_score >= 30
                                    else "DUMP")
                            pu = bd["price_usd"]
                            if pu > 0 and STATE.sol_price_usd > 0:
                                np = pu / STATE.sol_price_usd
                                p.current_price_sol = np
                                p.peak_price_sol = max(p.peak_price_sol, np)
                                p.trough_price_sol = min(p.trough_price_sol, np)
                                if p.entry_price_sol > 0:
                                    p.pct_change = (np - p.entry_price_sol) / p.entry_price_sol * 100
                                p.price_source = "DEX"
                                p.price_fetch_failures = 0
                        else:
                            # Standard heat calc from price history (BC-based tokens)
                            p.heat_score, p.heat_pattern = calc_heat_score(p)

                    # ── Exit logic (strategy-aware) ────────────────────
                    exit_reason = None
                    hold_sec = now - p.entry_time

                    # ── Universal heat exit (DUMP only — selling pressure) ─
                    if (not p.is_moonbag and hold_sec > 15 and
                            len(p.price_history) >= 5 and
                            p.heat_pattern == "DUMP" and p.pct_change < -5):
                        exit_reason = f"HEAT_DUMP({p.pct_change:+.1f}% heat={p.heat_score:.0f})"
                        _dbg(f"HEAT_EXIT: {p.symbol} [{p.strategy}] {exit_reason}")
                        close_position(p, exit_reason, p.current_price_sol)
                        STATE.hft_trades_hour += 1
                        STATE.hft_profits.append((p.profit_sol, hold_sec))
                        log_hft_csv(p.symbol, p.score, p.entry_price_sol,
                                   p.current_price_sol, p.profit_sol,
                                   p.profit_usd, hold_sec, exit_reason, p.strategy)
                        continue

                    # ── Moonbag exit logic (ADAPTIVE per-token ATR) ──
                    if p.is_moonbag:
                        if p.pct_change > p.moonbag_peak_pct:
                            p.moonbag_peak_pct = p.pct_change
                        peak = p.moonbag_peak_pct
                        current = p.pct_change
                        atr = calc_position_atr(p)
                        keep_pct = calc_adaptive_trail(p, atr)

                        # ABSOLUTE FLOOR: never let a winner go negative
                        if peak >= 5.0 and current <= 0:
                            exit_reason = f"MOON_PROTECT({current:+.0f}% pk:{peak:.0f}% atr:{atr:.1f})"
                        # ADAPTIVE TRAILING STOP: exit when below keep threshold
                        elif peak > 0 and current <= peak * keep_pct:
                            exit_reason = (f"MOON_TRAIL({current:+.0f}% pk:{peak:.0f}% "
                                          f"keep:{keep_pct:.0%} atr:{atr:.1f})")
                        # MOMENTUM REVERSAL: 3+ down ticks AND lost 5%+ from peak
                        elif (p.consecutive_down >= 3 and peak - current > 5.0):
                            exit_reason = f"MOON_REVERSAL({current:+.0f}% pk:{peak:.0f}% d:{p.consecutive_down})"
                        # DEXScreener sell signal
                        elif "DEX_MOON_SELL" in p.signals:
                            exit_reason = f"MOON_TREND_EXIT({current:+.0f}%)"

                        if exit_reason:
                            _dbg(f"MOONBAG_CLOSE: {p.symbol} {exit_reason}")
                            close_position(p, exit_reason, p.current_price_sol)
                            try:
                                with open(MOONBAG_LOG_CSV, "a", newline="", encoding="utf-8") as f:
                                    csv.writer(f).writerow([
                                        SESSION_ID, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        p.mint, p.symbol, p.strategy,
                                        f"{p.remaining_sol:.6f}", f"{p.pct_change:.1f}",
                                        f"{p.entry_price_sol:.10f}",
                                        f"{p.current_price_sol:.10f}", exit_reason,
                                        f"{atr:.2f}", f"{keep_pct:.2f}"])
                            except: pass
                            continue
                        continue  # moonbags skip all other exit logic

                    # Strategy-specific hard cap
                    _hard_caps = {"HFT": 120, "GRAD_SNIPE": GRAD_MAX_HOLD_SEC + 60,
                                  "NEAR_GRAD": NEAR_GRAD_MAX_HOLD_SEC + 60,
                                  "TRENDING": TRENDING_MAX_HOLD_SEC + 60,
                                  "REDDIT": REDDIT_MAX_HOLD_SEC + 60,
                                  "SWING": SWING_MAX_HOLD_SEC + 300,
                                  "SCALP": SCALP_MAX_HOLD_SEC + 30,
                                  "MOMENTUM": MOMENTUM_MAX_HOLD_SEC + 60}
                    hard_cap = _hard_caps.get(p.strategy, 120)
                    if hold_sec >= hard_cap:
                        # If profitable, this is a TP not a hard cap
                        if p.pct_change > 0.5:
                            exit_reason = f"TIME_TP(+{p.pct_change:.1f}%@{hold_sec:.0f}s)"
                        else:
                            exit_reason = f"HARD_CAP({p.pct_change:+.1f}%@{hold_sec:.0f}s)"

                    # ── GRAD_SNIPE: validation + pyramiding + trailing stop ─
                    elif p.strategy == "GRAD_SNIPE":
                        # Bad entry validation (first 15 seconds)
                        if hold_sec <= 15:
                            if p.pct_change <= -15.0:
                                exit_reason = f"GRAD_BAD_ENTRY({p.pct_change:.1f}%@{hold_sec:.0f}s)"
                                _dbg(f"GRAD_BAD_ENTRY: {p.symbol} {p.pct_change:.1f}% in {hold_sec:.0f}s")
                            elif (hold_sec >= 15 and abs(p.pct_change) < 0.01
                                  and p.price_source != "DEX"):
                                # Only trigger if price source isn't DEX (DEX prices can be stable)
                                exit_reason = f"GRAD_PRICE_STUCK({p.pct_change:.1f}%@{hold_sec:.0f}s)"
                                _dbg(f"GRAD_PRICE_STUCK: {p.symbol} price unchanged, src={p.price_source}")

                        # Track peak and trailing stop
                        if p.pct_change > p.peak_pct: p.peak_pct = p.pct_change
                        if p.peak_pct >= HFT_TRAIL_ACTIVATE: p.trail_active = True

                        # Pyramiding: add to winning positions at +3%, +8%, +15%
                        if (p.pyramid_count < PYRAMID_MAX_ADDS and
                                p.pct_change > 0 and _check_loss_limits()):
                            for idx_lvl, lvl in enumerate(PYRAMID_LEVELS):
                                if (lvl not in p.pyramid_levels and
                                        p.pct_change >= lvl):
                                    ratio = PYRAMID_ADD_RATIOS[idx_lvl] if idx_lvl < len(PYRAMID_ADD_RATIOS) else 0.5
                                    add_sol = _cap_position_size(
                                        p.entry_sol * ratio)
                                    if STATE.balance_sol >= add_sol:
                                        # Recalculate average entry price
                                        old_total = p.remaining_sol
                                        p.remaining_sol += add_sol
                                        STATE.balance_sol -= add_sol
                                        # Weighted average entry
                                        p.entry_price_sol = (
                                            (p.entry_price_sol * old_total +
                                             p.current_price_sol * add_sol) /
                                            p.remaining_sol)
                                        p.entry_sol += add_sol
                                        p.pyramid_count += 1
                                        p.pyramid_levels.append(lvl)
                                        # Recalc pct_change with new avg entry
                                        p.pct_change = ((p.current_price_sol - p.entry_price_sol)
                                                        / p.entry_price_sol * 100)
                                        STATE.recent_activity.append(
                                            f"PYRAMID: {p.symbol} +{add_sol:.2f}SOL "
                                            f"@+{lvl:.0f}% (#{p.pyramid_count})")
                                        _dbg(f"PYRAMID: {p.symbol} add={add_sol:.3f}SOL "
                                             f"lvl=+{lvl}% total={p.remaining_sol:.3f}SOL "
                                             f"avg_entry={p.entry_price_sol:.10f}")
                                    break  # only one pyramid per update cycle

                        # 1. Hard stop loss
                        if p.pct_change <= GRAD_SL_PCT:
                            exit_reason = f"GRAD_SL({p.pct_change:.1f}%)"
                        # 2. Negative velocity kill — dumping grads never recover
                        elif p.bc_velocity <= -5.0 and hold_sec > 10:
                            exit_reason = f"GRAD_VEL_DUMP({p.pct_change:+.1f}% vel={p.bc_velocity:.1f})"
                        # 3. ATR-adaptive trailing stop — wider for volatile grads
                        elif p.trail_active:
                            _grad_atr = calc_position_atr(p)
                            _grad_trail = max(5.0, min(_grad_atr * 2.5, 20.0))
                            if p.pct_change <= p.peak_pct - _grad_trail:
                                exit_reason = (f"GRAD_TRAIL(+{p.pct_change:.1f}% pk:{p.peak_pct:.0f}% "
                                              f"atr:{_grad_atr:.1f} trail:{_grad_trail:.0f}%)")
                        # 4. Tiered take profit: 50% at 2x
                        elif p.pct_change >= 200.0 and not p.partial_exit_3x and p.partial_exit_2x:
                            p.partial_exit_3x = True
                            sold = p.remaining_sol * 0.50
                            p.remaining_sol -= sold
                            profit_sol = sold * (p.pct_change / 100.0)
                            STATE.total_pnl_sol += profit_sol
                            STATE.balance_sol += sold + profit_sol
                            STATE.recent_activity.append(f"GRAD_TP2: {p.symbol} 25% at {p.pct_change:.0f}%")
                            _log_partial_exit(p, "GRAD_TP2_25%", sold, profit_sol)
                        elif p.pct_change >= 100.0 and not p.partial_exit_2x:
                            p.partial_exit_2x = True
                            sold = p.remaining_sol * 0.50
                            p.remaining_sol -= sold
                            profit_sol = sold * (p.pct_change / 100.0)
                            STATE.total_pnl_sol += profit_sol
                            STATE.balance_sol += sold + profit_sol
                            STATE.recent_activity.append(f"GRAD_TP1: {p.symbol} 50% at {p.pct_change:.0f}%")
                            _log_partial_exit(p, "GRAD_TP1_50%", sold, profit_sol)
                        elif hold_sec >= GRAD_MAX_HOLD_SEC:
                            exit_reason = f"GRAD_TIME({p.pct_change:+.1f}%@{hold_sec:.0f}s)"

                    # ── NEAR_GRAD: hold until graduation or 10min ────
                    elif p.strategy == "NEAR_GRAD":
                        if p.pct_change <= NEAR_GRAD_SL_PCT:
                            exit_reason = f"NGRAD_SL({p.pct_change:.1f}%)"
                        elif p.graduated:
                            p.strategy = "GRAD_SNIPE"
                            STATE.recent_activity.append(f"CONV: {p.symbol} ->GRAD_SNIPE")
                        elif hold_sec >= NEAR_GRAD_MAX_HOLD_SEC:
                            exit_reason = f"NGRAD_TIME({p.pct_change:+.1f}%@{hold_sec:.0f}s)"

                    # ── TRENDING: ATR trailing stop + 5min max ─────
                    elif p.strategy == "TRENDING":
                        if p.pct_change > p.peak_pct: p.peak_pct = p.pct_change
                        if p.peak_pct >= HFT_TRAIL_ACTIVATE: p.trail_active = True
                        # Force-exit dead trending: low heat + no movement + held > 60s
                        if p.heat_score < 50 and abs(p.pct_change) < 1.0 and hold_sec > 60:
                            exit_reason = f"TREND_DEAD(h={p.heat_score:.0f} {p.pct_change:+.1f}%@{hold_sec:.0f}s)"
                        elif p.pct_change <= TRENDING_SL_PCT:
                            exit_reason = f"TREND_SL({p.pct_change:.1f}%)"
                        elif p.trail_active:
                            _tr_atr = calc_position_atr(p)
                            _tr_trail = max(4.0, min(_tr_atr * 2.0, 15.0))
                            if p.pct_change <= p.peak_pct - _tr_trail:
                                exit_reason = f"TREND_TRAIL(+{p.pct_change:.1f}% pk:{p.peak_pct:.0f}% atr:{_tr_atr:.1f})"
                        elif hold_sec >= TRENDING_MAX_HOLD_SEC:
                            exit_reason = f"TREND_TIME({p.pct_change:+.1f}%@{hold_sec:.0f}s)"

                    # ── REDDIT: ATR trailing stop + 5min max ───────
                    elif p.strategy == "REDDIT":
                        if p.pct_change > p.peak_pct: p.peak_pct = p.pct_change
                        if p.peak_pct >= HFT_TRAIL_ACTIVATE: p.trail_active = True
                        if p.pct_change <= REDDIT_SL_PCT:
                            exit_reason = f"REDDIT_SL({p.pct_change:.1f}%)"
                        elif p.trail_active:
                            _rd_atr = calc_position_atr(p)
                            _rd_trail = max(4.0, min(_rd_atr * 2.0, 15.0))
                            if p.pct_change <= p.peak_pct - _rd_trail:
                                exit_reason = f"REDDIT_TRAIL(+{p.pct_change:.1f}% pk:{p.peak_pct:.0f}% atr:{_rd_atr:.1f})"
                        elif hold_sec >= REDDIT_MAX_HOLD_SEC:
                            exit_reason = f"REDDIT_TIME({p.pct_change:+.1f}%@{hold_sec:.0f}s)"

                    # ── SWING: trailing stop + tighter SL + 2hr max ─
                    elif p.strategy == "SWING":
                        if p.pct_change > p.peak_pct: p.peak_pct = p.pct_change
                        if p.peak_pct >= SWING_TP_PCT: p.trail_active = True
                        # Partial exit at +15%
                        if p.pct_change >= SWING_TP_PCT and not p.partial_exit_2x:
                            p.partial_exit_2x = True
                            sold = p.remaining_sol * 0.50
                            p.remaining_sol -= sold
                            profit_sol = sold * (p.pct_change / 100.0)
                            STATE.total_pnl_sol += profit_sol
                            STATE.balance_sol += sold + profit_sol
                            STATE.recent_activity.append(f"SWING_TP: {p.symbol} 50% at +{p.pct_change:.0f}%")
                            _log_partial_exit(p, "SWING_TP_50%", sold, profit_sol)
                        if p.pct_change <= SWING_SL_PCT:
                            exit_reason = f"SWING_SL({p.pct_change:.1f}%)"
                        elif p.trail_active:
                            _sw_atr = calc_position_atr(p)
                            _sw_trail = max(4.0, min(_sw_atr * 2.5, 18.0))
                            if p.pct_change <= p.peak_pct - _sw_trail:
                                exit_reason = f"SWING_TRAIL(+{p.pct_change:.1f}% pk:{p.peak_pct:.0f}% atr:{_sw_atr:.1f})"
                        elif hold_sec >= SWING_MAX_HOLD_SEC:
                            exit_reason = f"SWING_TIME({p.pct_change:+.1f}%@{hold_sec:.0f}s)"

                    # ── GRID / MOMENTUM: grid positions wait for grid level sell ──
                    elif p.strategy == "MOMENTUM":
                        if p.pct_change > p.peak_pct: p.peak_pct = p.pct_change
                        if p.size_reason == "GRID":
                            # Grid positions: sell handled by grid engine (GRID_SELL)
                            # Only intervene for hard SL or extreme time
                            if p.pct_change <= -5.0:
                                exit_reason = f"GRID_SL({p.pct_change:+.1f}%)"
                            elif hold_sec >= 7200:  # 2 hour hard cap for grid
                                if p.pct_change > 0.6:
                                    exit_reason = f"GRID_TIME_TP(+{p.pct_change:.1f}%@{hold_sec:.0f}s)"
                                else:
                                    exit_reason = f"GRID_TIME({p.pct_change:+.1f}%@{hold_sec:.0f}s)"
                        else:
                            # Legacy momentum positions (if any remain)
                            if p.pct_change >= GRID_SPACING_PCT:
                                exit_reason = f"MOM_TP(+{p.pct_change:.2f}%)"
                            elif p.pct_change <= MOMENTUM_SL_PCT:
                                exit_reason = f"MOM_SL({p.pct_change:+.2f}%)"
                            elif hold_sec >= MOMENTUM_MAX_HOLD_SEC:
                                exit_reason = f"MOM_TIME({p.pct_change:+.2f}%@{hold_sec:.0f}s)"

                    # ── SCALP: trailing micro-profit + fast recovery ──
                    elif p.strategy == "SCALP":
                        # Track scalp peak
                        if p.pct_change > p.scalp_peak_pct:
                            p.scalp_peak_pct = p.pct_change
                        # Activate trailing at +0.5%
                        if p.scalp_peak_pct >= SCALP_TRAIL_ACTIVATE:
                            p.scalp_trail_active = True

                        # Price momentum for scalp decisions
                        _s_rising = p.price_direction == "UP" and p.consecutive_up >= 2
                        _s_falling = p.price_direction == "DOWN" and p.consecutive_down >= 2
                        _s_reversal = (p.prev_direction == "UP" and p.price_direction == "DOWN"
                                       and p.consecutive_down >= 2 and p.scalp_peak_pct >= 0.3)

                        # === IMMEDIATE EXITS ===
                        if p.price_fetch_failures >= 2:
                            exit_reason = f"SCALP_NO_PRICE(fails={p.price_fetch_failures})"
                            if p.size_reason != "ESTAB":
                                _scalp_watch_blacklist[p.mint] = time.time() + 120
                        elif p.heat_score == 0 and abs(p.pct_change) < 0.01 and hold_sec > 6:
                            exit_reason = f"SCALP_DEAD(heat=0@{hold_sec:.0f}s)"
                        elif p.heat_score < 25 and p.pct_change < 0:
                            exit_reason = f"SCALP_DUMP({p.pct_change:+.1f}%|h={p.heat_score:.0f})"
                        elif _s_reversal and p.pct_change > 0:
                            # Momentum reversal on a profitable scalp — lock in gains
                            exit_reason = (f"SCALP_REVERSAL({p.pct_change:+.1f}% pk:{p.scalp_peak_pct:.1f}% "
                                          f"d:{p.consecutive_down})")
                        elif _s_falling and p.pct_change < -0.5 and hold_sec > 10:
                            # Price actively falling + already red — cut it
                            exit_reason = f"SCALP_MOM_EXIT({p.pct_change:+.1f}%|d:{p.consecutive_down})"

                        # === TRAILING MICRO-PROFIT (core money maker) ===
                        elif p.pct_change >= SCALP_HARD_TP_PCT:
                            exit_reason = f"SCALP_TP(+{p.pct_change:.1f}%)"
                        elif p.scalp_trail_active:
                            # Trail at 40% of peak gain, floor at +0.3%
                            trail_exit = max(SCALP_TRAIL_FLOOR,
                                           p.scalp_peak_pct * (1 - SCALP_TRAIL_MULT))
                            if p.pct_change <= trail_exit:
                                exit_reason = (f"SCALP_TRAIL(+{p.pct_change:.1f}% "
                                             f"pk:{p.scalp_peak_pct:.1f}%)")

                        # === HEAT-ACCELERATED EXIT ===
                        elif p.pct_change >= 0.3 and p.heat_score < 45:
                            exit_reason = f"SCALP_HEAT_FADE(+{p.pct_change:.1f}%|h={p.heat_score:.0f})"

                        # === STOP LOSS ===
                        elif p.pct_change <= SCALP_SL_PCT:
                            exit_reason = f"SCALP_SL({p.pct_change:.1f}%)"
                        elif p.pct_change <= SCALP_WEAK_SL_PCT and p.heat_score < 30:
                            exit_reason = f"SCALP_WEAK_SL({p.pct_change:.1f}%|h={p.heat_score:.0f})"

                        # === AI CROSSROAD CHECK ===
                        elif (not exit_reason and hold_sec >= 8
                              and (p.pct_change > 0.2 or (hold_sec > 12 and p.heat_score < 40))):
                            ai_exit = await ai_should_exit({
                                "symbol": p.symbol, "pnl_pct": p.pct_change,
                                "peak_pct": p.scalp_peak_pct, "heat": p.heat_score,
                                "heat_trend": "dropping" if p.heat_score < p.heat_at_entry - 15 else "stable",
                                "hold_sec": hold_sec, "entry_sol": p.entry_sol})
                            ai_action = ai_exit.get("action", "FALLBACK")
                            if ai_action == "SELL_ALL":
                                exit_reason = f"AI_EXIT({p.pct_change:+.1f}%|{ai_exit.get('reason','')[:20]})"
                            elif ai_action == "SELL_HALF" and p.remaining_sol > 0.003:
                                sold = p.remaining_sol * 0.5
                                p.remaining_sol -= sold
                                profit_s = sold * (p.pct_change / 100.0)
                                STATE.total_pnl_sol += profit_s
                                STATE.balance_sol += sold + profit_s
                                _log_partial_exit(p, f"AI_HALF({ai_exit.get('reason','')[:15]})", sold, profit_s)

                        # === TIME EXITS ===
                        elif hold_sec >= 10 and p.heat_score < 35 and not p.scalp_trail_active:
                            exit_reason = f"SCALP_COLD({p.pct_change:+.1f}%@{hold_sec:.0f}s)"
                        elif (hold_sec >= SCALP_TIME_STOP_SEC and abs(p.pct_change) < 0.3
                              and not p.scalp_trail_active):
                            # Only flat-exit if trail NOT active — winners get more time
                            exit_reason = f"SCALP_FLAT({p.pct_change:+.1f}%@{hold_sec:.0f}s)"
                        elif hold_sec >= SCALP_MAX_HOLD_SEC and not p.scalp_trail_active:
                            exit_reason = f"SCALP_TIME({p.pct_change:+.1f}%@{hold_sec:.0f}s)"
                        elif hold_sec >= SCALP_MAX_HOLD_SEC + 15:
                            # Even trailing positions max out at 45s
                            exit_reason = f"SCALP_TIME({p.pct_change:+.1f}%@{hold_sec:.0f}s)"

                        # Track + blacklist
                        if exit_reason:
                            STATE.scalp_pnl_today += p.profit_sol
                            # Short blacklist — estab tokens exempt (always re-tradeable)
                            if p.size_reason != "ESTAB":
                                bl_time = 120 if "SL" in exit_reason else 60 if "DUMP" in exit_reason else 30
                                _scalp_watch_blacklist[p.mint] = time.time() + bl_time
                            # Track creator performance
                            _track_creator(p.creator_wallet, p.symbol, p.pct_change, p.graduated)
                            STATE.scalp_token_names.append(p.symbol)

                    # ── HFT: pyramiding + momentum lock + exits ──────
                    elif p.strategy == "HFT":  # exits always run, even if HFT entry is disabled
                        if p.pct_change > p.peak_pct: p.peak_pct = p.pct_change
                        if p.peak_pct >= HFT_TRAIL_ACTIVATE: p.trail_active = True

                        # MOMENTUM LOCK: if token ever hit +3%, disable flat exit
                        momentum_locked = p.peak_pct >= MOMENTUM_LOCK_PCT

                        # HFT Pyramiding: add at +3%, +8%, +15%
                        if (p.pyramid_count < PYRAMID_MAX_ADDS and
                                p.pct_change > 0 and _check_loss_limits()):
                            for idx_lvl, lvl in enumerate(PYRAMID_LEVELS):
                                if lvl not in p.pyramid_levels and p.pct_change >= lvl:
                                    ratio = PYRAMID_ADD_RATIOS[idx_lvl] if idx_lvl < len(PYRAMID_ADD_RATIOS) else 0.5
                                    add_sol = _cap_position_size(p.entry_sol * ratio)
                                    if STATE.balance_sol >= add_sol:
                                        old_total = p.remaining_sol
                                        p.remaining_sol += add_sol
                                        STATE.balance_sol -= add_sol
                                        p.entry_price_sol = (
                                            (p.entry_price_sol * old_total +
                                             p.current_price_sol * add_sol) / p.remaining_sol)
                                        p.entry_sol += add_sol
                                        p.pyramid_count += 1
                                        p.pyramid_levels.append(lvl)
                                        p.pct_change = ((p.current_price_sol - p.entry_price_sol)
                                                        / p.entry_price_sol * 100)
                                        STATE.recent_activity.append(
                                            f"PYR: {p.symbol} +{add_sol:.2f}SOL @+{lvl:.0f}% (#{p.pyramid_count})")
                                        _dbg(f"PYRAMID_HFT: {p.symbol} add={add_sol:.3f}SOL "
                                             f"lvl=+{lvl}% total={p.remaining_sol:.3f}SOL")
                                    break

                        sl_pct = HFT_MEGA_STOP_LOSS_PCT if p.score >= 130 else HFT_STOP_LOSS_PCT
                        price_rising = p.price_direction == "UP" and p.consecutive_up >= 2
                        price_falling = p.price_direction == "DOWN" and p.consecutive_down >= 2
                        reversal = (p.prev_direction == "UP" and p.price_direction == "DOWN"
                                    and p.consecutive_down >= 2 and p.peak_pct >= 2.0)

                        # AGGRESSIVE TAKE PROFIT — don't let big winners sit
                        if p.pct_change >= 20.0:
                            exit_reason = f"HFT_BIG_TP(+{p.pct_change:.1f}%)"
                            STATE.hft_tp_count += 1
                        elif p.pct_change >= 5.0 and not price_rising:
                            exit_reason = f"HFT_TP(+{p.pct_change:.1f}%)"
                            STATE.hft_tp_count += 1
                        elif p.pct_change >= 3.0 and price_falling:
                            exit_reason = f"HFT_TP_FALL(+{p.pct_change:.1f}% d:{p.consecutive_down})"
                            STATE.hft_tp_count += 1
                        elif p.pct_change <= sl_pct:
                            exit_reason = f"HFT_SL({p.pct_change:.1f}%|sl={sl_pct}%)"
                            STATE.hft_sl_count += 1
                        elif reversal:
                            # MOMENTUM REVERSAL: was going up, now falling — catch the peak
                            exit_reason = (f"HFT_REVERSAL({p.pct_change:+.1f}% pk:{p.peak_pct:.0f}% "
                                          f"d:{p.consecutive_down})")
                            STATE.hft_tp_count += 1
                        elif p.trail_active:
                            # ATR-adaptive trailing stop: volatile tokens get wider trail
                            _hft_atr = calc_position_atr(p)
                            _hft_trail = max(3.0, min(_hft_atr * 2.0, 15.0))
                            if p.pct_change <= p.peak_pct - _hft_trail:
                                exit_reason = (f"HFT_TRAIL(+{p.pct_change:.1f}% pk:{p.peak_pct:.0f}% "
                                              f"atr:{_hft_atr:.1f} trail:{_hft_trail:.0f}%)")
                                STATE.hft_tp_count += 1
                            elif price_falling:
                                # Trailing + price falling = tighter: use 1.5x ATR
                                _tight_trail = max(2.0, min(_hft_atr * 1.5, 10.0))
                                if p.pct_change <= p.peak_pct - _tight_trail:
                                    exit_reason = (f"HFT_TRAIL_MOM(+{p.pct_change:.1f}% pk:{p.peak_pct:.0f}% "
                                                  f"d:{p.consecutive_down} atr:{_hft_atr:.1f})")
                                    STATE.hft_tp_count += 1
                        elif hold_sec >= 30 and not momentum_locked and not p.trail_active and not price_rising:
                            if p.pct_change >= 1.5:
                                # Green at 30s check — that's a win, not a flat exit
                                exit_reason = f"HFT_TP({p.pct_change:+.1f}%@{hold_sec:.0f}s)"
                                STATE.hft_tp_count += 1
                            elif p.pct_change < 1.0:
                                exit_reason = f"HFT_FLAT_30S({p.pct_change:+.1f}%@{hold_sec:.0f}s)"
                                STATE.hft_flat_count += 1
                        elif (hold_sec >= HFT_FLAT_EXIT_SEC and
                              abs(p.pct_change) < HFT_FLAT_RANGE_PCT and
                              not momentum_locked):
                            if p.pct_change >= 1.0:
                                # Green at timeout — take the win
                                exit_reason = f"HFT_TP({p.pct_change:+.1f}%@{hold_sec:.0f}s)"
                                STATE.hft_tp_count += 1
                            else:
                                exit_reason = f"HFT_FLAT({p.pct_change:+.1f}%@{hold_sec:.0f}s)"
                                STATE.hft_flat_count += 1
                        elif hold_sec >= (120 if momentum_locked else HFT_MAX_HOLD_SEC):
                            # Extended hold if price is UP and accelerating
                            if price_rising and p.price_accelerating and hold_sec < 180:
                                pass  # let it ride — momentum is building
                            else:
                                exit_reason = f"HFT_TIME({p.pct_change:+.1f}%@{hold_sec:.0f}s)"
                                STATE.hft_timeout_count += 1

                    # ── Standard (non-HFT, non-strategy) fallback ────
                    else:
                        if p.pct_change <= STOP_LOSS_PCT:
                            exit_reason = f"STOP_LOSS({p.pct_change:.1f}%)"
                        elif hold_sec >= HARD_EXIT_30MIN_SEC:
                            exit_reason = f"30MIN_EXIT({p.pct_change:.1f}%)"
                        elif p.dev_sold and p.dev_sold_pct >= DEV_SELL_THRESHOLD:
                            exit_reason = f"DEV_DUMP({p.dev_sold_pct:.0%})"

                    # ── Close if exit triggered ──────────────────────
                    if exit_reason:
                        is_trail = "TRAIL" in exit_reason
                        # Moonbag: on trailing stop exit, sell 75%, keep 25%
                        if is_trail and not p.is_moonbag and p.remaining_sol > 0.005:
                            sell_pct = 0.75
                            sold = p.remaining_sol * sell_pct
                            moonbag_sol = p.remaining_sol - sold
                            # Record the 75% exit
                            profit_sol = sold * (p.pct_change / 100.0)
                            STATE.total_pnl_sol += profit_sol
                            STATE.balance_sol += sold + profit_sol
                            _log_partial_exit(p, exit_reason, sold, profit_sol)
                            STATE.hft_trades_hour += 1
                            STATE.hft_profits.append((profit_sol, hold_sec))
                            log_hft_csv(p.symbol, p.score, p.entry_price_sol,
                                       p.current_price_sol, profit_sol,
                                       profit_sol * STATE.sol_price_usd,
                                       hold_sec, exit_reason, p.strategy)
                            # Convert remainder to moonbag
                            p.remaining_sol = moonbag_sol
                            p.is_moonbag = True
                            p.moonbag_peak_pct = p.pct_change
                            p.signals.append("MOONBAG")
                            STATE.recent_activity.append(
                                f"MOON: {p.symbol} 25% kept ({moonbag_sol:.3f}SOL "
                                f"@+{p.pct_change:.0f}%)")
                            _dbg(f"MOONBAG: {p.symbol} keeping {moonbag_sol:.3f}SOL "
                                 f"at +{p.pct_change:.0f}% (sold {sold:.3f}SOL)")
                            # Log moonbag creation
                            try:
                                with open(MOONBAG_LOG_CSV, "a", newline="", encoding="utf-8") as f:
                                    csv.writer(f).writerow([
                                        SESSION_ID, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        p.mint, p.symbol, p.strategy,
                                        f"{moonbag_sol:.6f}", f"{p.pct_change:.1f}",
                                        f"{p.entry_price_sol:.10f}",
                                        f"{p.current_price_sol:.10f}", "CREATED"])
                            except: pass
                            continue  # don't close — moonbag stays open

                        _dbg(f"CLOSING: {p.symbol} [{p.strategy}] reason={exit_reason}")
                        close_position(p, exit_reason, p.current_price_sol)
                        STATE.hft_trades_hour += 1
                        STATE.hft_profits.append((p.profit_sol, hold_sec))
                        log_hft_csv(p.symbol, p.score, p.entry_price_sol,
                                   p.current_price_sol, p.profit_sol,
                                   p.profit_usd, hold_sec, exit_reason, p.strategy)
                        if now - STATE.hft_hour_start >= 3600:
                            STATE.hft_trades_hour = 0; STATE.hft_hour_start = now
                        continue

                except Exception as e: _dbg(f"Update {p.symbol}: {e}")
            await asyncio.sleep(PRICE_CHECK_INTERVAL)
        except Exception as e: _dbg(f"Sim loop: {e}"); await asyncio.sleep(PRICE_CHECK_INTERVAL)


# ── Trade stubs ───────────────────────────────────────────────────────────────
async def execute_buy(session, mint, amount_sol):
    if not EXECUTE_TRADES: return None
    _dbg(f"BUY {mint[:12]} {amount_sol} SOL"); return None
async def execute_sell(session, mint, token_amount):
    if not EXECUTE_TRADES: return None
    _dbg(f"SELL {mint[:12]}"); return None


# ══════════════════════════════════════════════════════════════════════════════
# ██  DASHBOARD  ███████████████████████████████████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════

_CAT = {"SAFE":"bold green","WATCH":"bold yellow","RISKY":"bold red","UNKNOWN":"dim"}
_ALR = {"OK":"dim","YELLOW":"yellow","ORANGE":"dark_orange","RED":"bold red"}

def _uptime():
    if not STATE.start_time: return "--:--:--"
    s = int(time.monotonic() - STATE.start_time)
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"
def _hs(sec):
    if sec<60: return f"{sec:.0f}s"
    if sec<3600: return f"{sec/60:.0f}m"
    return f"{sec/3600:.1f}h"
def _mc(v):
    if v>=1e6: return f"${v/1e6:.1f}M"
    if v>=1e3: return f"${v/1e3:.0f}K"
    return f"${v:.0f}" if v else ""

def build_display():
    ts = datetime.now().strftime("%H:%M:%S")
    _, timing_label = get_timing_score()

    # Header
    hdr = Text(justify="center")
    hdr.append("  Pump.fun v4  ", style="bold magenta")
    hdr.append(f"S#{STATE.session_number} ", style="dim")
    hdr.append(f"Slot:{STATE.slot} ", style="white")
    if STATE.sol_price_usd: hdr.append(f"SOL:${STATE.sol_price_usd:.2f} ", style="yellow")
    hdr.append(f"{STATE.last_ms:.0f}ms ", style="green")
    hdr.append("GEY:", style="white")
    hdr.append("ON " if STATE.geyser_connected else "OFF ",
               style="bold green" if STATE.geyser_connected else "dim")
    hdr.append("WS:", style="white")
    hdr.append("ON " if STATE.ws_connected else "OFF ",
               style="bold green" if STATE.ws_connected else "dim")
    hdr.append(f"{timing_label} ", style="cyan")
    hdr.append(f"{ts} ")
    hdr.append("LIVE" if EXECUTE_TRADES else "SIM", style="bold red" if EXECUTE_TRADES else "bold cyan")
    # Market state color + daily loss bar
    _ms_bg = {"HOT": "on red", "WARM": "on dark_orange", "SLOW": "on blue", "DEAD": "on grey23"}
    ms_style = _ms_bg.get(STATE.market_state, "")
    hdr.append(f" [{STATE.market_state}] ", style=f"bold white {ms_style}")
    # Daily loss progress bar
    loss_pct = min(STATE.loss_today_sol / MAX_LOSS_PER_DAY, 1.0) if MAX_LOSS_PER_DAY > 0 else 0
    filled = int(loss_pct * 10)
    loss_bar = "█" * filled + "░" * (10 - filled)
    loss_color = "red" if loss_pct > 0.5 else "yellow" if loss_pct > 0.25 else "green"
    hdr.append(f" LOSS:[{loss_color}]{loss_bar}[/] ", style="dim")
    hdr.append(f"{STATE.loss_today_sol:.2f}/{MAX_LOSS_PER_DAY:.1f}", style=loss_color)
    header = Panel(hdr, box=box.HEAVY, border_style="bright_magenta")

    # Stats
    open_pos = [p for p in STATE.sim_positions.values() if p.status=="OPEN"]
    w=STATE.total_wins; l=STATE.total_losses; wr=w/(w+l)*100 if w+l else 0
    st = Text()
    st.append("\n  "); st.append("SIMULATION", style="bold cyan")
    st.append(f"\n  Found: {STATE.tokens_found}  Open: {len(open_pos)}\n", style="white")
    st.append(f"  {w}W/{l}L  {wr:.0f}%\n", style="green" if wr>=50 else "yellow")
    ps = "bold green" if STATE.total_pnl_sol>=0 else "bold red"
    st.append(f"  P&L: {STATE.total_pnl_sol:+.4f} SOL\n", style=ps)
    st.append(f"  Balance: {STATE.balance_sol:.3f} SOL\n", style="white")
    # Moonbag count
    moonbags = [p for p in STATE.sim_positions.values() if p.is_moonbag and p.status == "OPEN"]
    if moonbags:
        moon_pnl = sum(p.profit_sol for p in moonbags)
        st.append(f"  BAGS: {len(moonbags)} tokens ", style="bold yellow")
        st.append(f"{moon_pnl:+.3f} SOL\n", style="green" if moon_pnl >= 0 else "red")
    # Daily loss counter
    loss_pct = STATE.loss_today_sol / MAX_LOSS_PER_DAY * 100 if MAX_LOSS_PER_DAY else 0
    loss_color = "red" if loss_pct > 75 else "yellow" if loss_pct > 50 else "green"
    st.append(f"  Lost today: {STATE.loss_today_sol:.3f}/{MAX_LOSS_PER_DAY:.1f} SOL",
              style=loss_color)
    if STATE.daily_halted:
        st.append(" HALTED", style="bold red")
    elif STATE.hourly_paused_until > 0 and time.monotonic() < STATE.hourly_paused_until:
        remain = int(STATE.hourly_paused_until - time.monotonic())
        st.append(f" PAUSE {remain}s", style="yellow")
    st.append("\n")
    total_sig = STATE.reddit_signals_count + STATE.twitter_signals_count
    twk = STATE.twikit_status
    twk_style = ("green" if twk == "OK" else "yellow" if twk in ("INIT", "CAPTCHA", "VERIFY")
                  else "red")
    st.append(f"  Reddit:{STATE.reddit_signals_count} Twitter:{STATE.twitter_signals_count} "
              f"Total:{total_sig}\n", style="magenta")
    st.append(f"  Twikit:", style="dim"); st.append(twk, style=twk_style)
    st.append(f" Whale:{STATE.whale_alerts_count} "
              f"Viral:{STATE.viral_alerts_count}\n", style="magenta")
    # Strategy breakdown with win rates
    st.append("\n", style="dim")
    best_strat = ""; best_wr = -1
    for s in ["HFT", "SCALP", "GRAD_SNIPE", "SWING", "TRENDING", "REDDIT"]:
        cnt = _strategy_count(s)
        c = STRAT_COLORS.get(s, "white")
        closed_s = [cp for cp in STATE.sim_closed if cp.strategy == s]
        wins_s = sum(1 for cp in closed_s if cp.profit_sol > 0)
        total_s = len(closed_s)
        wr_s = wins_s / total_s * 100 if total_s else 0
        pnl_s = sum(cp.profit_sol for cp in closed_s)
        if wr_s > best_wr and total_s >= 3: best_wr = wr_s; best_strat = s
        st.append(f"  {s[:6]:<6}", style=f"bold {c}")
        st.append(f" {cnt}open", style="white")
        if total_s:
            wr_st = "green" if wr_s >= 50 else "red"
            st.append(f" {wins_s}W/{total_s-wins_s}L", style=wr_st)
            st.append(f" {wr_s:.0f}%", style=wr_st)
            st.append(f" {pnl_s:+.3f}", style="green" if pnl_s >= 0 else "red")
        st.append("\n", style="dim")
    if best_strat:
        st.append(f"  Best: {best_strat} ({best_wr:.0f}%)\n", style="bold green")
    st.append(f"  Wallets:{len(STATE.successful_wallets)} "
              f"Skipped:{STATE.skipped_bots}\n", style="dim")
    # Swing watchlist
    wl = getattr(STATE, 'swing_watchlist', [])
    if wl:
        st.append(f"  SWING Watch: {len(wl)} tokens\n", style="bold cyan")
        for w in wl[:3]:
            st.append(f"    {w['symbol'][:8]} vol={w['vol_sol']:.0f}SOL "
                      f"h1:{w.get('chg_h1',0):+.0f}%\n", style="dim")
    # Scalp stats
    if STATE.scalp_enabled:
        now_t = time.time()
        tpm = sum(1 for t in STATE.scalp_trade_times if now_t - t < 60)
        scalp_usd = STATE.scalp_pnl_today * STATE.sol_price_usd
        dpm = scalp_usd / max(1, (time.monotonic() - (STATE.start_time or time.monotonic())) / 60)
        dpm_color = ("bold green" if dpm >= 0.18 else "green" if dpm >= 0.10
                     else "yellow" if dpm >= 0.05 else "red")
        bl_count = len(_scalp_watch_blacklist)
        scalp_open = _strategy_count("SCALP")
        st.append(f"  SCALP: ", style="bright_white")
        st.append(f"{scalp_open}/{SCALP_MAX_POSITIONS}slots ", style="white")
        st.append(f"{tpm}t/min ", style="white")
        st.append(f"${dpm:.2f}/min ", style=dpm_color)
        st.append(f"${scalp_usd:+.2f}", style="green" if scalp_usd >= 0 else "red")
        st.append(f" h>{SCALP_MIN_HEAT}", style="dim")
        if bl_count: st.append(f" BL:{bl_count}", style="dim")
        st.append("\n")
    # Latency stats
    st.append(f"\n  Detect: {STATE.latency_detect_ms:.0f}ms\n",
              style="green" if STATE.latency_detect_ms < 100 else "yellow")
    st.append(f"  Safety: {STATE.latency_safety_ms:.0f}ms\n",
              style="green" if STATE.latency_safety_ms < 500 else "yellow")
    st.append(f"  Total:  {STATE.latency_total_ms:.0f}ms\n",
              style="bold green" if STATE.latency_total_ms < 1000 else "bold yellow")
    # Geyser status
    gey_st = "bold green" if STATE.geyser_connected else "red"
    st.append(f"  Geyser: ", style="white")
    if STATE.geyser_connected:
        st.append("ON", style="bold green")
    else:
        st.append(f"{STATE.status_msg}" if "RETRY" in STATE.status_msg else "OFF",
                  style="yellow" if "RETRY" in STATE.status_msg else "red")
    # Helius integration status
    st.append(f"  DAS:", style="dim")
    st.append("ON" if STATE.das_active else "OFF",
              style="green" if STATE.das_active else "dim")
    st.append(f"  Fee:", style="dim")
    st.append(f"{STATE.priority_fee:.0f}" if STATE.priority_fee else "?", style="cyan")
    st.append(f"  RPC:{len(RPC_ENDPOINTS)}\n", style="dim")
    # Market state + adaptive values
    _ms_colors = {"HOT": "bold red", "WARM": "bold yellow", "SLOW": "cyan", "DEAD": "dim"}
    st.append(f"  Market:", style="white")
    st.append(f"{STATE.market_state}", style=_ms_colors.get(STATE.market_state, "dim"))
    st.append(f" SC:{STATE.adaptive_score} MOM:{STATE.adaptive_mom}%", style="dim")
    st.append(f" WR:{STATE.rolling_win_rate:.0f}%{STATE.wr_trend}\n",
              style="green" if STATE.rolling_win_rate >= 30 else "red")
    # AI status
    ai_st = {"OK": "green", "INIT": "yellow", "FAIL": "red", "LIMIT": "red"}
    st.append(f"  AI: Groq ", style="dim")
    st.append(STATE.ai_status, style=ai_st.get(STATE.ai_status, "dim"))
    st.append(f" {STATE.ai_last_latency:.0f}ms", style="dim")
    st.append(f" calls:{STATE.ai_calls_today}/{AI_MAX_CALLS_DAY}\n", style="dim")
    stats = Panel(st, title="[bold cyan]Stats[/]", border_style="cyan", box=box.ROUNDED)

    # Controls + keys
    sl = Text("RUN", style="bold green") if STATE.running else Text("STOP", style="bold red")
    ct = Text(); ct.append("\n  "); ct.append_text(sl)
    if STATE.hft_enabled:
        ct.append("  "); ct.append("HFT", style="bold yellow")
    ct.append(f"\n  {_uptime()}\n", style="dim")
    ct.append(f"  {STATE.status_msg[:30]}\n", style="dim italic")
    ct.append("  SPACE pause  Q quit\n", style="dim")
    ct.append("  H hft  P scalp  +/- score\n", style="dim")
    ct.append("  arrows scroll\n", style="dim")
    controls = Panel(ct, title="Ctrl", border_style="blue", box=box.ROUNDED)

    # Pre-fire
    pf = Table(box=box.SIMPLE_HEAVY, header_style="bold yellow", expand=True, padding=(0,1))
    pf.add_column("Token",7); pf.add_column("Sc",4); pf.add_column("Src",14)
    pf.add_column("Tw",4); pf.add_column("Reach",6); pf.add_column("Badge",8)
    now_t = time.time()
    for sig in sorted(STATE.prefire_list.values(), key=lambda x:-x.signal_score)[:8]:
        lb = sig.ticker or (sig.mint[:6]+".." if sig.mint else "?")
        rc = f"{sig.follower_reach//1000}K" if sig.follower_reach>=1000 else str(sig.follower_reach)
        sst = "bold green" if sig.signal_score>=80 else "yellow" if sig.signal_score>=50 else "dim"
        badge = "[bold red]VIRAL[/]" if sig.is_viral else "[bold magenta]WHALE[/]" if sig.whale_wallet else "[bold yellow]FIRE[/]" if sig.signal_score>=80 else "[dim]sig[/]"
        pf.add_row(lb[:7], f"[{sst}]{sig.signal_score}[/]", ",".join(sig.sources)[:14],
                   str(sig.tweet_count), rc, badge)
    pf_panel = Panel(pf, title="[bold yellow]Pre-Fire[/]", border_style="yellow", box=box.ROUNDED)

    # ── Whale panel ───────────────────────────────────────────────────
    wh = Text()
    active_w = sum(1 for w in WATCH_WALLETS if STATE.wallet_status.get(w, {}).get("active"))
    wh.append(f"  Watching: {len(WATCH_WALLETS)} wallets ",
              style="green" if WATCH_WALLETS else "dim")
    if WATCH_WALLETS and STATE.wallet_status:
        wh.append(f"({active_w} active)\n", style="green" if active_w else "red")
    else:
        wh.append("\n")
    wh.append(f"  Buys today: {STATE.whale_buys_today}\n", style="white")
    # Show per-wallet status
    for w in WATCH_WALLETS[:6]:
        ws = STATE.wallet_status.get(w, {})
        st_label = "ACTIVE" if ws.get("active") else "IDLE"
        st_color = "green" if ws.get("active") else "red"
        lt = ws.get("last_trade", 0)
        age = f"{(time.time()-lt)/3600:.0f}h" if lt else "?"
        wh.append(f"  {w[:6]}.. ", style="dim")
        wh.append(f"{st_label}", style=st_color)
        wh.append(f" ({age})\n", style="dim")
    if STATE.whale_best_sym:
        wh.append(f"  Best call: {STATE.whale_best_sym} ", style="green")
        wh.append(f"+{STATE.whale_best_pct:.0f}%\n", style="bold green")
    # Recent whale buys
    for wt in list(STATE.whale_tokens)[-4:]:
        age = time.time() - wt[0]
        wh.append(f"  {wt[1]}.. → {wt[2]}.. ", style="dim")
        wh.append(f"{wt[4]:.1f}SOL ", style="cyan")
        wh.append(f"{age:.0f}s ago\n", style="dim")
    if not STATE.whale_tokens and not WATCH_WALLETS:
        wh.append("  Set WATCH_WALLETS in .env\n", style="dim italic")
    whale_panel = Panel(wh, title="[bold magenta]Whales[/]", border_style="magenta", box=box.ROUNDED)

    # ── Live P&L panel ────────────────────────────────────────────────
    open_pnl = sum(p.profit_sol for p in open_pos)
    total_combined = STATE.total_pnl_sol + open_pnl
    usd = STATE.sol_price_usd
    best_p = max(open_pos, key=lambda x: x.pct_change) if open_pos else None
    worst_p = min(open_pos, key=lambda x: x.pct_change) if open_pos else None

    pl = Text()
    pl.append(f"  Open:      {open_pnl:+.4f} SOL", style="green" if open_pnl>=0 else "red")
    if usd: pl.append(f"  (${open_pnl*usd:+,.2f})", style="dim")
    pl.append(f"\n  Realized:  {STATE.total_pnl_sol:+.4f} SOL", style="green" if STATE.total_pnl_sol>=0 else "red")
    pl.append(f"\n  Combined:  {total_combined:+.4f} SOL", style="bold green" if total_combined>=0 else "bold red")
    if usd: pl.append(f"  (${total_combined*usd:+,.2f})", style="bold green" if total_combined>=0 else "bold red")
    if best_p: pl.append(f"\n  Best now:  {best_p.symbol} {best_p.pct_change:+.0f}%", style="green")
    if worst_p: pl.append(f"\n  Worst now: {worst_p.symbol} {worst_p.pct_change:+.0f}%", style="red")
    # Hourly rate from P&L history
    if len(STATE.pnl_history) >= 2:
        oldest = STATE.pnl_history[0]; newest = STATE.pnl_history[-1]
        dt_hr = (newest[0] - oldest[0]) / 3600
        if dt_hr > 0.01:
            rate_sol = (newest[1] - oldest[1]) / dt_hr
            pl.append(f"\n  Rate: {rate_sol:+.4f} SOL/hr", style="cyan")
            if usd: pl.append(f" (${rate_sol*usd:+,.2f}/hr)", style="dim")
            pl.append(f"\n  Proj: ${rate_sol*usd*24:+,.0f}/day  ${rate_sol*usd*720:+,.0f}/mo", style="dim")
    # Mini ASCII chart (last 20 samples)
    if len(STATE.pnl_history) >= 3:
        vals = [h[1] for h in STATE.pnl_history][-20:]
        mn, mx = min(vals), max(vals)
        rng = mx - mn if mx != mn else 0.001
        chart = "\n  "
        for v in vals:
            level = int((v - mn) / rng * 4)
            chart += ["▁","▂","▃","▄","█"][min(level, 4)]
        pl.append(chart, style="cyan")
    pnl_panel = Panel(pl, title="[bold green]P&L Live[/]", border_style="green", box=box.ROUNDED)

    # ── HFT stats panel (only if HFT enabled) ────────────────────────
    hft_text = Text()
    if STATE.hft_enabled:
        hft_text.append("  "); hft_text.append("HFT ON", style="bold yellow")
        hft_text.append(f"  {STATE.hft_trades_hour}/hr\n", style="white")
        if STATE.hft_profits:
            avg_profit = sum(p[0] for p in STATE.hft_profits) / len(STATE.hft_profits)
            avg_hold = sum(p[1] for p in STATE.hft_profits) / len(STATE.hft_profits)
            hft_text.append(f"  Avg: {avg_profit:+.4f}SOL {avg_hold:.0f}s\n",
                           style="green" if avg_profit>=0 else "red")
            if usd:
                hourly = avg_profit * max(STATE.hft_trades_hour, 1)
                hft_text.append(f"  ${hourly*usd:+,.2f}/hr ${hourly*usd*24:+,.0f}/d\n", style="cyan")
        # Exit breakdown
        tp = STATE.hft_tp_count; sl = STATE.hft_sl_count
        to = STATE.hft_timeout_count; fl = STATE.hft_flat_count
        hft_text.append(f"  TRAIL:", style="green"); hft_text.append(f"{tp} ", style="white")
        hft_text.append(f"SL:", style="red"); hft_text.append(f"{sl} ", style="white")
        hft_text.append(f"FLAT:", style="dim"); hft_text.append(f"{fl} ", style="white")
        hft_text.append(f"TO:", style="yellow"); hft_text.append(f"{to}\n", style="white")
        # Active trailing stops
        trailing = sum(1 for pp in open_pos if pp.trail_active)
        if trailing:
            hft_text.append(f"  Trailing: {trailing}\n", style="green")
        # Skip breakdown (dead tokens avoided)
        skips = STATE.hft_skip_mom + STATE.hft_skip_buyers + STATE.hft_skip_bc + STATE.hft_skip_vel
        if skips:
            hft_text.append(f"  Avoided {skips}: ", style="dim")
            hft_text.append(f"mom:{STATE.hft_skip_mom} ", style="dim")
            hft_text.append(f"buy:{STATE.hft_skip_buyers} ", style="dim")
            hft_text.append(f"bc:{STATE.hft_skip_bc} ", style="dim")
            hft_text.append(f"vel:{STATE.hft_skip_vel}\n", style="dim")
    else:
        hft_text.append("  HFT OFF  [H]\n", style="dim")
    hft_panel = Panel(hft_text, title="[bold yellow]HFT[/]", border_style="yellow", box=box.ROUNDED)

    # ── Sim positions (scrollable) ────────────────────────────────────
    sorted_all = sorted(open_pos, key=lambda x:x.pct_change, reverse=True)
    total_open = len(sorted_all)
    off = min(STATE.scroll_offset, max(0, total_open - 14))
    visible = sorted_all[off:off+14]

    pt = Table(box=box.SIMPLE_HEAVY, header_style="bold magenta", expand=True, padding=(0,1))
    pt.add_column("Sym",7); pt.add_column("Sc",4); pt.add_column("P&L%",7)
    pt.add_column("P&L",7); pt.add_column("Heat",6); pt.add_column("Dir",5)
    pt.add_column("ATR",4); pt.add_column("Reason",10)
    pt.add_column("Held",5,style="dim")
    _conf_colors = {"LOW": "dim", "MED": "yellow", "HIGH": "green", "MAX": "bold green"}
    for idx, p in enumerate(visible):
        h = time.monotonic()-p.entry_time
        row_style = "" if (off+idx) != STATE.scroll_selected else "on grey23"
        pst = "bold green" if p.pct_change>0 else "bold red" if p.pct_change<-20 else "yellow"
        sst = "bold green" if p.score>=70 else "yellow" if p.score>=40 else "red"
        pnl_st = "green" if p.profit_sol>=0 else "red"
        cc = _conf_colors.get(p.confidence, "dim")
        pk_st = "bold green" if p.trail_active else "dim"
        pk_str = f"[{pk_st}]{p.peak_pct:+.0f}[/]" if p.peak_pct != 0 else "[dim]0[/]"
        strat_c = STRAT_COLORS.get(p.strategy, "dim")
        if p.is_moonbag:
            reason_display = "MOONBAG"
            cc = "bold yellow"
        elif p.strategy == "GRAD_SNIPE":
            reason_display = f"GRAD:{p.price_source}"
        else:
            reason_display = p.size_reason[:10] if p.size_reason else p.strategy[:5]
        # Show pyramid count
        if p.pyramid_count > 0:
            reason_display = f"PYR:{p.pyramid_count} {reason_display[:5]}"
        # Heat display
        _hc = ("bold red" if p.heat_score >= 80 else "yellow" if p.heat_score >= 60
               else "cyan" if p.heat_score >= 40 else "dim")
        heat_str = f"[{_hc}]{p.heat_score:.0f}{p.heat_pattern[:3] if p.heat_pattern else ''}[/]"
        # Direction arrows: ↑↑↑ for consecutive ups, ↓↓ for consecutive downs
        _dir_arrows = {"UP": "↑", "DOWN": "↓", "FLAT": "→"}
        _dir_colors = {"UP": "bold green", "DOWN": "bold red", "FLAT": "dim"}
        _arrow = _dir_arrows.get(p.price_direction, "→")
        _n_arrows = max(1, p.consecutive_up if p.price_direction == "UP"
                       else p.consecutive_down if p.price_direction == "DOWN" else 1)
        _dir_str = f"[{_dir_colors.get(p.price_direction, 'dim')}]{_arrow * min(_n_arrows, 4)}[/]"
        _pos_atr = calc_position_atr(p)
        _atr_c = "bold red" if _pos_atr >= 10 else "yellow" if _pos_atr >= 3 else "dim"
        pt.add_row(p.symbol[:7], f"[{sst}]{p.score}[/]",
            f"[{pst}]{p.pct_change:+.0f}%[/]", f"[{pnl_st}]{p.profit_sol:+.2f}[/]",
            heat_str, _dir_str,
            f"[{_atr_c}]{_pos_atr:.1f}[/]",
            f"[{strat_c}]{reason_display}[/]",
            _hs(h), style=row_style)
    scroll_info = f"  {off+1}-{off+len(visible)} of {total_open}" if total_open else ""
    sim_panel = Panel(pt,
        title=f"[bold magenta]Positions ({total_open})[/]{scroll_info}",
        border_style="magenta", box=box.ROUNDED)

    # Results with exit type icons
    rt = Table(box=box.SIMPLE_HEAVY, header_style="bold cyan", expand=True, padding=(0,1))
    rt.add_column("",3); rt.add_column("Sym",7); rt.add_column("P&L",8); rt.add_column("Exit",18,style="dim")
    _exit_icons = {
        "TRAIL": ("[green]^[/]", "green"), "SL": ("[red]v[/]", "red"),
        "FLAT": ("[yellow]-[/]", "yellow"), "TIME": ("[dim]T[/]", "dim"),
        "MOON": ("[yellow]*[/]", "yellow"), "HEAT": ("[red]![/]", "red"),
        "DUMP": ("[red]![/]", "red"), "GRAD": ("[cyan]G[/]", "cyan"),
        "SWING": ("[magenta]S[/]", "magenta"), "PRICE": ("[dim]?[/]", "dim"),
    }
    for p in list(STATE.sim_closed)[:10]:
        ps = "bold green" if p.profit_sol>0 else "bold red"
        icon = "[dim].[/]"
        for key, (ic, _) in _exit_icons.items():
            if key in p.exit_reason: icon = ic; break
        sc = STRAT_COLORS.get(p.strategy, "dim")
        rt.add_row(icon, p.symbol[:7],
            f"[{ps}]{p.profit_sol:+.3f}[/]",
            f"[{sc}]{p.strategy[:3]}[/] {p.exit_reason[:14]}")
    results = Panel(rt, title="[bold cyan]Results[/]", border_style="cyan", box=box.ROUNDED)

    # Top terms
    tt = Text()
    for term, s in sorted(STATE.patterns.get("term_stats",{}).items(),
                           key=lambda x:-x[1].get("wins",0))[:4]:
        total=s.get("total",0); wins_t=s.get("wins",0)
        wr_t=wins_t/total*100 if total else 0
        tt.append(f"  {term[:18]:<18} {wins_t}/{total} {wr_t:.0f}%\n",
                  style="green" if wr_t>=50 else "red")
    if not STATE.patterns.get("term_stats"): tt.append("  Collecting...\n", style="dim")
    terms = Panel(tt, title="[bold green]Terms[/]", border_style="green", box=box.ROUNDED)

    # Activity log with color coding
    al = Text()
    for line in reversed(list(STATE.recent_activity)):
        if "CLOSE" in line and "+" in line: style = "green"
        elif "CLOSE" in line: style = "red"
        elif "GRAD" in line or "MIGRATE" in line: style = "cyan"
        elif "PYRAMID" in line or "PYR:" in line: style = "green"
        elif "HEAT" in line or "DUMP" in line: style = "red"
        elif "OPEN" in line: style = "white"
        elif "Market:" in line: style = "yellow"
        elif "error" in line.lower() or "fail" in line.lower(): style = "bold red"
        else: style = "dim"
        al.append(f"  {line}\n", style=style)
    if not STATE.recent_activity: al.append("  ...\n", style="dim")
    activity = Panel(al, title="[bold blue]Log[/]", border_style="blue", box=box.ROUNDED)

    # Layout
    root = Layout()
    root.split_column(
        Layout(name="header", size=4),
        Layout(name="top", size=14),
        Layout(name="sim", size=18),
        Layout(name="bottom", size=12))
    root["top"].split_row(
        Layout(name="top_left", ratio=1),
        Layout(name="top_mid", ratio=1),
        Layout(name="top_right", ratio=1))
    root["top_left"].split_column(
        Layout(name="ctrl", size=7),
        Layout(name="hft", size=7))
    root["bottom"].split_row(
        Layout(name="results", ratio=1),
        Layout(name="whales", ratio=1),
        Layout(name="activity", ratio=1))
    root["header"].update(header)
    root["ctrl"].update(controls)
    root["hft"].update(hft_panel)
    root["top_mid"].update(stats)
    root["top_right"].update(pnl_panel)
    root["sim"].update(sim_panel)
    root["results"].update(results)
    root["whales"].update(whale_panel)
    root["activity"].update(activity)
    return root


# ── Keyboard ──────────────────────────────────────────────────────────────────
def keyboard_thread():
    try:
        import msvcrt
        while not STATE.should_exit:
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch == b" ":
                    STATE.running = not STATE.running
                    STATE.start_time = time.monotonic() if STATE.running else None
                elif ch in (b"q", b"Q", b"\x03"):
                    STATE.should_exit = True; break
                elif ch in (b"h", b"H"):
                    STATE.hft_enabled = not STATE.hft_enabled
                    STATE.status_msg = f"HFT {'ON' if STATE.hft_enabled else 'OFF'}"
                elif ch in (b"p", b"P"):
                    STATE.scalp_enabled = not STATE.scalp_enabled
                    STATE.status_msg = f"SCALP {'ON' if STATE.scalp_enabled else 'OFF'}"
                    STATE.recent_activity.append(f"Scalp {'enabled' if STATE.scalp_enabled else 'disabled'}")
                elif ch in (b"+", b"="):
                    HFT_MIN_SCORE = min(150, HFT_MIN_SCORE + 5)
                    STATE.status_msg = f"Score: {HFT_MIN_SCORE}"
                    STATE.recent_activity.append(f"Score raised to {HFT_MIN_SCORE}")
                elif ch in (b"-", b"_"):
                    HFT_MIN_SCORE = max(90, HFT_MIN_SCORE - 5)  # floor=90: sub-90 empirically 0% WR
                    STATE.status_msg = f"Score: {HFT_MIN_SCORE}"
                    STATE.recent_activity.append(f"Score lowered to {HFT_MIN_SCORE}")
                elif ch == b"\xe0":  # arrow key prefix on Windows
                    ch2 = msvcrt.getch()
                    open_count = sum(1 for p in STATE.sim_positions.values() if p.status=="OPEN")
                    if ch2 == b"H":   # UP
                        STATE.scroll_offset = max(0, STATE.scroll_offset - 1)
                    elif ch2 == b"P": # DOWN
                        STATE.scroll_offset = min(max(0, open_count - 14), STATE.scroll_offset + 1)
                    elif ch2 == b"I": # PAGE UP
                        STATE.scroll_offset = max(0, STATE.scroll_offset - 10)
                    elif ch2 == b"Q": # PAGE DOWN
                        STATE.scroll_offset = min(max(0, open_count - 14), STATE.scroll_offset + 10)
            time.sleep(0.05)
    except ImportError:
        pass  # non-Windows: basic controls only

async def pnl_snapshot_task(session):
    """Record total P&L every 60 seconds for the chart."""
    while not STATE.should_exit:
        open_pnl = sum(p.profit_sol for p in STATE.sim_positions.values() if p.status=="OPEN")
        total = STATE.total_pnl_sol + open_pnl
        STATE.pnl_history.append((time.monotonic(), total))
        await asyncio.sleep(60)

def _send_context_email(body: str, message_id: str = ""):
    """Send/reply context email in a single Gmail thread."""
    if not ALERT_EMAIL or not GMAIL_APP_PASSWORD: return
    def _send():
        try:
            from email.mime.text import MIMEText
            msg = MIMEText(body, "plain")
            msg["Subject"] = "SOLANA BOT CONTEXT"
            msg["From"] = ALERT_EMAIL_FROM
            msg["To"] = ALERT_EMAIL
            if message_id:
                msg["In-Reply-To"] = message_id
                msg["References"] = message_id
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as s:
                s.login(ALERT_EMAIL_FROM, GMAIL_APP_PASSWORD)
                s.send_message(msg)
            _dbg("Context email sent")
        except Exception as e:
            _dbg(f"Context email error: {e}")
    threading.Thread(target=_send, daemon=True).start()

async def claude_context_writer(session):
    """Write CLAUDE_CONTEXT.md every 5 min + email every 30 min if changed."""
    context_path = os.path.join(_BASE, "CLAUDE_CONTEXT.md")
    _last_email_time = 0.0
    _last_email_wr = 0.0
    _last_email_state = ""
    _last_email_errors = 0
    _last_email_loss_pct = 0.0
    _email_msg_id = f"<solbot-context-{SESSION_ID}@solanabot>"
    await asyncio.sleep(30)
    while not STATE.should_exit:
        try:
            now = datetime.now()
            uptime_s = time.monotonic() - STATE.start_time if STATE.start_time else 0
            uptime_h = int(uptime_s // 3600)
            uptime_m = int((uptime_s % 3600) // 60)
            w = STATE.total_wins; l = STATE.total_losses
            wr = w / (w + l) * 100 if w + l else 0
            open_pos = [p for p in STATE.sim_positions.values() if p.status == "OPEN"]
            open_pnl = sum(p.profit_sol for p in open_pos)
            total_pnl = STATE.total_pnl_sol + open_pnl
            loss_pct = STATE.loss_today_sol / MAX_LOSS_PER_DAY * 100 if MAX_LOSS_PER_DAY > 0 else 0

            lines = []
            lines.append("# SOLANA BOT — LIVE CONTEXT")
            lines.append(f"Last Updated: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append("")

            # Current State
            lines.append("## Current State")
            lines.append(f"- Mode: {'LIVE' if EXECUTE_TRADES else 'SIM'}")
            lines.append(f"- Market State: {STATE.market_state}")
            lines.append(f"- Uptime: {uptime_h}h {uptime_m}m")
            lines.append(f"- GEY: {'ON' if STATE.geyser_connected else 'OFF'}  "
                         f"WS: {'ON' if STATE.ws_connected else 'OFF'}")
            lines.append(f"- Open Positions: {len(open_pos)}")
            lines.append(f"- Tokens Found: {STATE.tokens_found}")
            lines.append("")

            # Performance
            lines.append("## Performance Today")
            lines.append(f"- Trades: {w}W/{l}L {wr:.0f}% WR")
            lines.append(f"- P&L: {total_pnl:+.4f} SOL (${total_pnl * STATE.sol_price_usd:+.2f})")
            lines.append(f"- Daily loss used: {STATE.loss_today_sol:.3f}/{MAX_LOSS_PER_DAY:.1f} SOL ({loss_pct:.0f}%)")
            if STATE.best_trade_sol > 0:
                lines.append(f"- Best trade: {STATE.best_trade_sol:+.4f} SOL")
            if STATE.worst_set:
                lines.append(f"- Worst trade: {STATE.worst_trade_sol:+.4f} SOL")
            lines.append("")

            # Active Positions
            lines.append("## Active Positions")
            if open_pos:
                for p in sorted(open_pos, key=lambda x: -x.pct_change):
                    hold = time.monotonic() - p.entry_time
                    lines.append(f"- {p.symbol} [{p.strategy}] {p.pct_change:+.1f}% "
                                 f"heat={p.heat_score:.0f} {p.heat_pattern} "
                                 f"held={hold:.0f}s entry={p.entry_sol:.3f}SOL")
            else:
                lines.append("- None")
            lines.append("")

            # Last 10 Closed
            lines.append("## Last 10 Closed Trades")
            for p in list(STATE.sim_closed)[:10]:
                lines.append(f"- {p.symbol} [{p.strategy}] {p.exit_reason[:25]} "
                             f"{p.profit_sol:+.4f} SOL")
            if not STATE.sim_closed:
                lines.append("- None yet")
            lines.append("")

            # Current Settings
            lines.append("## Current Settings (adaptive)")
            lines.append(f"- Min Score: {STATE.adaptive_score} (base: {HFT_MIN_SCORE})")
            lines.append(f"- Momentum: {STATE.adaptive_mom}%")
            lines.append(f"- BC Filter: {STATE.adaptive_bc}%")
            lines.append(f"- Position Size Mult: {STATE.adaptive_size_mult:.0%}")
            lines.append(f"- Win Rate Trend: {STATE.rolling_win_rate:.0f}%{STATE.wr_trend}")
            lines.append("")

            # Strategy Status
            lines.append("## Strategy Status")
            for strat in ["HFT", "GRAD_SNIPE", "SWING", "TRENDING", "REDDIT"]:
                cnt = _strategy_count(strat)
                closed_s = [p for p in STATE.sim_closed if p.strategy == strat]
                ws = sum(1 for p in closed_s if p.profit_sol > 0)
                ts = len(closed_s)
                swr = ws / ts * 100 if ts else 0
                lines.append(f"- {strat}: {cnt} open, {ts} trades, {swr:.0f}% WR")
            moonbags = [p for p in open_pos if p.is_moonbag]
            if moonbags:
                best_moon = max(moonbags, key=lambda x: x.pct_change)
                lines.append(f"- Moonbags: {len(moonbags)} active, best {best_moon.symbol} "
                             f"at +{best_moon.pct_change:.0f}%")
            wl = getattr(STATE, 'swing_watchlist', [])
            if wl:
                lines.append(f"- Swing Watchlist: {len(wl)} tokens")
            lines.append("")

            # Errors
            lines.append("## Errors Last Hour")
            try:
                with open(DEBUG_LOG, "r", encoding="utf-8") as f:
                    debug_lines = f.readlines()
                cutoff = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
                errors = [l.strip() for l in debug_lines[-200:]
                          if ("error" in l.lower() or "fail" in l.lower() or "429" in l)
                          and l[1:17] >= cutoff]
                for e in errors[-5:]:
                    lines.append(f"- {e[:80]}")
                if not errors:
                    lines.append("- None")
            except:
                lines.append("- Could not read debug.log")
            lines.append("")

            # Config
            lines.append("## Config Snapshot")
            lines.append(f"- EXECUTE_TRADES: {EXECUTE_TRADES}")
            lines.append(f"- HFT_MODE: {HFT_MODE}")
            lines.append(f"- HFT_MIN_SCORE: {HFT_MIN_SCORE}")
            lines.append(f"- HFT_STOP_LOSS_PCT: {HFT_STOP_LOSS_PCT}%")
            lines.append(f"- HFT_MAX_HOLD_SEC: {HFT_MAX_HOLD_SEC}s")
            lines.append(f"- STARTING_BALANCE: {STARTING_BALANCE_SOL} SOL")
            lines.append(f"- BALANCE_NOW: {STATE.balance_sol:.3f} SOL")
            lines.append(f"- MAX_LOSS_PER_DAY: {MAX_LOSS_PER_DAY} SOL")
            lines.append(f"- SOL_PRICE: ${STATE.sol_price_usd:.2f}")
            lines.append(f"- RPC_ENDPOINTS: {len(RPC_ENDPOINTS)}")
            lines.append(f"- WATCH_WALLETS: {len(WATCH_WALLETS)}")
            lines.append("")

            context_text = "\n".join(lines)
            with open(context_path, "w", encoding="utf-8") as f:
                f.write(context_text)

            # Conditional email: only if something important changed
            now_mono = time.monotonic()
            should_email = False
            reason = ""

            if now_mono - _last_email_time >= 1800:  # at least 30 min between emails
                # Check for important changes
                current_wr = wr
                current_state = STATE.market_state
                current_loss_pct = loss_pct
                error_count = len([l for l in lines if l.startswith("- [2026")])

                if abs(current_wr - _last_email_wr) >= 5:
                    should_email = True; reason = f"WR changed {_last_email_wr:.0f}%->{current_wr:.0f}%"
                elif current_state != _last_email_state and _last_email_state:
                    should_email = True; reason = f"Market {_last_email_state}->{current_state}"
                elif current_loss_pct >= 50 and _last_email_loss_pct < 50:
                    should_email = True; reason = "Daily loss over 50%"
                elif error_count > _last_email_errors:
                    should_email = True; reason = "New errors"
                elif _last_email_time == 0:
                    should_email = True; reason = "Initial context"
                elif now_mono - _last_email_time >= 1800:
                    should_email = True; reason = "30min heartbeat"

                if should_email:
                    _send_context_email(context_text, _email_msg_id)
                    _last_email_time = now_mono
                    _last_email_wr = current_wr
                    _last_email_state = current_state
                    _last_email_loss_pct = current_loss_pct
                    _last_email_errors = error_count
                    _dbg(f"Context email triggered: {reason}")

        except Exception as e:
            _dbg(f"Context writer error: {e}")
        await asyncio.sleep(300)  # every 5 minutes


async def sol_price_updater(session):
    while not STATE.should_exit:
        try:
            p=await fetch_sol_price(session)
            if p>0: STATE.sol_price_usd=p
        except: pass
        await asyncio.sleep(60)

async def slot_tracker(session):
    while not STATE.should_exit:
        try:
            r=await rpc_call(session,"getSlot",[{"commitment":"confirmed"}])
            if r and isinstance(r,int): STATE.slot=r
        except: pass
        await asyncio.sleep(5)

async def priority_fee_updater(session):
    """Poll Helius getPriorityFeeEstimate every 30s."""
    await asyncio.sleep(5)
    while not STATE.should_exit:
        try:
            r = await rpc_call(session, "getPriorityFeeEstimate", [{
                "accountKeys": [PUMP_PROGRAM_ID],
                "options": {"priorityLevel": "High"}
            }])
            if r and isinstance(r, dict):
                STATE.priority_fee = r.get("priorityFeeEstimate", 0)
        except: pass
        await asyncio.sleep(30)

async def helius_webhook_setup(session):
    """Set up Helius webhooks for whale wallet monitoring (one-time on startup)."""
    if not WATCH_WALLETS or not HELIUS_API_KEY:
        _dbg("Webhooks: no wallets or API key"); return
    await asyncio.sleep(10)
    try:
        # Check existing webhooks
        async with session.get(HELIUS_WEBHOOK_URL,
                timeout=aiohttp.ClientTimeout(total=10)) as r:
            existing = await r.json(content_type=None)
            if not isinstance(existing, list): existing = []

        # Check if our webhook already exists
        our_hook = None
        for hook in existing:
            if hook.get("webhookType") == "enhanced" and \
               set(hook.get("accountAddresses", [])) == set(WATCH_WALLETS):
                our_hook = hook
                break

        if our_hook:
            STATE.webhook_active = True
            _dbg(f"Webhook already active: {our_hook.get('webhookID', '?')}")
            STATE.recent_activity.append("HOOK: already active")
        else:
            _dbg(f"Webhooks: configured for {len(WATCH_WALLETS)} wallets (polling mode)")
            STATE.recent_activity.append(f"HOOK: {len(WATCH_WALLETS)} wallets (poll)")
        # Note: creating webhooks requires a callback URL (public server)
        # For now we use the existing logsSubscribe approach
        # Webhook creation would need: POST with webhookURL, accountAddresses, etc.
    except Exception as e:
        _dbg(f"Webhook setup: {e}")

async def enhanced_tx_scanner(session):
    """Use Helius Enhanced Transactions API to check whale wallet activity.
    Faster and richer than raw RPC — gets parsed buy/sell/swap types."""
    if not WATCH_WALLETS or not HELIUS_API_KEY: return
    await asyncio.sleep(30)
    seen_txs: set = set()
    while not STATE.should_exit:
        try:
            for wallet in WATCH_WALLETS[:6]:
                if STATE.should_exit: return
                ws = STATE.wallet_status.get(wallet, {})
                url = (f"{HELIUS_ENHANCED_TX}/{wallet}/transactions"
                       f"?api-key={HELIUS_API_KEY}&limit=5")
                try:
                    async with session.get(url,
                            timeout=aiohttp.ClientTimeout(total=10)) as r:
                        if r.status != 200: continue
                        txs = await r.json(content_type=None)
                except: continue
                if not isinstance(txs, list): continue

                for tx in txs:
                    sig = tx.get("signature", "")
                    if sig in seen_txs: continue
                    seen_txs.add(sig)
                    tx_type = tx.get("type", "")
                    # Track activity
                    ts = tx.get("timestamp", 0)
                    if ts:
                        STATE.wallet_status[wallet] = {
                            "active": (time.time() - ts) < 86400,
                            "last_trade": ts,
                            "checked": time.time(),
                            "last_type": tx_type
                        }
                    # Detect pump.fun swaps
                    if tx_type in ("SWAP", "TOKEN_MINT"):
                        desc = tx.get("description", "")
                        # Check token transfers for pump.fun mints
                        for tf in tx.get("tokenTransfers", []):
                            mint = tf.get("mint", "")
                            amount = tf.get("tokenAmount", 0)
                            if mint and len(mint) >= 32 and amount > 0:
                                _dbg(f"WHALE_ENH: {wallet[:8]}.. {tx_type} "
                                     f"mint={mint[:12]} amt={amount}")
                await asyncio.sleep(3)

            if len(seen_txs) > 5000:
                seen_txs = set(list(seen_txs)[-2000:])
        except Exception as e:
            _dbg(f"Enhanced TX error: {e}")
        await asyncio.sleep(60)

def print_startup():
    mw=WALLET_ADDRESS[:6]+"..."+WALLET_ADDRESS[-4:] if len(WALLET_ADDRESS)>10 else "NOT SET"
    rpc=HELIUS_RPC_URL[:40]+"..." if len(HELIUS_RPC_URL)>40 else HELIUS_RPC_URL
    prev = _count_previous_sessions()
    print("\n"+"="*65)
    print(f"  Pump.fun Sniper v4 — Session #{prev + 1}")
    print("="*65)
    print(f"  Session:  {SESSION_ID} ({prev} previous sessions logged)")
    print(f"  RPC:      {rpc}")
    print(f"  RPC pool: {len(RPC_ENDPOINTS)} endpoints (parallel submission)")
    print(f"  Geyser:   {'ENABLED' if GEYSER_WS_URL else 'DISABLED'}")
    print(f"  uvloop:   {'YES' if _UVLOOP else 'NO (Windows)'}")
    print(f"  TxPool:   10 pre-warmed templates")
    print(f"  Wallet:   {mw}")
    print(f"  Twitter:  {'SET' if TWITTER_BEARER_TOKEN else 'NOT SET'}")
    print(f"  Bitquery: {'SET' if BITQUERY_API_KEY else 'NOT SET'}")
    print(f"  Mode:     {'LIVE' if EXECUTE_TRADES else 'SIMULATION'}")
    print(f"  Trade:    {TRADE_SIZE_SOL} SOL | SL:{STOP_LOSS_PCT}% | TP: 2x/3x")
    print(f"  Watch:    {len(WATCH_WALLETS)} wallets | {len(STATE.successful_wallets)} tracked")
    if not EXECUTE_TRADES: print("\n  *** SIMULATION ONLY ***")
    else: print("\n  !!! LIVE MODE !!!")
    print("  SPACE=start/stop  Q=quit\n"+"="*65+"\n")
    time.sleep(1)  # reduced from 2s — every ms counts

async def main():
    init_csvs(); load_wallets(); load_patterns(); _load_prefire_list()
    _load_wallet_sets(); load_state()
    TX_POOL.warm()
    STATE.session_number = _count_previous_sessions()
    print_startup()
    if not HELIUS_RPC_URL or "YOUR_KEY" in HELIUS_RPC_URL:
        print("ERROR: Set HELIUS_RPC_URL in .env"); return
    threading.Thread(target=keyboard_thread, daemon=True).start()
    STATE.start_time = time.monotonic()

    # Connection-pooled session (persistent connections, no per-request overhead)
    session = create_pooled_session()
    try:
        # Pre-warm connections to all endpoints
        _dbg(f"Pre-warming connections to {len(RPC_ENDPOINTS)} RPC endpoints...")
        warmup_tasks = [rpc_call_to(session, url, "getSlot",
                                     [{"commitment":"confirmed"}])
                        for url in RPC_ENDPOINTS]
        warmup_results = await asyncio.gather(*warmup_tasks, return_exceptions=True)
        for i, r in enumerate(warmup_results):
            if isinstance(r, int):
                STATE.slot = r
                _dbg(f"  RPC {i+1}: connected, slot={r}")
            else:
                _dbg(f"  RPC {i+1}: {'error' if isinstance(r, Exception) else 'ok'}")

        STATE.sol_price_usd = await fetch_sol_price(session)
        _dbg(f"SOL: ${STATE.sol_price_usd:.2f} | uvloop: {_UVLOOP} | "
             f"RPC endpoints: {len(RPC_ENDPOINTS)} | TxPool: {TX_POOL.ready}")

        # Launch all tasks including Geyser (primary) + logsSubscribe (fallback)
        tasks = [asyncio.create_task(f(session)) for f in [
            geyser_token_listener,    # PRIMARY: ~50ms detection (Geyser)
            ws_token_listener,        # FALLBACK: ~400ms detection (logsSubscribe)
            migration_listener,       # GRADUATION: migration wrapper logsSubscribe
            update_sim_positions,
            sol_price_updater, slot_tracker, priority_fee_updater, claude_context_writer,
            helius_webhook_setup, enhanced_tx_scanner, pnl_snapshot_task,
            reddit_scanner, twitter_scanner, reddit_catalyst_consumer,
            dexscreener_scanner, helius_trending_scanner,
            swing_watchlist_builder, swing_pattern_scanner,
            scalp_scanner, scalp_watch_loop, estab_token_scalper, scalp_ai_monitor,
            gmgn_wallet_finder, dexscreener_ws_stream,
            check_wallet_activity, wallet_activity_checker,
            bitquery_scan, watch_wallets_scanner, email_monitor_task,
            overnight_manager]]

        STATE.recent_activity.append(
            f"v4 started | uvloop:{_UVLOOP} | RPC:{len(RPC_ENDPOINTS)} | "
            f"TxPool:{TX_POOL.ready}")
        STATE.status_msg = "Scanning (Geyser+WS+API)..."

        with Live(build_display(), refresh_per_second=4, screen=True) as live:
            while not STATE.should_exit:
                live.update(build_display())
                await asyncio.sleep(0.5)

        STATE.should_exit = True; _save_prefire_list()
        _save_json(PATTERNS_JSON, STATE.patterns); save_wallets()
        save_state(); _log_session_end()
        for t in tasks: t.cancel()
    finally:
        await session.close()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
