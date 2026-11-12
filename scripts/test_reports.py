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

print("1. Saptamanal — vineri de la 20:00, fereastra continua, recuperare pana luni 12:00")
check(CFG["weekly_time"] == "20:00", "ora implicita = vineri 20:00 (laptopul se inchide de obicei dupa 20:00)")
fri_before = datetime(2026, 11, 6, 19, 59)     # vineri 19:59
fri_after = datetime(2026, 11, 6, 20, 5)       # vineri 20:05
sat = datetime(2026, 11, 7, 10, 0)
mon = datetime(2026, 11, 9, 9, 0)
mon_late = datetime(2026, 11, 9, 12, 1)
check(not S.weekly_due(fri_before, CFG, {}), "vineri inainte de ora raportului -> nu")
check(S.weekly_due(fri_after, CFG, {}), "vineri dupa ora raportului -> da")
check(not S.weekly_due(fri_after, CFG, {"weekly_sent": "2026-11-06"}), "deja trimis pentru vinerea asta -> nu (fara dubluri la restart)")
check(S.weekly_due(sat, CFG, {}) and S.weekly_due(mon, CFG, {}),
      "laptop inchis vineri -> RECUPERAT sambata / luni dimineata")
check(not S.weekly_due(sat, CFG, {"weekly_sent": "2026-11-06"}), "... o singura data")
check(not S.weekly_due(mon_late, CFG, {}), "luni dupa 12:00 -> nu mai recupereaza (raport vechi)")
check(not S.weekly_due(datetime(2026, 11, 4, 12, 0), CFG, {"weekly_sent": "2026-10-30"}), "miercuri (deja trimis vinerea trecuta) -> nu")
ws, we = S.weekly_window(fri_after, CFG)
check((ws, we) == (datetime(2026, 10, 30, 20, 0), datetime(2026, 11, 6, 20, 0)), "fereastra nominala vineri 20:00 -> vineri 20:00", (ws, we))
check(S.weekly_window(sat, CFG)[1] == datetime(2026, 11, 6, 20, 0), "sambata: ultima fereastra = cea de vineri")
w = S.weekly_send_window(datetime(2026, 11, 6, 20, 12), CFG, {"weekly_last_end": "2026-10-30T20:09:00"})
check(w == (datetime(2026, 10, 30, 20, 9), datetime(2026, 11, 6, 20, 12)),
      "fereastra trimisa = de la sfarsitul raportului trecut pana ACUM (inchiderile de vineri 20:00-20:12 incluse)", w)
w = S.weekly_send_window(datetime(2026, 11, 6, 20, 12), CFG, {})
check(w[0] == datetime(2026, 10, 30, 20, 0), "fara marcaj -> inceputul nominal", w)
pos = [{"symbol": "EURUSD", "comment": "S1-EURUSD-1"}, {"symbol": "BTCUSD", "comment": "S3-BTCUSD-2"}]
check(S.friday_close_pending(fri_after, pos), "vineri: pozitie Custom FX deschisa -> asteapta inchiderea de vineri")
check(not S.friday_close_pending(fri_after, [pos[1]]), "... doar cripto (non-stop) -> nu asteapta")
check(not S.friday_close_pending(sat, pos), "... in afara zilei de vineri -> nu asteapta")
cfg2 = dict(CFG, weekly_time="21:30")
check(not S.weekly_due(datetime(2026, 11, 6, 21, 0), cfg2, {}) and S.weekly_due(datetime(2026, 11, 6, 21, 31), cfg2, {}),
      "ora configurata respectata (21:30)")

