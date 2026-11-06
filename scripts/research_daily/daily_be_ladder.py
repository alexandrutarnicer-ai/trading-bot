"""
Daily Engine — break-even in TREPTE + SL mai larg (2026-11-06). DOAR backtest, engine-ul neatins.

Intrari = EXACT engine-ul Daily (config curent: GBPUSD Londra, DE40 Frankfurt), fara TP, inchidere la final de fereastra.
Regula userului: la pragul A (ex. 2R) SL → A − L (1R); la fiecare +1R in plus SL urca cu 1R (3R → 2R, 4R → 3R …).
Variante: A ∈ {2,3,4,5}, L ∈ {0.5, 1, 1.5, 2}; SL mai larg: multiplu m ∈ {1, 1.25, 1.5, 2} × distanta actuala
(riscul in bani constant → R se masoara pe noul SL; costul in R scade proportional).
Ordinea pe bara = conservatoare: intai SL-ul curent (gap la open → la open), abia apoi varful barei muta SL-ul
(efect de la bara URMATOARE). Bara de intrare breakout: doar SL-ul.
Train = primele 70% din trade-uri (in timp), test = ultimele 30%.
Rezultat: data/research_daily/daily_be_ladder.json + .log
"""
import json, os, sys, time
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts", "research_tp"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "research_pair"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "research_special"))
from tp_modes import daily_trades  # noqa: E402

OUT = os.path.join(ROOT, "data", "research_daily")


def sim(t, path, A=None, L=1.0, m=1.0):
    o, h, l, c, _ = path
    side, e = t["side"], t["entry"]
    risk = t["risk"] * m                         # 1R = noul SL
    sl = e - side * risk
    peak = 0.0
    stage = None
    for i in range(t["i0"], t["end"]):
        # 1) SL curent (gap la open)
        if side == 1 and l[i] <= sl:
            px = min(o[i], sl) if o[i] <= sl else sl
            return (px - e) / risk, "BE" if stage is not None else "SL", peak
        if side == -1 and h[i] >= sl:
            px = max(o[i], sl) if o[i] >= sl else sl
            return (e - px) / risk, "BE" if stage is not None else "SL", peak
        # 2) varful barei → SL pentru bara urmatoare
        fav = (h[i] - e) / risk if side == 1 else (e - l[i]) / risk
        peak = max(peak, fav)
        if A is not None and peak >= A - 1e-12:
            k = A + np.floor(peak - A + 1e-12)        # cel mai mare prag atins (A, A+1, …)
            lock = k - L
            if stage is None or lock > stage:
                stage = lock
                sl = e + side * lock * risk
    px = c[t["end"] - 1]
    return side * (px - e) / risk, "EOD", peak


def metrics(R, why):
    R = np.asarray(R)
    eq = np.cumsum(R)
    cut = int(0.7 * len(R))
    w, ls = R[R > 0], R[R < 0]
    return {"n": len(R), "exp": round(float(R.mean()), 4), "net": round(float(R.sum()), 1),
            "wr": round(float((R > 0).mean() * 100), 1),
            "pf": round(float(w.sum() / -ls.sum()), 3) if ls.sum() < 0 else None,
            "dd": round(float((eq - np.maximum.accumulate(eq)).min()), 1),
            "train": round(float(R[:cut].mean()), 4), "test": round(float(R[cut:].mean()), 4),
            "max": round(float(R.max()), 1), "be_exits": int(sum(1 for x in why if x == "BE"))}


def main():
    t0 = time.time()
    from daily_engine.config import load_config
    res, lines = {}, []
    for mk in load_config()["markets"]:
        trades, path_of = daily_trades(mk)
        name = f"{mk['symbol']} ({mk['tz'].split('/')[-1]} {mk['or_minutes']}m {mk['entry']})"
        res[name] = {}
        variants = [("actual (fara BE)", None, 1.0, 1.0)]
        variants += [(f"BE de la {A}R, SL la {A}-{L:g}R", A, L, 1.0) for A in (2, 3, 4, 5) for L in (0.5, 1.0, 1.5, 2.0)
                     if L < A]
        for mm in (1.25, 1.5, 2.0):
            variants.append((f"SL x{mm:g} (fara BE)", None, 1.0, mm))
            variants.append((f"SL x{mm:g} + BE 2R→1R", 2, 1.0, mm))
            variants.append((f"SL x{mm:g} + BE 3R→2R", 3, 1.0, mm))
        for vn, A, L, mm in variants:
            R, why = [], []
            for t in trades:
                r, w, _ = sim(t, path_of(t), A, L, mm)
                R.append(r - t["cost_R"] / mm)
                why.append(w)
            res[name][vn] = metrics(R, why)
        cur = res[name]["actual (fara BE)"]
        lines.append(f"\n== {name}: {cur['n']} trade-uri")
        for vn, x in res[name].items():
            lines.append(f"  {vn:30} exp {x['exp']:+.4f}  net {x['net']:+7.1f}R  WR {x['wr']:4.1f}%  PF {x['pf']}  "
                         f"DD {x['dd']:6.1f}  train {x['train']:+.4f}  test {x['test']:+.4f}  BE {x['be_exits']}")
        print("\n".join(lines[-len(res[name]) - 1:]), flush=True)
    json.dump(res, open(os.path.join(OUT, "daily_be_ladder.json"), "w"), indent=1)
    open(os.path.join(OUT, "daily_be_ladder.log"), "w", encoding="utf-8").write("\n".join(lines))
    print(f"gata in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
