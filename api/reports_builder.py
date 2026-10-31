"""
Rapoartele saptamanal / lunar — „ce s-a intamplat, cat de bine, in ce conditii, ce probleme,
ce a mers pe fiecare engine si ce invatam” (nu doar un raport de profit).

Fiecare sectiune e construita IZOLAT: o sursa indisponibila (MT5, calendar, AI) nu pica tot
raportul — sectiunea respectiva spune explicit ce lipseste. Definitiile de performanta sunt
ACELEASI ca Dashboard / Tranzactii (api/routers/mt5status.py::_perf): pozitii INCHISE din MT5,
dedup pe pozitie, win = profit > 0, win rate = W/(W+L), profit brut + costuri separat.

Sectiuni:
  1. Performanta per engine (Custom / AI / Daily) + TOTAL; manualele separat
  2. Comparatia engine-urilor (net, factor de profit, drawdown, consistenta — nu doar win rate)
  3. Conditiile de piata (volatilitate, lichiditate, trend/range) din barele MT5
  4. Evenimente (calendar ForexFactory) + weekend (gap-uri, saptamana urmatoare)
  5. Probleme (notificari, ordine esuate/respinse, blocaje, protectii) cu severitate
  6. Analiza AI (consultativa; daca AI e indisponibil raportul se trimite oricum)
"""
from __future__ import annotations

import csv
import glob
import json
import os
import threading
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
_ENGINES = (("custom", "bot", "⚙️ Custom Engine"), ("ai", "ai", "🤖 AI Engine"), ("daily", "daily", "🕘 Daily Engine"))


def _sgn(v, nd=2):
    if v is None:
        return "—"
    if round(v, nd) == 0:
        return f"{0:.{nd}f}"
    return f"+{v:.{nd}f}" if v > 0 else f"{v:.{nd}f}"


# ── 1-2. Performanta + comparatie ─────────────────────────────────────────────

def engine_stats(trades: list[dict]) -> dict:
    """_perf (definitia Dashboard-ului) + drawdown, factor de profit, consistenta pe zile."""
    from api.routers.mt5status import _perf
    p = _perf(trades)
    eq, peak, dd = 0.0, 0.0, 0.0
    days: dict = {}
    for t in sorted(trades, key=lambda x: x["close_time"]):
        net = t["profit"] + t["commission"] + t["swap"]
        eq += net
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
        d = t["close_time"].date()
        days[d] = days.get(d, 0.0) + net
    p["max_dd"] = round(dd, 2)
    p["profit_factor"] = round(p["profit"] / -p["loss"], 2) if p["loss"] < 0 else None
    p["active_days"] = len(days)
    p["positive_days_pct"] = round(100 * sum(1 for v in days.values() if v > 0) / len(days)) if days else None
    p.pop("symbols", None)
    return p


def daily_shadow(start: datetime, end: datetime) -> dict:
    try:
        from daily_engine.engine import load_trades
        tr = [t for t in load_trades() if start <= datetime.fromisoformat(t["recorded_at"][:19]) < end]
    except Exception:
        return {"trades": 0}
    rs = [t["R"] for t in tr]
    est = [t["pnl_money_est"] for t in tr if t.get("pnl_money_est") is not None]
    return {"trades": len(tr), "wins": sum(1 for r in rs if r > 0), "losses": sum(1 for r in rs if r < 0),
            "total_R": round(sum(rs), 2), "pnl_money_est": round(sum(est), 2) if est else None}