print("2. Lunar — luna completa, prima zi disponibila")
check(S.monthly_window(datetime(2026, 11, 1, 9, 0)) == (datetime(2026, 10, 1), datetime(2026, 11, 1)), "1 nov -> octombrie complet")
check(S.monthly_window(datetime(2027, 1, 1, 9, 5)) == (datetime(2026, 12, 1), datetime(2027, 1, 1)), "ianuarie -> decembrie anul trecut")
check(not S.monthly_due(datetime(2026, 11, 1, 8, 59), CFG, {}), "1 nov 08:59 -> inca nu")
check(S.monthly_due(datetime(2026, 11, 1, 9, 0), CFG, {}), "1 nov 09:00 -> da")
check(S.monthly_due(datetime(2026, 11, 3, 14, 0), CFG, {"monthly_sent": "2026-09"}), "API oprit pe 1 -> recuperare la prima ocazie")
check(not S.monthly_due(datetime(2026, 10, 31, 17, 10), CFG, {}), "prima pornire pe 31 -> NU trimite luna trecuta cu o luna intarziere")
check(not S.monthly_due(datetime(2026, 11, 8, 9, 0), CFG, {}), "dupa 7 zile -> nu mai recupereaza")
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

print("3b. Programatorul (pas cu pas): zilnic optional + fara dubluri, saptamanal asteapta vinerea, lunar doar luna incheiata")
_tmpd = tempfile.mkdtemp()
S.STATE_FILE = os.path.join(_tmpd, "reports_state.json")
S.CONFIG_FILE = os.path.join(_tmpd, "reports_config2.json")
SENT_R = []
S.send_daily_report = lambda d: SENT_R.append(("daily", d)) or ""
_orig_period = S.send_period_report
S.send_period_report = lambda kind, now=None, window=None: SENT_R.append((kind, window)) or ""
ok_ready = lambda kind, now: True
no_pend = lambda now: False
S._last_daily = None
d1 = datetime(2026, 11, 11, 23, 31)
check(S.scheduler_tick(d1, ready=ok_ready, pending=no_pend) == ["daily"], "zilnic: trimis la 23:31")
S._last_daily = None                                         # restart al API-ului (memoria pierduta)
check(S.scheduler_tick(datetime(2026, 11, 11, 23, 40), ready=ok_ready, pending=no_pend) == [],
      "restart / al doilea API: zilnicul NU se mai trimite (marcaj persistent)")
S.save_reports_config({"daily_enabled": False})
S._last_daily = None
check(S.scheduler_tick(datetime(2026, 11, 12, 23, 31), ready=ok_ready, pending=no_pend) == [], "zilnic OPRIT -> nu se trimite")
S.save_reports_config({"daily_enabled": True})
fri = datetime(2026, 11, 13, 20, 1)
check("weekly" not in S.scheduler_tick(fri, ready=ok_ready, pending=lambda now: True),
      "vineri 20:01 cu pozitii Custom inca deschise -> asteapta inchiderea de vineri")
out = S.scheduler_tick(datetime(2026, 11, 13, 20, 6), ready=ok_ready, pending=no_pend)
check("weekly" in out and SENT_R[-1][1][1] == datetime(2026, 11, 13, 20, 6),
      "pozitiile s-au inchis -> trimis, fereastra pana in momentul trimiterii", SENT_R[-1])
check("weekly" not in S.scheduler_tick(datetime(2026, 11, 13, 20, 30), ready=ok_ready, pending=no_pend), "o singura data")
out = S.scheduler_tick(datetime(2026, 11, 13, 20, 25), ready=ok_ready, pending=lambda now: True)
S.STATE_FILE = os.path.join(_tmpd, "reports_state_b.json")
check("weekly" in S.scheduler_tick(datetime(2026, 11, 13, 20, 21), ready=ok_ready, pending=lambda now: True),
      "pozitii tot deschise dupa 20 min -> trimis oricum (nu se pierde raportul)")
S.STATE_FILE = os.path.join(_tmpd, "reports_state_c.json")
check("weekly" in S.scheduler_tick(datetime(2026, 11, 16, 8, 0), ready=ok_ready, pending=no_pend),
      "laptop inchis vineri -> recuperat luni dimineata")
