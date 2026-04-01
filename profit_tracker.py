"""Live profit tracker — run in a separate terminal alongside the bot."""
import json, time, os, sys
from datetime import datetime

STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")
SOL_PRICE = 83

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

prev_pnl = 0
prev_trades = 0
start_time = time.time()
snapshots = []

print("SOLANA BOT — LIVE PROFIT TRACKER")
print("Press Ctrl+C to stop\n")

while True:
    try:
        d = json.load(open(STATE_FILE))
        w = d.get('total_wins', 0)
        l = d.get('total_losses', 0)
        wr = w / (w + l) * 100 if w + l else 0
        pnl = d.get('total_pnl_sol', 0)
        bal = d.get('balance_sol', 0)
        opened = d.get('total_opened', 0)
        open_pos = len(d.get('open_positions', {}))
        loss = d.get('settings', {}).get('loss_today_sol', 0)

        pnl_usd = pnl * SOL_PRICE
        elapsed = time.time() - start_time
        elapsed_min = elapsed / 60 if elapsed > 0 else 1
        rate_per_min = pnl_usd / elapsed_min if elapsed_min > 0 else 0
        trades_per_min = opened / elapsed_min if elapsed_min > 0 else 0

        # Track changes
        delta_pnl = pnl - prev_pnl
        delta_trades = opened - prev_trades
        prev_pnl = pnl
        prev_trades = opened

        # Snapshot for sparkline
        snapshots.append(pnl_usd)
        if len(snapshots) > 40: snapshots = snapshots[-40:]

        # Sparkline
        if len(snapshots) > 1:
            mn = min(snapshots)
            mx = max(snapshots)
            rng = mx - mn if mx != mn else 1
            blocks = " ▁▂▃▄▅▆▇█"
            spark = ""
            for v in snapshots[-30:]:
                idx = int((v - mn) / rng * 8)
                spark += blocks[max(0, min(8, idx))]
        else:
            spark = ""

        clear()
        now = datetime.now().strftime("%H:%M:%S")
        
        print(f"{'='*50}")
        print(f"  SOLANA BOT PROFIT TRACKER  {now}")
        print(f"{'='*50}")
        print()
        
        # Big P&L display
        color = "\033[92m" if pnl >= 0 else "\033[91m"
        reset = "\033[0m"
        print(f"  P&L:  {color}{pnl:+.4f} SOL  (${pnl_usd:+.2f}){reset}")
        print(f"  Balance: {bal:.3f} / 5.000 SOL")
        print()
        
        # Stats
        print(f"  Trades:  {opened} ({w}W/{l}L {wr:.0f}% WR)")
        print(f"  Open:    {open_pos} positions")
        print(f"  Loss:    {loss:.3f} / 1.2 SOL ({loss/1.2*100:.0f}%)")
        print()
        
        # Rates
        print(f"  $/min:   ${rate_per_min:+.3f}")
        print(f"  $/hr:    ${rate_per_min * 60:+.2f}")
        print(f"  t/min:   {trades_per_min:.1f}")
        print()
        
        # Sparkline
        print(f"  P&L trend: {spark}")
        print()
        
        # Last change
        if delta_trades > 0:
            d_color = "\033[92m" if delta_pnl >= 0 else "\033[91m"
            print(f"  Last 5s: {delta_trades} trades  {d_color}{delta_pnl:+.4f} SOL{reset}")
        
        print(f"\n  Running: {int(elapsed//60)}m {int(elapsed%60)}s")
        
        time.sleep(5)
        
    except KeyboardInterrupt:
        print("\nStopped.")
        break
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(5)
