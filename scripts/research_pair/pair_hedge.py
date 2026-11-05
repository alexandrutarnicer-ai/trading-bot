"""
Cercetare — perechea GBPUSD / EURUSD „opusa” (ideea userului, 2026-11-04). DOAR backtest, nu atinge nimic live.

Regulile:
  - Semnalul vine de pe piata de SEMNAL cu regulile Custom Engine (pullback default + Inside Bar + Flag, fara filtru AI,
    fara break-even), parametrii sesiunii din profilul standard (S15 GBPUSD / S1 EURUSD), directie BOTH, TP 2R.
    Semnalele sunt generate de ACELASI engine.portfolio.run_portfolio ca backtestul din Audit; se capteaza momentul
    in care ordinul stop se ACTIVEAZA.
  - In acel minut se deschide la piata un ordin OPUS pe piata de HEDGE. 1R pe hedge = riscul semnalului x ATR(hedge) /
    ATR(semnal) (acelasi timeframe, ultima bara inchisa); risc egal in $ pe ambele.
  - Ambele: SL −1R, TP +2R. O singura pereche deschisa odata. Totul se inchide vineri la 20:00 (fara weekend).
  - Un picior atinge SL → celalalt: pe minus → inchis; 0..1R → SL 0; >= 1R → SL = treapta atinsa (1R, 2R, ...),
    TP = treapta + 2R, mutat continuu pe masura ce profitul creste, plafon 10R.
  - Un picior atinge TP 2R → celalalt: intre −1R si −0,5R → inchis; peste −0,5R → SL la −0,5R, continua normal (TP 2R).
  - Ambele SL in acelasi minut → ambele −1R.
Simulare pe M1 (minut cu minut); in acelasi minut SL inainte de TP (pesimist); profitul celuilalt picior la momentul
evenimentului = inchiderea minutului. Costuri: spread-ul live al contului Standard (GBPUSD 0,9 / EURUSD 0,8 pip) per picior.

Rulare:  python scripts/research_pair/pair_hedge.py            (dupa build_data.py)
Iesire:  data/research_pair/results.json + pairs_<varianta>.csv
"""
import copy
import json
import math
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
DATA = os.path.join(ROOT, "data", "research_pair")

import engine.portfolio as P                                    # noqa: E402
from adapters.csv_source import CsvDataSource                   # noqa: E402
from strategy.preparation import prepare_symbol_tf              # noqa: E402
from strategy.indicators import atr as atr_fn                   # noqa: E402
from m0.session_runner import _apply_session_to_cfg, _build_params, _load_base_cfg   # noqa: E402
from m0.robustness import evaluate_trades                       # noqa: E402

PIP = 0.0001
SPREAD_PIPS = {"GBPUSD": 0.9, "EURUSD": 0.8}                   # live, cont Standard (masurat 2026-11-04)
SESSION_OF = {"GBPUSD": "session15", "EURUSD": "session1"}
OTHER = {"GBPUSD": "EURUSD", "EURUSD": "GBPUSD"}
TFS = [("M1", "M5"), ("M15", "M30"), ("M30", "H1")]
TF_MIN = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60}
CAP_R = 10.0


# ── semnale: exact motorul Custom ───────────────────────────────────────────────────────────────────────────

def session_cfg(sig: str, entry_tf: str, trend_tf: str) -> dict:
    prof = json.load(open(os.path.join(ROOT, "data", "profiles", "standard.json"), encoding="utf-8"))
    s = copy.deepcopy(next(x for x in prof["sessions"] if x["session_key"] == SESSION_OF[sig]))
    s.update(markets=[sig], entry_tf=entry_tf, trend_tf=trend_tf, direction="BOTH",
             r_base=2.0, r_mid=2.0, r_top=2.0, r_max=2.0,
             inside_bar_enabled=True, inside_bar_r_ratio=2.0, flag_enabled=True, flag_r_ratio=2.0,
             break_even_enabled=False, ai_filter_enabled=False, max_concurrent_per_market=1)
    return s


