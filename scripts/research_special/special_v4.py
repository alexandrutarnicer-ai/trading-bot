"""Special Engine v4 — pairs trading DIRECT pe EURGBP (= GBPUSD vs EURUSD, un singur spread): mean reversion pe z-score
(close − SMA20) / STD20, pe H1 / H4 / D1, intrare la urmatoarea bara, iesire la z = 0 / max N bare / stop 2×ATR.
Pragul z din {1.5, 2.0, 2.5} — raportate TOATE (fara alegere ascunsa)."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
from daily_candidates import ind, zmr
out = {}
for tf, n, mx in (("H1", 40000, 24), ("H4", 15000, 15), ("D1", 3000, 15)):
    d = ind(C.fetch("EURGBP", tf, n))
    for z in (1.5, 2.0, 2.5):
        r = C.report(zmr("EURGBP", d, z, mx), label=f"v4 EURGBP {tf} z{z}")
        out[r["label"]] = r
        print(C.fmt(r), flush=True)
json.dump(out, open(os.path.join(C.OUT, "special_v4.json"), "w"), indent=1, default=str)
