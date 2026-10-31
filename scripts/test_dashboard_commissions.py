"""
Test: comisioane + swap pe Dashboard (azi/ieri), in Indicele Saptamanal si pe
Motorul AI (magic 770015). Verifica logica de agregare din endpointuri, cu MT5
mock-uit (fara conexiune reala).

Ruleaza din radacina proiectului:
    python scripts/test_dashboard_commissions.py

Ce verifica:
1. /mt5/stats — commission_today/yesterday + swap sunt CONT-WIDE (includ si AI)
2. /mt5/weekly-stats — commission_usd/swap_usd per perioada (cont-wide)
3. /mt5/sessions — doar tranzactiile Bot Engine, atribuite pe sesiune din comment
   (AI Engine pe acelasi simbol NU e atribuit sesiunii botului)
4. /mt5/transactions — filtrele source/session_id + campurile de atribuire
5. raportul programat (Telegram) — construit din MT5, separat Bot / AI

Nota: comisioanele AI se vad ca parte din totalul CONT-WIDE de pe MT5 (sursa MT5
include si Bot, si AI, si manual) — nu exista un breakdown separat pentru AI.
"""

import os, sys
from datetime import datetime, date, timedelta, time as _time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.mt5_pool as mt5_pool
from api.mt5_pool import classify_trade

PASS = 0
FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {msg}")
    else:
        FAIL += 1
        print(f"  FAIL  {msg}")


# ---------------------------------------------------------------------------
# Tranzactii sintetice (close_time = ora locala naiva, ca in mt5_pool)
# ---------------------------------------------------------------------------
AI_MAGIC = 770015
_today = date.today()
_yest  = _today - timedelta(days=1)
_week_start = _today - timedelta(days=_today.weekday())   # luni
_old   = _week_start - timedelta(days=10)                 # cu siguranta alta saptamana


def _dt(d, h=3):
    return datetime.combine(d, _time(h, 0))


TRADES = [
    # AZI — AI (2)
    {"magic": AI_MAGIC, "commission": -2.0, "swap": -0.5, "profit": 10.0, "result_r": 1.0,  "symbol": "EURUSD", "close_time": _dt(_today, 3)},
    {"magic": AI_MAGIC, "commission": -1.5, "swap":  0.0, "profit": -5.0, "result_r": -0.5, "symbol": "USDJPY", "close_time": _dt(_today, 4)},
    # AZI — bot (magic 0)
    {"magic": 0,        "commission": -3.0, "swap": -1.0, "profit":  7.0, "result_r": 1.0,  "symbol": "GBPUSD", "close_time": _dt(_today, 5), "comment": "S15-GBPUSD-IB001"},
    # IERI — AI (1)
    {"magic": AI_MAGIC, "commission": -1.0, "swap": -0.25, "profit": 4.0, "result_r": 0.8,  "symbol": "EURUSD", "close_time": _dt(_yest, 6)},
    # IERI — bot (1)
    {"magic": 0,        "commission": -0.8, "swap":  0.0,  "profit": 2.0, "result_r": 0.5,  "symbol": "GBPUSD", "close_time": _dt(_yest, 7), "comment": "S15-GBPUSD-SIG00"},
    # VECHI (alta saptamana) — AI (1)
    {"magic": AI_MAGIC, "commission": -9.0, "swap": -3.0,  "profit": 1.0, "result_r": 0.1,  "symbol": "EURUSD", "close_time": _dt(_old, 8)},
]


def _with_pool_fields(t):
    """Campurile adaugate de mt5_pool._fetch_closed_trades_raw (atribuire + chei optionale)."""
    base = {"position_id": id(t), "entry_price": 1.0, "entry_time": t["close_time"],
            "exit_price": 1.0, "direction": 1, "sl": None, "tp": None, "planned_r": None,
            "comment": "", **t}
    return {**base, **classify_trade(base["magic"], base["comment"])}


def fake_get_closed_trades(days):
    cutoff = datetime.now() - timedelta(days=days)
    return [_with_pool_fields(t) for t in TRADES if t["close_time"] >= cutoff]


# ── expected (calculate din aceeasi lista, deci robust la ziua saptamanii) ──
def _sum(pred, key):
    return round(sum(t[key] for t in TRADES if pred(t)), 2)


ai = lambda t: t["magic"] == AI_MAGIC
is_today = lambda t: t["close_time"].date() == _today
is_yest  = lambda t: t["close_time"].date() == _yest
is_week  = lambda t: t["close_time"].date() >= _week_start

exp_ai_comm_total = _sum(ai, "commission")
exp_ai_comm_today = _sum(lambda t: ai(t) and is_today(t), "commission")
exp_ai_swap_today = _sum(lambda t: ai(t) and is_today(t), "swap")
exp_ai_comm_yest  = _sum(lambda t: ai(t) and is_yest(t), "commission")
exp_ai_comm_week  = _sum(lambda t: ai(t) and is_week(t), "commission")