def gen_fills(sig: str, entry_tf: str, trend_tf: str) -> tuple[list[dict], pd.DataFrame]:
    s = session_cfg(sig, entry_tf, trend_tf)
    cfg = _apply_session_to_cfg(_load_base_cfg(), s)
    df = prepare_symbol_tf(CsvDataSource(DATA), sig, cfg, entry_tf, trend_tf)
    params = _build_params(s, {sig: df}, 1e9)    # balanta uriasa: lotul minim nu blocheaza semnale dupa pierderi
    params["spread_pips"] = {sig: SPREAD_PIPS[sig]}
    fills = []
    orig = P.simulate_trade

    def spy(d, j, p, *a, **k):
        res = orig(d, j, p, *a, **k)
        fills.append({"bar_time": d.iloc[j]["time"], "dir": int(p["dir"]), "entry": float(p["entry"]),
                      "sl": float(p["sl"]), "type": p.get("signal_type", "pullback"), "sig_time": p["time"],
                      "solo_engine_R": res["pnl_usd"] / p["risk_usd"] if p.get("risk_usd") else None})
        return res

    P.simulate_trade = spy
    try:
        P.run_portfolio({sig: df}, cfg, params, verbose=False)
    finally:
        P.simulate_trade = orig
    return fills, df


# ── simulare M1 ─────────────────────────────────────────────────────────────────────────────────────────────

def load_m1() -> dict:
    g = pd.read_csv(os.path.join(DATA, "GBPUSD_M1.csv"), parse_dates=["time"])
    e = pd.read_csv(os.path.join(DATA, "EURUSD_M1.csv"), parse_dates=["time"])
    t = pd.Index(sorted(set(g["time"]) | set(e["time"])))
    out = {"time": t.values.astype("datetime64[ns]")}
    for sym, d in (("GBPUSD", g), ("EURUSD", e)):
        d = d.set_index("time").reindex(t)
        c = d["close"].ffill()
        for col in ("open", "high", "low"):          # minut lipsa pe o piata = pret neschimbat
            d[col] = d[col].fillna(c)
        out[sym] = {k: d[k if k != "close" else "close"].ffill().to_numpy(float) for k in ("open", "high", "low")}
        out[sym]["close"] = c.to_numpy(float)
    return out


def friday_deadline(ts: pd.Timestamp) -> pd.Timestamp:
    wd = ts.weekday()
    return (ts.normalize() + pd.Timedelta(days=(4 - wd) % 7)) + pd.Timedelta(hours=20)


class Leg:
    __slots__ = ("sym", "d", "entry", "risk", "sl", "tp", "mode", "R", "exit_i", "why", "cost")

    def __init__(self, sym, d, entry, risk):
        self.sym, self.d, self.entry, self.risk = sym, d, entry, risk
        self.sl, self.tp, self.mode = -1.0, 2.0, "init"
        self.R = None
        self.exit_i = None
        self.why = None
        self.cost = SPREAD_PIPS[sym] * PIP / risk

    def r(self, px):
        return (px - self.entry) * self.d / self.risk

    def bar(self, m, i):
        a = m[self.sym]
        o, h, lo, c = a["open"][i], a["high"][i], a["low"][i], a["close"][i]
        fav = self.r(h if self.d == 1 else lo)
        adv = self.r(lo if self.d == 1 else h)
        return self.r(o), fav, adv, self.r(c)

    def close(self, R, i, why):
        self.R, self.exit_i, self.why = R, i, why

    @property
    def open(self):
        return self.R is None


def step_exit(leg: Leg, o, fav, adv, i):
    """SL / TP pe bara curenta (SL intai). Mod trail: TP doar la plafon, SL urcat dupa bara (continuu)."""
    if adv <= leg.sl:
        leg.close(min(o, leg.sl) if o < leg.sl else leg.sl, i, "sl")
        return "sl"
    tp = CAP_R if leg.mode == "trail" else leg.tp
    if fav >= tp:
        leg.close(max(o, tp) if o > tp else tp, i, "tp" if leg.mode != "trail" else "cap")
        return "tp"
    if leg.mode == "trail":
        k = math.floor(fav)
        if k >= 1 and k > leg.sl:
            leg.sl = float(k)
            leg.tp = min(k + 2.0, CAP_R)
    return None


