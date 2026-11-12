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
from special_engine.config import COSTS, DATA_DIR, NOISE_MARKETS, ORB_MARKETS, load_config, market_mode  # noqa: E402
from special_engine import executor as X  # noqa: E402
import position_sizing as ps  # noqa: E402
from special_engine.strategies import NOISE_LOOKBACK, noise_day, noise_moves, nr_flag, orb_day  # noqa: E402

os.makedirs(DATA_DIR, exist_ok=True)
STATUS_FILE = os.path.join(DATA_DIR, "status.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
DESIRED_FILE = os.path.join(DATA_DIR, "desired_running.json")   # sters DOAR de Stop-ul din UI (watchdog)
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


def _notify(cfg: dict, text: str, force: bool = False) -> None:
    """Telegram (in fundal). force=True: evenimente cu BANI REALI (ordine, inchideri, blocari) — trimise mereu."""
    if not force and not cfg.get("notify_telegram", True):
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
            ctx = {"kind": "ORB", "r": r, "b": b, "or_minutes": orm, "entry": ent}
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
            ctx = {"kind": "NOISE", "r": r, "b": b}
            trades = [{"entry_t": str(t["entry_t"]), "exit_t": str(t["exit_t"]), "d": int(t["d"]), "entry": float(t["entry"]),
                       "exit": float(t["exit"]), "R": float(t["R"]), "why": t["why"]} for t in r["trades"]]
            st = {**base, "phase": "in_position" if r["open"] else ("closed" if done else "watching")}
            if r["open"]:
                st.update(side=int(r["open"]["d"]), entry=float(r["open"]["entry"]), open_R=float(r["open"]["open_R"]))
        # PAUZA pe piata: fara intrari NOI (nici virtuale, nici reale) de la momentul pauzei; ce era deschis ramane
        cut = self._pause_cut(sym, tz)
        if cut is not None:
            trades = [t for t in trades if pd.Timestamp(t["entry_t"]) < cut]
            if st.get("phase") == "in_position" and pd.Timestamp(self._open_entry_t(ctx, today)) >= cut:
                st = {**{k: v for k, v in st.items() if k not in ("side", "entry", "sl", "open_R")}, "phase": "paused"}
        mode = market_mode(self.cfg, sym)
        st["mode"] = mode
        ok_x, why_x = self.exec_state(sym)
        st["execution"] = {"active": ok_x, "reason": why_x}
        st["trades_today"] = len(trades)
        st["R_today"] = round(sum(t["R"] for t in trades), 3)
        try:
            self._execute(comp, sym, today, st, ctx, now_loc, w_end, done, len(trades))
        except Exception as e:                                    # noqa: BLE001 — executia nu opreste shadow-ul
            log.exception(f"{comp} executie")
            st.setdefault("exec_error", f"{type(e).__name__}: {e}")
        self._record(comp, strategy, sym, str(today.date()), trades)
        pos, _ = X.own(self.mt5, sym) if hasattr(self.mt5, "positions_get") else ([], [])
        st["real_positions"] = [{"ticket": p.ticket, "side": "LONG" if p.type == 0 else "SHORT", "volume": p.volume,
                                 "price": p.price_open, "sl": p.sl, "profit": getattr(p, "profit", None)}
                                for p in pos if (p.comment or "").startswith(X.day_prefix(sym, today))]
        return st

    # ── EXECUTIE REALA (per piata: Live + cont permis) ──────────────────────────────────────────────────────
    def exec_state(self, sym: str) -> tuple[bool, str]:
        mode = market_mode(self.cfg, sym)
        if mode == "pause":
            return False, "piață pe PAUZĂ (fără intrări noi)"
        if mode != "live":
            return False, "piață în SHADOW (fără ordine reale)"
        from live_guard import live_allowed
        return X.execution_allowed(self.mt5, live_allowed)

    def _pause_cut(self, sym: str, tz: str):
        m = (self.cfg.get("markets") or {}).get(sym) or {}
        if m.get("mode") != "pause":
            return None
        try:
            at = datetime.fromisoformat(m["paused_at"]) if m.get("paused_at") else None
        except (TypeError, ValueError):
            at = None
        if at is None:
            return pd.Timestamp.min
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        return pd.Timestamp(at.astimezone(ZoneInfo(tz)).replace(tzinfo=None))

    @staticmethod
    def _open_entry_t(ctx: dict, today) -> str:
        r = ctx["r"]
        if ctx["kind"] == "NOISE":
            return str((r.get("open") or {}).get("entry_t") or today)
        return str(today + pd.Timedelta(minutes=int(r.get("entry_min") or 0)))

    def _capital(self, acc) -> float:
        c = self.cfg.get("capital") or {}
        eq = float(getattr(acc, "equity", 0) or 0) if acc else 0.0
        return ps.capital_base(c.get("capital_sync_mt5", True), c.get("capital_usd"), eq) * ps.clamp_fraction(c.get("fraction", 1.0))

    def _note(self, sym: str, text: str, important: bool = True, audit: str | None = None) -> None:
        msg = f"🟢 <b>Special EXECUȚIE — {sym}</b>\n{text}"
        log.info(msg.replace("<b>", "").replace("</b>", ""))
        if important:
            _notify(self.cfg, msg, force=True)
        if audit:
            try:
                from api import audit_log
                audit_log.record("special", audit, text.replace("\n", " · "), market=sym, source="engine")
            except Exception:
                pass

    def _size(self, sym: str, side: int, entry: float, sl: float) -> tuple[float, str, float]:
        """(loturi, motiv daca 0 / redus, risc in bani). Lantul: risc% × capitalul engine-ului → limita globala de
        risc / trade → riscul TOTAL deschis al engine-ului → marja totala a contului."""
        info, acc = self.mt5.symbol_info(sym), self.mt5.account_info()
        if info is None or acc is None:
            return 0.0, "symbol_info / cont indisponibil", 0.0
        cap = self._capital(acc)
        r = ps.size_by_risk(info, entry, sl, cap, self.cfg["risk_pct"])
        lots, risk = float(r.get("lots") or 0.0), float(r.get("risk_money") or 0.0)
        if not lots:
            return 0.0, r.get("reason") or "lot 0", 0.0
        from live.global_guard import risk_cap_pct
        gcap = risk_cap_pct()
        if gcap:
            lots2, why = ps.apply_risk_cap(info, lots, entry, sl, float(acc.equity), gcap)
            if not lots2:
                return 0.0, why, 0.0
            if lots2 != lots:
                risk, lots = risk * lots2 / lots, lots2
        pos, ords = X.own(self.mt5)
        if len(pos) + len(ords) >= self.cfg["max_positions"]:
            return 0.0, f"maxim {self.cfg['max_positions']} poziții Special deschise", 0.0
        open_risk = sum(X.position_risk_money(self.mt5, p) for p in pos)
        room = self.cfg["max_open_risk_pct"] * cap - open_risk
        if risk > room + 1e-9:
            return 0.0, (f"riscul total deschis Special ar depăși {self.cfg['max_open_risk_pct'] * 100:.1f}% din capital "
                         f"({open_risk:.2f} deschis + {risk:.2f} nou > {self.cfg['max_open_risk_pct'] * cap:.2f})"), 0.0
        try:
            otype = self.mt5.ORDER_TYPE_BUY if side == 1 else self.mt5.ORDER_TYPE_SELL
            need = self.mt5.order_calc_margin(otype, sym, lots, entry)
            mroom = self.cfg["max_margin_pct"] / 100.0 * float(acc.equity) - float(getattr(acc, "margin", 0.0) or 0.0)
            if need is not None and need > mroom:
                return 0.0, (f"marjă insuficientă: {need:.2f} necesar, loc {max(0.0, mroom):.2f} "
                             f"(limita {self.cfg['max_margin_pct']:.0f}% din equity, cu toate pozițiile contului)"), 0.0
        except Exception:
            pass
        return lots, "", risk

    def _guards(self, sym: str, now_loc) -> tuple[bool, str]:
        from live import global_guard
        ok, why = global_guard.check_open(self.mt5, "special", sym)
        if not ok:
            return False, why
        fc, why = global_guard.friday_close_now(sym, now_loc.astimezone(timezone.utc))
        if fc:
            return False, why
        if global_guard.load_settings()["news_protection"]["enabled"]:
            try:
                from live.news_guard import _fetch_forexfactory
                if global_guard.news_window_active(sym, _fetch_forexfactory()):
                    return False, "fereastră de știri (Setări Globale)"
            except Exception:
                pass
        return True, ""

    def _execute(self, comp: str, sym: str, today, st: dict, ctx: dict, now_loc, w_end, done: bool, k_open: int) -> None:
        if not hasattr(self.mt5, "positions_get"):
            return
        ev = self.state.setdefault("events", {})
        day = today.date()
        pre = X.day_prefix(sym, day)
        pos, ords = X.own(self.mt5, sym)
        pos_t = [p for p in pos if (p.comment or "").startswith(pre)]
        ord_t = [o for o in ords if (o.comment or "").startswith(pre)]
        if not pos_t and not ord_t and market_mode(self.cfg, sym) != "live":
            return                                            # SHADOW / PAUZA fara expunere reala: nimic de facut
        # 1) final de sesiune sau inchiderea de vineri: anuleaza + inchide tot (niciodata peste noapte / weekend)
        from live.global_guard import friday_close_now
        fc, fc_why = friday_close_now(sym, now_loc.astimezone(timezone.utc))
        if done or now_loc >= w_end or fc:
            for o in ord_t:
                X.cancel(self.mt5, o)
            for p in pos_t:
                ok, res = X.close(self.mt5, p)
                self._note(sym, f"închis — {'final de sesiune' if not fc else fc_why} "
                                f"({'ok' if ok else 'EȘUAT ' + str(getattr(res, 'retcode', res))})", audit="close")
            return
        virtual_open = st.get("phase") == "in_position"
        # 2) iesirea VIRTUALA s-a produs (banda / VWAP, SL, EOD) → pozitia reala se inchide si ea
        if pos_t and not virtual_open and st.get("phase") != "paused":
            for p in pos_t:
                ok, res = X.close(self.mt5, p)
                self._note(sym, f"închis după ieșirea strategiei ({'ok' if ok else 'EȘUAT ' + str(getattr(res, 'retcode', res))})",
                           audit="close")
            for o in ord_t:
                X.cancel(self.mt5, o)
            return
        # 2b) OCO (ORB breakout): o margine umpluta → cealalta anulata
        if pos_t and ord_t:
            for o in ord_t:
                X.cancel(self.mt5, o)
            return
        # 3) pauza: ordinele de intrare neactivate se anuleaza; pozitiile raman (SL, final de sesiune)
        if market_mode(self.cfg, sym) == "pause":
            for o in ord_t:
                X.cancel(self.mt5, o)
            return
        if pos_t or ord_t:
            return
        ok_x, why_x = self.exec_state(sym)
        if not ok_x:
            return
        r, b = ctx["r"], ctx["b"]
        if ctx["kind"] == "ORB":
            key = f"{day}|{comp}|placed0"
            if ev.get(key):
                return
            n_or = ctx["or_minutes"] // 5
            last_i = len(b) - 1
            fresh_wait = st.get("phase") == "waiting_entry" and r.get("or_hi") is not None and len(b) <= n_or + 1
            fresh_pos = virtual_open and int(r.get("entry_bar", -9)) >= last_i - 1
            if not (fresh_wait or fresh_pos):
                if virtual_open:
                    ev[key] = "stale"                       # restart tarziu: semnalul e vechi → niciun ordin
                return
            ok_g, why_g = self._guards(sym, now_loc)
            if not ok_g:
                ev[key] = "blocked"
                self._note(sym, f"BLOCAT: {why_g}", audit="blocked")
                return
            hi, lo = float(r["or_hi"]), float(r["or_lo"])
            tick = self.mt5.symbol_info_tick(sym)
            if tick is None:
                return
            results = []
            if ctx["entry"] == "direction":
                o0, c_last = float(b["open"].iloc[0]), float(b["close"].iloc[n_or - 1])
                if c_last == o0:
                    ev[key] = "skip"
                    return
                side = 1 if c_last > o0 else -1
                entry, sl = (tick.ask, lo) if side == 1 else (tick.bid, hi)
                lots, why, risk = self._size(sym, side, entry, sl)
                if not lots:
                    ev[key] = "skip"
                    self._note(sym, f"nu plasez: {why}", audit="blocked")
                    return
                ok_o, res = X.place_market(self.mt5, sym, side, lots, sl, X.tag(sym, day, 0))
                results.append(("LONG" if side == 1 else "SHORT", lots, risk, ok_o, res))
            else:
                for side, lvl, sl in ((1, hi, lo), (-1, lo, hi)):
                    lots, why, risk = self._size(sym, side, lvl, sl)
                    if not lots:
                        self._note(sym, f"{'BUY' if side == 1 else 'SELL'}_STOP nu se plasează: {why}", audit="blocked")
                        continue
                    beyond = (side == 1 and tick.ask >= lvl) or (side == -1 and tick.bid <= lvl)
                    if beyond:
                        ok_o, res = X.place_market(self.mt5, sym, side, lots, sl, X.tag(sym, day, 0))
                        results.append(("LONG piață (gap)" if side == 1 else "SHORT piață (gap)", lots, risk, ok_o, res))
                        break
                    ok_o, res = X.place_stop(self.mt5, sym, side, lvl, lots, sl, X.tag(sym, day, 0))
                    results.append((("BUY_STOP" if side == 1 else "SELL_STOP") + f" @ {lvl:.5g}", lots, risk, ok_o, res))
            ev[key] = "yes" if any(x[3] for x in results) else ("failed" if results else "skip")
        else:
            op = r.get("open")
            if not virtual_open or not op:
                return
            key = f"{day}|{comp}|placed{k_open}"
            if ev.get(key):
                return
            if pd.Timestamp(op["entry_t"]) < today + pd.Timedelta(minutes=int(b["mins"].iloc[-1])):
                ev[key] = "stale"                           # semnalul nu e pe ultima bara inchisa (restart tarziu)
                return
            ok_g, why_g = self._guards(sym, now_loc)
            if not ok_g:
                ev[key] = "blocked"
                self._note(sym, f"BLOCAT: {why_g}", audit="blocked")
                return
            tick = self.mt5.symbol_info_tick(sym)
            if tick is None:
                return
            side = int(op["d"])
            entry = tick.ask if side == 1 else tick.bid
            sl = entry - side * self.cfg["noise_stop_mult"] * float(op["unit"])
            lots, why, risk = self._size(sym, side, entry, sl)
            if not lots:
                ev[key] = "skip"
                self._note(sym, f"nu plasez: {why}", audit="blocked")
                return
            ok_o, res = X.place_market(self.mt5, sym, side, lots, sl, X.tag(sym, day, k_open))
            results = [("LONG" if side == 1 else "SHORT", lots, risk, ok_o, res)]
            ev[key] = "yes" if ok_o else "failed"
        cur = getattr(self.mt5.account_info(), "currency", "USD")
        lines = [f"{'✅' if ok_o else '❌'} {what} · {lots} loturi · SL atașat · risc {risk:.2f} {cur}"
                 + ("" if ok_o else f" — {getattr(res, 'retcode', res)}") for what, lots, risk, ok_o, res in results]
        self._note(sym, f"ORDINE REALE ({why_x}) — {comp}\n" + "\n".join(lines),
                   audit="order" if all(x[3] for x in results) else "rejected")
        _write(STATE_FILE, self.state)

    def sweep_stale(self, now_utc: datetime) -> None:
        """Orice pozitie / ordin Special din ALTA zi decat ziua bursei lui → inchis / anulat (restart peste noapte,
        sesiune ratata). Ruleaza mereu, in orice mod — niciodata o pozitie peste noapte."""
        if not hasattr(self.mt5, "positions_get"):
            return
        try:
            pos, ords = X.own(self.mt5)
        except Exception:
            return
        def stale(x) -> bool:
            tbl = ORB_MARKETS.get(x.symbol) or NOISE_MARKETS.get(x.symbol)
            if not tbl:
                return False
            day = now_utc.astimezone(ZoneInfo(tbl[0])).date()
            return not (x.comment or "").startswith(X.day_prefix(x.symbol, day))
        for o in ords:
            if stale(o):
                X.cancel(self.mt5, o)
                self._note(o.symbol, f"ordin rămas din altă zi anulat ({o.comment})", audit="close")
        for p_ in pos:
            if stale(p_):
                ok, _ = X.close(self.mt5, p_)
                self._note(p_.symbol, f"poziție rămasă din altă zi închisă ({p_.comment}) — {'ok' if ok else 'EȘUAT'}",
                           audit="close")

    def _record(self, comp, strategy, sym, day, trades) -> None:
        ev = self.state.setdefault("events", {})
        new = []
        for k, t in enumerate(trades):
            key = f"{day}|{comp}|{k}"
            if key in ev:
                continue
            ev[key] = True
            acc = self.mt5.account_info()
            risk_money = self._capital(acc) * self.cfg["risk_pct"]
            placed = ev.get(f"{day}|{comp}|placed{k}")
            rec = {"day": day, "strategy": strategy, "comp": comp, "symbol": sym, "k": k, **t,
                   "mode": "execute" if placed == "yes" else "shadow", "market_mode": market_mode(self.cfg, sym),
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
        self.sweep_stale(now_utc)
        rows, errors = [], []
        for comp, strat in self.components():
            try:
                rows.append(self.process(comp, strat, now_utc))
            except Exception as e:                    # noqa: BLE001 — o componenta nu opreste restul
                errors.append(f"{comp}: {type(e).__name__}: {e}")
                rows.append({"comp": comp, "strategy": strat, "phase": "error", "reason": str(e)})
        self.daily_summary(now_utc)
        acc = self.mt5.account_info() if hasattr(self.mt5, "account_info") else None
        cap = self._capital(acc)
        pos_all, ord_all = X.own(self.mt5) if hasattr(self.mt5, "positions_get") else ([], [])
        open_risk = sum(X.position_risk_money(self.mt5, p) for p in pos_all)
        st = {"updated": now_utc.isoformat(timespec="seconds"), "mode": self.cfg["mode"], "pid": os.getpid(),
              "markets": {sym: market_mode(self.cfg, sym) for sym in {c.split(":")[1] for c, _ in self.components()}},
              "capital": {"account_equity": round(float(getattr(acc, "equity", 0) or 0), 2) if acc else None,
                          "engine_capital": round(cap, 2), "risk_per_trade": round(cap * self.cfg["risk_pct"], 2),
                          "open_risk": round(open_risk, 2), "open_risk_limit": round(cap * self.cfg["max_open_risk_pct"], 2),
                          "available_risk": round(max(0.0, cap * self.cfg["max_open_risk_pct"] - open_risk), 2),
                          "margin_used": round(float(getattr(acc, "margin", 0) or 0), 2) if acc else None,
                          "positions": len(pos_all), "orders": len(ord_all), "max_positions": self.cfg["max_positions"]},
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
    _write(DESIRED_FILE, {"running": True, "since": datetime.now(RO).isoformat(timespec="seconds"), "pid": os.getpid()})
    modes = ", ".join(f"{s}: {m['mode'].upper()}" for s, m in (cfg.get("markets") or {}).items()) or "toate piețele SHADOW"
    log.info(f"Special Engine pornit — {modes}")
    _notify(cfg, f"🧪 <b>Special Engine pornit</b> — {modes}\nA: portofoliu adaptiv NR4 · B: noise area "
                 f"{cfg['strategy_b']['symbol']} · risc {cfg['risk_pct'] * 100:.1f}% / trade, "
                 f"max {cfg['max_open_risk_pct'] * 100:.1f}% deschis", force=True)
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