def performance_section(trades: list[dict] | None, start, end, cur: str) -> tuple[str, dict]:
    if trades is None:
        return "📊 <b>Performanță</b>\n⚠️ MT5 indisponibil — performanța nu a putut fi calculată.", {}
    by = {k: [t for t in trades if t.get("source") == src] for k, src, _ in _ENGINES}
    stats = {k: engine_stats(v) for k, v in by.items()}
    engines_all = by["custom"] + by["ai"] + by["daily"]
    stats["total"] = engine_stats(engines_all)
    manual = [t for t in trades if t.get("source") == "manual"]
    lines = ["📊 <b>Performanță (MT5, poziții închise)</b>"]

    def row(label, s):
        if not s["trades"]:
            return f"{label}: nicio tranzacție"
        return (f"{label}: {s['trades']} trades · {s['wins']}W/{s['losses']}L · WR "
                f"{s['win_rate'] if s['win_rate'] is not None else '—'}% · profit {_sgn(s['profit'])} · "
                f"loss {_sgn(s['loss'])} · net {_sgn(s['net'])} {cur}")
    for k, _, label in _ENGINES:
        lines.append(row(label, stats[k]))
        if k == "daily":
            sh = daily_shadow(start, end)
            if sh.get("trades"):
                lines.append(f"   └ SHADOW (virtual): {sh['trades']} trade-uri · {sh['wins']}W/{sh['losses']}L · "
                             f"{_sgn(sh['total_R'])}R" + (f" · ≈{_sgn(sh['pnl_money_est'])} {cur} estimat" if sh.get("pnl_money_est") is not None else ""))
    lines.append(row("Σ <b>TOTAL engine-uri</b>", stats["total"]))
    if manual:
        m = engine_stats(manual)
        lines.append(f"✋ Manual (în afara TOTAL): {m['trades']} trades · net {_sgn(m['net'])} {cur}")
    return "\n".join(lines), stats


def comparison_section(stats: dict, cur: str) -> str:
    cand = {k: stats[k] for k, _, _ in _ENGINES if stats.get(k, {}).get("trades", 0) >= 5}
    if len(cand) < 2:
        return ("⚖️ <b>Comparație engine-uri</b>\nDate insuficiente (minim 2 engine-uri cu ≥ 5 trade-uri în perioadă).")
    names = {k: label for k, _, label in _ENGINES}

    def score(s):    # profitabilitate ajustata la risc: net / |drawdown| (+ consistenta)
        return s["net"] / max(1.0, abs(s["max_dd"])) + (s["positive_days_pct"] or 0) / 200
    best = max(cand, key=lambda k: score(cand[k]))
    worst = min(cand, key=lambda k: score(cand[k]))
    lines = ["⚖️ <b>Comparație engine-uri</b> (profit + risc + drawdown + consistență, nu doar WR)"]
    for k, s in cand.items():
        lines.append(f"• {names[k]}: net {_sgn(s['net'])} {cur} · PF {s['profit_factor'] or '—'} · DD {_sgn(s['max_dd'])} · "
                     f"zile pozitive {s['positive_days_pct']}% · medie {_sgn(s['avg_r'], 3) if s['avg_r'] is not None else '—'}R")
    lines.append(f"🏆 Cel mai bun (ajustat la risc): {names[best]} · cel mai slab: {names[worst]}")
    wr = max(cand, key=lambda k: cand[k]["win_rate"] or 0)
    if wr != best:
        lines.append(f"ℹ️ Cel mai mare WR îl are {names[wr]}, dar nu și cel mai bun rezultat ajustat la risc.")
    return "\n".join(lines)


# ── 3. Conditiile de piata ────────────────────────────────────────────────────

def _er(closes):
    if len(closes) < 3:
        return None
    path = sum(abs(b - a) for a, b in zip(closes[:-1], closes[1:]))
    return abs(closes[-1] - closes[0]) / path if path else None