def on_partner(leg: Leg, ev: str, c_now: float, i: int):
    if ev == "sl":
        if c_now < 0:
            leg.close(c_now, i, "partner_sl_loss")
        else:
            k = math.floor(c_now)
            leg.sl = 0.0 if k < 1 else float(k)
            leg.tp = min((0 if k < 1 else k) + 2.0, CAP_R)
            leg.mode = "trail"
    elif ev == "tp":
        if c_now <= -0.5:
            leg.close(c_now, i, "partner_tp_cut")
        else:
            leg.sl = max(leg.sl, -0.5)
            leg.mode = "normal"


def find_trigger(m, sym, d, entry, t0, tf_min):
    """Primul minut din bara de semnal in care stop-ul se activeaza → (index, pret de umplere)."""
    i0 = int(np.searchsorted(m["time"], np.datetime64(t0)))
    i1 = int(np.searchsorted(m["time"], np.datetime64(t0 + pd.Timedelta(minutes=tf_min))))
    a = m[sym]
    for i in range(i0, max(i1, i0 + 1)):
        if (d == 1 and a["high"][i] >= entry) or (d == -1 and a["low"][i] <= entry):
            o = a["open"][i]
            fill = max(entry, o) if d == 1 else min(entry, o)
            return i, fill
    return i0, entry


def sim(m, fills, sig, atr_ratio_at, tf_min, mode: str) -> list[dict]:
    """mode: pair (regulile userului) / plain (pereche fara reguli) / solo (doar piata de semnal)."""
    hed = OTHER[sig]
    out, busy_until = [], np.datetime64("1970-01-01")
    n = len(m["time"])
    for f in sorted(fills, key=lambda x: x["bar_time"]):
        ti, fill = find_trigger(m, sig, f["dir"], f["entry"], pd.Timestamp(f["bar_time"]), tf_min)
        t_trig = m["time"][ti]
        if t_trig < busy_until:
            continue
        dl = np.datetime64(friday_deadline(pd.Timestamp(t_trig)))
        if t_trig >= dl:
            continue
        risk = abs(f["entry"] - f["sl"])
        legs = [Leg(sig, f["dir"], f["entry"], risk)]
        legs[0].entry = fill                                    # stop executat (gap → pret mai slab)
        legs[0].sl = (f["sl"] - fill) * f["dir"] / risk        # SL / TP la nivelurile ordinului (≈ −1R / +2R)
        legs[0].tp = (f["entry"] + f["dir"] * 2 * risk - fill) * f["dir"] / risk
        if mode != "solo":
            ratio = atr_ratio_at(pd.Timestamp(f["bar_time"]))
            legs.append(Leg(hed, -f["dir"], m[hed]["close"][ti], risk * ratio))
        i = ti + 1
        while i < n and any(lg.open for lg in legs):
            if m["time"][i] >= dl:
                for lg in legs:
                    if lg.open:
                        lg.close(lg.bar(m, i)[0], i, "friday")
                break
            bars = {id(lg): lg.bar(m, i) for lg in legs if lg.open}
            evs = {}
            for lg in legs:
                if lg.open:
                    o, fav, adv, c = bars[id(lg)]
                    ev = step_exit(lg, o, fav, adv, i)
                    if ev:
                        evs[id(lg)] = ev
            if mode == "pair" and len(legs) == 2:
                a, b = legs
                for x, y in ((a, b), (b, a)):
                    if id(x) in evs and y.open and id(y) not in evs and y.mode == "init":
                        on_partner(y, evs[id(x)], bars[id(y)][3], i)
            i += 1
        for lg in legs:
            if lg.open:
                lg.close(lg.bar(m, n - 1)[3], n - 1, "eod")
        end_i = max(lg.exit_i for lg in legs)
        busy_until = m["time"][end_i]
        row = {"entry_t": pd.Timestamp(t_trig), "exit_t": pd.Timestamp(m["time"][end_i]), "dir": f["dir"],
               "type": f["type"]}
        tot = 0.0
        for k, lg in enumerate(legs):
            net = lg.R - lg.cost
            row[f"leg{k}_sym"], row[f"leg{k}_R"], row[f"leg{k}_why"] = lg.sym, round(net, 4), lg.why
            tot += net
        row["R"] = round(tot, 4)
        row["outcome"] = "win" if tot > 0 else "loss"
        out.append(row)
    return out


