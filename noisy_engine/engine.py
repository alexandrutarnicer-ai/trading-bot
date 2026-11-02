"""Noisy Engine — mean reversion (M1 implicit / M5), o singura piata, SHADOW (virtual) sau EXECUTIE (ordine reale).

Bucla (la `poll_seconds`):
  1. barele INCHISE ale timeframe-ului ales (+ istoric pentru indicatori), ora RO din ora serverului detectata din tick
  2. `strategy.run_day` reconstruieste ziua de la zero (restart-safe, identic cu backtestul)
  3. semnal nou → protectiile GLOBALE (global_guard + stiri globale); respins → pastrat in state.json
     ca recalcularea sa ramana identica
  4. trade-uri inchise → data/noisy_engine/trades.jsonl (+ P&L virtual din lotul pe care l-ar fi plasat)
  5. buget IZOLAT (P&L Noisy realizat + flotant, nu equity-ul contului) → sub prag = BUDGET LOCKED
  6. starea (cu motivul) → status.json; evenimente → log + Telegram, o singura data

NU porneste automat (fara autostart, fara repornire din watchdog). Ordinele reale trec DOAR prin
noisy_engine/executor.py si doar in modul „execute” (DEMO, sau REAL deblocat in Trading LIVE).
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

from noisy_engine.config import (DATA_DIR, TIMEFRAMES, intervals_label, load_config, resolve_spread,  # noqa: E402
                                 save_default_config)
from noisy_engine.strategy import run_day  # noqa: E402
import position_sizing as ps  # noqa: E402
from noisy_engine import executor as X  # noqa: E402

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
    """Atomic + rezistent la blocarile Windows (safe_io). status.json = doar afisare → o blocare nu mai pica iteratia."""
    from safe_io import write_json_atomic
    write_json_atomic(path, data, critical=os.path.basename(path) != "status.json")


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


def friday_block(now_ro: datetime, settings: dict | None = None) -> tuple[datetime, datetime] | None:
    """Inchiderea de vineri din Setari Globale (ora in fusul aplicatiei) ca interval in ora RO: de la ora
    configurata vineri pana la sfarsitul zilei. Nicio intrare noua; in EXECUTIE pozitiile Noisy se inchid."""
    try:
        from live.global_guard import load_settings
        fc = (settings or load_settings())["friday_close"]
        if not fc.get("enabled"):
            return None
        from tz_helper import get_configured_tz_name
        app_tz = ZoneInfo(get_configured_tz_name())
    except Exception:
        return None
    now_app = now_ro.replace(tzinfo=RO).astimezone(app_tz)
    fri = now_app.date() - timedelta(days=(now_app.weekday() - 4) % 7)
    start = datetime(fri.year, fri.month, fri.day, int(fc.get("hour", 20)), tzinfo=app_tz)
    a = start.astimezone(RO).replace(tzinfo=None)
    return a, datetime(fri.year, fri.month, fri.day) + timedelta(days=1)


def symbol_currencies(symbol: str) -> set[str]:
    """Valutele pietei pentru stiri: harta comuna (live.news_guard.SYMBOL_CURRENCIES — acopera si indici / metale,
    ex. US500 → USD, GER40 → EUR); pereche FX necunoscuta → primele 3 + urmatoarele 3 litere."""
    sym = str(symbol).upper()
    try:
        from live.news_guard import SYMBOL_CURRENCIES
        if sym in SYMBOL_CURRENCIES:
            return set(SYMBOL_CURRENCIES[sym])
        base = sym.split(".")[0]
        if base in SYMBOL_CURRENCIES:
            return set(SYMBOL_CURRENCIES[base])
    except Exception:
        pass
    return {sym[:3], sym[3:6]} if len(sym) >= 6 and sym[:6].isalpha() else set()


def news_blocks(symbol: str, events: list[dict], pre: int, post: int) -> list[tuple[datetime, datetime]]:
    """Intervalele (ora RO) in care Noisy nu intra: stiri High pe valutele pietei."""
    curs = symbol_currencies(symbol)
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
        self._spread_samples: list[tuple[float, float]] = []   # (epoch, points) — spread-ul LIVE observat
        self.spread_info: dict = {}

    def connect(self) -> bool:
        if not self.mt5.initialize():
            self._err(f"MT5 initialize esuat: {self.mt5.last_error()}")
            return False
        a = self.mt5.account_info()
        if a is not None:
            self.account = {"login": a.login, "server": a.server, "is_demo": getattr(a, "trade_mode", None) == 0}
        self.mt5.symbol_select(self.cfg["symbol"], True)
        return True

    PER_SYMBOL = ("checked", "vetoed", "recorded", "placed", "rejects_logged", "spread_ref")

    def _switch_symbol(self, sym: str) -> None:
        """Piata schimbata din UI: starea per semnal (ID-uri pe timestamp, fara simbol) e ARHIVATA pe piata veche
        si restaurata pentru cea noua — altfel un semnal USDJPY de la 10:23 ar „ascunde” unul US500 de la 10:23,
        iar revenirea pe piata veche in aceeasi zi ar dubla trade-urile in jurnal. Bugetul ramane comun."""
        old = self.state.get("symbol")
        if old == sym:
            return
        if old:
            arch = self.state.setdefault("per_symbol", {})
            arch[old] = {k: self.state.get(k) for k in self.PER_SYMBOL}
            restored = arch.pop(sym, {}) or {}
            for k in self.PER_SYMBOL:
                self.state[k] = restored.get(k) if restored.get(k) is not None else ({} if k == "vetoed" else None if k == "spread_ref" else [])
            self._spread_samples = []
            log.info(f"Noisy: piața schimbată {old} → {sym} (starea per semnal arhivată / restaurată)")
            self._event_once(f"symbol-{old}-{sym}-{datetime.now(RO):%Y%m%d%H%M}",
                             f"🔁 <b>Noisy Engine — piața schimbată</b>: {old} → {sym}")
        self.state["symbol"] = sym

    def _overlap_guard(self, res: dict, trades: list[dict]) -> tuple[bool, str]:
        """Doar cu trade-uri SUPRAPUSE: regulile globale si bugetul au prioritate peste max_open al engine-ului.
        (1) Setari Globale → pozitii simultane pe piata: si pozitiile VIRTUALE (shadow) se numara (in executie
            global_guard.check_open numara deja pozitiile reale de pe cont);
        (2) buget: riscul (la SL) al TUTUROR pozitiilor deschise + al celei noi nu poate cobori bugetul sub prag."""
        opens = res.get("opens") or []
        pend = res.get("pending") or {}
        try:
            from live.global_guard import load_settings
            mc = load_settings()["max_concurrent_per_market"]
            if mc.get("enabled") and self.cfg["mode"] != "execute" and len(opens) >= int(mc.get("max", 1)):
                return False, f"GLOBAL: max {mc.get('max')} poziții simultane pe piață (Setări Globale) — {len(opens)} deschise"
        except Exception:
            pass
        bud = self.budget(trades, opens)
        risk_open = 0.0
        for q in opens:
            sz = self._size(q["entry"], q["sl"])
            risk_open += abs(q["entry"] - q["sl_now"] if q.get("sl_now") is not None else q["entry"] - q["sl"]) * (sz.get("value_per_price") or 0.0)
        new_risk = 0.0
        if pend.get("atr"):
            dist = self.cfg["strategy"]["sl_atr"] * pend["atr"]
            sz = self._size(pend["close"], pend["close"] - dist)
            new_risk = dist * (sz.get("value_per_price") or 0.0)
        left = bud["remaining"] - risk_open - new_risk
        if left < bud["min_remaining"]:
            return False, (f"BUGET: risc deschis {risk_open:.2f}$ + nou {new_risk:.2f}$ ar coborî bugetul ({bud['remaining']:.2f}$) "
                           f"sub prag ({bud['min_remaining']:.2f}$)")
        return True, ""

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

    SPREAD_WINDOW_S = 1800          # mediana spread-ului live pe ultimele 30 min (auto)

    def _sample_spread(self, sym: str, point: float | None) -> float | None:
        """Inregistreaza spread-ul LIVE (points) al tick-ului curent; intoarce valoarea curenta."""
        tick = self.mt5.symbol_info_tick(sym)
        if tick is None or not getattr(tick, "ask", 0) or not getattr(tick, "bid", 0) or not point:
            return None
        pts = (tick.ask - tick.bid) / point
        now = time.time()
        self._spread_samples = [x for x in self._spread_samples if now - x[0] <= self.SPREAD_WINDOW_S] + [(now, pts)]
        return pts

    def _auto_spread_points(self, sym: str, day, in_window: bool) -> tuple[float | None, str]:
        """Spread-ul TIPIC in mod auto: mediana tick-urilor live din ultimele 30 min, INGHETATA pe zi la prima
        iteratie din fereastra (o valoare pe zi → recalcularea zilei e identica la fiecare iteratie / restart)."""
        ref = self.state.get("spread_ref") or {}
        if ref.get("day") == str(day) and ref.get("symbol") == sym:
            return ref["points"], f"înghețat azi la {ref['at'][11:16]} (mediana a {ref['n']} tick-uri live)"
        vals = sorted(v for _, v in self._spread_samples)
        if not vals:
            return None, "fără tick-uri încă"
        med = round(vals[len(vals) // 2], 3)
        if in_window:
            self.state["spread_ref"] = {"day": str(day), "symbol": sym, "points": med, "n": len(vals),
                                        "at": datetime.now(RO).isoformat(timespec="seconds")}
            log.info(f"Noisy {sym}: spread tipic AUTO pentru azi = {med:.1f} points (mediana a {len(vals)} tick-uri live)")
            return med, f"înghețat azi (mediana a {len(vals)} tick-uri live)"
        return med, f"provizoriu (mediana a {len(vals)} tick-uri; se îngheață la deschiderea ferestrei)"

    def _live_spread_ok(self, sym: str) -> tuple[bool, str]:
        """Spread-ul LIVE (tick) la momentul semnalului vs spread-ul MAXIM (spread.max_*, rezolvat in pret)."""
        lim = self.cfg["strategy"].get("spread_max", 0.0)
        if lim <= 0:
            return True, ""
        tick = self.mt5.symbol_info_tick(sym)
        if tick is None or not tick.ask or not tick.bid:
            return True, ""
        live = tick.ask - tick.bid
        if live > lim + 1e-12:
            pt = self.spread_info.get("point") or 0
            pts = f" = {live / pt:.1f} points" if pt else ""
            mpts = f" = {lim / pt:.1f} points" if pt else ""
            return False, f"SPREAD live {live:.5g}{pts} > maxim {lim:.5g}{mpts} ({self.spread_info.get('max_source', '')})"
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

    def budget(self, trades: list[dict], open_pos) -> dict:
        """Buget shadow: realizat (trade-uri virtuale) + flotantul TUTUROR pozitiilor deschise (lista sau una)."""
        b = self.cfg["budget"]
        since = self.state.get("budget_reset_at")
        realized = sum(t.get("pnl_money") or 0.0 for t in trades if not since or t["exit_t"] >= since)
        floating = 0.0
        for q in (open_pos if isinstance(open_pos, list) else [open_pos] if open_pos else []):
            sz = self._size(q["entry"], q["sl"])
            floating += (q["float_R"] * q["risk"]) * (sz.get("value_per_price") or 0.0)
        remaining = b["capital"] + realized + floating
        return {"capital": b["capital"], "min_remaining": b["min_remaining"], "realized": round(realized, 2),
                "floating": round(floating, 2), "remaining": round(remaining, 2),
                "locked": self.state.get("budget_lock"), "since": since}

    # ── executie reala ──────────────────────────────────────────────────────
    def exec_state(self) -> tuple[bool, str]:
        if self.cfg["mode"] != "execute":
            return False, "mod SHADOW (fără ordine)"
        try:
            from live_guard import live_allowed
            return X.execution_allowed(self.mt5, live_allowed)
        except Exception as e:
            return False, f"verificare execuție indisponibilă: {e}"

    def budget_real(self, now_utc: datetime) -> dict:
        """Buget din MT5: P&L REALIZAT (deal-uri magic Noisy, de la pornirea executiei / reset) + FLOTANT."""
        b = self.cfg["budget"]
        since = max(filter(None, [self.state.get("budget_reset_at"), self.state.get("exec_since")]), default=None)
        try:
            since_epoch = datetime.fromisoformat(since).timestamp() if since else now_utc.timestamp()
        except Exception:
            since_epoch = now_utc.timestamp()
        realized = X.realized_pnl(self.mt5, since_epoch, now_utc.timestamp())
        floating = X.floating_pnl(self.mt5, self.cfg["symbol"])
        remaining = b["capital"] + realized + floating
        return {"capital": b["capital"], "min_remaining": b["min_remaining"], "realized": round(realized, 2),
                "floating": round(floating, 2), "remaining": round(remaining, 2), "source": "mt5",
                "locked": self.state.get("budget_lock"), "since": since}

    def _execute(self, sym: str, signal: dict | None, res: dict, blocked: bool, tf_min: int) -> None:
        """Semnal nou → ordin la piata cu SL + tinta atasate; stop de timp → inchidere; o pozitie odata (sau pana la
        overlap.max_open cand trade-urile suprapuse sunt activate — semnalul a trecut deja prin aceleasi reguli)."""
        cfg = self.cfg
        tick = self.mt5.symbol_info_tick(sym)
        positions = X.own(self.mt5, sym)
        # 1) stop de timp (+ plasa: orice pozitie Noisy mai veche decat stopul de timp + o bara)
        limit_s = (cfg["strategy"]["time_stop_bars"] + 1) * tf_min * 60
        for p in positions:
            if tick is not None and tick.time and tick.time - p.time >= limit_s:
                done, r = X.close(self.mt5, p)
                self._event_once(f"real-timeclose-{p.ticket}",
                                 f"⏱ <b>Noisy EXECUȚIE — {sym} închis la stop de timp</b> #{p.ticket} "
                                 + ("" if done else f"⚠️ EȘUAT: {getattr(r, 'retcode', r)}"))
        positions = X.own(self.mt5, sym)
        # 1b) break-even pe pozitia REALA: aceeasi faza ca trade-ul virtual pereche (acelasi semnal),
        # aplicata pe pretul REAL de intrare / tinta (lock% din distanta intrare → tinta)
        be = cfg.get("break_even") or {}
        for vo in (res.get("opens") or ([res["open"]] if res.get("open") else [])):
            if be.get("enabled") and vo and vo.get("be_phase", 0) >= 2:
                lock = be["lock2_pct"] if vo["be_phase"] >= 4 else be["lock1_pct"]
                for p in positions:
                    if str(p.comment)[:16] != X.tag(sym, vo["signal_t"]) or not p.tp:
                        continue
                    d = 1 if p.type == getattr(self.mt5, "POSITION_TYPE_BUY", 0) else -1
                    want = p.price_open + d * abs(p.tp - p.price_open) * lock / 100.0
                    if (d > 0 and want > (p.sl or 0) + 1e-9) or (d < 0 and (not p.sl or want < p.sl - 1e-9)):
                        done, r = X.modify_sl(self.mt5, p, want)
                        self._event_once(f"real-be-{p.ticket}-{vo['be_phase']}",
                                         f"🔒 <b>Noisy EXECUȚIE — {sym} break-even</b> #{p.ticket}: SL → {want:.3f} ({lock:.0f}% din țintă)"
                                         + ("" if done else f" ⚠️ EȘUAT: {getattr(r, 'retcode', r)}"),
                                         notify=cfg.get("notify_trades", False) or not done)
                positions = X.own(self.mt5, sym)
        # 2) intrare noua
        max_open = cfg["overlap"]["max_open"] if cfg["overlap"]["enabled"] else 1
        if signal is None or blocked or len(positions) >= max_open or tick is None or not tick.ask:
            return
        if signal["signal_t"] in self.state.setdefault("placed", []):
            return
        self.state["placed"].append(signal["signal_t"])
        self.state["placed"] = self.state["placed"][-500:]
        d = 1 if signal["dir"] == "LONG" else -1
        entry = tick.ask if d > 0 else tick.bid
        risk = cfg["strategy"]["sl_atr"] * signal["atr"]
        sl = entry - d * risk
        tp_rr = cfg["strategy"].get("tp_rr", 0) or 0
        tp = entry + d * (tp_rr * risk if tp_rr > 0 else abs(signal["ema"] - signal["close"]) + 1e-12)
        size = self._size(entry, sl)
        if not size["lots"]:
            self._event_once(f"real-nolot-{signal['signal_t']}",
                             f"⚠️ Noisy EXECUȚIE — {sym}: ordin NEplasat (lot 0: {size.get('risk_cap') or size.get('reason') or 'sub lotul minim'})")
            return
        ok, r = X.place_market(self.mt5, sym, d, size["lots"], sl, tp, X.tag(sym, signal["signal_t"]))
        self._event_once(f"real-entry-{signal['signal_t']}",
                         (f"🟢 <b>Noisy EXECUȚIE — {sym} {signal['dir']}</b> {size['lots']} lot @ {entry:.3f}\n"
                          f"SL {sl:.3f} · țintă {tp:.3f} · stop de timp {cfg['strategy']['time_stop_bars'] * tf_min} min")
                         if ok else f"⚠️ <b>Noisy EXECUȚIE — {sym} {signal['dir']}: ordin RESPINS</b> "
                                    f"({getattr(r, 'retcode', r)} {getattr(r, 'comment', '')})")

    def _ensure_terminal(self) -> tuple[bool, str]:
        """Terminal MT5 VIU si conectat la broker. IPC pierdut (terminal inchis / repornit) → re-initialize
        (altfel fiecare apel MT5 intoarce None pana la restartul engine-ului); deconectat de la broker →
        datele sunt inghetate, iteratia e sarita cu motivul vizibil (audit 2026-11-01)."""
        fn = getattr(self.mt5, "terminal_info", None)
        if fn is None:                       # MT5 simulat in teste
            return True, ""
        ti = fn()
        if ti is None:
            try:
                self.mt5.shutdown()
            except Exception:
                pass
            if not self.connect() or fn() is None:
                return False, "MT5: terminal indisponibil (IPC pierdut) — reîncerc automat"
            self._err("MT5: IPC restabilit (terminal repornit) — reconectat automat")
            ti = fn()
        if not getattr(ti, "connected", True):
            return False, "MT5 deconectat de la serverul brokerului — date înghețate, aștept reconectarea"
        return True, ""

    def iteration(self, now_utc: datetime | None = None) -> dict:
        self.cfg = load_config()
        cfg = self.cfg
        sym = cfg["symbol"]
        now_utc = now_utc or datetime.now(timezone.utc)
        ok_t, why_t = self._ensure_terminal()
        if not ok_t:
            self._err(why_t)
            st = {"running": True, "mode": cfg["mode"], "symbol": sym, "pid": os.getpid(), "state": "error",
                  "state_label": STATES["error"], "reason": why_t, "errors": self.errors,
                  "heartbeat": datetime.now(RO).isoformat(timespec="seconds"), "scorecard": scorecard(load_trades())}
            _write_json(STATUS_FILE, st)
            return st
        now_ro = now_utc.astimezone(RO).replace(tzinfo=None)
        day = now_ro.date()
        self._switch_symbol(sym)
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
        # spread: tick-ul live → tipic (auto, inghetat pe zi / manual) + maxim → strategy.spread_floor / spread_max
        from noisy_engine.strategy import _in_window as _inw
        point = getattr(si, "point", None) if si else None
        live_pts = self._sample_spread(sym, point)
        auto_pts, auto_note = self._auto_spread_points(sym, day, _inw(now_ro, cfg["window"]))
        self.spread_info = resolve_spread(cfg, point, auto_pts, getattr(si, "digits", None) if si else None)
        self.spread_info.update(live_points=None if live_pts is None else round(live_pts, 2),
                                auto_note=auto_note if cfg["spread"]["mode"] == "auto" else "")
        # toata ziua de azi + istoric pentru indicatori (recalcularea zilei trebuie sa vada si dimineata)
        need = int((now_ro.hour * 60 + now_ro.minute) / tf_min) + 400
        rates = self.mt5.copy_rates_from_pos(sym, getattr(self.mt5, f"TIMEFRAME_{cfg['timeframe']}"), 0, min(need, 3000))
        bars = rates_to_bars(rates, self.offset_s, si.point if si else 0.0, now_ro, tf_min)
        events = self._events_news()
        blocks = news_blocks(sym, events, cfg["news"]["pre_min"], cfg["news"]["post_min"]) if cfg["news"]["enabled"] else []
        fb = friday_block(now_ro)
        friday_active = bool(fb and fb[0] <= now_ro < fb[1])
        if fb:
            blocks = blocks + [fb]
        trades_all = load_trades()
        lock = self.state.get("budget_lock")
        vetoed = set(self.state["vetoed"].get(str(day), []))

        res = run_day(bars, day, cfg, news_blocks=blocks, vetoed=vetoed, no_new_entries=bool(lock) or paused)
        # semnal NOU → protectiile globale, o singura data per semnal
        pend = res.get("pending")
        global_block = None
        fresh_signal = None                                # semnal NOU acceptat in aceasta iteratie
        if pend and pend["signal_t"] not in self.state["checked"]:
            self.state["checked"].append(pend["signal_t"])
            ok, why = self._global_check(sym, events, now_utc)
            if ok:
                ok, why = self._live_spread_ok(sym)
            if ok and cfg["overlap"]["enabled"]:
                ok, why = self._overlap_guard(res, trades_all)
            if not ok:
                self.state["vetoed"].setdefault(str(day), []).append(pend["signal_t"])
                global_block = why
                kind = "spread prea mare" if why.startswith("SPREAD") else "protecție globală"
                self._event_once(f"veto-{pend['signal_t']}",
                                 f"🛡 <b>Noisy {'EXECUȚIE' if cfg['mode'] == 'execute' else 'SHADOW'} — {sym} {pend['dir']} "
                                 f"respins ({kind})</b>\n{why}")
                res = run_day(bars, day, cfg, news_blocks=blocks, vetoed=vetoed | {pend["signal_t"]},
                              no_new_entries=bool(lock) or paused)
            else:
                fresh_signal = pend
                self._event_once(f"sig-{pend['signal_t']}", f"Noisy {sym}: semnal {pend['dir']} la {pend['signal_t'][11:16]} "
                                 f"— intrare la deschiderea barei urmatoare", notify=False)
        # semnale respinse de filtrele strategiei → jurnal (o data per semnal; fara Telegram — pot fi zeci / zi)
        logged = self.state.setdefault("rejects_logged", [])
        for rj in res.get("rejected", []):
            key = f"{rj['t']}|{rj['reason']}"
            if key in logged:
                continue
            logged.append(key)
            log.info(f"Noisy {sym}: semnal {rj['dir']} la {rj['t'][11:16]} RESPINS — {rj['reason']}: {rj['detail']}")
        self.state["rejects_logged"] = logged[-1000:]
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
        opens = res.get("opens") or ([op] if op else [])
        for q in opens:
            self._event_once(f"entry-{q['id']}",
                             f"🧪 <b>Noisy SHADOW — {sym} {q['dir']}</b> @ {q['entry']:.3f}\n"
                             f"SL {q['sl']:.3f} · țintă {q['tp']:.3f} · stop de timp {cfg['strategy']['time_stop_bars'] * tf_min} min (virtual)"
                             + (f" · {len(opens)} deschise" if len(opens) > 1 else ""),
                             notify=cfg.get("notify_trades", False))
        # executie reala (DEMO / REAL deblocat) — modul shadow nu atinge executorul
        ex_ok, ex_why = self.exec_state()
        if ex_ok:
            self.state.setdefault("exec_since", now_utc.isoformat(timespec="seconds"))
        # buget izolat: in EXECUTIE din dealurile reale MT5 (magic Noisy), in shadow din trade-urile virtuale
        bud = self.budget_real(now_utc) if ex_ok else self.budget(trades_all, opens)
        if ex_ok and friday_active:
            n_ok, n_bad = X.close_all(self.mt5, sym)
            if n_ok or n_bad:
                self._event_once(f"friday-close-{day}", f"📅 Noisy EXECUȚIE — închidere de vineri (Setări Globale): "
                                 f"{n_ok} poziții închise" + (f", {n_bad} EȘUATE — verifică MT5!" if n_bad else ""))
        if ex_ok:
            try:
                self._execute(sym, fresh_signal, res, bool(lock) or paused or bool(res.get("lock")) or friday_active, tf_min)
            except Exception as e:                       # o eroare de executie nu opreste engine-ul
                self._err(f"executie: {type(e).__name__}: {e}")
        if not lock and bud["remaining"] <= bud["min_remaining"]:
            lock = {"at": now_ro.isoformat(timespec="seconds"), "remaining": bud["remaining"]}
            self.state["budget_lock"] = lock
            bud["locked"] = lock
            self._event_once(f"budget-{lock['at']}",
                             f"⛔ <b>Noisy Engine — BUDGET LIMIT</b>\nBuget rămas {bud['remaining']:.2f}$ ≤ prag "
                             f"{bud['min_remaining']:.2f}$ → fără intrări noi până la resetarea manuală a bugetului.")
            if ex_ok and cfg.get("on_stop", "close") == "close":
                n_ok, n_bad = X.close_all(self.mt5, sym)
                if n_ok or n_bad:
                    self._event_once(f"budget-close-{lock['at']}", f"⛔ Noisy: {n_ok} poziții închise la BUDGET LIMIT"
                                     + (f", {n_bad} EȘUATE — verifică MT5!" if n_bad else ""))
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
            state, reason = "in_position", " · ".join(f"{q['dir']} @ {q['entry']:.3f} ({q['float_R']:+.2f}R)" for q in opens)
        elif res.get("lock"):
            state, reason = res["lock"], "limită zilnică atinsă — reset la miezul nopții"
        elif friday_active:
            state, reason = "risk_locked", "închidere de vineri (Setări Globale) — fără intrări până luni"
        elif global_block:
            state, reason = "risk_locked", global_block
        elif not in_win:
            state, reason = "outside_window", f"intră doar {intervals_label(cfg['window'])} (ora RO)"
        else:
            state, reason = "running", "aștept semnal"
            if not cfg["tf_profiles"][cfg["timeframe"]].get("cost_filter_enabled", True):
                reason += " · filtrul cost/ATR OPRIT (probă — intră și când costul mănâncă mișcarea)"
            rc = res.get("reject_counts") or {}
            if rc:
                top = ", ".join(f"{k} {v}" for k, v in sorted(rc.items(), key=lambda kv: -kv[1])[:3])
                reason += f" · semnale respinse azi: {top}"
                if rc.get("cost_atr") and rc["cost_atr"] == sum(rc.values()):
                    reason += " — costul (spread) e prea mare față de mișcarea pieței (filtrul cost/ATR)"
        today = [t for t in trades_all if t.get("day") == str(day) and t.get("tf", "M5") == cfg["timeframe"]]
        real_pos = []
        if ex_ok or cfg["mode"] == "execute":
            try:
                real_pos = [{"ticket": p.ticket, "type": "LONG" if p.type == getattr(self.mt5, "POSITION_TYPE_BUY", 0) else "SHORT",
                             "volume": p.volume, "price": p.price_open, "sl": p.sl, "tp": p.tp, "profit": p.profit}
                            for p in X.own(self.mt5, sym)]
            except Exception:
                real_pos = []
        status.update(execution={"active": ex_ok, "reason": ex_why}, real_positions=real_pos)
        status.update(spread=self.spread_info, rejects_today=res.get("reject_counts") or {},
                      rejected_recent=(res.get("rejected") or [])[-20:])
        status.update(opens=opens)
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
    mode_txt = "EXECUȚIE (ordine reale, dacă contul o permite)" if cfg["mode"] == "execute" else "SHADOW (trade-uri virtuale)"
    log.info(f"Noisy Engine pornit — {cfg['symbol']} {cfg['timeframe']}, mod {mode_txt}")
    _notify(cfg, f"🧪 <b>Noisy Engine pornit</b> — {cfg['symbol']} {cfg['timeframe']}, mod {mode_txt}\n"
                 f"Fereastră {intervals_label(cfg['window'])} RO · buget {cfg['budget']['capital']:.0f}$ "
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