def market_conditions(symbols: list[str], start: datetime, end: datetime) -> tuple[str, list[dict]]:
    """Din barele MT5: volatilitate (ATR D1 in perioada vs 60 zile anterioare), lichiditate
    (volum tick H1 vs anterior), trend/range (efficiency ratio pe inchiderile D1)."""
    from api import mt5_pool
    rows = []
    try:
        with mt5_pool._LOCK:
            mt5 = mt5_pool._ensure_mt5()
            for s in symbols:
                mt5.symbol_select(s, True)
                d1 = mt5.copy_rates_range(s, mt5.TIMEFRAME_D1, start - timedelta(days=95), end)
                h1 = mt5.copy_rates_range(s, mt5.TIMEFRAME_H1, start - timedelta(days=60), end)
                if d1 is None or len(d1) < 20:
                    continue
                ts0 = start.timestamp()
                prev = [b for b in d1 if b["time"] < ts0][-60:]
                cur = [b for b in d1 if b["time"] >= ts0]
                if len(cur) < 2 or len(prev) < 10:
                    continue
                rng = lambda bs: sum(b["high"] - b["low"] for b in bs) / len(bs)
                vol_ratio = rng(cur) / rng(prev)
                er = _er([b["close"] for b in cur])
                chg = 100 * (cur[-1]["close"] / cur[0]["open"] - 1)
                liq = None
                if h1 is not None and len(h1) > 50:
                    hp = [b["tick_volume"] for b in h1 if b["time"] < ts0]
                    hc = [b["tick_volume"] for b in h1 if b["time"] >= ts0]
                    if hp and hc:
                        liq = (sum(hc) / len(hc)) / (sum(hp) / len(hp))
                rows.append({"symbol": s, "vol_ratio": round(vol_ratio, 2), "er": round(er, 2) if er is not None else None,
                             "change_pct": round(chg, 2), "liq_ratio": round(liq, 2) if liq else None})
    except Exception as e:
        return f"🌍 <b>Condiții de piață</b>\n⚠️ Date de piață indisponibile ({e}).", []
    if not rows:
        return "🌍 <b>Condiții de piață</b>\nDate insuficiente (bare MT5 lipsă pentru perioadă).", []
    lines = ["🌍 <b>Condiții de piață</b> (bare MT5; volatilitate și lichiditate față de cele 60 de zile anterioare)"]
    trend = rng_ = hi = lo = 0
    for r in rows:
        reg = "trend" if (r["er"] or 0) >= 0.35 else "range" if (r["er"] or 0) < 0.15 else "mixt"
        vol = "ridicată" if r["vol_ratio"] > 1.3 else "scăzută" if r["vol_ratio"] < 0.75 else "normală"
        trend += reg == "trend"; rng_ += reg == "range"; hi += vol == "ridicată"; lo += vol == "scăzută"
        liq = f" · lichiditate {r['liq_ratio']}×" if r["liq_ratio"] else ""
        lines.append(f"• {r['symbol']}: {reg} (ER {r['er']}) · volatilitate {vol} ({r['vol_ratio']}×){liq} · {_sgn(r['change_pct'])}%")
    n = len(rows)
    if trend >= n / 2:
        verdict = "predominant în TREND — condiții favorabile strategiilor de continuare (pullback, ORB)"
    elif rng_ >= n / 2:
        verdict = "predominant în RANGE — condiții nefavorabile strategiilor de trend (rupturi false, SL-uri)"
    else:
        verdict = "MIXT — unele piețe în trend, altele în range"
    if hi >= n / 2:
        verdict += "; volatilitate peste normal (SL-uri mai largi, mișcări bruște)"
    elif lo >= n / 2:
        verdict += "; volatilitate sub normal (mișcări mici, costuri relativ mai mari)"
    lines.append(f"➡️ Piața a fost {verdict}.")
    return "\n".join(lines), rows


# ── 4. Evenimente + weekend ───────────────────────────────────────────────────

def events_section(kind: str, start: datetime, end: datetime, now: datetime) -> str:
    lines = ["📅 <b>Evenimente economice (High impact)</b>"]
    try:
        from live.news_guard import _fetch_forexfactory
        evs = [e for e in _fetch_forexfactory() if str(e.get("impact", "")).lower() == "high"]
    except Exception as e:
        evs, err = None, str(e)
    if evs is None or not evs:
        lines.append("Insufficient data — calendarul ForexFactory nu a răspuns acum"
                     + (" (oferă doar săptămâna curentă și următoarea)." if kind == "monthly" else "."))
        return "\n".join(lines)
    from zoneinfo import ZoneInfo
    from datetime import timezone as _tz
    from tz_helper import get_configured_tz_name
    tzl = ZoneInfo(get_configured_tz_name())
    loc = lambda e: e["event_time"].replace(tzinfo=_tz.utc).astimezone(tzl).replace(tzinfo=None)   # UTC -> fusul aplicatiei
    past = [e for e in evs if start <= loc(e) < now]
    future = [e for e in evs if loc(e) >= now]
    if kind == "monthly":
        lines.append("Insufficient data pentru luna întreagă — sursa oferă doar săptămâna curentă și următoarea.")
    else:
        by_cur: dict = {}
        for e in past:
            by_cur.setdefault(e["currency"], []).append(e["title"])
        lines.append("Săptămâna aceasta: " + ("; ".join(f"{c}: {len(v)} ({', '.join(sorted(set(v))[:3])})"
                                                      for c, v in sorted(by_cur.items())) or "niciun eveniment High"))
    if future:
        nxt = sorted(future, key=lambda e: e["event_time"])[:8]
        lines.append("Urmează: " + "; ".join(f"{loc(e):%a %d.%m %H:%M} {e['currency']} {e['title']}" for e in nxt))
    else:
        lines.append("Săptămâna următoare: Insufficient data (calendarul nu e publicat încă).")
    return "\n".join(lines)


