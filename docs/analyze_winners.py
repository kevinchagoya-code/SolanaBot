import csv
from collections import defaultdict

wins = defaultdict(int)
losses = defaultdict(int)
total = defaultdict(int)
pnl = defaultdict(float)
strategies = defaultdict(set)

with open(r'C:\Users\kevin\SolanaBot\snipe_log.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        sym = row.get('symbol', '').strip()
        if not sym:
            continue
        try:
            profit = float(row.get('profit_sol', 0))
        except:
            continue
        total[sym] += 1
        pnl[sym] += profit
        strat = row.get('strategy', row.get('exit_reason', ''))
        strategies[sym].add(strat)
        if profit > 0:
            wins[sym] += 1
        else:
            losses[sym] += 1

# Show tokens with 2+ trades, sorted by total PnL
print("=" * 70)
print(f"{'TOKEN':<15} {'WINS':>5} {'TOTAL':>5} {'WR%':>6} {'PnL SOL':>10} {'STRATEGIES'}")
print("=" * 70)
ranked = sorted(total.keys(), key=lambda x: pnl[x], reverse=True)
for s in ranked:
    if total[s] >= 2:
        wr = wins[s] / total[s] * 100
        strats = ','.join(strategies[s])[:30]
        marker = " <== WINNER" if pnl[s] > 0 and wins[s] >= 2 else ""
        print(f"{s:<15} {wins[s]:>5} {total[s]:>5} {wr:>5.0f}% {pnl[s]:>10.4f} {strats}{marker}")

print("\n" + "=" * 70)
print("TOKENS THAT MADE MONEY ACROSS MULTIPLE TRADES:")
print("=" * 70)
for s in ranked:
    if total[s] >= 2 and pnl[s] > 0 and wins[s] >= 2:
        wr = wins[s] / total[s] * 100
        print(f"  {s}: {wins[s]}W/{total[s]}T ({wr:.0f}% WR) = +{pnl[s]:.4f} SOL")
