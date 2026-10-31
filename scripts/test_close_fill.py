"""
Test: pretul real de iesire la inchiderile fortate (news_close / vineri_close).

Bug 2026-10-30: ICMarketsEU intoarce `result.price == 0` la TRADE_ACTION_DEAL, iar
botul scria exit_price=0 → result_r de ordinul -1000R si pnl_usd ~ -1300 $ in
outcomes.csv (13 randuri) + mesaje Telegram „Inchis la stire ... → 0.00000".
Fix: live/signal_generator.py::_close_fill.

Ruleaza din radacina proiectului (fara MT5, fara Telegram):
    python scripts/test_close_fill.py
"""

import os, sys
from types import SimpleNamespace as NS

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live.signal_generator as sg

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {msg}")
    else:
        FAIL += 1
        print(f"  FAIL  {msg}")


class FakeMt5:
    def __init__(self, deals=None, raise_on_history=False):
        self.deals = deals or {}
        self.raise_on_history = raise_on_history
        self.calls = 0

    def history_deals_get(self, ticket=None):
        self.calls += 1
        if self.raise_on_history:
            raise RuntimeError("IPC lost")
        d = self.deals.get(ticket)
        return (d,) if d else ()


_orig = sg._mt5_exec
try:
    print("\n[1] result.price > 0 → folosit ca atare")
    sg._mt5_exec = FakeMt5({7: NS(price=1.2, profit=3.0, commission=-0.1, swap=0.0)})
    px, pnl = sg._close_fill(NS(price=1.33512, deal=7), 1.33500)
    check(px == 1.33512, f"exit = pretul din result [got {px}]")
    check(pnl == 2.9, f"pnl = profit real al deal-ului (net) [got {pnl}]")

    print("\n[2] result.price == 0 (cazul ICMarketsEU) → pretul deal-ului MT5")
    sg._mt5_exec = FakeMt5({42: NS(price=1.32480, profit=-1.15, commission=0.0, swap=-0.05)})
    px, pnl = sg._close_fill(NS(price=0.0, deal=42), 1.32470)
    check(px == 1.32480, f"exit = pretul deal-ului [got {px}]")
    check(pnl == -1.2, f"pnl = profit + comision + swap [got {pnl}]")

    print("\n[3] price == 0 si deal-ul inca nu e in istoric → pretul din request")
    sg._mt5_exec = FakeMt5({})
    px, pnl = sg._close_fill(NS(price=0.0, deal=99), 1.32470)
    check(px == 1.32470, f"exit = pretul tick-ului trimis [got {px}]")
    check(pnl is None, "pnl = None → apelantul cade pe calculul din R")

    print("\n[4] price == 0, deal=0 (lipsa) → pretul din request, fara interogare MT5")
    fm = FakeMt5({})
    sg._mt5_exec = fm
    px, _ = sg._close_fill(NS(price=0.0, deal=0), 0.65512)
    check(px == 0.65512, f"exit = pretul din request [got {px}]")
    check(fm.calls == 0, "nicio interogare de istoric fara ticket de deal")

    print("\n[5] istoricul MT5 arunca exceptie → nu crapa, pretul din request")
    sg._mt5_exec = FakeMt5(raise_on_history=True)
    px, pnl = sg._close_fill(NS(price=0.0, deal=5), 1.1)
    check(px == 1.1 and pnl is None, f"fail-safe [got {px}, {pnl}]")

    print("\n[6] result fara atribute price/deal (obiect minimal) → pretul din request")
    sg._mt5_exec = FakeMt5({})
    px, _ = sg._close_fill(NS(retcode=10009), 2.5)
    check(px == 2.5, f"exit = pretul din request [got {px}]")

    print("\n[7] regresia reala: S15-GBPUSD-IB0016 (entry 1.35136, SL 1.35049)")
    entry, sl, d = 1.35136, 1.35049, 1
    sg._mt5_exec = FakeMt5({})
    px, _ = sg._close_fill(NS(price=0.0, deal=0), 1.35090)
    r = round((px - entry) * d / abs(entry - sl), 3)
    check(-1.5 < r < 1.5, f"result_r plauzibil ({r}R), nu -1553R")
    check(px > 0, "exit_price niciodata 0")
finally:
    sg._mt5_exec = _orig

print(f"\n{'=' * 60}\nREZULTAT: {PASS} PASS / {FAIL} FAIL\n{'=' * 60}")
sys.exit(1 if FAIL else 0)
