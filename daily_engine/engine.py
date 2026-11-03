"""Daily Engine — motor intraday ORB, mod SHADOW (trade-uri virtuale, ZERO ordine reale).

Bucla (la `poll_seconds`):
  1. pentru fiecare piata activa: barele M5 INCHISE de azi din fereastra bursei (ora locala, DST-corect)
  2. `strategy.evaluate_day` recalculeaza starea zilei de la zero (restart-safe)
  3. evenimente noi (intrare / inchidere / zi sarita) -> log + Telegram, o singura data (state.json)
  4. trade-urile inchise -> data/daily_engine/trades.jsonl; heartbeat -> status.json

Izolare: conexiune MT5 proprie, DOAR citire (copy_rates / symbol_info / tick). Modulul nu contine
niciun apel de plasare ordine — verificat de selftest. Merge pe cont real sau demo fara risc.
Ora serverului: detectata din tick-ul proaspat (server − UTC), nu presupusa.
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
from datetime import datetime, timezone, timedelta
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from daily_engine.config import DATA_DIR, ENTRY_MODES, load_config, save_default_config, hm_to_min  # noqa: E402
from daily_engine.strategy import evaluate_day_multi  # noqa: E402
import position_sizing as ps  # noqa: E402
from daily_engine import executor as X  # noqa: E402

PID_FILE = os.path.join(DATA_DIR, "daily_engine.pid")
STATUS_FILE = os.path.join(DATA_DIR, "status.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
TRADES_FILE = os.path.join(DATA_DIR, "trades.jsonl")
LOG_FILE = os.path.join(DATA_DIR, "engine.log")
DESIRED_FILE = os.path.join(DATA_DIR, "desired_running.json")   # sters doar de Stop-ul din UI
RO = ZoneInfo("Europe/Bucharest")
_MUTEX_NAMES = ("Global\\TradingBot_DailyEngine_SingleInstance", "Local\\TradingBot_DailyEngine_SingleInstance")
_mutex_handle = None
log = logging.getLogger("daily_engine")


# ── utilitare ────────────────────────────────────────────────────────────────

def _setup_logging() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    fh = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(fh)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # stdout -> fisier: diacritice fara erori
    except Exception:
        pass
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    log.addHandler(sh)


def _acquire_single_instance(names=_MUTEX_NAMES) -> bool:
    """Mutex Windows numit (eliberat de OS si la taskkill). Non-Windows: nu blocheaza."""
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
        if err == 183:                      # ERROR_ALREADY_EXISTS
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
    """Telegram + tab Notificari, non-blocant. Esecul nu afecteaza motorul."""
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
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    except FileNotFoundError:
        pass
    return out


def scorecard(trades: list[dict]) -> dict:
    def _sc(ts):
        rs = [t["R"] for t in ts]
        n = len(rs)
        w = sum(1 for r in rs if r > 0)
        est = [t["pnl_money_est"] for t in ts if t.get("pnl_money_est") is not None]
        return {"trades": n, "wins": w, "losses": sum(1 for r in rs if r < 0),
                "pnl_money_est": round(sum(est), 2) if est else None,
                "total_R": round(sum(rs), 3), "expectancy_R": round(sum(rs) / n, 3) if n else None,
                "win_rate": round(w / n, 3) if n else None}
    syms = sorted({t["symbol"] for t in trades})
    return {**_sc(trades), "by_symbol": {s: _sc([t for t in trades if t["symbol"] == s]) for s in syms}}


# ── timp ────────────────────────────────────────────────────────────────────

def _app_window(w_open: datetime, w_end: datetime) -> dict:
    """Fereastra in fusul aplicatiei (tz_helper: Romania / Germania) + eticheta scurta, pentru UI."""
    try:
        from tz_helper import get_configured_tz_name
        name = get_configured_tz_name()
    except Exception:
        name = "Europe/Bucharest"
    tz = ZoneInfo(name)
    return {"window_app": f"{w_open.astimezone(tz):%H:%M}–{w_end.astimezone(tz):%H:%M}",
            "app_tz": name, "app_tz_label": "DE" if name == "Europe/Berlin" else "RO"}


def window_times(m: dict, day_local) -> tuple[datetime, datetime]:
    """(deschidere, sfarsit ultima bara) ca datetime aware in fusul bursei, pentru ziua data."""
    tz = ZoneInfo(m["tz"])
    o, lb = hm_to_min(m["open"]), hm_to_min(m["last_bar"]) + 5
    base = datetime(day_local.year, day_local.month, day_local.day, tzinfo=tz)
    return base + timedelta(minutes=o), base + timedelta(minutes=lb)


X_MODE = ENTRY_MODES


def bars_today(rates, server_offset_s: int, m: dict, now_utc: datetime) -> pd.DataFrame:
    """Barele M5 INCHISE de azi (zi locala a bursei) din fereastra pietei."""
    if rates is None or len(rates) == 0:
        return pd.DataFrame(columns=["mins", "open", "high", "low", "close", "spread"])
    d = pd.DataFrame(rates)
    start_utc = pd.to_datetime(d["time"] - server_offset_s, unit="s", utc=True)
    closed = start_utc + pd.Timedelta(minutes=5) <= pd.Timestamp(now_utc)
    loc = start_utc.dt.tz_convert(m["tz"])
    today = pd.Timestamp(now_utc).tz_convert(m["tz"]).date()
    d["mins"] = loc.dt.hour * 60 + loc.dt.minute
    keep = closed & (loc.dt.date == today) & (d["mins"] >= hm_to_min(m["open"])) & \
        (d["mins"] <= hm_to_min(m["last_bar"]))
    return d[keep].reset_index(drop=True)


# ── motor ───────────────────────────────────────────────────────────────────

class DailyEngine:
    def __init__(self, mt5_module=None):
        if mt5_module is None:
            import MetaTrader5 as mt5_module
        self.mt5 = mt5_module
        self.cfg = load_config()
        self.state = _read_json(STATE_FILE, {"events": {}})
        self.server_offset_s: int | None = None
        self.errors: list[str] = []
        self.account: dict = {}

    # MT5 — DOAR citire
    def connect(self) -> bool:
        if not self.mt5.initialize():
            self._err(f"MT5 initialize esuat: {self.mt5.last_error()}")
            return False
        a = self.mt5.account_info()
        if a is not None:
            demo = getattr(a, "trade_mode", None) == 0
            self.account = {"login": a.login, "server": a.server, "is_demo": demo}
        for m in self.cfg["markets"]:
            self.mt5.symbol_select(m["symbol"], True)
        return True

    def _err(self, msg: str) -> None:
        log.warning(msg)
        self.errors = (self.errors + [f"{datetime.now(RO):%d.%m %H:%M} {msg}"])[-10:]

    def _refresh_offset(self, symbol: str, now_utc: datetime) -> None:
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None or not tick.time:
            return
        diff = tick.time - now_utc.timestamp()
        hours = round(diff / 3600)
        # tick proaspat (< 3 min dupa scaderea offset-ului) => offset de incredere
        if abs(diff - hours * 3600) < 180:
            self.server_offset_s = int(hours * 3600)

    def process_market(self, m: dict, now_utc: datetime) -> dict:
        sym = m["symbol"]
        tz = ZoneInfo(m["tz"])
        now_loc = now_utc.astimezone(tz)
        day = now_loc.date()
        w_open, w_end = window_times(m, day)
        info = {"symbol": sym, "label": m.get("label", ""), "role": m.get("role", ""),
                "enabled": m.get("enabled", True), "entry_mode": m["entry"], "or_minutes": m["or_minutes"],
                "rr": m.get("rr"), "reentry": m.get("reentry"),
                "day": str(day),
                "window_local": f"{m['open']}–{w_end:%H:%M} ({m['tz'].split('/')[-1].replace('_', ' ')})",
                "window_ro": f"{w_open.astimezone(RO):%H:%M}–{w_end.astimezone(RO):%H:%M}",
                # fereastra si in fusul APLICATIEI (RO / DE) — doar afisare; logica ramane pe ora bursei
                **_app_window(w_open, w_end)}
        if not m.get("enabled", True):
            return {**info, "phase": "disabled"}
        if now_loc.weekday() >= 5:
            return {**info, "phase": "weekend"}
        if now_loc < w_open:
            self._arm(sym, day)
            return {**info, "phase": "waiting_open", **self._exec_info(sym, day)}

        self._refresh_offset(sym, now_utc)
        if self.server_offset_s is None:
            return {**info, "phase": "waiting_open", "note": "astept un tick proaspat (ora serverului)"}
        rates = self.mt5.copy_rates_from_pos(sym, self.mt5.TIMEFRAME_M5, 0, 200)
        b = bars_today(rates, self.server_offset_s, m, now_utc)
        si = self.mt5.symbol_info(sym)
        point = si.point if si else 0.0
        day_complete = now_loc >= w_end + timedelta(minutes=2)
        if day_complete and len(b) == 0:
            return {**info, "phase": "skipped", "reason": "piata inchisa azi (fara bare)"}
        # o zi = unul sau mai multe trade-uri (re-intrari OPTIONALE in prima ora); oprit → identic cu inainte
        st = evaluate_day_multi(b.open, b.high, b.low, b.close, b.spread * point, b.mins,
                                open_min=hm_to_min(m["open"]), or_minutes=m["or_minutes"],
                                mode=ENTRY_MODES[m["entry"]], rr=m.get("rr"), slip=m["slip"],
                                comm=m["comm"], day_complete=day_complete, reentry=m.get("reentry"))
        if st["phase"] in ("waiting_open", "forming_or"):
            self._arm(sym, day)
        self._events(m, str(day), st)
        try:
            self._execute(m, day, st, b, now_loc, w_end)
        except Exception as e:                       # o eroare de executie nu opreste shadow-ul
            self._err(f"{sym} executie: {type(e).__name__}: {e}")
        clean = {k: (v.item() if isinstance(v, np.generic) else v) for k, v in st.items() if k != "trades"}
        tr = st.get("trades") or []
        return {**info, **clean, **self._exec_info(sym, day),
                "trades_today": len(tr) + (1 if st["phase"] == "in_position" else 0),
                "R_today": round(sum(t["R"] for t in tr), 3)}

    # ── EXECUTIE REALA (doar mode=execute + cont permis + zi armata) ──────────

    def exec_state(self) -> tuple[bool, str]:
        if self.cfg.get("mode") != "execute":
            return False, "mod SHADOW (fără ordine)"
        from live_guard import live_allowed
        return X.execution_allowed(self.mt5, live_allowed)

    def _arm(self, sym: str, day) -> None:
        """Ziua devine REALA doar daca modul Executie era activ INAINTE de formarea intervalului."""
        ok, _ = self.exec_state()
        ev = self.state.setdefault("events", {})
        k = f"{day}|{sym}|armed"
        if ok and not ev.get(k):
            ev[k] = True
            log.info(f"{sym} {day}: zi ARMATA pentru executie reala")

    def _exec_info(self, sym: str, day) -> dict:
        ev = self.state.get("events", {})
        return {"exec_armed": bool(ev.get(f"{day}|{sym}|armed")), "exec_placed": ev.get(f"{day}|{sym}|placed")}

    def _execute(self, m: dict, day, st: dict, b, now_loc, w_end) -> None:
        sym = m["symbol"]
        ev = self.state.setdefault("events", {})
        key = f"{day}|{sym}"
        tag = X.day_tag(sym, day)
        pos, ords = X.own(self.mt5, sym)
        pos_t = [p for p in pos if (p.comment or "").startswith(tag)]
        ord_t = [o for o in ords if (o.comment or "").startswith(tag)]
        # 1) final de fereastra: anuleaza tot, inchide tot — niciodata peste noapte
        if now_loc >= w_end:
            for o in ord_t:
                X.cancel(self.mt5, o)
            for p in pos_t:
                ok, res = X.close(self.mt5, p)
                self._exec_note(sym, f"închis la final de fereastră ({'ok' if ok else 'EȘUAT ' + str(getattr(res, 'retcode', res))})")
            return
        # 2) o pozitie deschisa -> anuleaza cealalta margine (OCO)
        if pos_t and ord_t:
            for o in ord_t:
                X.cancel(self.mt5, o)
            return
        # 2b) RE-INTRARE (k >= 1): trade-ul virtual k tocmai a intrat → ordin la piata cu SL (+ TP), o pozitie odata
        k = int(st.get("k") or 0)
        if k >= 1:
            if st["phase"] == "in_position" and not pos_t and not ord_t and ev.get(f"{key}|armed") \
                    and not ev.get(f"{key}|placed{k}"):
                self._execute_reentry(m, day, st, b, k, tag)
            return
        if pos_t or ord_t or ev.get(f"{key}|placed") or not ev.get(f"{key}|armed"):
            return
        ok, why = self.exec_state()
        if not ok or st["phase"] not in ("waiting_entry",) or st.get("or_hi") is None:
            return
        hi, lo = st["or_hi"], st["or_lo"]
        info, tick = self.mt5.symbol_info(sym), self.mt5.symbol_info_tick(sym)
        if info is None or tick is None:
            return
        spread = tick.ask - tick.bid
        if hi - lo < 2 * (spread + m["slip"] + m["comm"]):
            ev[f"{key}|placed"] = "skip"
            self._exec_note(sym, f"zi sărită: interval {hi - lo:.5g} < 2× cost")
            return
        # protectiile globale (capital, circuit breaker, max pozitii / piata) + stiri globale
        from live import global_guard
        ok_g, reason = global_guard.check_open(self.mt5, "daily", sym)
        if ok_g and global_guard.load_settings()["news_protection"]["enabled"]:
            try:                            # calendarul se descarca DOAR cand protectia globala e activa
                from live.news_guard import _fetch_forexfactory
                if global_guard.news_window_active(sym, _fetch_forexfactory()):
                    ok_g, reason = False, "fereastră de știri (Setări Globale)"
            except Exception:
                pass
        if not ok_g:
            ev[f"{key}|placed"] = "blocked"
            self._exec_note(sym, f"BLOCAT: {reason}")
            return
        mode = X_MODE[m["entry"]]
        sz = self.cfg.get("sizing") or {}
        acc = self.mt5.account_info()
        cap = ps.capital_base(sz.get("capital_sync_mt5", True), sz.get("capital_usd"),
                              getattr(acc, "equity", 0) if acc else 0) * ps.clamp_fraction(sz.get("fraction", 1.0))
        results = []
        if mode == "dir":
            o0 = float(b.open.iloc[0])
            c_last = float(b.close.iloc[m["or_minutes"] // 5 - 1])
            if c_last == o0:
                ev[f"{key}|placed"] = "skip"
                return
            side = 1 if c_last > o0 else -1
            entry, sl = (tick.ask, lo) if side == 1 else (tick.bid, hi)
            r = self._capped(ps.size_by_risk(info, entry, sl, cap, sz.get("risk_pct", 0.01)), info, entry, sl, acc)
            if not r["lots"]:
                ev[f"{key}|placed"] = "skip"
                self._exec_note(sym, f"nu plasez: {r['reason']}")
                return
            tp = entry + side * m["rr"] * abs(entry - sl) if m.get("rr") else None
            ok_o, res = X.place_market(self.mt5, sym, side, r["lots"], sl, tag, tp=tp)
            results.append((("LONG" if side == 1 else "SHORT") + " piață" + (f" · TP {m['rr']:g}R" if tp else ""), r, ok_o, res))
        else:
            for side, lvl, sl in ((1, hi, lo), (-1, lo, hi)):
                r = self._capped(ps.size_by_risk(info, lvl, sl, cap, sz.get("risk_pct", 0.01)), info, lvl, sl, acc)
                if not r["lots"]:
                    if r.get("reason"):
                        self._exec_note(sym, f"{'BUY' if side == 1 else 'SELL'}_STOP nu se plasează: {r['reason']}")
                    continue
                beyond = (side == 1 and tick.ask >= lvl) or (side == -1 and tick.bid <= lvl)
                tp = lvl + side * m["rr"] * abs(lvl - sl) if m.get("rr") else None
                if beyond:      # pretul a trecut deja de margine -> ca in backtest: umplere la piata
                    ok_o, res = X.place_market(self.mt5, sym, side, r["lots"], sl, tag, tp=tp)
                    results.append((("LONG" if side == 1 else "SHORT") + " piață (gap)", r, ok_o, res))
                    break
                ok_o, res = X.place_stop(self.mt5, sym, side, lvl, r["lots"], sl, tag, tp=tp)
                results.append((("BUY_STOP" if side == 1 else "SELL_STOP") + f" @ {lvl:.5g}", r, ok_o, res))
        ev[f"{key}|placed"] = "yes" if any(x[2] for x in results) else "failed"
        cur = getattr(acc, "currency", "USD") if acc else "USD"
        lines = [f"{'✅' if ok_o else '❌'} {what} · {r['lots']} loturi · SL · risc {r['risk_money']:.2f} {cur}"
                 + ("" if ok_o else f" — retcode {getattr(res, 'retcode', res)}") for what, r, ok_o, res in results]
        self._exec_note(sym, "ORDINE REALE (" + why + ")\n" + "\n".join(lines), important=True)
        _write_json(STATE_FILE, self.state)

    def _execute_reentry(self, m: dict, day, st: dict, b, k: int, tag: str) -> None:
        """Re-intrarea k (>= 1) in executie: doar daca semnalul virtual e PROASPAT (intrare pe ultima bara inchisa sau
        cea dinainte) — un restart tarziu nu plaseaza un ordin vechi. Aceleasi protectii ca primul trade."""
        sym, ev, key = m["symbol"], self.state.setdefault("events", {}), f"{day}|{m['symbol']}"
        ok, why = self.exec_state()
        if not ok:
            return
        if len(b) == 0 or int(st.get("entry_min", -1)) < int(b.mins.iloc[-1]) - 5:
            ev[f"{key}|placed{k}"] = "stale"
            return
        from live import global_guard
        ok_g, reason = global_guard.check_open(self.mt5, "daily", sym)
        if not ok_g:
            ev[f"{key}|placed{k}"] = "blocked"
            self._exec_note(sym, f"re-intrarea {k + 1} BLOCATĂ: {reason}")
            return
        info, tick, acc = self.mt5.symbol_info(sym), self.mt5.symbol_info_tick(sym), self.mt5.account_info()
        if info is None or tick is None:
            return
        side, sl = int(st["side"]), float(st["sl"])
        entry = tick.ask if side == 1 else tick.bid
        if (side == 1 and entry <= sl) or (side == -1 and entry >= sl):
            ev[f"{key}|placed{k}"] = "skip"
            return
        sz = self.cfg.get("sizing") or {}
        cap = ps.capital_base(sz.get("capital_sync_mt5", True), sz.get("capital_usd"),
                              getattr(acc, "equity", 0) if acc else 0) * ps.clamp_fraction(sz.get("fraction", 1.0))
        r = self._capped(ps.size_by_risk(info, entry, sl, cap, sz.get("risk_pct", 0.01)), info, entry, sl, acc)
        if not r["lots"]:
            ev[f"{key}|placed{k}"] = "skip"
            self._exec_note(sym, f"re-intrarea {k + 1} nu se plasează: {r.get('reason')}")
            return
        tp = entry + side * m["rr"] * abs(entry - sl) if m.get("rr") else None
        ok_o, res = X.place_market(self.mt5, sym, side, r["lots"], sl, f"{tag}{k}"[:16], tp=tp)
        ev[f"{key}|placed{k}"] = "yes" if ok_o else "failed"
        self._exec_note(sym, f"{'✅' if ok_o else '❌'} RE-INTRARE {k + 1} {'LONG' if side == 1 else 'SHORT'} piață · "
                             f"{r['lots']} loturi · SL{' · TP ' + format(m['rr'], 'g') + 'R' if tp else ''}"
                             + ("" if ok_o else f" — retcode {getattr(res, 'retcode', res)}"), important=True)
        _write_json(STATE_FILE, self.state)

    @staticmethod
    def _capped(r: dict, info, entry: float, sl: float, acc) -> dict:
        """Limita globala de risc pe trade (Setari Globale → risk_cap) — comuna cu Custom / AI."""
        from live.global_guard import risk_cap_pct
        cap = risk_cap_pct()
        if not cap or not r.get("lots"):
            return r
        lots, why = ps.apply_risk_cap(info, r["lots"], entry, sl, getattr(acc, "equity", None) if acc else None, cap)
        if why:
            rm = r.get("risk_money")
            r = {**r, "lots": lots, "reason": why if not lots else r.get("reason"), "risk_cap": why,
                 "risk_money": (rm * lots / r["lots"]) if (rm is not None and r["lots"]) else rm}
        return r

    def _exec_note(self, sym: str, text: str, important: bool = False) -> None:
        msg = f"🟢 <b>Daily EXECUȚIE — {sym}</b>\n{text}"
        log.info(msg.replace("<b>", "").replace("</b>", ""))
        _notify(self.cfg, msg)

    def sweep_stale(self, now_utc: datetime) -> None:
        """Orice pozitie / ordin Daily din ALTA zi decat cea curenta a pietei lui -> inchis / anulat
        (plasa de siguranta: restart peste noapte, fereastra ratata). Ruleaza in orice mod."""
        try:
            pos, ords = X.own(self.mt5)
        except Exception:
            return
        tags = {}
        for m in self.cfg["markets"]:
            d = now_utc.astimezone(ZoneInfo(m["tz"])).date()
            tags[m["symbol"]] = X.day_tag(m["symbol"], d)
        for o in ords:
            if not (o.comment or "").startswith(tags.get(o.symbol, "\0")):
                X.cancel(self.mt5, o)
                self._exec_note(o.symbol, f"ordin rămas din altă zi anulat ({o.comment})")
        for p in pos:
            if not (p.comment or "").startswith(tags.get(p.symbol, "\0")):
                ok, _ = X.close(self.mt5, p)
                self._exec_note(p.symbol, f"poziție rămasă din altă zi închisă ({p.comment}) — {'ok' if ok else 'EȘUAT'}", True)

    def _events(self, m: dict, day: str, st: dict) -> None:
        """Evenimentele zilei, O DATA per trade (k = indexul trade-ului din zi; k = 0 pastreaza cheile vechi, deci
        starea salvata inainte de re-intrari ramane valida): intrare / inchidere → Telegram + trades.jsonl."""
        sym, ev = m["symbol"], self.state.setdefault("events", {})
        key = f"{day}|{sym}"
        sent = ev.setdefault(key, [])
        trades = list(st.get("trades") or [])
        items = [(t, "closed") for t in trades]
        if st["phase"] == "in_position":
            items.append((st, "open"))
        for t, kind in items:
            k = int(t.get("k") or 0)
            sfx = "" if k == 0 else str(k)
            side = {1: "LONG", -1: "SHORT"}.get(t.get("side"), "")
            nr = f" #{k + 1}" if (k or len(items) > 1) else ""
            if f"entry{sfx}" not in sent:
                sent.append(f"entry{sfx}")
                sz = self.virtual_size(sym, t)
                ev.setdefault(f"{key}|size{sfx}", sz)
                lot_txt = (f"\nLot ipotetic {sz['lots']} · risc ~{sz['risk_money']:.2f} {sz['currency']}"
                           + (" (lot minim > țintă)" if sz.get("at_min_lot") else "")) if sz.get("lots") else ""
                tp_txt = f" | TP {t['tp']:.5g}" if t.get("tp") else ""
                msg = (f"🧪 <b>Daily SHADOW — {sym} {side}{nr}</b> (virtual, fără ordin)"
                       + (" — re-intrare" if k else "") + "\n"
                       f"Intrare {t['entry']:.5g} | SL {t['sl']:.5g}{tp_txt} | interval {t['or_lo']:.5g}–{t['or_hi']:.5g}"
                       + lot_txt)
                log.info(msg.replace("<b>", "").replace("</b>", ""))
                _notify(self.cfg, msg)
            if kind == "closed" and f"closed{sfx}" not in sent:
                sent.append(f"closed{sfx}")
                rec = {"day": day, "symbol": sym, "side": side, "entry": t["entry"], "sl": t["sl"],
                       "exit": t["exit"], "R": round(t["R"], 4), "reason": t["reason"],
                       "or_hi": t["or_hi"], "or_lo": t["or_lo"], "risk": t["risk"], "k": k,
                       "tp": t.get("tp"), "rr": m.get("rr"),
                       "mode": self.cfg["mode"], "recorded_at": datetime.now(RO).isoformat(timespec="seconds")}
                sz = ev.get(f"{key}|size{sfx}") or self.virtual_size(sym, t)
                if sz.get("lots"):
                    rec.update(lots=sz["lots"], risk_money=round(sz["risk_money"], 4),
                               pnl_money_est=round(t["R"] * sz["risk_money"], 4), currency=sz["currency"])
                with open(TRADES_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                icon = "✅" if t["R"] > 0 else "❌"
                msg = (f"{icon} <b>Daily SHADOW — {sym} {side}{nr} închis</b> ({t['reason']})\n"
                       f"{t['entry']:.5g} → {t['exit']:.5g} = <b>{t['R']:+.2f}R</b> (virtual)")
                log.info(msg.replace("<b>", "").replace("</b>", ""))
                _notify(self.cfg, msg)
        if st.get("reentry_stop") and len(trades) > 1 and "reentry_stop" not in sent:
            sent.append("reentry_stop")
            log.info(f"{sym} {day}: fără alte re-intrări — {st['reentry_stop']}")
        if st["phase"] == "skipped" and "skipped" not in sent:
            sent.append("skipped")
            log.info(f"{sym} {day}: zi sarita — {st.get('reason')}")
        # pastreaza doar ultimele ~120 de chei (mai multe trade-uri / zi)
        if len(ev) > 120:
            for kk in sorted(ev)[:-120]:
                ev.pop(kk, None)
        _write_json(STATE_FILE, self.state)

    def virtual_size(self, sym: str, st: dict) -> dict:
        """Lotul pe care Daily l-ar plasa (aceeasi componenta ca Custom / AI). Shadow: doar estimare."""
        try:
            sz = self.cfg.get("sizing") or {}
            acc = self.mt5.account_info()
            eq = float(getattr(acc, "equity", 0) or 0) if acc else 0.0
            base = ps.capital_base(sz.get("capital_sync_mt5", True), sz.get("capital_usd"), eq)
            cap = base * ps.clamp_fraction(sz.get("fraction", 1.0))
            si = self.mt5.symbol_info(sym)
            r = self._capped(ps.size_by_risk(si, st["entry"], st["sl"], cap, sz.get("risk_pct", 0.01)), si, st["entry"], st["sl"], acc)
            return {**r, "currency": getattr(acc, "currency", "USD") if acc else "USD", "capital": round(cap, 2)}
        except Exception as e:                 # estimarea nu are voie sa opreasca shadow-ul
            return {"lots": 0.0, "risk_money": None, "reason": str(e), "currency": "USD"}

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
        self.cfg = load_config()                        # hot-reload
        now_utc = now_utc or datetime.now(timezone.utc)
        ok_t, why_t = self._ensure_terminal()
        if not ok_t:
            self._err(why_t)
            st = {"running": True, "mode": self.cfg["mode"], "pid": os.getpid(), "markets": [],
                  "heartbeat": datetime.now(RO).isoformat(timespec="seconds"), "errors": self.errors,
                  "execution": {"active": False, "reason": why_t}, "scorecard": scorecard(load_trades())}
            _write_json(STATUS_FILE, st)
            return st
        markets = []
        self.sweep_stale(now_utc)
        for m in self.cfg["markets"]:
            try:
                markets.append(self.process_market(m, now_utc))
            except Exception as e:
                self._err(f"{m.get('symbol')}: {type(e).__name__}: {e}")
                markets.append({"symbol": m.get("symbol"), "phase": "error", "reason": str(e)})
        trades = load_trades()
        ex_ok, ex_why = self.exec_state()
        status = {"running": True, "mode": self.cfg["mode"], "pid": os.getpid(),
                  "execution": {"active": ex_ok, "reason": ex_why},
                  "heartbeat": datetime.now(RO).isoformat(timespec="seconds"),
                  "server_offset_h": None if self.server_offset_s is None else self.server_offset_s / 3600,
                  "account": self.account, "markets": markets, "scorecard": scorecard(trades),
                  "sizing": self.cfg.get("sizing"),
                  "errors": self.errors}
        _write_json(STATUS_FILE, status)
        return status


def run() -> None:
    _setup_logging()
    # crash-uri native (ex. modulul MetaTrader5) -> traceback in fisier, nu dispar fara urma
    try:
        faulthandler.enable(open(os.path.join(DATA_DIR, "crash.log"), "a", encoding="utf-8"))
    except Exception:
        pass
    try:
        _run()
    except BaseException as e:                       # inclusiv SystemExit / KeyboardInterrupt
        log.exception(f"Daily Engine s-a oprit neasteptat: {type(e).__name__}: {e}")
        raise


def _run() -> None:
    if not _acquire_single_instance():
        log.error("Daily Engine ruleaza deja (mutex detinut) — a doua instanta NU porneste.")
        return
    save_default_config()
    cfg = load_config()
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    _write_json(DESIRED_FILE, {"running": True, "since": datetime.now(RO).isoformat(timespec="seconds"),
                               "pid": os.getpid()})
    eng = DailyEngine()
    mode_txt = "EXECUȚIE (ordine reale, dacă contul o permite)" if cfg["mode"] == "execute" else "SHADOW (fără ordine reale)"
    log.info(f"Daily Engine pornit — mod {mode_txt}")
    _notify(cfg, f"🧪 <b>Daily Engine pornit</b> — mod {mode_txt}\n"
                 + "\n".join(f"• {m['symbol']}: {m.get('label', '')}" for m in cfg["markets"] if m.get("enabled", True)))
    while not eng.connect():
        _write_json(STATUS_FILE, {"running": True, "mode": "shadow", "pid": os.getpid(),
                                  "heartbeat": datetime.now(RO).isoformat(timespec="seconds"),
                                  "markets": [], "errors": eng.errors, "scorecard": scorecard(load_trades())})
        time.sleep(60)
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
        time.sleep(eng.cfg.get("poll_seconds", 15))
