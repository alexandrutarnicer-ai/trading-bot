"""
Piete active + semnale GLOBALE pentru Dashboard — toate engine-urile (Custom / AI / Daily / Noisy).

Inlocuieste grila "Sesiuni active" (S1..S22, doar Custom Engine) cu o vedere PE PIATA:
o piata apare o singura data, cu engine-urile care o folosesc ACUM (descoperite din
configuratiile reale — profilul Custom, ai_engine/config.json, daily_engine/config.json,
noisy_engine/config.json — nimic hardcodat) si cu starea fiecaruia pe acea piata.

Doua niveluri de stare, separate intentionat:
  - Engine pornit / oprit  (procesul engine-ului: PID viu)
  - Piata pe acel engine   (ce face engine-ul ACUM pe piata):
        in_position  pozitie reala deschisa (sau virtuala in shadow — marcat)
        active       poate deschide acum (in program, nimic nu blocheaza)
        observe      analizeaza dar NU plaseaza ordine (Custom observatie, AI observatie, Daily/Noisy shadow)
        idle         engine pornit, dar in afara programului (ore / zi / weekend / fereastra)
        blocked      blocat cu motiv (pauza, stiri, Setari Globale, limite, buget, eroare)
        stopped      engine-ul (sau sesiunea) nu ruleaza

Sursa rezultatelor = MT5 (api/mt5_pool, aceeasi lista ca /mt5/stats si rapoartele, atribuire
classify_trade). Trade-urile VIRTUALE (Daily / Noisy shadow) sunt raportate separat, in R,
niciodata adunate la bani.

Structura: `collect()` citeste (fiecare engine izolat in try — un engine stricat nu strica
restul) → `build(inputs, now)` = functie PURA (testata offline in scripts/test_market_overview.py).
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

ENGINES = ("custom", "ai", "daily", "noisy")
# ordinea de prioritate pentru starea AGREGATA a pietei (prima gasita castiga)
STATUS_ORDER = ("in_position", "active", "observe", "idle", "blocked", "stopped")
STATUS_LABEL = {"in_position": "În poziție", "active": "Activ", "observe": "Observație",
                "idle": "În afara programului", "blocked": "Blocat", "stopped": "Oprit"}

_CACHE_TTL = 5.0
_cache: dict = {"ts": 0.0, "data": None}

_DAILY_PHASE = {
    "waiting_open": ("idle", "așteaptă deschiderea"),
    "forming_or": ("active", "formează intervalul de deschidere"),
    "waiting_entry": ("active", "așteaptă intrarea"),
    "in_position": ("in_position", "în poziție"),
    "closed": ("idle", "terminat azi (1 trade / zi)"),
    "skipped": ("idle", "sărit azi"),
    "weekend": ("idle", "weekend"),
    "disabled": ("stopped", "piață dezactivată"),
    "error": ("blocked", "eroare"),
}
_NOISY_BLOCKED = {"paused", "budget_locked", "loss_limit", "loss_streak", "trade_limit", "risk_locked", "error"}


def _is_crypto(sym: str) -> bool:
    try:
        from live.global_guard import is_crypto
        return is_crypto(sym)
    except Exception:
        return str(sym).upper().startswith(("BTC", "ETH", "XRP", "LTC", "SOL", "ADA", "DOGE"))


def _net(t: dict) -> float:
    return float(t.get("profit") or 0) + float(t.get("commission") or 0) + float(t.get("swap") or 0)


def _custom_hours(s: dict, now: datetime) -> tuple[bool, str]:
    """(in program, motiv) — aceeasi regula ca signal_generator._check_signals (ora / zi / weekend)."""
    start, end = int(s.get("session_start", 0)), int(s.get("session_end", 24))
    skip_wd = set(s.get("skip_weekdays") or [])
    if s.get("friday_close_enabled", True) and not _is_crypto(s["symbol"]):
        skip_wd |= {5, 6}
    if now.weekday() in skip_wd:
        return False, "weekend" if now.weekday() >= 5 else "zi exclusă din program"
    if not (start <= now.hour < end):
        return False, f"în afara orelor ({start:02d}–{end:02d})"
    if now.hour in set(s.get("skip_hours") or []):
        return False, f"ora {now.hour:02d} exclusă"
    return True, ""


def _ai_weekend(sym: str, now: datetime, close_hour: int = 22) -> bool:
    if _is_crypto(sym):
        return False
    return now.weekday() >= 5 or (now.weekday() == 4 and now.hour >= close_hour)


# ── calcul PUR ────────────────────────────────────────────────────────────────

def engine_entries(inp: dict, now: datetime) -> list[dict]:
    """O intrare (piata, engine) pentru fiecare piata configurata pe fiecare engine."""
    out: list[dict] = []
    glob = inp.get("global_block")          # motiv cont-wide (Setari Globale) sau None
    pos = inp.get("positions") or []

    def has_pos(sym: str, src: str) -> int:
        return sum(1 for p in pos if p.get("symbol") == sym and p.get("source") == src)

    # Custom Engine — o intrare per sesiune (piata unica per sesiune)
    c = inp.get("custom") or {}
    for s in c.get("sessions", []):
        sym = s["symbol"]
        e = {"symbol": sym, "engine": "custom", "ref": s["id"], "session_key": s["session_key"],
             "direction": s.get("direction"), "tf": s.get("tf"),
             "mode": "live" if s.get("execute") else "obs", "positions": has_pos(sym, "bot")}
        in_hours, why = _custom_hours(s, now)
        if not c.get("running") or not s.get("running"):
            e.update(status="stopped", reason="Custom Engine oprit" if not c.get("running") else "sesiunea nu rulează")
        elif s.get("paused"):
            e.update(status="blocked", reason="pauză manuală", manual_pause=True)
        elif s.get("news_paused"):
            e.update(status="blocked", reason="protecție știri")
        elif not s.get("execute"):
            e.update(status="observe", reason="observație — semnale fără ordine")
        elif glob:
            e.update(status="blocked", reason=glob)
        elif e["positions"]:
            e.update(status="in_position", reason=f"{e['positions']} poziție/ii deschise")
        elif not in_hours:
            e.update(status="idle", reason=why)
        else:
            e.update(status="active", reason="caută setup-uri")
        if e["positions"] and e["status"] != "in_position":
            e["reason"] += f" · {e['positions']} poziție/ii deschise"
        out.append(e)

    # AI Engine
    a = inp.get("ai") or {}
    ms = a.get("market_status") or {}
    for sym in a.get("markets", []):
        mode_obs = (a.get("modes") or {}).get(sym) == "observe"
        e = {"symbol": sym, "engine": "ai", "ref": "AI", "direction": "BOTH", "tf": "M15",
             "mode": "obs" if mode_obs else ("shadow" if a.get("mode") == "shadow" else "live"),
             "positions": has_pos(sym, "ai")}
        st = ms.get(sym) or {}
        if not a.get("running"):
            e.update(status="stopped", reason="AI Engine oprit")
        elif mode_obs:
            e.update(status="observe", reason="observație — consiliul analizează, fără ordine")
        elif a.get("mode") == "shadow":
            e.update(status="observe", reason="mod shadow")
        elif e["positions"]:
            e.update(status="in_position", reason=f"{e['positions']} poziție/ii deschise")
        elif st and st.get("can_open") is False:
            e.update(status="blocked", reason=st.get("reason") or "limită atinsă")
        elif glob:
            e.update(status="blocked", reason=glob)
        elif _ai_weekend(sym, now, a.get("weekend_close_hour", 22)):
            e.update(status="idle", reason="weekend")
        else:
            e.update(status="active", reason="consiliul analizează la trigger")
        out.append(e)

    # Daily Engine
    d = inp.get("daily") or {}
    phases = {m.get("symbol"): m for m in d.get("status_markets", [])}
    for m in d.get("markets", []):
        sym = m["symbol"]
        shadow = d.get("mode") != "execute"
        e = {"symbol": sym, "engine": "daily", "ref": m.get("label") or "ORB",
             "direction": "BOTH", "tf": "M5", "mode": "shadow" if shadow else "execute",
             "window": m.get("window_ro"), "positions": has_pos(sym, "daily")}
        ph = phases.get(sym) or {}
        if not m.get("enabled", True):
            e.update(status="stopped", reason="piață dezactivată")
        elif not d.get("running"):
            e.update(status="stopped", reason="Daily Engine oprit")
        elif m.get("paused"):
            e.update(status="blocked", reason="piață pe pauză (manual) — fără intrări noi", manual_pause=True,
                     phase=ph.get("phase"))
        else:
            status, label = _DAILY_PHASE.get(ph.get("phase"), ("idle", ph.get("phase") or "—"))
            if ph.get("reason") and status in ("idle", "blocked"):
                label = f"{label}: {ph['reason']}"
            win = ph.get("window_app") or ph.get("window_ro")   # fusul aplicatiei (RO / DE), altfel RO
            if win and ph.get("phase") == "waiting_open":
                label += f" ({win} ora {ph.get('app_tz_label', 'RO')})"
            if shadow and status in ("active", "in_position"):
                label = label + (" (virtual)" if status == "in_position" else "") + " · shadow"
                status = "observe"
            e.update(status=status, reason=label, phase=ph.get("phase"))
        out.append(e)

    # Noisy Engine — o singura piata
    n = inp.get("noisy") or {}
    if n.get("symbol"):
        sym = n["symbol"]
        shadow = n.get("mode") != "execute"
        e = {"symbol": sym, "engine": "noisy", "ref": f"Noisy {n.get('timeframe', '')}".strip(),
             "direction": "BOTH", "tf": n.get("timeframe"), "mode": "shadow" if shadow else "execute",
             "positions": has_pos(sym, "noisy")}
        state = n.get("state")
        label = n.get("state_label") or state or "—"
        if not n.get("running"):
            e.update(status="stopped", reason="Noisy Engine oprit")
        elif state == "paused":
            e.update(status="blocked", reason=label, manual_pause=True)
        elif state in _NOISY_BLOCKED:
            e.update(status="blocked", reason=f"{label}" + (f": {n['reason']}" if n.get("reason") else ""))
        elif state == "outside_window":
            e.update(status="idle", reason=n.get("reason") or label)
        elif state == "in_position":
            e.update(status="observe" if shadow else "in_position",
                     reason="poziție virtuală · shadow" if shadow else "în poziție")
        else:
            e.update(status="observe" if shadow else "active",
                     reason="caută semnale · shadow" if shadow else "caută semnale")
        out.append(e)
    for e in out:
        e["status_label"] = STATUS_LABEL[e["status"]]
        e["in_use"] = entry_in_use(e)
    return out


def entry_in_use(e: dict) -> bool:
    """Piata e FOLOSITA de acest engine: engine pornit + piata activa (nu dezactivata) + nepusa manual pe
    pauza — inclusiv observatie / shadow / in afara programului / blocata temporar de o protectie automata
    (engine-ul o urmareste). Expunerea deschisa (pozitii) o face mereu folosita."""
    if e.get("positions"):
        return True
    return e["status"] != "stopped" and not e.get("manual_pause")


def _stats(trades: list[dict], today: str, yesterday: str) -> dict:
    """ACELEASI definitii ca /mt5/stats si /mt5/engine-performance (_perf): win = profit > 0,
    win rate = wins / (wins + losses) in %, P&L = profitul brut MT5, net = P&L + comision + swap."""
    w = sum(1 for t in trades if float(t.get("profit") or 0) > 0)
    l_ = sum(1 for t in trades if float(t.get("profit") or 0) < 0)
    on = lambda d: [t for t in trades if str(t.get("close_time"))[:10] == d]
    pnl = lambda ts: round(sum(float(t.get("profit") or 0) for t in ts), 2)
    return {"trades": len(trades), "wins": w, "losses": l_,
            "win_rate": round(100 * w / (w + l_), 1) if (w + l_) else None,
            "pnl": pnl(trades), "net": round(sum(_net(t) for t in trades), 2),
            "costs": round(sum(_net(t) - float(t.get("profit") or 0) for t in trades), 2),
            "pnl_today": pnl(on(today)), "pnl_yesterday": pnl(on(yesterday)),
            "trades_today": len(on(today))}


_SRC = {"custom": "bot", "ai": "ai", "daily": "daily", "noisy": "noisy"}


def build(inp: dict, now: datetime) -> dict:
    """Piete agregate (o piata = un card) + piete doar cu istoric. PUR."""
    entries = engine_entries(inp, now)
    today = now.date().isoformat()
    yesterday = (now.date() - timedelta(days=1)).isoformat()
    trades = inp.get("trades")            # None = MT5 indisponibil
    sig = inp.get("signals_today") or {}  # {(symbol, engine): n}
    virt = inp.get("virtual_today") or {} # {(symbol, engine): {"n", "R"}}

    markets: dict[str, dict] = {}
    for e in entries:
        m = markets.setdefault(e["symbol"], {"symbol": e["symbol"], "engines": []})
        e["signals_today"] = int(sig.get((e["symbol"], e["engine"]), 0))
        if e["engine"] in ("daily", "noisy") and e["mode"] == "shadow":
            v = virt.get((e["symbol"], e["engine"])) or {}
            e["virtual_today"] = {"trades": int(v.get("n", 0)), "R": round(float(v.get("R", 0.0)), 2)}
        m["engines"].append(e)

    configured = set(markets)
    for sym, m in markets.items():
        m["engines"].sort(key=lambda e: ENGINES.index(e["engine"]))
        m["engine_ids"] = list(dict.fromkeys(e["engine"] for e in m["engines"]))
        m["status"] = next(s for s in STATUS_ORDER if any(e["status"] == s for e in m["engines"]))
        # folosita = cel putin un engine o foloseste ACUM, sau exista expunere deschisa pe ea (orice sursa)
        m["in_use"] = any(e["in_use"] for e in m["engines"])
        m["status_label"] = STATUS_LABEL[m["status"]]
        m["positions"] = sum(1 for p in inp.get("positions") or [] if p.get("symbol") == sym)
        m["pending"] = sum(1 for p in inp.get("pending") or [] if p.get("symbol") == sym)
        if m["positions"] or m["pending"]:
            m["in_use"] = True
        m["signals_today"] = sum(e["signals_today"] for e in m["engines"])
        dirs = {e.get("direction") for e in m["engines"] if e["status"] != "stopped"} - {None}
        m["direction"] = "BOTH" if (len(dirs) > 1 or "BOTH" in dirs) else (next(iter(dirs)) if dirs else None)
        if trades is not None:
            mt = [t for t in trades if t.get("symbol") == sym]
            m["stats"] = _stats(mt, today, yesterday)
            m["stats_by_engine"] = {eid: _stats([t for t in mt if t.get("source") == _SRC[eid]], today, yesterday)
                                    for eid in m["engine_ids"]}
            other = [t for t in mt if t.get("source") not in {_SRC[x] for x in m["engine_ids"]}]
            m["stats_other"] = _stats(other, today, yesterday) if other else None
        else:
            m["stats"] = m["stats_by_engine"] = m["stats_other"] = None

    # piete cu tranzactii in fereastra dar fara niciun engine configurat ACUM (vechi / manual)
    history_only = []
    if trades is not None:
        by_sym: dict[str, list] = {}
        for t in trades:
            if t.get("symbol") and t["symbol"] not in configured:
                by_sym.setdefault(t["symbol"], []).append(t)
        for sym, mt in sorted(by_sym.items(), key=lambda kv: -len(kv[1])):
            srcs: dict[str, int] = {}
            for t in mt:
                srcs[t.get("source", "manual")] = srcs.get(t.get("source", "manual"), 0) + 1
            history_only.append({"symbol": sym, "sources": srcs, "stats": _stats(mt, today, yesterday)})

    order = {s: i for i, s in enumerate(STATUS_ORDER)}
    ms = sorted(markets.values(), key=lambda m: (order[m["status"]], -len(m["engine_ids"]), m["symbol"]))
    counts = {s: sum(1 for m in ms if m["status"] == s) for s in STATUS_ORDER}
    counts["unused"] = sum(1 for m in ms if not m["in_use"])
    return {"computed_at": now.isoformat(timespec="seconds"), "markets": ms, "history_only": history_only,
            "counts": counts, "global_block": inp.get("global_block"),
            "engines": {eid: bool((inp.get(eid) or {}).get("running")) for eid in ENGINES},
            "mt5_connected": trades is not None, "errors": inp.get("errors", {})}


# ── colectare (I/O) ───────────────────────────────────────────────────────────

def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _profile_sessions() -> list[dict]:
    pid = _read_json(os.path.join(DATA, "active_profile.json")).get("id", "standard")
    prof = _read_json(os.path.join(DATA, "profiles", f"{pid}.json")) or _read_json(
        os.path.join(DATA, "profiles", "standard.json"))
    return prof.get("sessions", [])


def _collect_custom(errors: dict, today: str) -> dict:
    from api.routers import bot, sessions as S
    running = bool(bot.bot_status().running)
    live = {s.id: s for s in S.list_sessions()}
    out, sig = [], {}
    for ps in _profile_sessions():
        key = ps.get("session_key")
        st = live.get(key)
        for sym in ps.get("markets") or []:
            out.append({"id": ps.get("id"), "session_key": key, "symbol": sym,
                        "direction": "LONG" if ps.get("only_long") else ps.get("direction"),
                        "tf": ps.get("entry_tf"), "execute": bool(ps.get("execute_trades", True)),
                        "session_start": ps.get("session_start", 0), "session_end": ps.get("session_end", 24),
                        "skip_weekdays": ps.get("skip_weekdays") or [], "skip_hours": ps.get("skip_hours") or [],
                        "friday_close_enabled": ps.get("friday_close_enabled", True),
                        "running": bool(st and st.running), "paused": bool(st and st.paused),
                        "news_paused": bool(st and st.news_paused)})
        try:
            df = S._read_signals(key)
            if not df.empty:
                for sym, n in df[df["time"].astype(str).str.startswith(today)].groupby("symbol").size().items():
                    sig[(str(sym), "custom")] = sig.get((str(sym), "custom"), 0) + int(n)
        except Exception as e:
            errors.setdefault("custom_signals", str(e))
    return {"running": running, "sessions": out, "signals": sig}


def _collect_ai(today: str) -> dict:
    from api.routers import ai_engine as A
    st = A.ai_status()
    cfg = A.load_config()
    running = bool(st.get("running"))
    modes = {}
    for sym, ov in (cfg.get("market_overrides") or {}).items():
        if isinstance(ov, dict) and (ov.get("mode") == "observe" or ov.get("isolated")):
            modes[sym] = "observe"
    sig = {}
    if os.path.isfile(A.DB_FILE):
        with contextlib.closing(sqlite3.connect(f"file:{A.DB_FILE}?mode=ro", uri=True)) as con:
            for sym, n in con.execute("SELECT symbol, COUNT(*) FROM decisions WHERE action LIKE 'OPEN%' "
                                      "AND substr(ts,1,10)=? GROUP BY symbol", (today,)):
                sig[(sym, "ai")] = int(n)
    return {"running": running, "mode": cfg.get("mode"), "markets": list(cfg.get("markets") or []),
            "modes": modes, "market_status": st.get("market_status") if running else None,
            "weekend_close_hour": cfg.get("weekend_close_hour", 22), "signals": sig}


def _collect_daily(today: str) -> dict:
    from api.routers import daily_engine as D
    from daily_engine.config import load_config
    from daily_engine.engine import load_trades
    st = D.daily_status()
    cfg = load_config()
    virt, sig = {}, {}
    for t in load_trades():
        if str(t.get("day")) == today:
            k = (t.get("symbol"), "daily")
            v = virt.setdefault(k, {"n": 0, "R": 0.0})
            v["n"] += 1
            v["R"] += float(t.get("R") or 0)
            sig[k] = sig.get(k, 0) + 1
    return {"running": bool(st.get("running")), "mode": cfg.get("mode", "shadow"),
            "markets": [{"symbol": m.get("symbol"), "enabled": m.get("enabled", True), "label": m.get("label"),
                         "window_ro": None} for m in cfg.get("markets", []) if m.get("symbol")],
            "status_markets": (st.get("markets") or []) if st.get("running") else [],
            "virtual": virt, "signals": sig}


def _collect_noisy(today: str) -> dict:
    from api.routers import noisy_engine as N
    from noisy_engine.config import load_config
    from noisy_engine.engine import load_trades
    st = N.noisy_status()
    cfg = load_config()
    virt, sig = {}, {}
    for t in load_trades():
        if str(t.get("day")) == today and t.get("tf", cfg.get("timeframe")) == cfg.get("timeframe"):
            k = (t.get("symbol"), "noisy")
            v = virt.setdefault(k, {"n": 0, "R": 0.0})
            v["n"] += 1
            v["R"] += float(t.get("R") or 0)
            sig[k] = sig.get(k, 0) + 1
    return {"running": bool(st.get("running")), "mode": cfg.get("mode", "shadow"), "symbol": cfg.get("symbol"),
            "timeframe": cfg.get("timeframe"), "state": st.get("state"), "state_label": st.get("state_label"),
            "reason": st.get("reason"), "virtual": virt, "signals": sig}


def global_block(trades: list[dict] | None, equity: float | None, today: str) -> str | None:
    """Blocaj cont-wide din Setari Globale (capital / circuit breaker), din datele deja cache-uite."""
    try:
        from live.global_guard import load_settings, consecutive_losses, _profile_start_balance
        s = load_settings()
        cp = s["capital_protection"]
        if cp["enabled"] and equity is not None:
            start = cp["start_balance"] or _profile_start_balance()
            if start and equity < start * cp["threshold_pct"] / 100.0:
                return f"Protecția capitalului: equity {equity:.2f}$ sub {cp['threshold_pct']:.0f}% din {start:.2f}$"
        cb = s["circuit_breaker"]
        if cb["enabled"] and trades is not None:
            td = sorted((t for t in trades if str(t.get("close_time"))[:10] == today and t.get("source") != "manual"),
                        key=lambda t: t["close_time"])
            n = consecutive_losses([{"net": _net(t)} for t in td])
            if n >= cb["max_consecutive_losses"]:
                return f"Circuit breaker global: {n} pierderi consecutive azi"
    except Exception:
        return None
    return None


def collect() -> dict:
    from tz_helper import now_local
    now = now_local()
    today = now.date().isoformat()
    errors: dict = {}
    inp: dict = {"errors": errors}
    for eid, fn in (("custom", lambda: _collect_custom(errors, today)), ("ai", lambda: _collect_ai(today)),
                    ("daily", lambda: _collect_daily(today)), ("noisy", lambda: _collect_noisy(today))):
        try:
            inp[eid] = fn()
        except Exception as e:      # un engine stricat nu strica Dashboard-ul
            inp[eid] = {}
            errors[eid] = str(e)
    sig, virt = {}, {}
    for eid in ENGINES:
        sig.update((inp[eid] or {}).get("signals", {}))
        virt.update((inp[eid] or {}).get("virtual", {}))
    inp["signals_today"], inp["virtual_today"] = sig, virt
    from api import mt5_pool
    try:
        inp["trades"] = mt5_pool.get_closed_trades(mt5_pool.HISTORY_DAYS)
    except Exception as e:
        inp["trades"] = None
        errors["mt5"] = str(e)
    o = mt5_pool.get_orders()
    inp["positions"], inp["pending"] = o.get("positions") or [], o.get("pending") or []
    equity = (o.get("account") or {}).get("equity")
    inp["global_block"] = global_block(inp["trades"], equity, today)
    return inp, now


def get_markets(refresh: bool = False) -> dict:
    if refresh or _cache["data"] is None or time.time() - _cache["ts"] > _CACHE_TTL:
        inp, now = collect()
        _cache.update(ts=time.time(), data=build(inp, now))
    return _cache["data"]


# ── semnale GLOBALE ───────────────────────────────────────────────────────────

_CUSTOM_STATUS = {"ai_reject": ("rejected", "respins AI"), "expirat": ("expired", "expirat"),
                  "invalidat": ("expired", "invalidat"), "global_block": ("rejected", "blocat (Setări Globale)"),
                  "TP": ("executed", "executat · TP"), "SL": ("executed", "executat · SL"),
                  "vineri_close": ("executed", "executat · închis vineri"), "news_close": ("executed", "executat · închis la știri"),
                  "news_cancel": ("expired", "anulat la știri"), "vineri_cancel": ("expired", "anulat vineri"),
                  "be_lock": ("executed", "executat · break-even"), "be_lock2": ("executed", "executat · break-even 2")}
_STRAT_LABEL = {"pullback": "Pullback", "inside_bar": "Inside Bar", "flag": "Flag"}


def signals(symbol: str | None = None, engine: str | None = None, limit: int = 100) -> list[dict]:
    """Semnalele tuturor engine-urilor, cele mai noi primele. Fiecare engine izolat (try)."""
    from api import mt5_pool
    rows: list[dict] = []
    want = lambda eid: engine in (None, "", "all", eid)
    sym_ok = lambda s: not symbol or s == symbol

    if want("custom"):
        try:
            from api.routers import sessions as S
            for ps in _profile_sessions():
                key = ps.get("session_key")
                if symbol and symbol not in (ps.get("markets") or []):
                    continue
                df = S._read_signals(key)
                if df.empty:
                    continue
                smap = S._signal_status_map(key)
                execute = bool(ps.get("execute_trades", True))
                for _, r in df.tail(limit).iterrows():
                    if not sym_ok(str(r.get("symbol"))):
                        continue
                    sid = str(r.get("signal_id", ""))
                    raw = smap.get(sid)
                    kind, lab = _CUSTOM_STATUS.get(raw, ("pending", "în așteptare") if raw is None else ("other", raw))
                    if not execute and raw is None:
                        kind, lab = "observe", "observație (fără ordin)"
                    strat = mt5_pool._strategy_from_comment(sid) if "-" in sid else None
                    rows.append({"time": str(r.get("time", ""))[:19], "engine": "custom", "symbol": str(r.get("symbol")),
                                 "direction": str(r.get("dir_str", "")), "strategy": _STRAT_LABEL.get(strat, strat or "—"),
                                 "status": kind, "status_label": lab, "id": sid, "ref": ps.get("id"),
                                 "detail": f"intrare {r.get('entry')} · SL {r.get('sl')} · TP {r.get('tp')} ({r.get('r_ratio')}R)"})
        except Exception:
            pass

    if want("ai"):
        try:
            from api.routers import ai_engine as A
            if os.path.isfile(A.DB_FILE):
                q = ("SELECT id, ts, symbol, action, order_type, entry, sl, tp, confidence, exec_status, exec_detail "
                     "FROM decisions WHERE action != 'WAIT'" + (" AND symbol=?" if symbol else "")
                     + " ORDER BY id DESC LIMIT ?")
                with contextlib.closing(sqlite3.connect(f"file:{A.DB_FILE}?mode=ro", uri=True)) as con:
                    for (did, ts, sym, act, otype, entry, sl, tp, conf, ex, det) in con.execute(
                            q, ((symbol,) if symbol else ()) + (limit,)):
                        kind = {"placed": "executed", "rejected": "rejected", "failed": "rejected",
                                "shadow": "observe", "skipped": "expired"}.get(ex, "other")
                        lab = {"placed": "ordin plasat", "rejected": "respins (rails)", "failed": "eșuat la broker",
                               "shadow": "observație (fără ordin)", "skipped": "sărit"}.get(ex, ex or "—")
                        rows.append({"time": str(ts)[:19].replace("T", " "), "engine": "ai", "symbol": sym,
                                     "direction": "LONG" if act == "OPEN_LONG" else "SHORT" if act == "OPEN_SHORT" else "CLOSE",
                                     "strategy": f"Consiliu AI{f' · {otype}' if otype else ''}", "status": kind,
                                     "status_label": lab + (f" · încredere {conf}%" if conf is not None else ""),
                                     "id": f"AI-{did}", "ref": "AI",
                                     "detail": (f"intrare {entry} · SL {sl} · TP {tp}" if entry else (det or ""))})
        except Exception:
            pass

    for eid, mod, strat in (("daily", "daily_engine.engine", "ORB (deschiderea bursei)"),
                            ("noisy", "noisy_engine.engine", "Mean reversion")):
        if not want(eid):
            continue
        try:
            import importlib
            trades = importlib.import_module(mod).load_trades()
            for t in trades[-limit:]:
                if not sym_ok(t.get("symbol")):
                    continue
                virtual = t.get("mode", "shadow") != "execute"
                r = t.get("R")
                tm = t.get("entry_t") or t.get("recorded_at") or t.get("day")
                rows.append({"time": str(tm)[:19].replace("T", " "), "engine": eid, "symbol": t.get("symbol"),
                             "direction": t.get("dir") or t.get("side") or "", "strategy": strat
                             + (f" {t.get('tf')}" if t.get("tf") else ""),
                             "status": "virtual" if virtual else "executed",
                             "status_label": ("virtual · " if virtual else "") + f"{t.get('reason', '')}"
                             + (f" · {float(r):+.2f}R" if r is not None else ""),
                             "id": str(t.get("id") or f"{eid}-{t.get('day')}-{t.get('symbol')}"), "ref": eid.capitalize(),
                             "detail": f"intrare {t.get('entry')} · ieșire {t.get('exit')} · SL {t.get('sl')}"})
        except Exception:
            pass

    rows.sort(key=lambda r: r["time"], reverse=True)
    return rows[:limit]
