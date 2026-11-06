"""
Special Engine — SHADOW (zero ordine). Doua strategii, evaluate separat si impreuna:
  A  portofoliu adaptiv walk-forward (ORB + NOISE pe 10 piete), doar in zilele NR4; componentele = selectia
     trimestriala (special_engine.data.select — doar TRECUT); recalculata singura la inceputul fiecarui trimestru
  B  noise area pe USTEC (Zarattini et al. 2024), fara selectie
Fiecare iteratie recalculeaza ziua de la zero din barele M5 INCHISE (functii pure = cercetarea; restart-safe).
Trade-urile virtuale inchise → data/special_engine/trades.jsonl (o singura data: state.json::events); starea pe
componenta → status.json. MT5 doar CITIRE. Rulare: python -m special_engine (sau din tab-ul Special Engine).
"""
from __future__ import annotations

import faulthandler
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from daily_engine.config import hm_to_min  # noqa: E402
from special_engine import data as D  # noqa: E402
from special_engine.config import COSTS, DATA_DIR, NOISE_MARKETS, ORB_MARKETS, load_config  # noqa: E402
from special_engine.strategies import NOISE_LOOKBACK, noise_day, noise_moves, nr_flag, orb_day  # noqa: E402

os.makedirs(DATA_DIR, exist_ok=True)
STATUS_FILE = os.path.join(DATA_DIR, "status.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
TRADES_FILE = os.path.join(DATA_DIR, "trades.jsonl")
SELECTION_FILE = os.path.join(DATA_DIR, "selection.json")
LOG_FILE = os.path.join(DATA_DIR, "engine.log")
PID_FILE = os.path.join(DATA_DIR, "special_engine.pid")
RO = ZoneInfo("Europe/Bucharest")
log = logging.getLogger("special_engine")


def _setup_logging() -> None:
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    h = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    s = logging.StreamHandler(sys.stdout)
    s.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    log.addHandler(s)


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write(path, data, critical=True):
    from safe_io import write_json_atomic
    write_json_atomic(path, data, critical=critical)


def _notify(cfg: dict, text: str) -> None:
    if not cfg.get("notify_telegram", True):
        return

    def _send():
        try:
            from api.telegram import send_message
            send_message(text)
        except Exception:
            pass
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


_TZ_LABEL = {"America/New_York": "NY", "Europe/Berlin": "Frankfurt", "Europe/London": "Londra",
             "Asia/Tokyo": "Tokyo", "Australia/Sydney": "Sydney"}
LIVE_GRACE_MIN = 20          # un trade observat live e inregistrat la cateva minute dupa iesire (bara inchisa + poll)


def annotate_trade(t: dict, app_tz: str = "Europe/Bucharest") -> dict:
    """Doar AFISARE (pur): momentele reale ale trade-ului in ora bursei SI in fusul aplicatiei + daca a fost
    OBSERVAT live sau RECONSTITUIT (engine-ul recalculeaza ziua din barele inchise, deci la o pornire tarzie
    inregistreaza retroactiv trade-urile de peste zi).
    entry_t / exit_t din jurnal = inceputul lumanarii M5 (ora bursei). NOISE decide la INCHIDEREA lumanarii →
    momentul = +5 min; ORB: intrarea in lumanare (stop atins / open), iesirea EOD la inchiderea ultimei lumanari."""
    from zoneinfo import ZoneInfo
    out = dict(t)
    try:
        sym = t.get("symbol")
        kind = str(t.get("comp", "")).split(":")[0]
        tbl = NOISE_MARKETS if kind == "NOISE" else ORB_MARKETS
        tz_name = tbl[sym][0]
        tz, atz = ZoneInfo(tz_name), ZoneInfo(app_tz)
        e = pd.Timestamp(t["entry_t"]).to_pydatetime()
        x = pd.Timestamp(t["exit_t"]).to_pydatetime()
        e += timedelta(minutes=5) if kind == "NOISE" else timedelta(0)
        x += timedelta(minutes=5) if (kind == "NOISE" or t.get("why") == "EOD") else timedelta(0)
        e, x = e.replace(tzinfo=tz), x.replace(tzinfo=tz)
        out.update(exch_tz=tz_name, exch_label=_TZ_LABEL.get(tz_name, tz_name.split("/")[-1]),
                   entry_exch=f"{e:%H:%M}", exit_exch=f"{x:%H:%M}",
                   entry_app=f"{e.astimezone(atz):%Y-%m-%d %H:%M}", exit_app=f"{x.astimezone(atz):%Y-%m-%d %H:%M}",
                   app_label="DE" if app_tz == "Europe/Berlin" else "RO")
        logged = datetime.fromisoformat(t["logged_at"]) if t.get("logged_at") else None
        seen = datetime.fromisoformat(t["seen_since"]) if t.get("seen_since") else None
        if logged is None:
            out["live"] = None
        else:
            late = logged > x.astimezone(timezone.utc) + timedelta(minutes=LIVE_GRACE_MIN)
            before_start = seen is not None and seen > e.astimezone(timezone.utc)
            out["live"] = not (late or before_start)
            out["recorded_app"] = f"{logged.astimezone(atz):%Y-%m-%d %H:%M}"
            if late:
                out["live_note"] = (f"reconstituit: înregistrat la {out['recorded_app']} {out['app_label']}, "
                                    "după închiderea trade-ului (engine-ul nu rula în timpul lui)")
            elif before_start:
                out["live_note"] = "parțial: engine-ul a pornit după intrare (intrarea nu a fost văzută live)"
            else:
                out["live_note"] = "observat live"
    except Exception:            # afisarea nu are voie sa strice lista
        pass
    return out


def scorecard(trades: list[dict]) -> dict:
    def sc(ts):
        rs = [t["R"] for t in ts]
        n = len(rs)
        eq = np.cumsum(rs) if rs else np.array([0.0])
        est = [t["pnl_money_est"] for t in ts if t.get("pnl_money_est") is not None]
        return {"trades": n, "wins": sum(1 for r in rs if r > 0), "losses": sum(1 for r in rs if r < 0),
                "total_R": round(float(sum(rs)), 3), "expectancy_R": round(float(np.mean(rs)), 3) if n else None,
                "win_rate": round(sum(1 for r in rs if r > 0) / n, 3) if n else None,
                "max_dd_R": round(float((eq - np.maximum.accumulate(eq)).min()), 2) if n else 0.0,
                "pnl_money_est": round(sum(est), 2) if est else None}
    return {"total": sc(trades), "A": sc([t for t in trades if t["strategy"] == "A"]),
            "B": sc([t for t in trades if t["strategy"] == "B"]),
            "by_component": {c: sc([t for t in trades if t["comp"] == c]) for c in sorted({t["comp"] for t in trades})}}


def quarter_start(now_utc: datetime) -> pd.Timestamp:
    d = now_utc.date()
    return pd.Timestamp(d.year, 3 * ((d.month - 1) // 3) + 1, 1)


def compute_selection(mt5, cfg: dict, q_start: pd.Timestamp, progress=None) -> dict:
    """Selectia strategiei A pentru trimestrul `q_start`, recalculata din MT5 cu ACELEASI functii ca cercetarea."""
    a = cfg["strategy_a"]
    rows, ranges, d1s = [], {}, {}
    for sym, (tz, op, last) in ORB_MARKETS.items():
        d = D.fetch_m5(mt5, sym)
        if d.empty:
            continue
        pt = float(mt5.symbol_info(sym).point)
        slip, comm = COSTS[sym]
        rows += D.orb_history(d, sym, tz, op, last, slip, comm, pt)
        if sym in NOISE_MARKETS:
            tz2, op2, cl2 = NOISE_MARKETS[sym]
            rows += D.noise_history(d, sym, tz2, op2, cl2, slip + comm, pt)
        ranges[sym] = [str(d.time.min().date()), str(d.time.max().date())]
        d1s[sym] = D.fetch_d1(mt5, sym)
        if progress:
            progress(f"istoric {sym}: {len(rows)} trade-uri cumulat")
    t = pd.DataFrame(rows)
    if t.empty:
        return {"quarter": str(q_start.date()), "components": [], "error": "fara istoric MT5"}
    if a["nr_filter"]:
        parts = []
        for s, g in t.groupby("sym"):
            f = D.nr_series(d1s[s], a["nr_filter"]).reindex(g.entry_t.dt.normalize()).to_numpy() if s in d1s else None
            parts.append(g[f == True] if f is not None else g.iloc[0:0])   # noqa: E712
        t = pd.concat(parts)
    comps, table = D.select(t, q_start, a)
    return {"quarter": str(q_start.date()), "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "components": comps, "params": a, "data_range": ranges,
            "table": [{"comp": c, "n": int(r["count"]), "mean_R": round(float(r["mean"]), 4), "t": round(float(r["t"]), 2),
                       "selected": c in comps} for c, r in table.head(40).iterrows()]}


class SpecialEngine:
    def __init__(self, mt5_module=None):
        self.mt5 = mt5_module
        self.cfg = load_config()
        self.state = _read(STATE_FILE, {"events": {}})
        self.selection = _read(SELECTION_FILE, {})
        self._sel_thread = None
        self._sel_note = ""
        self._d1 = {}           # (sym, day) → D1
        self._hist = {}         # (sym, day) → (sigma, prev_close) pentru NOISE
        self.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")   # live vs reconstituit

    def connect(self) -> bool:
        if self.mt5 is None:
            import MetaTrader5 as m
            self.mt5 = m
        return bool(self.mt5.initialize())

    # ── selectia trimestriala (in fundal: dureaza cateva minute) ─────────────────────────────────────────────
    def ensure_selection(self, now_utc: datetime) -> None:
        q = quarter_start(now_utc)
        if self.selection.get("quarter") == str(q.date()) and "components" in self.selection:
            return
        if self._sel_thread and self._sel_thread.is_alive():
            return

        def job():
            try:
                self._sel_note = "calculez selecția trimestrului…"
                sel = compute_selection(self.mt5, self.cfg, q, progress=lambda s: setattr(self, "_sel_note", s))
                old = self.selection.get("components")
                self.selection = sel
                _write(SELECTION_FILE, sel)
                self._sel_note = ""
                log.info(f"selectie {sel['quarter']}: {sel.get('components')}")
                if old != sel.get("components"):
                    _notify(self.cfg, "🧪 <b>Special Engine SHADOW — selecția trimestrului " + sel["quarter"] + "</b>\n"
                            + ("\n".join(f"• {c}" for c in sel.get("components", [])) or "nicio componentă cu edge") +
                            "\n<i>Strategia A tranzacționează (virtual) doar aceste componente, doar în zilele NR4.</i>")
            except Exception as e:                    # noqa: BLE001
                self._sel_note = f"selecția a eșuat: {type(e).__name__}: {e}"
                log.exception("selectie esuata")
        self._sel_thread = threading.Thread(target=job, daemon=True)
        self._sel_thread.start()

    # ── date ─────────────────────────────────────────────────────────────────────────────────────────────────
    def _d1_for(self, sym: str, day) -> pd.DataFrame:
        k = (sym, str(day))
        if k not in self._d1:
            self._d1 = {kk: v for kk, v in self._d1.items() if kk[1] == str(day)}
            self._d1[k] = D.fetch_d1(self.mt5, sym, 40)
        return self._d1[k]

    def _today_bars(self, sym, tz, op, end, inclusive, now_utc) -> pd.DataFrame:
        r = self.mt5.copy_rates_from_pos(sym, self.mt5.TIMEFRAME_M5, 0, 400)
        d = D.rates_df(r) if r is not None and len(r) else pd.DataFrame()
        if d.empty:
            return d
        s, _, _ = D.session(d, tz, op, end, inclusive)
        now_loc = now_utc.astimezone(ZoneInfo(tz)).replace(tzinfo=None)
        today = pd.Timestamp(now_loc.date())
        s = s[s["day"] == today]
        # doar bare INCHISE: inceputul barei + 5 min <= acum
        closed = s["loc"].dt.tz_localize(None) + pd.Timedelta(minutes=5) <= pd.Timestamp(now_loc)
        return s[closed].reset_index(drop=True)

    def _noise_prev(self, sym, tz, op, cl, today) -> tuple | None:
        k = (sym, str(today))
        if k not in self._hist:
            self._hist = {kk: v for kk, v in self._hist.items() if kk[1] == str(today)}
            d = D.fetch_m5(self.mt5, sym, 9000)
            days, slots, mv, om, cm = D.noise_days(d, tz, op, cl)
            prev = [(dd, g, m_) for (dd, g), m_ in zip(days, mv) if dd < today]
            if len(prev) < NOISE_LOOKBACK:
                self._hist[k] = None
            else:
                sig = np.nanmean(np.array([m_ for _, _, m_ in prev[-NOISE_LOOKBACK:]]), axis=0)
                self._hist[k] = (sig, float(prev[-1][1]["close"].iat[-1]), slots, om, cm)
        return self._hist[k]

    # ── o componenta ─────────────────────────────────────────────────────────────────────────────────────────
    def process(self, comp: str, strategy: str, now_utc: datetime) -> dict:
        kind, sym = comp.split(":")[0], comp.split(":")[1]
        var = comp.split(":")[2] if kind == "ORB" else None
        tz, op, end = (ORB_MARKETS if kind == "ORB" else NOISE_MARKETS)[sym]
        z = ZoneInfo(tz)
        now_loc = now_utc.astimezone(z)
        today = pd.Timestamp(now_loc.date())
        base = {"comp": comp, "strategy": strategy, "symbol": sym, "kind": kind, "variant": var,
                "window": f"{op}–{end} ({tz.split('/')[-1].replace('_', ' ')})", "day": str(today.date())}
        w_open = datetime.combine(now_loc.date(), datetime.strptime(op, "%H:%M").time(), z)
        w_end = datetime.combine(now_loc.date(), datetime.strptime(end, "%H:%M").time(), z) + \
            (timedelta(minutes=5) if kind == "ORB" else timedelta(0))
        base["window_ro"] = f"{w_open.astimezone(RO):%H:%M}–{w_end.astimezone(RO):%H:%M}"
        if now_loc.weekday() >= 5:
            return {**base, "phase": "weekend"}
        if strategy == "A" and self.cfg["strategy_a"]["nr_filter"]:
            n = self.cfg["strategy_a"]["nr_filter"]
            fl = nr_flag(self._d1_for(sym, today.date()), today, n)
            base["nr"] = fl
            if not fl:
                return {**base, "phase": "no_nr", "reason": f"azi nu e zi NR{n} (range-ul de ieri nu e minimul ultimelor {n} zile)"}
        if now_loc < w_open:
            return {**base, "phase": "waiting_open"}
        done = now_loc >= w_end + timedelta(minutes=2)
        pt = float(self.mt5.symbol_info(sym).point)
        slip, comm = COSTS[sym]
        if kind == "ORB":
            b = self._today_bars(sym, tz, op, end, True, now_utc)
            om = hm_to_min(op)
            if b.empty or b.mins.iloc[0] != om:
                return {**base, "phase": "skipped" if done else "waiting_open", "reason": "fără bara de deschidere"}
            orm, ent = int(var.split("/")[0]), var.split("/")[1]
            if len(b) < orm // 5:
                return {**base, "phase": "forming_or"}
            r = orb_day(*(b[k].to_numpy(float) for k in ("open", "high", "low", "close")),
                        b["spread"].to_numpy(float) * pt, b["mins"].to_numpy(), open_min=om, or_minutes=orm,
                        entry=ent, slip=slip, comm=comm, day_complete=done)
            st = {**base, "phase": r.get("phase"), "reason": r.get("reason")}
            trades = []
            if r.get("phase") == "closed":
                trades = [{"entry_t": str(today + pd.Timedelta(minutes=int(r["entry_min"]))),
                           "exit_t": str(today + pd.Timedelta(minutes=int(r["exit_min"]))), "d": int(r["side"]),
                           "entry": float(r["entry"]), "exit": float(r["exit"]), "R": float(r["R"]), "why": r["reason"]}]
            elif r.get("phase") == "in_position":
                st.update(side=int(r["side"]), entry=float(r["entry"]), sl=float(r["sl"]), open_R=float(r["open_R"]))
            if r.get("or_hi") is not None:
                st.update(or_hi=float(r["or_hi"]), or_lo=float(r["or_lo"]))
        else:
            prev = self._noise_prev(sym, tz, op, end, today)
            if prev is None:
                return {**base, "phase": "skipped", "reason": f"sub {NOISE_LOOKBACK} zile de istoric"}
            sig, prev_close, slots, om, cm = prev
            b = self._today_bars(sym, tz, op, end, False, now_utc)
            if b.empty or b.mins.iloc[0] != om:
                return {**base, "phase": "skipped" if done else "waiting_open", "reason": "fără bara de deschidere"}
            r = noise_day(b, sig=sig, slots=slots, prev_close=prev_close, om=om, cm=cm, point=pt, cost_px=slip + comm,
                          day=today, sym=sym, day_complete=done)
            trades = [{"entry_t": str(t["entry_t"]), "exit_t": str(t["exit_t"]), "d": int(t["d"]), "entry": float(t["entry"]),
                       "exit": float(t["exit"]), "R": float(t["R"]), "why": t["why"]} for t in r["trades"]]
            st = {**base, "phase": "in_position" if r["open"] else ("closed" if done else "watching")}
            if r["open"]:
                st.update(side=int(r["open"]["d"]), entry=float(r["open"]["entry"]), open_R=float(r["open"]["open_R"]))
        st["trades_today"] = len(trades)
        st["R_today"] = round(sum(t["R"] for t in trades), 3)
        self._record(comp, strategy, sym, str(today.date()), trades)
        return st

    def _record(self, comp, strategy, sym, day, trades) -> None:
        ev = self.state.setdefault("events", {})
        new = []
        for k, t in enumerate(trades):
            key = f"{day}|{comp}|{k}"
            if key in ev:
                continue
            ev[key] = True
            acc = self.mt5.account_info()
            risk_money = (getattr(acc, "equity", 0) or 0) * self.cfg["risk_pct"]
            rec = {"day": day, "strategy": strategy, "comp": comp, "symbol": sym, "k": k, **t,
                   "risk_money_est": round(risk_money, 2), "pnl_money_est": round(t["R"] * risk_money, 2),
                   "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "seen_since": self.started_at}
            with open(TRADES_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            new.append(rec)
            log.info(f"[{strategy}] {comp} {day}: {'LONG' if t['d'] == 1 else 'SHORT'} {t['entry']:.5g} → {t['exit']:.5g} "
                     f"= {t['R']:+.2f}R ({t['why']})")
        if new:
            _write(STATE_FILE, self.state)
            if self.cfg.get("notify_trades"):
                for rec in new:
                    _notify(self.cfg, f"🧪 <b>Special SHADOW [{strategy}] {comp}</b>: {'LONG' if rec['d'] == 1 else 'SHORT'} "
                                      f"{rec['entry']:.5g} → {rec['exit']:.5g} = <b>{rec['R']:+.2f}R</b> (virtual)")

    def components(self) -> list[tuple[str, str]]:
        out = []
        if self.cfg["strategy_a"]["enabled"]:
            out += [(c, "A") for c in (self.selection.get("components") or [])]
        if self.cfg["strategy_b"]["enabled"]:
            out.append((f"NOISE:{self.cfg['strategy_b']['symbol']}", "B"))
        return out

    def daily_summary(self, now_utc: datetime) -> None:
        now_ro = now_utc.astimezone(RO)
        day = str(now_ro.date())
        if now_ro.hour < 23 or self.state.get("summary_day") == day:
            return
        self.state["summary_day"] = day
        _write(STATE_FILE, self.state)
        tr = [t for t in load_trades() if t["logged_at"][:10] == str(now_utc.date())]
        sc = scorecard(load_trades())
        _notify(self.cfg, f"🧪 <b>Special Engine SHADOW — ziua {day}</b>\n"
                          f"Azi: {len(tr)} trade-uri virtuale · {sum(t['R'] for t in tr):+.2f}R\n"
                          f"Total: A {sc['A']['trades']} t / {sc['A']['total_R']:+.2f}R · B {sc['B']['trades']} t / "
                          f"{sc['B']['total_R']:+.2f}R")

    def iteration(self, now_utc: datetime | None = None) -> dict:
        now_utc = now_utc or datetime.now(timezone.utc)
        self.cfg = load_config()
        self.ensure_selection(now_utc)
        rows, errors = [], []
        for comp, strat in self.components():
            try:
                rows.append(self.process(comp, strat, now_utc))
            except Exception as e:                    # noqa: BLE001 — o componenta nu opreste restul
                errors.append(f"{comp}: {type(e).__name__}: {e}")
                rows.append({"comp": comp, "strategy": strat, "phase": "error", "reason": str(e)})
        self.daily_summary(now_utc)
        st = {"updated": now_utc.isoformat(timespec="seconds"), "mode": "shadow", "pid": os.getpid(),
              "selection": {k: self.selection.get(k) for k in ("quarter", "computed_at", "components", "params", "error")},
              "selection_note": self._sel_note, "components": rows, "errors": errors[-10:],
              "scorecard": scorecard(load_trades())}
        _write(STATUS_FILE, st, critical=False)
        return st


def _acquire_single_instance() -> bool:
    try:
        import ctypes
        h = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\TradingBot_SpecialEngine_SingleInstance")
        return bool(h) and ctypes.windll.kernel32.GetLastError() != 183
    except Exception:
        return True


def run() -> None:
    _setup_logging()
    faulthandler.enable(open(os.path.join(DATA_DIR, "crash.log"), "a"))
    if not _acquire_single_instance():
        log.warning("alta instanta Special Engine ruleaza deja — ies")
        return
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    eng = SpecialEngine()
    if not eng.connect():
        log.error("MT5 indisponibil")
        return
    cfg = load_config()
    log.info("Special Engine pornit (SHADOW)")
    _notify(cfg, "🧪 <b>Special Engine pornit — SHADOW</b> (zero ordine)\nA: portofoliu adaptiv NR4 · B: noise area "
                 f"{cfg['strategy_b']['symbol']}")
    try:
        while True:
            try:
                eng.iteration()
            except Exception:                         # noqa: BLE001
                log.exception("iteratie esuata")
            time.sleep(load_config()["poll_seconds"])
    finally:
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