exp_all_comm_today = _sum(is_today, "commission")   # cont-wide (bot + AI)
exp_all_comm_week  = _sum(is_week, "commission")


_orig = mt5_pool.get_closed_trades
mt5_pool.get_closed_trades = fake_get_closed_trades

try:
    # -----------------------------------------------------------------------
    # Test 1: /mt5/stats — cont-wide (include si AI)
    # -----------------------------------------------------------------------
    print("\n[Test 1] /mt5/stats — comisioane azi/ieri CONT-WIDE (bot + AI)")
    from api.routers.mt5status import mt5_trade_stats
    s = mt5_trade_stats()
    check(s["connected"] is True, "connected=True")
    check(s["commission_today"] == exp_all_comm_today,
          f"commission_today cont-wide = {exp_all_comm_today} [got {s['commission_today']}]")
    check("commission_yesterday" in s and "swap_yesterday" in s,
          "campurile commission_yesterday/swap_yesterday exista")
    # cont-wide > doar-AI (fiindca include si botul)
    check(abs(s["commission_today"]) > abs(exp_ai_comm_today),
          "comisionul cont-wide de azi INCLUDE botul (mai mare decat doar AI)")

    # -----------------------------------------------------------------------
    # Test 2: /mt5/weekly-stats — comisioane per perioada
    # -----------------------------------------------------------------------
    print("\n[Test 2] /mt5/weekly-stats — commission_usd/swap_usd per perioada")
    from api.routers.mt5status import mt5_weekly_stats
    w = mt5_weekly_stats()
    check(w["connected"] is True, "connected=True")
    cw = w["current_week"]
    check("commission_usd" in cw and "swap_usd" in cw,
          "current_week are commission_usd + swap_usd")
    check(cw["commission_usd"] == exp_all_comm_week,
          f"current_week commission = {exp_all_comm_week} (cont-wide) [got {cw['commission_usd']}]")
    check("commission_usd" in w["previous_month"],
          "previous_month are commission_usd (toate perioadele)")

    # -----------------------------------------------------------------------
    # Test 3: /mt5/sessions — doar Bot, sesiunea din comment
    # -----------------------------------------------------------------------
    print("\n[Test 3] /mt5/sessions — atribuire pe sesiune, fara tranzactiile AI")
    from api.routers.mt5status import mt5_session_stats
    ss = {i["session_id"]: i for i in mt5_session_stats()["items"]}
    check(ss["session15"]["trades_total"] == 2,
          f"session15 (GBPUSD) = 2 trades bot [got {ss['session15']['trades_total']}]")
    check(ss["session1"]["trades_total"] == 0,
          f"session1 (EURUSD) = 0 — tranzactiile AI pe EURUSD NU sunt ale botului [got {ss['session1']['trades_total']}]")

    # -----------------------------------------------------------------------
    # Test 4: /mt5/transactions — filtre source/session + atribuire
    # -----------------------------------------------------------------------
    print("\n[Test 4] /mt5/transactions — source / session_id / strategy")
    from api.routers.mt5status import mt5_transactions
    tb = mt5_transactions(source="bot")
    ta = mt5_transactions(source="ai")
    check(tb["total"] == 2, f"source=bot → 2 [got {tb['total']}]")
    check(ta["total"] == sum(1 for t in TRADES if ai(t)), f"source=ai → toate AI [got {ta['total']}]")
    check(all(i["session_id"] == "session15" for i in tb["items"]), "bot: session_id = session15")
    check({i["strategy"] for i in tb["items"]} == {"inside_bar", "pullback"}, "bot: strategy din comment (IB / SIG)")
    check(mt5_transactions(session_id="session15")["total"] == 2, "filtrul session_id=session15 → 2")
    check(all(i["session_id"] is None for i in ta["items"]), "AI: fara session_id")

    # -----------------------------------------------------------------------
    # Test 5: raportul programat — din MT5, separat pe engine
    # -----------------------------------------------------------------------
    print("\n[Test 5] raport Telegram — construit din MT5, Bot / AI separat")
    import api.scheduled_reports as sr
    txt = sr._build_report(sr._mt5_trades(_today, _today + timedelta(days=1)), "T")
    check("Bot Engine:</b> 1 trades" in txt, "sectiunea Bot Engine are tranzactia botului de azi")
    check("AI Engine:</b> 2 trades" in txt, "sectiunea AI Engine are cele 2 tranzactii AI de azi")
    check("MT5 indisponibil" in sr._build_report(None, "T"), "MT5 indisponibil → mesaj explicit, nu raport gol")

finally:
    mt5_pool.get_closed_trades = _orig

# ---------------------------------------------------------------------------
print(f"\n{'='*60}")
print(f"REZULTAT: {PASS} PASS / {FAIL} FAIL")
print('='*60)
sys.exit(1 if FAIL else 0)
