"""
QA: rapoartele saptamanal / lunar (api/scheduled_reports.py + api/reports_builder.py).
Offline — MT5, calendar si AI simulate; NU trimite nimic pe Telegram.
    python scripts/test_reports.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import scheduled_reports as S  # noqa: E402
from api import reports_builder as B  # noqa: E402

PASS = FAIL = 0


def check(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {detail}")


CFG = dict(S.DEFAULT_CONFIG)

print("1. Saptamanal — doar vineri, fereastra continua")
fri_before = datetime(2026, 11, 6, 22, 0)     # vineri 22:00
fri_after = datetime(2026, 11, 6, 23, 35)     # vineri 23:35
sat = datetime(2026, 11, 7, 10, 0)
mon = datetime(2026, 11, 9, 9, 0)
check(not S.weekly_due(fri_before, CFG, {}), "vineri inainte de ora raportului -> nu")
check(S.weekly_due(fri_after, CFG, {}), "vineri dupa ora raportului -> da")
check(not S.weekly_due(fri_after, CFG, {"weekly_sent": "2026-11-06"}), "deja trimis azi -> nu (fara dubluri la restart)")
check(not S.weekly_due(sat, CFG, {}) and not S.weekly_due(mon, CFG, {}), "sambata / luni -> NICIODATA (nici recuperare)")
ws, we = S.weekly_window(fri_after, CFG)
check((ws, we) == (datetime(2026, 10, 30, 23, 30), datetime(2026, 11, 6, 23, 30)), "fereastra vineri 23:30 -> vineri 23:30", (ws, we))
ws2, we2 = S.weekly_window(datetime(2026, 11, 13, 23, 40), CFG)
check(ws2 == we, "ferestre CONTINUE: urmatoarea incepe exact unde s-a terminat (weekendul inclus o singura data)")
check(S.weekly_window(sat, CFG)[1] == datetime(2026, 11, 6, 23, 30), "sambata: ultima fereastra = cea de vineri")
cfg2 = dict(CFG, weekly_time="20:00")
check(S.weekly_due(datetime(2026, 11, 6, 20, 1), cfg2, {}), "ora configurata respectata (20:00)")

print("2. Lunar — luna completa, prima zi disponibila")
check(S.monthly_window(datetime(2026, 11, 1, 9, 0)) == (datetime(2026, 10, 1), datetime(2026, 11, 1)), "1 nov -> octombrie complet")
check(S.monthly_window(datetime(2027, 1, 1, 9, 5)) == (datetime(2026, 12, 1), datetime(2027, 1, 1)), "ianuarie -> decembrie anul trecut")
check(not S.monthly_due(datetime(2026, 11, 1, 8, 59), CFG, {}), "1 nov 08:59 -> inca nu")
check(S.monthly_due(datetime(2026, 11, 1, 9, 0), CFG, {}), "1 nov 09:00 -> da")
check(S.monthly_due(datetime(2026, 11, 3, 14, 0), CFG, {"monthly_sent": "2026-09"}), "API oprit pe 1 -> recuperare la prima ocazie")
check(not S.monthly_due(datetime(2026, 11, 3, 14, 0), CFG, {"monthly_sent": "2026-10"}), "deja trimis pentru octombrie -> nu")
check(S.monthly_window(datetime(2026, 11, 1))[1] - S.monthly_window(datetime(2026, 11, 1))[0] == timedelta(days=31),
      "octombrie = 31 de zile (inclusiv weekendurile)")

print("3. Configurare")
S.CONFIG_FILE = os.path.join(tempfile.mkdtemp(), "reports_config.json")
c = S.save_reports_config({"weekly_time": "21:5", "weekly_weekday": 2, "monthly_day": 40})
check(c["weekly_time"] == "21:05" and c["weekly_weekday"] == 4 and c["monthly_day"] == 28,
      "ora normalizata, saptamanalul ramane vineri, ziua lunara limitata la 28", c)
try:
    S.save_reports_config({"daily_time": "25:00"})
    check(False, "ora invalida respinsa")
except ValueError:
    check(True, "ora invalida respinsa")

print("4. Continut + failure handling")
B.market_conditions = lambda syms, s, e: ("🌍 <b>Condiții de piață</b>\nok", [{"symbol": "EURUSD"}])
B.weekend_section = lambda k, syms, s, e: "🗓️ <b>Weekend</b>\nok"
B.events_section = lambda k, s, e, n: "📅 <b>Evenimente</b>\nok"
B.issues_section = lambda s, e: "🧯 <b>Probleme</b>\nok"
B.ai_section = lambda facts, timeout_s=150: "🧠 <b>Analiză AI</b>\nIndisponibilă la generarea raportului (test)"
import api.mt5_pool as P  # noqa: E402
P.get_status = lambda: {"currency": "USD", "is_demo": False}


def tr(src, profit, day, sym="EURUSD", r=None):
    return {"source": src, "profit": profit, "commission": -0.07, "swap": 0.0, "symbol": sym,
            "close_time": datetime(2026, 11, day, 12), "result_r": r}


start, end, now = datetime(2026, 10, 30, 23, 30), datetime(2026, 11, 6, 23, 30), datetime(2026, 11, 6, 23, 31)
txt = "\n".join(B.build_period_report("weekly", start, end, now, None, with_ai=True))
check("MT5 indisponibil" in txt and "Componente indisponibile: MT5" in txt and "Condiții de piață" in txt,
      "MT5 indisponibil -> raportul se trimite, sectiunea marcata, restul prezent")
txt = "\n".join(B.build_period_report("weekly", start, end, now, [], with_ai=True))
check("nicio tranzacție" in txt and "Date insuficiente" in txt, "saptamana fara trade-uri -> raport valid + comparatie 'date insuficiente'")
check("Indisponibil" in txt and "AI" in txt.split("Componente indisponibile:")[-1], "AI indisponibil -> mentionat, raport complet")
trades = [tr("bot", 2.0, 2), tr("bot", -1.0, 3), tr("bot", 1.5, 4), tr("bot", -0.5, 4), tr("bot", 3.0, 5),
          tr("ai", -1.0, 2), tr("ai", -1.0, 3), tr("ai", 0.8, 4), tr("ai", -0.6, 5), tr("ai", 1.2, 5),
          tr("manual", 5.0, 3)]
parts = B.build_period_report("weekly", start, end, now, trades, with_ai=False)
txt = "\n".join(parts)
check("5 trades · 3W/2L · WR 60.0%" in txt, "Custom: aceeasi definitie ca Dashboard (WR = W/(W+L))", txt[:600])
check("TOTAL engine-uri</b>: 10 trades" in txt and "Manual (în afara TOTAL): 1" in txt, "TOTAL = engine-uri; manualul separat")
check("Cel mai bun (ajustat la risc)" in txt and "nu doar WR" in txt, "comparatie pe profit + risc + DD + consistenta")
check("Daily Engine: nicio tranzacție" in txt, "Daily fara tranzactii reale (shadow) -> afisat explicit")
st = B.engine_stats([tr("bot", 2.0, 2), tr("bot", -3.0, 3), tr("bot", 1.0, 4)])
check(st["max_dd"] == -3.07 and st["profit_factor"] == 1.0, "drawdown si factor de profit corecte", st)
big = [tr("bot", 1.0, 2, sym=f"S{i}") for i in range(400)]
B.issues_section = lambda s, e: "🧯 <b>Probleme</b>\n" + "x" * 3500
parts = B.build_period_report("monthly", start, end, now, big, with_ai=False)
check(len(parts) >= 2 and all(len(p) < 4000 for p in parts), "raport lung -> impartit in mesaje < 4000 caractere", [len(p) for p in parts])


def boom(*a, **k):
    raise RuntimeError("calendar picat")


B.events_section = boom
txt = "\n".join(B.build_period_report("weekly", start, end, now, trades, with_ai=False))
check("calendar picat" in txt and "Performanță" in txt, "o sectiune care arunca -> marcata, raportul continua")

print("5. Modul liniste nu mai suprima rapoartele")
from api.notifications import is_important_notification as imp  # noqa: E402
check(imp("📆 <b>Raport Săptămânal</b> — x") and imp("🗓️ <b>Raport Lunar</b> — x") and imp("📅 Raport Zilnic — x"),
      "rapoartele sunt importante (trimise si in modul liniste)")

print(f"\nREZULTAT: {PASS} PASS / {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