S.send_period_report = _orig_period
sent_n = []
_orig_log = S.log_notification
S.log_notification = lambda t: sent_n.append(t)
r = S.send_period_report("monthly", datetime(2026, 11, 20, 10, 0), window=(datetime(2026, 11, 1), datetime(2026, 12, 1)))
check(r == "" and sent_n and "refuzat" in sent_n[-1], "garda: un raport lunar pe luna CURENTA (noiembrie, pe 20.11) e refuzat")
S.log_notification = _orig_log
S.send_period_report = lambda kind, now=None, window=None: SENT_R.append((kind, window)) or ""
mig = os.path.join(_tmpd, "reports_config_old.json")
open(mig, "w", encoding="utf-8").write('{"weekly_time": "23:30", "daily_time": "22:00"}')
S.CONFIG_FILE = mig
c = S.load_reports_config()
check(c["weekly_time"] == "20:00" and c["daily_time"] == "22:00" and c["daily_enabled"] is True,
      "migrare: vechiul implicit 23:30 -> 20:00; ora zilnica aleasa de user pastrata; zilnic pornit implicit", c)
S.save_reports_config({"weekly_time": "23:30"})
check(S.load_reports_config()["weekly_time"] == "23:30", "dupa migrare, 23:30 ales explicit de user ramane")
S.send_period_report = _orig_period

print("4. Continut + failure handling")
_ROWS = [{"symbol": "EURUSD", "vol_ratio": 1.0, "er": 0.4, "change_pct": 0.5, "liq_ratio": 1.0},
         {"symbol": "US500", "vol_ratio": 1.4, "er": 0.1, "change_pct": -1.2, "liq_ratio": None}]
_full_issues, _full_events, _full_weekend = B.issues_section, B.events_section, B.weekend_section
B.market_conditions = lambda syms, s, e: ("🌍 <b>Condiții de piață</b>\nok", _ROWS)
B.weekend_section = lambda k, syms, s, e, brief=False: "🗓️ <b>Weekend</b>\nok"
B.events_section = lambda k, s, e, n, brief=False: "📅 <b>Evenimente</b>\nok"
B.issues_section = lambda s, e, brief=False: "🧯 <b>Probleme</b>\nok"
B.ai_section = lambda facts, timeout_s=150, brief=False: "🧠 <b>Analiză AI</b>\nIndisponibilă la generarea raportului (test)"
import api.mt5_pool as P  # noqa: E402
P.get_status = lambda: {"currency": "USD", "is_demo": False}


def tr(src, profit, day, sym="EURUSD", r=None):
    return {"source": src, "profit": profit, "commission": -0.07, "swap": 0.0, "symbol": sym,
            "close_time": datetime(2026, 11, day, 12), "result_r": r}