def weekend_section(kind: str, symbols: list[str], start: datetime, end: datetime) -> str:
    """Gap-urile de weekend (ultima bara H1 de vineri -> prima de luni), in multipli de ATR D1."""
    from api import mt5_pool
    lines = ["🗓️ <b>Weekend</b>"]
    found = []
    try:
        with mt5_pool._LOCK:
            mt5 = mt5_pool._ensure_mt5()
            for s in symbols:
                h1 = mt5.copy_rates_range(s, mt5.TIMEFRAME_H1, start - timedelta(days=4), end)
                d1 = mt5.copy_rates_range(s, mt5.TIMEFRAME_D1, start - timedelta(days=30), end)
                if h1 is None or d1 is None or len(h1) < 10 or len(d1) < 10:
                    continue
                atr = sum(b["high"] - b["low"] for b in d1[-20:]) / 20
                for a, b in zip(h1[:-1], h1[1:]):
                    if b["time"] - a["time"] > 36 * 3600 and atr > 0:      # pauza de weekend
                        g = (b["open"] - a["close"]) / atr
                        when = datetime.fromtimestamp(b["time"])
                        if start <= when < end:              # redeschiderea cade in perioada
                            found.append((s, when, g))
    except Exception as e:
        return f"🗓️ <b>Weekend</b>\n⚠️ Date indisponibile ({e})."
    if not found:
        lines.append("Insufficient data — nicio redeschidere după weekend în barele MT5 pentru perioadă "
                     "(sau piețe 24/7).")
        return "\n".join(lines)
    big = [f for f in found if abs(f[2]) >= 0.3]
    lines.append(f"{len(found)} redeschideri după weekend analizate pe {len({f[0] for f in found})} piețe; "
                 f"{len(big)} cu gap ≥ 0,3×ATR.")
    for s, w, g in sorted(big, key=lambda x: -abs(x[2]))[:6]:
        lines.append(f"• {s} {w:%d.%m}: gap {_sgn(g, 2)}×ATR ({'în sus' if g > 0 else 'în jos'})")
    if not big:
        lines.append("Redeschideri liniștite — fără schimbări de sentiment semnificative peste weekend.")
    return "\n".join(lines)


# ── 5. Probleme ───────────────────────────────────────────────────────────────

_ISSUE_RULES = [  # (severitate, eticheta, cuvinte-cheie in notificare)
    ("🔴", "Engine oprit neașteptat", ("oprit neasteptat", "oprit neașteptat", "nu rămâne pornit", "nu ramane pornit")),
    ("🔴", "Conexiune MT5 pierdută", ("mt5 deconectat", "conexiune mt5", "ipc", "connection lost", "pierdut conexiunea")),
    ("🔴", "Protecția capitalului activată", ("protectie capital", "protecție capital", "protectia capitalului")),
    ("🔴", "Toate sursele AI indisponibile", ("toate sursele ai",)),
    ("🟠", "Ordine eșuate / erori de execuție", ("retcode", "eroare ordin", "order_send", "esuat", "eșuat", "failed")),
    ("🟠", "Circuit breaker", ("circuit breaker",)),
    ("🟠", "Blocaje Setări Globale", ("blocat global", "global_block", "setari globale", "setări globale")),
    ("🟠", "Filtru AI Strict a blocat", ("filtru ai strict",)),
    ("🟡", "Probleme Ollama / surse AI", ("ollama", "sursa ai", "sursă ai")),
    ("🟡", "Pauze / închideri la știri", ("stiri", "știri", "news")),
]


