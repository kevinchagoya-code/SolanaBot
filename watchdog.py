"""
Watchdog: monitors scanner.py and restarts on crash.
Run this — it handles scanner.py lifecycle automatically.
Crash rate limiter: stops restarting after 5 crashes in 10 minutes.
"""
import subprocess, time, os, sys, smtplib
from datetime import datetime
from collections import deque
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

SCANNER_PATH = os.path.join(os.path.dirname(__file__), "scanner.py")
LOG_PATH = os.path.join(os.path.dirname(__file__), "watchdog_log.txt")
RESTART_DELAY = 5
STATUS_INTERVAL = 30
# Crash rate limiter
MAX_CRASHES_WINDOW = 5      # max crashes before halt
CRASH_WINDOW_SEC = 600      # 10 minute window
COOLDOWN_SEC = 300           # 5 min cooldown after crash loop detected

ALERT_EMAIL = os.getenv("ALERT_EMAIL", "")
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass

def send_crash_alert(restarts, crash_times):
    """Send email alert when crash loop detected."""
    if not ALERT_EMAIL or not GMAIL_APP_PASSWORD:
        return
    try:
        body = f"""SOLANA BOT CRASH LOOP DETECTED

Restarts: {restarts}
Crashes in last 10 min: {len(crash_times)}
Last crash: {datetime.now().strftime('%I:%M %p')}

The watchdog has STOPPED restarting to prevent fee bleeding.
Waiting {COOLDOWN_SEC}s before retrying.

Check the debug log and watchdog_log.txt for the crash cause."""
        msg = MIMEText(body)
        msg["Subject"] = "SOLANA BOT - CRASH LOOP HALTED"
        msg["From"] = ALERT_EMAIL_FROM
        msg["To"] = ALERT_EMAIL
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as s:
            s.login(ALERT_EMAIL_FROM, GMAIL_APP_PASSWORD)
            s.sendmail(ALERT_EMAIL_FROM, ALERT_EMAIL, msg.as_string())
        log("Crash alert email sent")
    except Exception as e:
        log(f"Failed to send crash alert: {e}")

def main():
    log("WATCHDOG STARTED")
    log(f"Scanner: {SCANNER_PATH}")
    restarts = 0
    crash_times = deque(maxlen=MAX_CRASHES_WINDOW + 5)

    while True:
        log(f"Starting scanner (restart #{restarts})...")
        start_time = time.time()

        try:
            proc = subprocess.Popen(
                [sys.executable, SCANNER_PATH],
                cwd=os.path.dirname(SCANNER_PATH),
            )

            # Monitor the process
            while proc.poll() is None:
                elapsed = time.time() - start_time
                h = int(elapsed // 3600)
                m = int((elapsed % 3600) // 60)
                print(f"\r[WATCHDOG] Scanner running - uptime: {h}h {m}m - "
                      f"restarts: {restarts} - PID: {proc.pid}    ", end="", flush=True)
                time.sleep(STATUS_INTERVAL)

            exit_code = proc.returncode
            elapsed = time.time() - start_time
            log(f"Scanner exited with code {exit_code} after {elapsed:.0f}s")

            # Record crash time
            crash_times.append(time.time())

            # Check crash rate: count crashes in last CRASH_WINDOW_SEC
            now = time.time()
            recent_crashes = sum(1 for t in crash_times if now - t < CRASH_WINDOW_SEC)

            if recent_crashes >= MAX_CRASHES_WINDOW:
                log(f"CRASH LOOP DETECTED: {recent_crashes} crashes in {CRASH_WINDOW_SEC}s")
                log(f"HALTING restarts for {COOLDOWN_SEC}s to prevent fee bleeding")
                send_crash_alert(restarts, crash_times)
                time.sleep(COOLDOWN_SEC)
                # Clear crash history after cooldown
                crash_times.clear()
                log("Cooldown complete — resuming restart attempts")

            elif elapsed < 10:
                log("Scanner died too fast — waiting 30s before retry")
                time.sleep(30)
            else:
                log(f"Restarting in {RESTART_DELAY}s...")
                time.sleep(RESTART_DELAY)

        except KeyboardInterrupt:
            log("WATCHDOG: Ctrl+C — shutting down")
            if proc and proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
            break
        except Exception as e:
            log(f"WATCHDOG ERROR: {e}")
            time.sleep(RESTART_DELAY)

        restarts += 1

    log("WATCHDOG STOPPED")

if __name__ == "__main__":
    main()
