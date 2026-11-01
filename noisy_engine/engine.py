"""Noisy Engine — mean reversion (M1 implicit / M5), o singura piata, mod SHADOW (trade-uri virtuale, ZERO ordine).

Bucla (la `poll_seconds`):
  1. barele INCHISE ale timeframe-ului ales (+ istoric pentru indicatori), ora RO din ora serverului detectata din tick
  2. `strategy.run_day` reconstruieste ziua de la zero (restart-safe, identic cu backtestul)
  3. semnal nou → protectiile GLOBALE (global_guard + stiri globale); respins → pastrat in state.json
     ca recalcularea sa ramana identica
  4. trade-uri inchise → data/noisy_engine/trades.jsonl (+ P&L virtual din lotul pe care l-ar fi plasat)
  5. buget IZOLAT (P&L Noisy realizat + flotant, nu equity-ul contului) → sub prag = BUDGET LOCKED
  6. starea (cu motivul) → status.json; evenimente → log + Telegram, o singura data

NU porneste automat (fara autostart, fara repornire din watchdog). Modulul NU contine niciun apel de
plasare ordine — verificat de selftest.
"""
from __future__ import annotations

import ctypes
import faulthandler
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from noisy_engine.config import DATA_DIR, TIMEFRAMES, load_config, save_default_config  # noqa: E402
from noisy_engine.strategy import run_day  # noqa: E402
import position_sizing as ps  # noqa: E402