def issues_section(start: datetime, end: datetime) -> str:
    lines = ["🧯 <b>Probleme / incidente</b>"]
    counts: dict = {}
    coverage = None
    try:
        from api.notifications import _read_all_entries
        entries = _read_all_entries()
        if entries:
            coverage = min(e.get("time", "") for e in entries)[:10]
        for e in entries:
            t = e.get("time", "")[:19]
            if not t or not (start.isoformat() <= t < end.isoformat()):
                continue
            txt = (e.get("text_plain") or e.get("text") or "").lower()
            for sev, label, kws in _ISSUE_RULES:
                if any(k in txt for k in kws):
                    counts[(sev, label)] = counts.get((sev, label), 0) + 1
                    break
    except Exception as ex:
        lines.append(f"⚠️ Jurnalul de notificări indisponibil ({ex}).")
    # Custom Engine: statusuri din jurnalul de lucru (respingeri AI, blocaje, inchideri la stiri)
    st: dict = {}
    for f in glob.glob(os.path.join(DATA, "live_signals", "session*", "outcomes.csv")):
        try:
            for r in csv.DictReader(open(f, encoding="utf-8")):
                tt = (r.get("time_check") or r.get("exit_time") or "")[:19]
                if tt and start.isoformat() <= tt.replace(" ", "T") < end.isoformat():
                    st[r.get("status")] = st.get(r.get("status"), 0) + 1
        except Exception:
            continue
    # AI Engine: decizii esuate / respinse de rails
    ai = {}
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{os.path.join(DATA, 'ai', 'ledger.db')}?mode=ro", uri=True)
        for k, n in con.execute("SELECT exec_status, COUNT(*) FROM decisions WHERE ts >= ? AND ts < ? GROUP BY exec_status",
                                (start.isoformat(), end.isoformat())):
            ai[k] = n
        con.close()
    except Exception:
        pass
    if ai.get("failed"):
        counts[("🟠", "AI: ordine eșuate la plasare")] = ai["failed"]
    for (sev, label), n in sorted(counts.items(), key=lambda kv: ("🔴🟠🟡".index(kv[0][0]), -kv[1])):
        lines.append(f"{sev} {label}: {n}")
    extra = []
    if st.get("ai_reject"):
        extra.append(f"{st['ai_reject']} semnale respinse de filtrul AI")
    if st.get("global_block"):
        extra.append(f"{st['global_block']} blocate de Setările Globale")
    if st.get("news_close") or st.get("news_cancel"):
        extra.append(f"{st.get('news_close', 0)} poziții închise / {st.get('news_cancel', 0)} ordine anulate la știri")
    if ai.get("rejected"):
        extra.append(f"AI: {ai['rejected']} decizii respinse de regulile hard (rails)")
    if extra:
        lines.append("ℹ️ " + " · ".join(extra))
    if len(lines) == 1:
        lines.append("✅ Nicio problemă semnificativă înregistrată.")
    if coverage and coverage > start.isoformat()[:10]:
        lines.append(f"<i>Acoperire parțială: jurnalul de notificări începe la {coverage} (maxim 500 intrări).</i>")
    return "\n".join(lines)


# ── 6. Analiza AI (consultativa) ──────────────────────────────────────────────

_AI_SYSTEM = ("Ești analist de trading pentru un sistem automat cu 3 engine-uri (Custom = reguli pullback; "
              "AI = consiliu LLM; Daily = ORB intraday în shadow). Primești FAPTE dintr-un raport. Răspunde în ROMÂNĂ, "
              "maximum 6 puncte scurte: ce a mers bine, ce a mers prost, pattern-uri, anomalii, probleme repetate, ce ar "
              "trebui îmbunătățit. Folosește DOAR cifrele din fapte, copiate exact (nu recalcula, nu rotunji altfel); "
              "nu confunda categoriile (ex: problemele Ollama nu sunt semnale respinse). Dacă datele sunt prea puține, spune-o.")


def ai_section(facts: dict, timeout_s: float = 150.0) -> str:
    out: dict = {}

    def _run():
        try:
            from ai_engine.config import load_config, load_keys
            from ai_engine.providers import ProviderRegistry
            reg = ProviderRegistry(load_config().get("providers", {}), load_keys())
            order = reg.usable_sources()
            order.sort(key=lambda n: n == reg.DEFAULT)
            for name in order:
                inst = reg._instances.get(name)
                if inst is None:
                    continue
                try:
                    out["text"] = inst.chat(_AI_SYSTEM, json.dumps(facts, ensure_ascii=False, default=str)[:12000]).strip()
                    out["src"] = name
                    reg.report_success(name)
                    return
                except Exception as e:
                    out["err"] = str(e)
        except Exception as e:
            out["err"] = str(e)

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(timeout_s)
    if out.get("text"):
        return f"🧠 <b>Analiză AI</b> <i>(consultativă, sursa: {out['src']} — nu e sursă de adevăr)</i>\n{out['text'][:2500]}"
    return ("🧠 <b>Analiză AI</b>\nIndisponibilă la generarea raportului"
            + (f" ({out['err'][:120]})" if out.get("err") else " (timp depășit)") + " — restul raportului e complet.")


