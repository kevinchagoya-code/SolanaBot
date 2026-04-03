# OPTIMIZATION & STREAMLINE PROMPT

## READ ERROR_LOG.md FIRST — all rules apply

## PHASE 1: Remove Dead Code (~500 lines)
Delete these functions that are NEVER called anywhere:

1. _creator_score (line ~795) — 0 references
2. calc_dip_score (line ~1083) — 0 references  
3. rpc_batch (line ~1324) — 0 references
4. parallel_rpc_call (line ~1347) — 0 references
5. parallel_submit_tx (line ~1362) — 0 references
6. pump_buy_quote (line ~2045) — 0 references
7. pump_sell_quote (line ~2058) — 0 references
8. _ingest_signal (line ~2362) — 0 references, Reddit removed
9. _detect_viral (line ~2412) — 0 references, Reddit removed
10. send_jito_bundle (line ~2607) — 0 references, sim mode
11. build_jito_tip_instruction (line ~2632) — 0 references
12. _get_pool_price_rpc (line ~3586) — 0 references, replaced by Jupiter
13. open_scalp_position (line ~4069) — 0 references, replaced
14. execute_buy (line ~6517) — placeholder stub
15. execute_sell (line ~6520) — placeholder stub  
16. _mc (line ~6540) — 0 references

ALSO delete estab_token_scalper (line ~4504, 167 lines) — ESTAB 
strategy has 0 trades across ALL sessions. It's dead weight.

Verify each deletion: grep -n "function_name" scanner.py to confirm
0 references before deleting. Do NOT delete functions that are called
even once.

## PHASE 2: Split update_sim_positions (985 lines → 6 functions)

The exit logic monster at line 5532 should be broken into:

1. _update_position_price(p, session, _dex_batch_prices) 
   — Lines that fetch/update p.pct_change, p.current_price_sol
   — Currently scattered through the first ~100 lines of the loop

2. _check_universal_exits(p, hold_sec, atr) -> Optional[str]
   — FLOOR_SL / CEILING_TP / ATR_SL / ATR_TP / MAX_HOLD
   — Returns exit_reason or None

3. _check_moonbag_exit(p, hold_sec) -> Optional[str]

4. _check_scalp_exit(p, hold_sec) -> Optional[str]
   — Heat checks + proactive TPs + ratchet + pattern

5. _check_grad_exit(p, hold_sec) -> Optional[str]
   — Pyramiding + trailing + pattern detection

6. _check_momentum_exit(p, hold_sec) -> Optional[str]
   — Grid sells + momentum flat exit

Then update_sim_positions becomes:
```python
async def update_sim_positions(session):
    for mint, p in list(STATE.sim_positions.items()):
        try:
            await _update_position_price(p, session, _dex_batch_prices)
            hold_sec = time.monotonic() - p.entry_time
            atr = calc_position_atr(p)
            
            exit_reason = _check_universal_exits(p, hold_sec, atr)
            if not exit_reason and p.is_moonbag:
                exit_reason = _check_moonbag_exit(p, hold_sec)
            elif not exit_reason:
                handler = {
                    "SCALP": _check_scalp_exit,
                    "GRAD_SNIPE": _check_grad_exit,
                    "MOMENTUM": _check_momentum_exit,
                    "TRENDING": _check_momentum_exit,
                }.get(p.strategy)
                if handler:
                    exit_reason = handler(p, hold_sec)
            
            if exit_reason:
                close_position(p, exit_reason, p.current_price_sol)
        except Exception as e:
            _dbg(f"EXIT_ERROR: {p.symbol} {e}")
```

This makes each exit path independently testable and debuggable.

## PHASE 3: Move build_display to separate file (414 lines)

Move build_display() and its helpers (_uptime, _hs) to 
dashboard_tui.py. Import in scanner.py. The web dashboard 
(dashboard.py) is the primary UI now anyway.

## DO NOT CHANGE
- Any exit logic behavior (just reorganize, don't change thresholds)
- Grid trading engine
- Any working strategy
- Dashboard data JSON format
- CSV logging format

## ORDER OF OPERATIONS
1. Remove dead functions (safest — they're never called)
2. Split update_sim_positions (most impactful for debuggability)
3. Move build_display (lowest priority — cosmetic)

## COMMIT AFTER EACH PHASE
Phase 1: git commit -m "Remove 17 dead functions (~500 lines)"
Phase 2: git commit -m "Split update_sim_positions into 6 focused exit functions"
Phase 3: git commit -m "Move build_display to dashboard_tui.py"