PID_FILE = os.path.join(DATA_DIR, "noisy_engine.pid")
STATUS_FILE = os.path.join(DATA_DIR, "status.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
CONTROL_FILE = os.path.join(DATA_DIR, "control.json")      # pauza (scris de API)
TRADES_FILE = os.path.join(DATA_DIR, "trades.jsonl")
LOG_FILE = os.path.join(DATA_DIR, "engine.log")
RO = ZoneInfo("Europe/Bucharest")
NY = ZoneInfo("America/New_York")
_MUTEX_NAMES = ("Global\\TradingBot_NoisyEngine_SingleInstance", "Local\\TradingBot_NoisyEngine_SingleInstance")
_mutex_handle = None
log = logging.getLogger("noisy_engine")

# starile afisate in UI (cheie → eticheta)
STATES = {
    "stopped": "Stopped", "starting": "Starting", "running": "Running", "in_position": "Running – în poziție",
    "paused": "Paused", "outside_window": "Scheduled – în afara ferestrei", "risk_locked": "Risk Locked (global)",
    "budget_locked": "Stopped – Budget Limit", "loss_limit": "Loss Limit Reached", "loss_streak": "Loss Limit – serie",
    "trade_limit": "Trade Limit Reached", "error": "Error", "stopping": "Stopping",
}


# ── utilitare ────────────────────────────────────────────────────────────────

def _setup_logging() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    try:
        from log_utils import rotating_handler
        fh = rotating_handler(LOG_FILE)
    except Exception:
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(fh)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    log.addHandler(sh)


def _acquire_single_instance(names=_MUTEX_NAMES) -> bool:
    global _mutex_handle
    if os.name != "nt":
        return True
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = ctypes.c_void_p
        k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    except Exception:
        return True
    for name in names:
        hnd = k32.CreateMutexW(None, False, name)
        err = ctypes.get_last_error()
        if not hnd:
            continue
        if err == 183:
            k32.CloseHandle(ctypes.c_void_p(hnd))
            return False
        _mutex_handle = hnd
        return True
    return True


def _read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    os.replace(tmp, path)


def _notify(cfg: dict, text: str) -> None:
    if not cfg.get("notify_telegram", True):
        return

    def _send():
        try:
            from api.telegram import send_message
            send_message(text)
        except Exception as e:  # pragma: no cover
            log.warning(f"Telegram esuat: {e}")
    threading.Thread(target=_send, daemon=True).start()


def load_trades() -> list[dict]:
    out = []
    try:
        with open(TRADES_FILE, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    out.append(json.loads(line))
    except FileNotFoundError:
        pass
    return out


def scorecard(trades: list[dict]) -> dict:
    rs = [t["R"] for t in trades]
    n = len(rs)
    w = sum(1 for r in rs if r > 0)
    money = [t["pnl_money"] for t in trades if t.get("pnl_money") is not None]
    gw = sum(r for r in rs if r > 0)
    gl = -sum(r for r in rs if r < 0)
    eq, peak, dd = 0.0, 0.0, 0.0
    streak = cur = 0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
        cur = cur + 1 if r < 0 else 0
        streak = max(streak, cur)
    return {"trades": n, "wins": w, "losses": sum(1 for r in rs if r < 0),
            "win_rate": round(w / n, 3) if n else None, "total_R": round(sum(rs), 3),
            "expectancy_R": round(sum(rs) / n, 3) if n else None,
            "gross_R": round(sum(t.get("gross_R", 0) for t in trades) / n, 3) if n else None,
            "cost_R": round(sum(t.get("gross_R", 0) - t["R"] for t in trades) / n, 3) if n else None,
            "profit_factor": round(gw / gl, 2) if gl else None, "max_dd_R": round(dd, 2), "max_loss_streak": streak,
            "pnl_money": round(sum(money), 2) if money else None,
            "avg_hold_min": round(sum(t.get("hold_min", t.get("bars", 0) * 5) for t in trades) / n, 1) if n else None}


def server_to_ro(epoch_s, offset_s: int | None) -> pd.Series:
    """Ora serverului MT5 → ora RO (naiva). Cu offset detectat din tick (live) sau, fara el, regula
    ICMarkets server = New York + 7h (backtest pe istoric, DST-corect)."""
    s = pd.Series(epoch_s, dtype="int64")
    if offset_s is not None:
        utc = pd.to_datetime(s - offset_s, unit="s", utc=True)
    else:
        ny_naive = pd.to_datetime(s, unit="s") - pd.Timedelta(hours=7)
        utc = ny_naive.dt.tz_localize(NY, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    return utc.dt.tz_convert(RO).dt.tz_localize(None)


def rates_to_bars(rates, offset_s: int | None, point: float, now_ro: datetime | None = None,
                  tf_min: int = 5) -> pd.DataFrame:
    """Barele MT5 → DataFrame pentru strategie (doar bare INCHISE daca now_ro e dat)."""
    d = pd.DataFrame(rates)
    if d.empty:
        return pd.DataFrame(columns=["t", "open", "high", "low", "close", "spread"])
    d["t"] = server_to_ro(d["time"], offset_s)
    d = d.dropna(subset=["t"])
    d["spread"] = d["spread"].astype(float) * point
    if now_ro is not None:
        d = d[d["t"] + pd.Timedelta(minutes=tf_min) <= pd.Timestamp(now_ro)]
    d["t"] = [x.to_pydatetime() for x in d["t"]]
    return d[["t", "open", "high", "low", "close", "spread"]].reset_index(drop=True)


def news_blocks(symbol: str, events: list[dict], pre: int, post: int) -> list[tuple[datetime, datetime]]:
    """Intervalele (ora RO) in care Noisy nu intra: stiri High pe valutele pietei."""
    curs = {symbol[:3].upper(), symbol[3:6].upper()}
    out = []
    for e in events or []:
        if str(e.get("impact", "")).lower() != "high" or str(e.get("currency", "")).upper() not in curs:
            continue
        et = e.get("event_time")
        if not isinstance(et, datetime):
            continue
        loc = et.replace(tzinfo=timezone.utc).astimezone(RO).replace(tzinfo=None)
        out.append((loc - timedelta(minutes=pre), loc + timedelta(minutes=post)))
    return out


# ── motor ────────────────────────────────────────────────────────────────────

class NoisyEngine:
    def __init__(self, mt5_module=None, news_fetch=None, guard=None):
        if mt5_module is None:
            import MetaTrader5 as mt5_module
        self.mt5 = mt5_module
        self.cfg = load_config()
        self.state = _read_json(STATE_FILE, {})
        self.state.setdefault("events", [])
        self.state.setdefault("vetoed", {})
        self.state.setdefault("recorded", [])
        self.state.setdefault("checked", [])
        self.state.setdefault("budget_lock", None)
        self.state.setdefault("budget_reset_at", None)
        self.offset_s: int | None = None
        self.errors: list[str] = []
        self.account: dict = {}
        self._news_fetch = news_fetch
        self._guard = guard
        self._news_cache: tuple[float, list] = (0.0, [])

    def connect(self) -> bool:
        if not self.mt5.initialize():
            self._err(f"MT5 initialize esuat: {self.mt5.last_error()}")
            return False
        a = self.mt5.account_info()
        if a is not None:
            self.account = {"login": a.login, "server": a.server, "is_demo": getattr(a, "trade_mode", None) == 0}
        self.mt5.symbol_select(self.cfg["symbol"], True)
        return True

    def _err(self, msg: str) -> None:
        log.warning(msg)
        self.errors = (self.errors + [f"{datetime.now(RO):%d.%m %H:%M} {msg}"])[-10:]

    def _save_state(self) -> None:
        for k, n in (("events", 300), ("recorded", 2000), ("checked", 500)):
            self.state[k] = self.state[k][-n:]
        _write_json(STATE_FILE, self.state)

    def _event_once(self, key: str, text: str, notify: bool = True) -> None:
        if key in self.state["events"]:
            return
        self.state["events"].append(key)
        log.info(text.replace("<b>", "").replace("</b>", ""))
        if notify:
            _notify(self.cfg, text)

    def _refresh_offset(self, symbol: str, now_utc: datetime) -> None:
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None or not tick.time:
            return
        diff = tick.time - now_utc.timestamp()
        hours = round(diff / 3600)
        if abs(diff - hours * 3600) < 180:
            self.offset_s = int(hours * 3600)

    def _events_news(self) -> list[dict]:
        if self._news_fetch is not None:
            return self._news_fetch()
        ts, ev = self._news_cache
        if time.time() - ts < 600:
            return ev
        try:
            from live.news_guard import _fetch_forexfactory
            ev = _fetch_forexfactory() or []
        except Exception as e:
            self._err(f"calendar stiri indisponibil: {e}")
            ev = ev or []
        self._news_cache = (time.time(), ev)
        return ev

    def _global_check(self, sym: str, events: list[dict], now_utc: datetime) -> tuple[bool, str]:
        """Protectiile GLOBALE (Setari Globale) — Noisy nu le poate ocoli. Eroare → permis (fail-open,
        ca la celelalte engine-uri); in shadow nu exista ordin real oricum."""
        if self._guard is not None:
            return self._guard(sym)
        try:
            from live import global_guard
            ok, why = global_guard.check_open(self.mt5, "noisy", sym)
            if ok and global_guard.load_settings()["news_protection"]["enabled"]:
                act = global_guard.news_window_active(sym, events, now_utc.replace(tzinfo=None))
                if act:
                    return False, f"STIRI (global): {act[0].get('title', '')}"
            return ok, why or ""
        except Exception as e:
            return True, f"(verificare globala indisponibila: {e})"

    def _live_spread_ok(self, sym: str) -> tuple[bool, str]:
        """Spread-ul REAL (tick) la momentul semnalului: barele MT5 retin doar minimul din bara."""
        p = self.cfg["strategy"]
        if p["spread_max_mult"] <= 0 or p["spread_floor"] <= 0:
            return True, ""
        tick = self.mt5.symbol_info_tick(sym)
        if tick is None or not tick.ask or not tick.bid:
            return True, ""
        live = tick.ask - tick.bid
        lim = p["spread_max_mult"] * p["spread_floor"]
        if live > lim + 1e-12:
            return False, f"SPREAD: {live:.5g} > {lim:.5g} ({p['spread_max_mult']}× spread-ul normal)"
        return True, ""

    def _size(self, entry: float, sl: float) -> dict:
        """Lotul pe care Noisy l-ar plasa: risc % din BUGETUL engine-ului, plafonat de limita globala."""
        try:
            si = self.mt5.symbol_info(self.cfg["symbol"])
            r = ps.size_by_risk(si, entry, sl, self.cfg["budget"]["capital"], self.cfg["sizing"]["risk_pct"])
            acc = self.mt5.account_info()
            from live.global_guard import risk_cap_pct
            lots, why = ps.apply_risk_cap(si, r["lots"], entry, sl, getattr(acc, "equity", None) if acc else None,
                                          risk_cap_pct())
            vpu = (si.trade_tick_value / si.trade_tick_size) if si and si.trade_tick_size else 0.0
            return {"lots": lots, "value_per_price": vpu * lots, "risk_cap": why}
        except Exception as e:
            return {"lots": 0.0, "value_per_price": 0.0, "reason": str(e)}

    def _money(self, tr: dict, size: dict) -> float | None:
        v = size.get("value_per_price") or 0.0
        if not v:
            return None
        return round((tr["R"] * tr["risk"]) * v, 2)

    def budget(self, trades: list[dict], open_pos: dict | None) -> dict:
        b = self.cfg["budget"]
        since = self.state.get("budget_reset_at")
        realized = sum(t.get("pnl_money") or 0.0 for t in trades if not since or t["exit_t"] >= since)
        floating = 0.0
        if open_pos:
            sz = self._size(open_pos["entry"], open_pos["sl"])
            floating = (open_pos["float_R"] * open_pos["risk"]) * (sz.get("value_per_price") or 0.0)
        remaining = b["capital"] + realized + floating
        return {"capital": b["capital"], "min_remaining": b["min_remaining"], "realized": round(realized, 2),
                "floating": round(floating, 2), "remaining": round(remaining, 2),
                "locked": self.state.get("budget_lock"), "since": since}

    def iteration(self, now_utc: datetime | None = None) -> dict:
        self.cfg = load_config()
        cfg = self.cfg
        sym = cfg["symbol"]
        now_utc = now_utc or datetime.now(timezone.utc)
        now_ro = now_utc.astimezone(RO).replace(tzinfo=None)
        day = now_ro.date()
        paused = bool(_read_json(CONTROL_FILE, {}).get("paused"))
        self._refresh_offset(sym, now_utc)
        status = {"running": True, "mode": cfg["mode"], "symbol": sym, "timeframe": cfg["timeframe"],
                  "tf_min": TIMEFRAMES[cfg["timeframe"]], "pid": os.getpid(), "paused": paused,
                  "heartbeat": datetime.now(RO).isoformat(timespec="seconds"), "window": cfg["window"],
                  "limits": cfg["limits"], "account": self.account, "errors": self.errors,
                  "server_offset_h": None if self.offset_s is None else self.offset_s / 3600}
        if self.offset_s is None:
            # fara tick proaspat (weekend / noapte): regula ICMarkets server = New York + 7h (ca backtestul)
            status["server_time_rule"] = "NY+7 (fara tick proaspat)"
        si = self.mt5.symbol_info(sym)
        tf_min = TIMEFRAMES[cfg["timeframe"]]
        # toata ziua de azi + istoric pentru indicatori (recalcularea zilei trebuie sa vada si dimineata)
        need = int((now_ro.hour * 60 + now_ro.minute) / tf_min) + 400
        rates = self.mt5.copy_rates_from_pos(sym, getattr(self.mt5, f"TIMEFRAME_{cfg['timeframe']}"), 0, min(need, 3000))
        bars = rates_to_bars(rates, self.offset_s, si.point if si else 0.0, now_ro, tf_min)
        events = self._events_news()
        blocks = news_blocks(sym, events, cfg["news"]["pre_min"], cfg["news"]["post_min"]) if cfg["news"]["enabled"] else []
        trades_all = load_trades()
        lock = self.state.get("budget_lock")
        vetoed = set(self.state["vetoed"].get(str(day), []))

        res = run_day(bars, day, cfg, news_blocks=blocks, vetoed=vetoed, no_new_entries=bool(lock) or paused)
        # semnal NOU → protectiile globale, o singura data per semnal
        pend = res.get("pending")
        global_block = None
        if pend and pend["signal_t"] not in self.state["checked"]:
            self.state["checked"].append(pend["signal_t"])
            ok, why = self._global_check(sym, events, now_utc)
            if ok:
                ok, why = self._live_spread_ok(sym)
            if not ok:
                self.state["vetoed"].setdefault(str(day), []).append(pend["signal_t"])
                global_block = why
                self._event_once(f"veto-{pend['signal_t']}",
                                 f"🛡 <b>Noisy SHADOW — {sym} {pend['dir']} blocat global</b>\n{why}")
                res = run_day(bars, day, cfg, news_blocks=blocks, vetoed=vetoed | {pend["signal_t"]},
                              no_new_entries=bool(lock) or paused)
            else:
                self._event_once(f"sig-{pend['signal_t']}", f"Noisy {sym}: semnal {pend['dir']} la {pend['signal_t'][11:16]} "
                                 f"— intrare la deschiderea barei urmatoare", notify=False)
        # trade-uri inchise → jurnal (o singura data)
        for tr in res["trades"]:
            if tr["id"] in self.state["recorded"]:
                continue
            size = self._size(tr["entry"], tr["sl"])
            row = {"symbol": sym, "day": str(day), **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in tr.items()},
                   "lots": size["lots"], "pnl_money": self._money(tr, size), "mode": "shadow",
                   "tf": cfg["timeframe"], "hold_min": tr["bars"] * tf_min}
            with open(TRADES_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            self.state["recorded"].append(tr["id"])
            trades_all.append(row)
            icon = "✅" if tr["R"] > 0 else "❌"
            self._event_once(f"exit-{tr['id']}",
                             f"{icon} <b>Noisy SHADOW — {sym} {tr['dir']} închis</b> ({tr['reason']})\n"
                             f"{tr['entry']:.3f} → {tr['exit']:.3f} = <b>{tr['R']:+.2f}R</b>"
                             + (f" ≈ {row['pnl_money']:+.2f}$" if row["pnl_money"] is not None else "") + " (virtual)",
                             notify=cfg.get("notify_trades", False))
        op = res.get("open")
        if op:
            self._event_once(f"entry-{op['id']}",
                             f"🧪 <b>Noisy SHADOW — {sym} {op['dir']}</b> @ {op['entry']:.3f}\n"
                             f"SL {op['sl']:.3f} · țintă {op['tp']:.3f} · stop de timp {cfg['strategy']['time_stop_bars'] * tf_min} min (virtual)",
                             notify=cfg.get("notify_trades", False))
        # buget izolat
        bud = self.budget(trades_all, op)
        if not lock and bud["remaining"] <= bud["min_remaining"]:
            lock = {"at": now_ro.isoformat(timespec="seconds"), "remaining": bud["remaining"]}
            self.state["budget_lock"] = lock
            bud["locked"] = lock
            self._event_once(f"budget-{lock['at']}",
                             f"⛔ <b>Noisy Engine — BUDGET LIMIT</b>\nBuget rămas {bud['remaining']:.2f}$ ≤ prag "
                             f"{bud['min_remaining']:.2f}$ → fără intrări noi până la resetarea manuală a bugetului.")
        if res.get("lock"):
            labels = {"trade_limit": "limita de trade-uri / zi", "loss_limit": "limita de pierderi / zi",
                      "loss_streak": "seria maximă de pierderi"}
            self._event_once(f"lock-{day}-{res['lock']}",
                             f"🔒 <b>Noisy Engine — {labels[res['lock']]} atinsă</b>: fără intrări noi azi (reset la miezul nopții).")
        self._save_state()

        # starea afisata
        from noisy_engine.strategy import _in_window
        in_win = _in_window(now_ro, cfg["window"])
        if lock:
            state, reason = "budget_locked", f"buget rămas {bud['remaining']:.2f}$ ≤ {bud['min_remaining']:.2f}$"
        elif paused:
            state, reason = "paused", "pus pe pauză din UI — fără intrări noi"
        elif op:
            state, reason = "in_position", f"{op['dir']} @ {op['entry']:.3f} ({op['float_R']:+.2f}R)"
        elif res.get("lock"):
            state, reason = res["lock"], "limită zilnică atinsă — reset la miezul nopții"
        elif global_block:
            state, reason = "risk_locked", global_block
        elif not in_win:
            state, reason = "outside_window", f"intră doar {cfg['window']['start']}–{cfg['window']['end']} (ora RO)"
        else:
            state, reason = "running", "aștept semnal"
        today = [t for t in trades_all if t.get("day") == str(day)]
        status.update(state=state, state_label=STATES[state], reason=reason, open=op, pending=res.get("pending"),
                      last=res.get("last"), counters=res["counters"], budget=bud,
                      today={"trades": len(today), "R": round(sum(t["R"] for t in today), 3),
                             "pnl_money": round(sum(t.get("pnl_money") or 0 for t in today), 2)},
                      scorecard=scorecard(trades_all), news_next=[(a.isoformat(), b.isoformat()) for a, b in blocks if b > now_ro][:3])
        _write_json(STATUS_FILE, status)
        return status


def run() -> None:
    _setup_logging()
    try:
        faulthandler.enable(open(os.path.join(DATA_DIR, "crash.log"), "a", encoding="utf-8"))
    except Exception:
        pass
    try:
        _run()
    except BaseException as e:
        log.exception(f"Noisy Engine s-a oprit neasteptat: {type(e).__name__}: {e}")
        raise


def _run() -> None:
    if not _acquire_single_instance():
        log.error("Noisy Engine ruleaza deja (mutex detinut) — a doua instanta NU porneste.")
        return
    save_default_config()
    cfg = load_config()
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    eng = NoisyEngine()
    log.info(f"Noisy Engine pornit — {cfg['symbol']} {cfg['timeframe']}, mod SHADOW (fără ordine reale)")
    _notify(cfg, f"🧪 <b>Noisy Engine pornit</b> — {cfg['symbol']} {cfg['timeframe']}, mod SHADOW (trade-uri virtuale)\n"
                 f"Fereastră {cfg['window']['start']}–{cfg['window']['end']} RO · buget {cfg['budget']['capital']:.0f}$ "
                 f"(prag {cfg['budget']['min_remaining']:.0f}$)")
    while not eng.connect():
        _write_json(STATUS_FILE, {"running": True, "state": "error", "state_label": STATES["error"],
                                  "reason": "MT5 indisponibil — reîncerc", "pid": os.getpid(), "errors": eng.errors,
                                  "heartbeat": datetime.now(RO).isoformat(timespec="seconds")})
        time.sleep(30)
    fails = 0
    while True:
        try:
            eng.iteration()
            fails = 0
        except Exception as e:
            fails += 1
            eng._err(f"iteratie esuata: {type(e).__name__}: {e}")
            if fails >= 3:
                eng.mt5.shutdown()
                eng.connect()
                fails = 0
        time.sleep(eng.cfg.get("poll_seconds", 10))