# ── Asamblare ─────────────────────────────────────────────────────────────────

def _markets_for(trades: list[dict] | None) -> list[str]:
    syms: list[str] = []
    for t in trades or []:
        if t["symbol"] not in syms:
            syms.append(t["symbol"])
    for src in ("ai_engine/config.json", "daily_engine/config.json"):
        try:
            c = json.load(open(os.path.join(ROOT, src), encoding="utf-8"))
            for m in c.get("markets", []):
                s = m["symbol"] if isinstance(m, dict) else m
                if s not in syms:
                    syms.append(s)
        except Exception:
            pass
    return syms[:8]


def build_period_report(kind: str, start: datetime, end: datetime, now: datetime,
                        trades: list[dict] | None, with_ai: bool = True) -> list[str]:
    """Intoarce raportul ca lista de mesaje Telegram (fiecare < 4000 caractere)."""
    from api import mt5_pool
    try:
        st = mt5_pool.get_status()
        cur = st.get("currency") or "USD"
        acct = "REAL" if st.get("is_demo") is False else "DEMO" if st.get("is_demo") else "?"
    except Exception:
        cur, acct = "USD", "?"
    from tz_helper import get_configured_tz_name
    title = ("📆 <b>Raport Săptămânal</b>" if kind == "weekly" else "🗓️ <b>Raport Lunar</b>")
    head = (f"{title} — {start:%d.%m.%Y %H:%M} → {end:%d.%m.%Y %H:%M}\n"
            f"<i>Fus orar {get_configured_tz_name()} · cont {acct} · {cur} · sursa rezultatelor: istoricul MT5</i>")
    missing = []
    perf, stats = performance_section(trades, start, end, cur)
    if trades is None:
        missing.append("MT5")
    syms = _markets_for(trades)
    sections = [head, perf, comparison_section(stats, cur) if stats else ""]
    try:
        mc, mrows = market_conditions(syms, start, end)
    except Exception as e:
        mc, mrows = f"🌍 <b>Condiții de piață</b>\n⚠️ {e}", []
    if not mrows:
        missing.append("date de piață")
    sections.append(mc)
    try:
        ev = events_section(kind, start, end, now)
    except Exception as e:
        ev = f"📅 <b>Evenimente</b>\n⚠️ {e}"
    if "Insufficient" in ev:
        missing.append("calendar știri (parțial)")
    sections.append(ev)
    try:
        sections.append(weekend_section(kind, syms, start, end))
    except Exception as e:
        sections.append(f"🗓️ <b>Weekend</b>\n⚠️ {e}")
    try:
        iss = issues_section(start, end)
    except Exception as e:
        iss = f"🧯 <b>Probleme</b>\n⚠️ {e}"
    sections.append(iss)
    if with_ai:
        import re as _re
        plain = lambda s: _re.sub(r"<[^>]+>", "", s)
        facts = {"perioada": f"{start:%d.%m.%Y %H:%M} → {end:%d.%m.%Y %H:%M}", "tip": kind,
                 "context": ("Daily Engine rulează în SHADOW: nu plasează ordine reale, deci 0 tranzacții MT5 e normal; "
                             "trade-urile lui virtuale apar separat. Rezultatele în bani vin din MT5."),
                 "FAPTE (text exact din raport)": "\n\n".join(plain(x) for x in (perf, mc, iss, ev[:1200]))}
        ai = ai_section(facts)
        if "Indisponibil" in ai:
            missing.append("AI")
        sections.append(ai)
    if missing:
        sections.append("⚠️ <i>Componente indisponibile: " + ", ".join(missing) + " — raportul conține restul datelor.</i>")
    # mesaje < 4000 caractere (limita Telegram 4096)
    msgs, curmsg = [], ""
    for s in [x for x in sections if x]:
        if len(curmsg) + len(s) + 2 > 3800 and curmsg:
            msgs.append(curmsg)
            curmsg = ""
        curmsg += ("\n\n" if curmsg else "") + s
    if curmsg:
        msgs.append(curmsg)
    return msgs