def summarize(rows: list[dict]) -> dict:
    df = pd.DataFrame(rows)
    if df.empty:
        return {"n": 0}
    split = df["entry_t"].iloc[int(0.7 * len(df))]
    ev = evaluate_trades(df[["R", "outcome", "entry_t"]].copy(), split_time=split, n_boot=2000)
    eq = df["R"].cumsum()
    years = df.groupby(df["entry_t"].dt.year)["R"].agg(["count", "sum", "mean"]).round(3)
    weeks = (df["entry_t"].max() - df["entry_t"].min()).days / 7
    res = {"n": len(df), "per_week": round(len(df) / max(weeks, 1), 2), "total_R": round(df["R"].sum(), 1),
           "exp_R": round(df["R"].mean(), 4), "win_rate": round((df["R"] > 0).mean() * 100, 1),
           "max_dd_R": round(float((eq - eq.cummax()).min()), 1),
           "verdict": ev["verdict"], "p_edge": round(ev["prob_positive"], 3),
           "train_exp": round(ev["train_exp"], 4), "test_exp": round(ev["test_exp"], 4),
           "frac_folds_pos": round(ev["frac_positive"], 2),
           "years": {int(y): {"n": int(r["count"]), "R": float(r["sum"]), "exp": float(r["mean"])}
                     for y, r in years.iterrows()},
           "from": str(df["entry_t"].min().date()), "to": str(df["entry_t"].max().date())}
    if "leg1_why" in df:
        res["second_leg_exits"] = df["leg1_why"].value_counts().to_dict()
        res["first_leg_exits"] = df["leg0_why"].value_counts().to_dict()
        best = df[["leg0_R", "leg1_R"]].max(axis=1)
        res["best_leg_dist"] = {f">={k}R": int((best >= k - 0.05).sum()) for k in (2, 3, 4, 6, 8, 10)}
    return res


def main():
    t0 = time.time()
    m = load_m1()
    print(f"M1 aliniat: {len(m['time'])} minute ({time.time() - t0:.0f}s)", flush=True)
    results = {}
    only = sys.argv[1:]
    for sig in ("GBPUSD", "EURUSD"):
        for etf, ttf in TFS:
            key = f"{sig}_{etf}+{ttf}"
            if only and key not in only and etf not in only:
                continue
            t1 = time.time()
            fills, _ = gen_fills(sig, etf, ttf)
            src = CsvDataSource(DATA)
            a_s = atr_fn(src.load_bars(sig, etf)).shift(1)
            hb = src.load_bars(OTHER[sig], etf)
            a_h = atr_fn(hb).shift(1)
            ts = src.load_bars(sig, etf)["time"]
            s_sig = pd.Series(a_s.values, index=ts)
            s_hed = pd.Series(a_h.values, index=hb["time"])

            def ratio_at(t, s_sig=s_sig, s_hed=s_hed):
                x = s_sig.asof(t)
                y = s_hed.asof(t)
                return float(y / x) if x and y and x > 0 else 1.0

            res = {}
            for mode in ("pair", "plain", "solo"):
                rows = sim(m, fills, sig, ratio_at, TF_MIN[etf], mode)
                res[mode] = summarize(rows)
                pd.DataFrame(rows).to_csv(os.path.join(DATA, f"pairs_{key}_{mode}.csv"), index=False)
            res["signals_filled"] = len(fills)
            results[key] = res
            p, s_ = res["pair"], res["solo"]
            print(f"{key}: semnale {len(fills)} | PERECHE n={p.get('n')} exp={p.get('exp_R')} tot={p.get('total_R')} "
                  f"DD={p.get('max_dd_R')} {p.get('verdict')} | fara reguli exp={res['plain'].get('exp_R')} | "
                  f"SOLO n={s_.get('n')} exp={s_.get('exp_R')} {s_.get('verdict')} ({time.time() - t1:.0f}s)",
                  flush=True)
            json.dump(results, open(os.path.join(DATA, "results.json" if not only else "results_partial.json"), "w"),
                      indent=1, default=str)
    print(f"gata in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
