"""
Teste pentru implementarile noi:
  - Task 1: P&L USD in _outcome_stats() si weekly_stats()
  - Task 2: avg_max_dd in frequency_estimate()
  - Task 3: _build_session_snapshot() complet (BE, friday_close, news, concurrent)
  - Task 4: logica apply-config (campuri suportate)
  - General: nu se strica nimic (baselines, weekly_stats structura, model SessionStatus)

Rulare: python scripts/test_new_features.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = 0
FAIL = 0

def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}{(' — ' + detail) if detail else ''}")

def section(title):
    print(f"\n[{title}]")

# ── 1. _outcome_stats — campuri noi ──────────────────────────────────────────
section("1. _outcome_stats() — campuri pnl_usd_today / pnl_usd_yesterday")
from api.routers.sessions import _outcome_stats

for sess_id in ["session1", "session2", "session3", "session9"]:
    result = _outcome_stats(sess_id)
    check(f"{sess_id}: are 'pnl_usd_today'",    "pnl_usd_today"    in result)
    check(f"{sess_id}: are 'pnl_usd_yesterday'", "pnl_usd_yesterday" in result)
    check(f"{sess_id}: campuri vechi prezente",
          all(k in result for k in ("total", "wins", "losses", "today", "yesterday")))
    # valorile sunt None sau float
    t = result["pnl_usd_today"]
    y = result["pnl_usd_yesterday"]
    check(f"{sess_id}: pnl_usd_today tip corect",    t is None or isinstance(t, float))
    check(f"{sess_id}: pnl_usd_yesterday tip corect", y is None or isinstance(y, float))

# ── 2. weekly_stats — structura extinsa ───────────────────────────────────────
section("2. weekly_stats() — current_month, previous_month, pnl_usd")
from api.routers.sessions import weekly_stats

ws = weekly_stats()
check("are current_week",    "current_week"    in ws)
check("are previous_week",   "previous_week"   in ws)
check("are current_month",   "current_month"   in ws)
check("are previous_month",  "previous_month"  in ws)

for period_key in ("current_week", "previous_week", "current_month", "previous_month"):
    p = ws[period_key]
    for field in ("start", "end", "trades", "wins", "losses", "total_r", "win_rate", "max_dd_r", "pnl_usd"):
        check(f"{period_key}: are '{field}'", field in p, f"keys={list(p.keys())}")
    # pnl_usd e None sau float
    pnl = p["pnl_usd"]
    check(f"{period_key}: pnl_usd tip corect", pnl is None or isinstance(pnl, (int, float)))
    # trades, wins, losses sunt intregi >= 0
    check(f"{period_key}: trades >= 0",  isinstance(p["trades"], int) and p["trades"]  >= 0)
    check(f"{period_key}: wins >= 0",    isinstance(p["wins"],   int) and p["wins"]    >= 0)
    check(f"{period_key}: losses >= 0",  isinstance(p["losses"], int) and p["losses"]  >= 0)

# ── 3. frequency_estimate — avg_max_dd ───────────────────────────────────────
section("3. frequency_estimate() — avg_max_dd")
from api.routers.sessions import frequency_estimate

fe = frequency_estimate()
check("are 'per_week'",    "per_week"    in fe)
check("are 'per_month'",   "per_month"   in fe)
check("are 'avg_max_dd'",  "avg_max_dd"  in fe)
check("are 'missing'",     "missing"     in fe)

dd = fe["avg_max_dd"]
check("avg_max_dd tip corect",  dd is None or isinstance(dd, (int, float)))
if dd is not None:
    check("avg_max_dd <= 0 (drawdown negativ)", dd <= 0,
          f"primit {dd} — DD ar trebui sa fie <= 0%")
    check("avg_max_dd > -100 (rezonabil)", dd > -100,
          f"primit {dd}")

# ── 4. _build_session_snapshot — campuri complete ────────────────────────────
section("4. _build_session_snapshot() — campuri obligatorii prezente")
from api.routers.backtest import _build_session_snapshot

# Config complet cu toti parametrii posibili
full_cfg = {
    "pullback_window": 8,
    "expire_bars": 4,
    "circuit_breaker": 3,
    "session_start": 10,
    "session_end": 18,
    "skip_hours": [15, 16],
    "skip_weekdays": [0],
    "r_base": 2.5, "r_mid": 3.5, "r_top": 4.5, "r_max": 5.5,
    "r_mid_threshold": 1, "r_top_threshold": 2, "r_max_threshold": 3,
    "risk_base": 0.01, "risk_mid": 0.01, "risk_top": 0.012, "risk_max": 0.015,
    "rsi_enabled": True,
    "rsi_buy_min": 40, "rsi_buy_max": 65,
    "rsi_sell_min": 35, "rsi_sell_max": 60,
    "ema_alignment_enabled": True,
    "body_strength_enabled": False,
    "body_strength_min_atr_ratio": 0.15,
    # Break-even
    "break_even_enabled": True,
    "be_trigger_pct": 80,
    "be_lock1_pct": 30,
    "be_lock2_pct": 50,
    "be_phase2_enabled": True,
    "be_phase2_zone_pct": 40,
    # Vineri
    "friday_close_enabled": True,
    "friday_close_hour": 20,
    # Stiri
    "news_protection_enabled": False,
    "news_impact_level": 2,
    "news_pre_minutes": 15,
    "news_post_minutes": 15,
    # Tranzactionare
    "max_concurrent_per_market": 1,
    "min_bars_between_trades": 0,
    # Flag / Inside Bar
    "flag_enabled": False,
    "flag_r_ratio": 2.5,
    "flag_risk_pct": 0.01,
    "inside_bar_enabled": False,
    "inside_bar_r_ratio": 2.5,
    "inside_bar_risk_pct": 0.01,
}

snap = _build_session_snapshot(full_cfg)

be_fields = ["break_even_enabled", "be_trigger_pct", "be_lock1_pct", "be_lock2_pct",
             "be_phase2_enabled", "be_phase2_zone_pct"]
friday_fields = ["friday_close_enabled", "friday_close_hour"]
news_fields = ["news_protection_enabled", "news_impact_level", "news_pre_minutes", "news_post_minutes"]
strategy_fields = ["pullback_window", "expire_bars", "session_start", "session_end",
                   "r_base", "r_mid", "r_top", "r_max",
                   "rsi_enabled", "ema_alignment_enabled"]
trade_fields = ["max_concurrent_per_market", "min_bars_between_trades"]
flag_fields = ["flag_enabled", "flag_r_ratio", "inside_bar_enabled"]

for f in be_fields:
    check(f"snapshot contine '{f}'", f in snap, f"keys={sorted(snap.keys())}")
for f in friday_fields:
    check(f"snapshot contine '{f}'", f in snap)
for f in news_fields:
    check(f"snapshot contine '{f}'", f in snap)
for f in strategy_fields:
    check(f"snapshot contine '{f}'", f in snap)
for f in trade_fields:
    check(f"snapshot contine '{f}'", f in snap)
for f in flag_fields:
    check(f"snapshot contine '{f}'", f in snap)

# Verifica valorile
check("be_trigger_pct = 80", snap.get("be_trigger_pct") == 80)
check("friday_close_hour = 20", snap.get("friday_close_hour") == 20)
check("news_protection_enabled = False", snap.get("news_protection_enabled") == False)

# Nu include campuri de identitate (markets, direction, etc.)
for excluded in ("markets", "direction", "session_key", "execute_trades", "account_fraction"):
    check(f"snapshot NU contine '{excluded}'", excluded not in snap)

# market_allocations vine din frontend_snap
frontend_snap = {"market_allocations": {"EURUSD": 150.0}, "start_balance": 300.0}
snap2 = _build_session_snapshot({"pullback_window": 6}, frontend_snap)
check("market_allocations din frontend_snap", snap2.get("market_allocations") == {"EURUSD": 150.0})
check("start_balance din frontend_snap", snap2.get("start_balance") == 300.0)
check("pullback_window din session_cfg", snap2.get("pullback_window") == 6)

# ── 5. Config minimal (campuri None nu apar in snapshot) ─────────────────────
section("5. _build_session_snapshot() — campuri None sunt omise")
minimal_cfg = {"pullback_window": 8, "break_even_enabled": False}
snap_min = _build_session_snapshot(minimal_cfg)
check("pullback_window prezent", "pullback_window" in snap_min)
check("break_even_enabled prezent (False != None)", "break_even_enabled" in snap_min)
check("be_trigger_pct absent (None in cfg)", "be_trigger_pct" not in snap_min)
check("friday_close_enabled absent (None in cfg)", "friday_close_enabled" not in snap_min)

# ── 6. SessionStatus model — campuri noi ──────────────────────────────────────
section("6. api.models.SessionStatus — campuri pnl_usd_today / pnl_usd_yesterday")
from api.models import SessionStatus

# Poate crea SessionStatus cu campurile noi
s = SessionStatus(
    id="session1", label="S1", markets=["EURUSD"], direction="LONG",
    tf="M15+M30", hours="10-18", validated=True, execute=True, capital_pct=12.5,
    running=False, pid=None,
    signals_today=0, signals_total=0, last_signal_time=None,
    outcomes_total=0, wins=0, losses=0,
    pnl_usd_today=150.25, pnl_usd_yesterday=-50.00,
)
check("pnl_usd_today setat corect",    s.pnl_usd_today    == 150.25)
check("pnl_usd_yesterday setat corect", s.pnl_usd_yesterday == -50.00)

# Default None
s2 = SessionStatus(
    id="session1", label="S1", markets=["EURUSD"], direction="LONG",
    tf="M15+M30", hours="10-18", validated=True, execute=True, capital_pct=12.5,
    running=False, pid=None,
    signals_today=0, signals_total=0, last_signal_time=None,
    outcomes_total=0, wins=0, losses=0,
)
check("pnl_usd_today default None",    s2.pnl_usd_today    is None)
check("pnl_usd_yesterday default None", s2.pnl_usd_yesterday is None)

# ── 7. Baseline backtest neschimbat ──────────────────────────────────────────
section("7. Baseline backtest S1 — numerele neschimbate")
import subprocess, re
result_proc = subprocess.run(
    [sys.executable, "portfolio_backtest.py"],
    capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
out = result_proc.stdout + result_proc.stderr
# Formatul: "TRAIN (primele 70%):  181 trades"  si  "TEST  (ultimele 30%, nevazut):  103 trades"
train_match = re.search(r"TRAIN.*?:\s+(\d+)\s+trades", out)
test_match  = re.search(r"TEST.*?:\s+(\d+)\s+trades", out)
exp_match   = re.search(r"TEST.*?expectancy\s+([+-]?\d+\.\d+)\s*R", out)
dd_match    = re.search(r"Drawdown maxim\s*:\s*([+-]?\d+\.\d+)%", out)

if train_match and test_match:
    train_t = int(train_match.group(1))
    test_t  = int(test_match.group(1))
    total   = train_t + test_t
    check(f"S1 total trades = 284 (baseline)", total == 284, f"primit {total}")
    check(f"S1 train = 181", train_t == 181, f"primit {train_t}")
    check(f"S1 test  = 103", test_t  == 103, f"primit {test_t}")
else:
    check("S1 trades parsabil din output", False, "nu gasit in output")

if exp_match:
    exp = float(exp_match.group(1))
    check(f"S1 test expectancy ~ +0.344R (baseline)", abs(exp - 0.344) < 0.005, f"primit {exp}")
else:
    check("S1 test expectancy parsabil", False)

if dd_match:
    dd = float(dd_match.group(1))
    check(f"S1 DD ~ -40.5% (baseline)", abs(dd - (-40.5)) < 0.5, f"primit {dd}%")
else:
    check("S1 DD parsabil", False)

# ── Sumar ─────────────────────────────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"Rezultat: {PASS} PASS, {FAIL} FAIL")
if FAIL == 0:
    print("Toate testele implementarilor noi TRECUTE.")
else:
    print(f"ATENTIE: {FAIL} teste esuate — verifica inainte de deploy.")
print('='*55)