start, end, now = datetime(2026, 10, 30, 23, 30), datetime(2026, 11, 6, 23, 30), datetime(2026, 11, 6, 23, 31)
txt = "\n".join(B.build_period_report("weekly", start, end, now, None, with_ai=True))
check("MT5 indisponibil" in txt and "Componente indisponibile: MT5" in txt and "Piața" in txt,
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
B.issues_section = lambda s, e, brief=False: "🧯 <b>Probleme</b>\n" + "x" * 3500
parts = B.build_period_report("monthly", start, end, now, big, with_ai=False)
check(len(parts) >= 2 and all(len(p) < 4000 for p in parts), "raport lung -> impartit in mesaje < 4000 caractere", [len(p) for p in parts])


def boom(*a, **k):
    raise RuntimeError("calendar picat")


B.events_section = boom
txt = "\n".join(B.build_period_report("weekly", start, end, now, trades, with_ai=False))
check("calendar picat" in txt and "Performanță" in txt, "o sectiune care arunca -> marcata, raportul continua")

print("4b. Saptamanal = esential (trading complet, context scurt); lunar = complet")
B.issues_section = lambda s, e, brief=False: "" if brief else "🧯 <b>Probleme</b>\nok"
B.weekend_section = lambda k, syms, s, e, brief=False: "" if brief else "🗓️ <b>Weekend</b>\nok"
B.events_section = lambda k, s, e, n, brief=False: "📅 <b>Evenimente</b>\nok"
wk = "\n".join(B.build_period_report("weekly", start, end, now, trades, with_ai=False))
mo = "\n".join(B.build_period_report("monthly", start, end, now, trades, with_ai=False))
check("5 trades · 3W/2L · WR 60.0%" in wk and "Cel mai bun (ajustat la risc)" in wk,
      "saptamanal: partea de trading neschimbata (performanta + comparatie)")
check("🌍 <b>Piața</b>: TREND" in wk and "EURUSD trend +0.50%" in wk and "US500 range -1.20%" in wk
      and "Condiții de piață" not in wk, "saptamanal: piata intr-un rand (regim + variatie)", wk[-400:])
check("Weekend" not in wk and "Probleme" not in wk, "saptamanal: weekend / probleme omise cand nu e nimic de raportat")
check("Condiții de piață" in mo and "Weekend" in mo and "Probleme" in mo, "lunar: ramane complet")
wk2 = "\n".join(B.build_period_report("weekly", start, end, now, trades, with_ai=False, brief=False))
check("Condiții de piață" in wk2, "brief=False -> saptamanal complet (la cerere)")

print("4c. Sectiunile esentiale reale")
import api.notifications as N  # noqa: E402
_orig_read = N._read_all_entries
N._read_all_entries = lambda: [
    {"time": "2026-11-02T10:00:00", "text_plain": "Ollama a inchis conexiunea"},
    {"time": "2026-11-03T10:00:00", "text_plain": "Bot Trading oprit neasteptat!"},
    {"time": "2026-11-03T11:00:00", "text_plain": "eroare ordin retcode 10006"}]
iss = _full_issues(start, end, brief=True)
check(iss.startswith("🧯 <b>Probleme</b>:") and "Engine oprit neașteptat (1)" in iss and "Ordine eșuate" in iss
      and "Ollama" not in iss, "probleme esentiale: doar 🔴/🟠, pe un rand", iss)
N._read_all_entries = lambda: [{"time": "2026-11-02T10:00:00", "text_plain": "Ollama a inchis conexiunea"}]
check(_full_issues(start, end, brief=True) == "", "doar zgomot 🟡 -> sectiunea lipseste")
N._read_all_entries = _orig_read

print("5. Modul liniste nu mai suprima rapoartele")
from api.notifications import is_important_notification as imp  # noqa: E402
check(imp("📆 <b>Raport Săptămânal</b> — x") and imp("🗓️ <b>Raport Lunar</b> — x") and imp("📅 Raport Zilnic — x"),
      "rapoartele sunt importante (trimise si in modul liniste)")

print("6. Incident 2.11: raportul lunar recuperat la pornire a plecat GOL (MT5 inca neautentificat)")
import time as _time  # noqa: E402
nov2 = datetime(2026, 11, 2, 9, 30)
m0 = S._STARTED
S._deferred.clear()
check(not S.report_ready("monthly", nov2, mono=m0 + 30, ready=lambda: (True, "")),
      "primele minute dupa pornirea API-ului -> NU genereaza (gratie la pornire)")
S._deferred.clear()
_logged = []
S.log_notification = lambda t: _logged.append(t)
check(not S.report_ready("monthly", nov2, mono=m0 + 400, ready=lambda: (False, "niciun cont MT5 autentificat")),
      "MT5 neautentificat -> raport AMANAT (nu se trimite gol)")
check(len(_logged) == 1 and "amânat" in _logged[0], "amanarea e notificata o singura data", _logged)
check(not S.report_ready("monthly", nov2, mono=m0 + 460, ready=lambda: (False, "x")) and len(_logged) == 1,
      "a doua incercare -> tot amanat, fara notificare dubla")
check(S.report_ready("monthly", nov2, mono=m0 + 520, ready=lambda: (True, "")), "MT5 gata -> se genereaza")
S._deferred.clear()
S.report_ready("monthly", nov2, mono=m0 + 400, ready=lambda: (False, "x"))
check(S.report_ready("monthly", nov2, mono=m0 + 400 + S.REPORT_DEFER_MAX_S, ready=lambda: (False, "x")),
      "MT5 indisponibil > 3h -> se trimite, cu MT5 marcat indisponibil (nu ramane netrimis la nesfarsit)")
S._deferred.clear()
S.report_ready("weekly", datetime(2026, 11, 6, 23, 31), mono=m0 + 400, ready=lambda: (False, "x"))
check(S.report_ready("weekly", datetime(2026, 11, 6, 23, 56), mono=m0 + 1900, ready=lambda: (False, "x")),
      "saptamanal: la 23:55 vineri se trimite oricum (nu se recupereaza sambata)")
S._deferred.clear()

# _mt5_trades_between: indisponibil (cont neautentificat) = None, NU [] („nicio tranzactie”)
_orig_hs, _orig_gct = P.history_status, P.get_closed_trades
P.history_status = lambda: (False, "niciun cont MT5 autentificat")
P.get_closed_trades = lambda days: []
check(S._mt5_trades_between(datetime(2026, 10, 1), datetime(2026, 11, 1)) is None,
      "istoric neincarcat -> None (raportul spune 'MT5 indisponibil', nu 'nicio tranzactie')")
oct_trades = [dict(tr("bot", 1.0, 1), close_time=datetime(2026, 10, d, 12)) for d in (1, 15, 31)]
oct_trades += [dict(tr("ai", -1.0, 1), close_time=datetime(2026, 11, 1, 0, 0)),    # 1 nov 00:00 → luna urmatoare
               dict(tr("ai", -1.0, 1), close_time=datetime(2026, 9, 30, 23, 59))]  # 30 sep → luna trecuta
P.history_status = lambda: (True, "")
P.get_closed_trades = lambda days: oct_trades
got = S._mt5_trades_between(*S.monthly_window(nov2))
check(got is not None and len(got) == 3, "octombrie: [1 oct 00:00, 1 nov 00:00) — capetele corecte (3 din 5)", got and len(got))
txt = "\n".join(B.build_period_report("monthly", *S.monthly_window(nov2), nov2, None, with_ai=False))
check("NU înseamnă zero tranzacții" in txt, "mesajul de MT5 indisponibil nu poate fi confundat cu luna goala")
P.get_closed_trades = lambda days: []
got = S._mt5_trades_between(*S.monthly_window(nov2))
txt = "\n".join(B.build_period_report("monthly", *S.monthly_window(nov2), nov2, got, with_ai=False))
check(got == [] and "nicio tranzacție" in txt, "luna REAL fara tranzactii (MT5 gata) -> raport valid 'nicio tranzactie'")

# fluxul automat cap-coada (scheduler): MT5 neautentificat → nimic trimis, marcaj nescris; apoi gata → trimis o data
sent, state = [], {}
S._state, S._save_state = (lambda: dict(state)), (lambda st: (state.clear(), state.update(st)))
S.send_period_report = lambda kind, now=None: sent.append(kind) or ""
S.load_reports_config = lambda: dict(S.DEFAULT_CONFIG, daily_time="23:59")
readiness = [(False, "niciun cont")]
S._mt5_ready = lambda: readiness[0]
S._STARTED = _time.monotonic() - 1000
S._deferred.clear()


def tick(now):
    cfg = S.load_reports_config()
    st = S._state()
    if S.monthly_due(now, cfg, st) and S.report_ready("monthly", now):
        st["monthly_sent"] = S.monthly_window(now)[0].strftime("%Y-%m")
        S._save_state(st)
        S.send_period_report("monthly", now)


tick(nov2)
check(sent == [] and "monthly_sent" not in state, "pornire cu MT5 neautentificat: nimic trimis, marcaj NEscris")
readiness[0] = (True, "")
tick(datetime(2026, 11, 2, 9, 31))
tick(datetime(2026, 11, 2, 9, 32))
check(sent == ["monthly"] and state.get("monthly_sent") == "2026-10", "MT5 gata -> raportul pe octombrie trimis O DATA", (sent, state))
P.history_status, P.get_closed_trades = _orig_hs, _orig_gct

print(f"\nREZULTAT: {PASS} PASS / {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
