"""
test_ai_weekend_guard.py — teste offline pentru pargia de weekend a MOTORULUI AI.

Cerinta: pentru pietele FX, INAINTE sa inceapa weekendul (Vineri, pana se inchid
pietele), motorul AI trebuie sa inchida pozitiile deschise + sa anuleze ordinele
pending si sa NU mai deschida nimic pana Luni. Cripto (XRPUSD, BTCUSD...) NU e
afectat (ruleaza non-stop).

Verifica `ai_engine.executor.is_market_weekend_closed` (logica pura de timp) +
`ai_engine.engine._weekend_guard` (inchidere efectiva), fara MT5 — ceas fals +
executor simulat, determinist.

Rulare:  python scripts/test_ai_weekend_guard.py
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_engine.engine as eng
from ai_engine.executor import is_market_weekend_closed

# Ancore de calendar (2026): Vineri 07, Sambata 08, Duminica 09, Luni 10 august.
FRI = lambda h, m=0: datetime(2026, 8, 7, h, m)
SAT = lambda h, m=0: datetime(2026, 8, 8, h, m)
SUN = lambda h, m=0: datetime(2026, 8, 9, h, m)
MON = lambda h, m=0: datetime(2026, 8, 10, h, m)


class FakePos:
    pass


class FakeOrder:
    def __init__(self, symbol, ticket):
        self.symbol = symbol
        self.ticket = ticket


def run_guard(symbol, now_dt, has_position=True, pendings=None, enabled=True, hour=22):
    """Ruleaza _weekend_guard cu executor + ceas simulate. Intoarce (result, calls)."""
    pendings = pendings or []
    calls = {"close": [], "cancel": []}

    saved = {
        "now_local": eng.now_local,
        "open_position_for": eng.executor.open_position_for,
        "close_position": eng.executor.close_position,
        "ai_pending_orders": eng.executor.ai_pending_orders,
        "cancel_order": eng.executor.cancel_order,
        "_send_telegram": eng._send_telegram,
    }
    try:
        eng.now_local = lambda: now_dt
        eng.executor.open_position_for = lambda s, m: (FakePos() if (has_position and s == symbol) else None)

        def fake_close(s, cfg):
            calls["close"].append(s)
            return ("placed", "TP/SL real")
        eng.executor.close_position = fake_close
        eng.executor.ai_pending_orders = lambda m: pendings

        def fake_cancel(t, cfg):
            calls["cancel"].append(t)
            return True
        eng.executor.cancel_order = fake_cancel
        eng._send_telegram = lambda *a, **k: None

        cfg = {"weekend_close_enabled": enabled, "weekend_close_hour": hour, "magic": 770015}
        result = eng._weekend_guard(symbol, cfg)
        return result, calls
    finally:
        eng.now_local = saved["now_local"]
        eng.executor.open_position_for = saved["open_position_for"]
        eng.executor.close_position = saved["close_position"]
        eng.executor.ai_pending_orders = saved["ai_pending_orders"]
        eng.executor.cancel_order = saved["cancel_order"]
        eng._send_telegram = saved["_send_telegram"]


PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [ESUAT] {name}")


def main():
    print("=== test_ai_weekend_guard: pargia de weekend a motorului AI ===\n")

    # ── A) Logica pura de timp (is_market_weekend_closed), FX = EURUSD ──
    print("A) Fereastra de timp FX (EURUSD, weekend_close_hour=22):")
    check("Vineri 21:00 -> INCA deschis (nu inchide)", is_market_weekend_closed("EURUSD", FRI(21)) is False)
    check("Vineri 21:59 -> INCA deschis", is_market_weekend_closed("EURUSD", FRI(21, 59)) is False)
    check("Vineri 22:00 -> INCHIS (pargia activa)", is_market_weekend_closed("EURUSD", FRI(22)) is True)
    check("Vineri 23:30 -> INCHIS", is_market_weekend_closed("EURUSD", FRI(23, 30)) is True)
    check("Sambata 10:00 -> INCHIS", is_market_weekend_closed("EURUSD", SAT(10)) is True)
    check("Duminica 20:00 -> INCHIS", is_market_weekend_closed("EURUSD", SUN(20)) is True)
    check("Luni 00:00 -> deschis din nou (se reia)", is_market_weekend_closed("EURUSD", MON(0)) is False)
    check("Luni 09:00 -> deschis", is_market_weekend_closed("EURUSD", MON(9)) is False)

    # ── B) Cripto NU e afectat niciodata ──
    print("\nB) Cripto (XRPUSD) — non-stop, exceptat:")
    check("XRPUSD Vineri 23:00 -> deschis", is_market_weekend_closed("XRPUSD", FRI(23)) is False)
    check("XRPUSD Sambata 10:00 -> deschis", is_market_weekend_closed("XRPUSD", SAT(10)) is False)
    check("XRPUSD Duminica 20:00 -> deschis", is_market_weekend_closed("XRPUSD", SUN(20)) is False)

    # ── C) _weekend_guard: inchidere efectiva FX inainte de weekend ──
    print("\nC) _weekend_guard — inchidere FX (CHFJPY) inainte de weekend:")
    # Vineri 22:30, pozitie deschisa + 1 pending pe simbol -> inchide + anuleaza + True
    res, calls = run_guard("CHFJPY", FRI(22, 30), has_position=True,
                           pendings=[FakeOrder("CHFJPY", 111)])
    check("Vineri 22:30 -> intoarce True (sare consiliul, nu deschide)", res is True)
    check("Vineri 22:30 -> pozitia a fost inchisa", calls["close"] == ["CHFJPY"])
    check("Vineri 22:30 -> pending-ul a fost anulat", calls["cancel"] == [111])

    # Vineri 21:00 (inainte de ora) -> NU inchide nimic, intoarce False
    res, calls = run_guard("CHFJPY", FRI(21), has_position=True,
                           pendings=[FakeOrder("CHFJPY", 222)])
    check("Vineri 21:00 -> False (piata inca deschisa)", res is False)
    check("Vineri 21:00 -> pozitia NU e inchisa (nici anulare)",
          calls["close"] == [] and calls["cancel"] == [])

    # Sambata: fara pozitie dar cu pending -> anuleaza pending, True (nu deschide)
    res, calls = run_guard("USDCAD", SAT(11), has_position=False,
                           pendings=[FakeOrder("USDCAD", 333)])
    check("Sambata -> True chiar fara pozitie (blocheaza deschideri)", res is True)
    check("Sambata -> fara pozitie: zero inchideri", calls["close"] == [])
    check("Sambata -> pending anulat", calls["cancel"] == [333])

    # Anuleaza DOAR pending-urile simbolului curent (nu ale altei piete)
    res, calls = run_guard("USDCAD", SAT(11), has_position=False,
                           pendings=[FakeOrder("USDCAD", 1), FakeOrder("NZDJPY", 2)])
    check("Sambata -> anuleaza doar pending-ul simbolului (nu al altei piete)",
          calls["cancel"] == [1])

    # Cripto in weekend -> guard-ul NU inchide, False (ruleaza normal)
    res, calls = run_guard("XRPUSD", SAT(11), has_position=True,
                           pendings=[FakeOrder("XRPUSD", 444)])
    check("XRPUSD Sambata -> False (nu inchide cripto)", res is False)
    check("XRPUSD Sambata -> zero inchideri/anulari", calls["close"] == [] and calls["cancel"] == [])

    # Toggle OFF -> guard inactiv chiar si Sambata
    res, calls = run_guard("EURUSD", SAT(11), has_position=True, enabled=False)
    check("weekend_close_enabled=False -> False (pargie dezactivata)", res is False)
    check("weekend_close_enabled=False -> nu inchide nimic", calls["close"] == [])

    # Luni -> se reia normal
    res, calls = run_guard("CHFJPY", MON(9), has_position=True)
    check("Luni 09:00 -> False (deschidere reluata)", res is False)

    print(f"\n=== {PASS} OK, {FAIL} esuate ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
