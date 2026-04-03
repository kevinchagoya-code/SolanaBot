---
name: restart-bot
description: Cleanly restart the bot — kill all processes, start fresh, verify working
---

# Restart Bot

## Steps
```bash
# 1. Kill everything
powershell.exe -NoProfile -Command "Stop-Process -Name python -Force -ErrorAction SilentlyContinue"
sleep 3

# 2. Start bot + dashboard
powershell -Command "Start-Process cmd -ArgumentList '/k', 'cd /d C:\Users\kevin\SolanaBot && title Solana Bot Dashboard && python watchdog.py' -WindowStyle Normal"
powershell -Command "Start-Process cmd -ArgumentList '/k', 'cd /d C:\Users\kevin\SolanaBot && title Dashboard Web Server && python dashboard.py' -WindowStyle Normal"
sleep 3

# 3. Open dashboard
powershell -Command "Start-Process 'http://localhost:8080'"

# 4. Verify (after 15s)
grep "CLEAN START\|started\|HEARTBEAT" debug.log | tail -10
```

## Always commit before restarting
```bash
git add scanner.py && git commit -m "description" && git push
```
