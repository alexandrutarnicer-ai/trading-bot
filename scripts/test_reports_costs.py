"""
Test: Top 5 Piete (Dashboard) + Rapoarte → Piete / Comisioane+Swap — definitii comune
(api/trade_stats.py), fara MT5 (pool simulat).

    python scripts/test_reports_costs.py
"""

import os
import sys
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.mt5_pool as mt5_pool
from api import trade_stats
from tz_helper import now_local

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {msg}")
    else:
        FAIL += 1
        print(f"  FAIL  {msg}")


NOW = now_local().replace(tzinfo=None)
OLD = NOW - timedelta(days=60)


def T(sym, profit, r=None, comm=0.0, swap=0.0, vol=0.01, src="bot", when=NOW):
    return {"symbol": sym, "profit": profit, "result_r": r, "commission": comm, "swap": swap,
            "volume": vol, "source": src, "close_time": when, "session_id": None}


TRADES = [
    # GBPUSD: profit in $ dar R mic (lot mai mare pe castig) → primul dupa net
    T("GBPUSD", 6.0, 0.5, swap=-0.2, src="ai"),
    T("GBPUSD", -1.0, -1.0, src="bot"),
    T("GBPUSD", 0.0, 0.0, src="bot"),                 # break-even
    # USDCHF: R mare, $ mic
    T("USDCHF", 1.0, 2.0, swap=0.1),
    # XRPUSD: fara SL (fara R), pierdere
    T("XRPUSD", -3.0, None, vol=100.0, src="ai"),
    # trade vechi (alta luna) — doar in "all"
    T("EURUSD", 2.0, 1.0, comm=-0.04, when=OLD),
]
SPL = {"GBPUSD": 10.0, "USDCHF": 9.0, "XRPUSD": 0.0021}

# ── 1. summarize ───────────────────────────────────────────────────────────
print("\n1. trade_stats.summarize — definitii")
g = trade_stats.summarize([t for t in TRADES if t["symbol"] == "GBPUSD"], SPL)
check(g["wins"] == 1 and g["losses"] == 1 and g["breakeven"] == 1, "break-even NU e pierdere")
check(g["win_rate"] == 50.0, f"win rate = wins/(wins+losses) = 50 [got {g['win_rate']}]")
check(g["pnl_gross"] == 5.0 and g["costs"] == -0.2 and g["pnl_net"] == 4.8, "brut / costuri / net")
check(g["spread_est"] == -0.3, f"spread = 3 × 0.01 lot × 10$ = −0,30 [got {g['spread_est']}]")
x = trade_stats.summarize([t for t in TRADES if t["symbol"] == "XRPUSD"], SPL)
check(x["expectancy_r"] is None and x["trades_with_r"] == 0, "fara SL → fara R (nu 0R diluat)")
check(x["spread_est"] == -0.21, f"XRP: 100 × 0,0021 = −0,21 [got {x['spread_est']}]")
e = trade_stats.summarize([], SPL)
check(e["trades"] == 0 and e["win_rate"] == 0.0 and e["spread_est"] is None, "grup gol fara erori")
n = trade_stats.summarize(TRADES[:1], {})
check(n["spread_est"] is None, "spread necunoscut → None (nu 0 inselator)")

# ── 2. rank ────────────────────────────────────────────────────────────────
print("\n2. trade_stats.rank")
st = trade_stats.group_by([t for t in TRADES if t["close_time"] == NOW], lambda t: t["symbol"])
check([k for k, _ in trade_stats.rank(st, "net")] == ["GBPUSD", "USDCHF", "XRPUSD"], "sortare implicita dupa net $")
check([k for k, _ in trade_stats.rank(st, "r")][0] == "USDCHF", "sortare dupa R: USDCHF primul")
check([k for k, _ in trade_stats.rank(st, "r")][-1] == "XRPUSD", "piata fara R ajunge ultima la sortarea dupa R")

# ── 3. endpointuri cu pool simulat ─────────────────────────────────────────
print("\n3. /mt5/top-markets + /mt5/costs + /mt5/costs-daily")
mt5_pool.get_closed_trades = lambda days: list(TRADES)
mt5_pool.get_spread_per_lot = lambda syms: {s: v for s, v in SPL.items() if s in syms}
from api.routers import mt5status as ms

top = ms.mt5_top_markets(period="all", limit=5)
check(top["connected"] and top["total_markets"] == 4, "toate pietele comune (4) agregate peste engine-uri")
check(top["items"][0]["symbol"] == "GBPUSD", "GBPUSD (bot + AI) primul dupa net")
gb = top["items"][0]
check(gb["trades"] == 3 and gb["losses"] == 1, "GBPUSD: 3 trade-uri bot+AI, 1 pierdere (nu 2)")
check(gb["pnl_usd"] == gb["pnl_gross"] and "pnl_net" in gb, "compat pnl_usd = brut + pnl_net nou")
check(len(ms.mt5_top_markets(period="all", limit=2)["items"]) == 2, "limit respectat")
mon = ms.mt5_top_markets(period="month", limit=10)
check(all(i["symbol"] != "EURUSD" for i in mon["items"]), "perioada Luna exclude trade-ul vechi")
ai = ms.mt5_top_markets(period="all", limit=10, source="ai")
check({i["symbol"] for i in ai["items"]} == {"GBPUSD", "XRPUSD"}, "filtrul de sursa AI")
check(ms.mt5_top_markets(period="all", sort="r")["items"][0]["symbol"] in ("USDCHF", "EURUSD"),
      "sort=r → R maxim primul")
check(top["totals"]["trades"] == len(TRADES), "totals pe toata selectia")

c = ms.mt5_costs()
check(c["connected"] and len(c["items"]) == 4, "costuri pe 4 piete")
check(c["totals"]["commission"] == -0.04 and c["totals"]["swap"] == -0.1, "totaluri comision / swap")
exp_spread = round(-(3 * 0.01 * 10 + 0.01 * 9 + 100 * 0.0021), 2)
check(c["totals"]["spread_est"] == exp_spread,
      f"spread estimat total {exp_spread} (EURUSD fara cotatie exclus) [got {c['totals']['spread_est']}]")
srcs = {r["source"]: r["trades"] for r in c["by_source"]}
check(srcs == {"bot": 4, "ai": 2}, f"defalcare pe engine [got {srcs}]")
check(sum(r["trades"] for r in c["by_source"]) == c["totals"]["trades"], "engine-urile se adună la total")
check(all(k in c["items"][0] for k in ("commission_usd", "swap_usd", "total_costs", "trades_with_mt5")),
      "campuri vechi pastrate (compat)")

d = ms.mt5_costs_daily()
check(sum(i["trades"] for i in d["items"]) == len(TRADES), "zilele se aduna la total")
check(d["total_costs"] == round(-0.04 - 0.1, 2), "total_costs zilnic = comision + swap")
check(d["items"][0]["date"] < d["items"][-1]["date"], "zile in ordine cronologica")


def _boom(days):
    raise mt5_pool.Mt5Unavailable("x")


mt5_pool.get_closed_trades = _boom
check(ms.mt5_top_markets()["connected"] is False, "MT5 indisponibil → connected False (top)")
check(ms.mt5_costs()["connected"] is False, "MT5 indisponibil → connected False (costuri)")

print(f"\n{PASS} PASS, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
