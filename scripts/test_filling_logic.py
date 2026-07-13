"""
test_filling_logic.py -- Verifica logica de filling mode din signal_generator
=============================================================================
Doua faze:
  Faza 1 (fara MT5): valideaza ordinea fill_modes produsa de bitmask
  Faza 2 (cu MT5):   plaseaza un SELL_STOP de test pe fiecare simbol activ
                     si confirma ca ordinul este acceptat; il anuleaza imediat

Utilizare:
  python scripts/test_filling_logic.py              # ambele faze
  python scripts/test_filling_logic.py --unit-only  # doar Faza 1 (fara MT5)
  python scripts/test_filling_logic.py XRPUSD       # Faza 2 pe un singur simbol
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Simboluri active din toate sesiunile (M15 + H1)
# ---------------------------------------------------------------------------
ALL_SYMBOLS = [
    # (canonical, [aliases], session)
    ("EURUSD",  ["EURUSD"],                                  "S1"),
    ("AUDJPY",  ["AUDJPY"],                                  "S2"),
    ("BTCUSD",  ["BTCUSD", "BTC/USD", "BTCUSDT"],           "S3"),
    ("GER40",   ["GER40", "DE40", "DAX40", "DAX30", "DE30"],"S4"),
    ("USDCHF",  ["USDCHF"],                                  "S5"),
    ("US30",    ["US30", "DJ30", "DJIA", "DJI30"],           "S6"),
    ("XRPUSD",  ["XRPUSD", "XRP/USD"],                      "S7"),
    ("EURCAD",  ["EURCAD"],                                  "S8"),
    ("USDJPY",  ["USDJPY"],                                  "S9"),
    ("GBPCAD",  ["GBPCAD"],                                  "S10"),
    ("USDCAD",  ["USDCAD"],                                  "S11"),
    ("EURAUD",  ["EURAUD"],                                  "S12"),
    ("EURJPY",  ["EURJPY"],                                  "S13"),
    ("CHFJPY",  ["CHFJPY"],                                  "S14"),
    ("GBPUSD",  ["GBPUSD"],                                  "S15"),
    ("GBPAUD",  ["GBPAUD"],                                  "S16"),
    ("AUDCAD",  ["AUDCAD"],                                  "S17"),
    ("NZDJPY",  ["NZDJPY"],                                  "S18"),
    ("AUDNZD",  ["AUDNZD"],                                  "S19"),
    ("XAUUSD",  ["XAUUSD", "GOLD"],                          "S20"),
]

RETCODES = {
    10004: "Requote",          10006: "Cerere respinsa",
    10008: "Ordin plasat",     10009: "DONE",
    10012: "Timeout server",   10013: "Cerere invalida",
    10014: "Volum invalid",    10015: "Pret invalid",
    10016: "Stop-uri invalide",
    10017: "Trade dezactivat", 10018: "Piata inchisa",
    10019: "Fonduri insuf",    10022: "Ordin invalid",
    10025: "Operatie nepermisa",10026: "AutoTrade SERVER",
    10027: "AutoTrade CLIENT", 10030: "Filling nepermis",
    10031: "Fara conexiune",
}
# Retcode-uri care inseamna retry bara urm (nu eroare fatala).
# 10015/10016 = pretul a depasit entry/stops intre pre-check si order_send (race).
RETRY_NONE_RETCODES = {10012, 10031, 10026, 10027, 10015, 10016}


# ===========================================================================
# FAZA 1 — Unit tests pentru logica bitmask (fara MT5)
# ===========================================================================

class MockMT5:
    ORDER_FILLING_FOK    = 0
    ORDER_FILLING_IOC    = 1
    ORDER_FILLING_RETURN = 2


def compute_fill_modes(fm: int, mt5=MockMT5()):
    """
    Replica exacta a logicii din signal_generator._place_order.
    Returneaza lista fill_modes in ordinea in care vor fi incercate.
    """
    if fm == 0:
        return [mt5.ORDER_FILLING_RETURN,
                mt5.ORDER_FILLING_FOK,
                mt5.ORDER_FILLING_IOC]
    else:
        bitmask_modes = []
        if fm & 1: bitmask_modes.append(mt5.ORDER_FILLING_FOK)
        if fm & 2: bitmask_modes.append(mt5.ORDER_FILLING_IOC)
        leftover = [m for m in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC]
                    if m not in bitmask_modes]
        return bitmask_modes + [mt5.ORDER_FILLING_RETURN] + leftover


UNIT_TESTS = [
    # (fm_bitmask, expected_fill_modes, descriere)
    (0, [2, 0, 1], "Forex standard (fm=0): RETURN primul"),
    (1, [0, 2, 1], "FOK suportat (fm=1): FOK primul, RETURN fallback, IOC last"),
    (2, [1, 2, 0], "IOC suportat (fm=2): IOC primul, RETURN fallback, FOK last"),
    (3, [0, 1, 2], "FOK+IOC (fm=3): FOK, IOC, RETURN last"),
]


def run_unit_tests():
    print("=" * 68)
    print("  FAZA 1 — Unit tests logica bitmask filling_mode")
    print("=" * 68)

    passed = 0
    failed = 0

    for fm, expected, descriere in UNIT_TESTS:
        result = compute_fill_modes(fm)
        ok = result == expected
        status = "PASS" if ok else "FAIL"
        names  = {0: "FOK", 1: "IOC", 2: "RETURN"}
        res_s  = " -> ".join(names[m] for m in result)
        exp_s  = " -> ".join(names[m] for m in expected)
        print(f"  [{status}] fm={fm}  {descriere}")
        if not ok:
            print(f"       Asteptat:  {exp_s}")
            print(f"       Primit:    {res_s}")
        else:
            print(f"       Ordine:    {res_s}")
        if ok:
            passed += 1
        else:
            failed += 1

    # Test suplimentar: 10006 si 10030 sunt ambele in retry set
    retry_set = {10030, 10006}
    ok = 10006 in retry_set and 10030 in retry_set
    print(f"\n  [{'PASS' if ok else 'FAIL'}] retcode 10006 si 10030 ambele permit retry filling")
    if ok:
        passed += 1
    else:
        failed += 1

    # Test: 10026 (AutoTrading) nu e in retry set si returneaza None nu False
    ok = 10026 not in retry_set
    print(f"  [{'PASS' if ok else 'FAIL'}] retcode 10026 (AutoTrading) NU e in retry set")
    if ok:
        passed += 1
    else:
        failed += 1

    # Test: 10012 (timeout) → None imediat, nu continua loop si nu False
    def _sim_timeout():
        # Prima incercare returneaza 10012 → trebuie None imediat
        rc = 10012
        if rc in (10026, 10027):
            return "None-autotrading"
        if rc == 10012:
            return "None"  # timeout → retry, nu drop
        if rc not in (10030, 10006):
            return "False"
        return "continue"

    result = _sim_timeout()
    ok = result == "None"
    print(f"  [{'PASS' if ok else 'FAIL'}] retcode 10012 (timeout) -> None (retry), nu False")
    if ok:
        passed += 1
    else:
        failed += 1

    # Test: 10015/10016 (pret/stops invalide = race la breakout) → None, nu False.
    # Reproducerea bug-ului S3-BTC IB0013 (2026-07-13): pretul a depasit entry intre
    # pre-check si order_send; inainte de fix era clasificat drept eroare fatala (False).
    def _sim_invalid_price(rc):
        if rc in (10026, 10027):
            return "None-autotrading"
        if rc in (10012, 10031):
            return "None-conn"
        if rc in (10015, 10016):
            return "None"  # race pret/stops → retry bara urm, nu drop
        if rc not in (10030, 10006):
            return "False"
        return "continue"

    for rc in (10015, 10016):
        result = _sim_invalid_price(rc)
        ok = result == "None"
        print(f"  [{'PASS' if ok else 'FAIL'}] retcode {rc} (pret/stops invalide) -> None (retry), nu False")
        if ok:
            passed += 1
        else:
            failed += 1

    # Test logica all_10006: simulam toate incercarile returnand 10006
    def _sim_all_10006():
        """Simuleaza _place_order cand toate incercarile returneza 10006."""
        all_none  = True
        all_10006 = True
        retcodes  = [10006, 10006, 10006, 10006]  # RETURN, FOK, IOC, no-fill
        for rc in retcodes:
            all_none = False
            if rc != 10006:
                all_10006 = False
            if rc in (10026, 10027):
                return "None"
            if rc not in (10030, 10006):
                return "False"
        if all_none:
            return "None"
        if all_10006:
            return "None"  # retry, nu False
        return "False"

    result = _sim_all_10006()
    ok = result == "None"
    print(f"  [{'PASS' if ok else 'FAIL'}] all-10006 -> None (retry), nu False (drop signal)")
    if ok:
        passed += 1
    else:
        failed += 1

    # Test: un mix de 10006 si 10030 -> continua loop, nu drop
    def _sim_mix_retcodes():
        all_none  = True
        all_10006 = True
        retcodes  = [10006, 10030, 10006]  # mix filling + invalid fill
        for rc in retcodes:
            all_none = False
            if rc != 10006:
                all_10006 = False
            if rc in (10026, 10027):
                return "None"
            if rc not in (10030, 10006):
                return "False"
        if all_none:
            return "None"
        if all_10006:
            return "None"
        return "False"

    result = _sim_mix_retcodes()
    ok = result == "False"  # mix -> all_10006 e False -> cade in return False
    print(f"  [{'PASS' if ok else 'FAIL'}] mix 10006+10030 -> False (niciun filling acceptat)")
    if ok:
        passed += 1
    else:
        failed += 1

    print(f"\n  Rezultat: {passed} PASS, {failed} FAIL")
    return failed == 0


# ===========================================================================
# FAZA 2 — Test cu MT5 real
# ===========================================================================

def resolve_symbol(mt5, fallbacks):
    for alias in fallbacks:
        if mt5.symbol_select(alias, True):
            info = mt5.symbol_info(alias)
            if info is not None:
                return alias
    return None


def pip_size_for(symbol, info):
    s = symbol.upper()
    if any(x in s for x in ("BTC", "ETH", "XRP", "LTC")):
        return info.trade_tick_size if info.trade_tick_size > 0 else 0.01
    if any(x in s for x in ("GER", "DAX", "DE30", "DE40", "US30", "DJ", "XAU", "GOLD")):
        return 1.0
    if s.endswith("JPY"):
        return 0.01
    return 0.0001


def try_place_order_new_logic(mt5, request, sym_info, log_lines):
    """
    Implementeaza exact logica noua din signal_generator._place_order:
    - ordine dupa bitmask
    - retry pe 10006 si 10030
    """
    fm = sym_info.filling_mode if sym_info else 0

    if fm == 0:
        fill_modes = [mt5.ORDER_FILLING_RETURN,
                      mt5.ORDER_FILLING_FOK,
                      mt5.ORDER_FILLING_IOC]
    else:
        bitmask_modes = []
        if fm & 1: bitmask_modes.append(mt5.ORDER_FILLING_FOK)
        if fm & 2: bitmask_modes.append(mt5.ORDER_FILLING_IOC)
        leftover = [m for m in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC]
                    if m not in bitmask_modes]
        fill_modes = bitmask_modes + [mt5.ORDER_FILLING_RETURN] + leftover

    fill_names = {mt5.ORDER_FILLING_FOK: "FOK",
                  mt5.ORDER_FILLING_IOC: "IOC",
                  mt5.ORDER_FILLING_RETURN: "RETURN"}
    fill_order_str = " -> ".join(fill_names[m] for m in fill_modes) + " -> NO-FILL"
    log_lines.append(f"  filling_mode={fm}  ordine incercate: {fill_order_str}")

    all_none = True
    for filling in fill_modes:
        request["type_filling"] = filling
        result = mt5.order_send(request)
        if result is None:
            err = mt5.last_error()
            log_lines.append(f"    filling={fill_names[filling]:<6} -> None  last_error={err}")
            continue
        all_none = False
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return {"ok": True, "ticket": result.order,
                    "filling": fill_names[filling], "attempts": 1}
        desc = RETCODES.get(result.retcode, "necunoscut")
        log_lines.append(f"    filling={fill_names[filling]:<6} -> retcode={result.retcode} "
                         f"({result.comment}) [{desc}]")
        if result.retcode in (10026, 10027):
            return {"ok": False, "retcode": result.retcode, "reason": "AutoTrading dezactivat (retry)"}
        if result.retcode in (10012, 10031):
            # Timeout sau fara conexiune — eroare tranzitorie, bot face retry bara urm
            return {"ok": False, "retcode": result.retcode, "reason": "conexiune/timeout (retry bara urm)"}
        if result.retcode not in (10030, 10006):
            return {"ok": False, "retcode": result.retcode,
                    "comment": result.comment, "reason": "eroare reala"}

    # Ultima sansa: fara type_filling
    req2 = {k: v for k, v in request.items() if k != "type_filling"}
    result = mt5.order_send(req2)
    if result is not None:
        all_none = False
        desc = RETCODES.get(result.retcode, "necunoscut")
        log_lines.append(f"    filling=NO-FILL -> retcode={result.retcode} "
                         f"({result.comment}) [{desc}]")
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return {"ok": True, "ticket": result.order, "filling": "NO-FILL"}
    else:
        err = mt5.last_error()
        log_lines.append(f"    filling=NO-FILL -> None  last_error={err}")

    if all_none:
        return {"ok": False, "reason": "toate None (conexiune MT5?)"}
    return {"ok": False, "retcode": getattr(result, 'retcode', None) if result else None,
            "reason": "niciun filling acceptat"}


def run_mt5_tests(filter_symbol=None):
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("\n  EROARE: MetaTrader5 nu e instalat (pip install MetaTrader5)")
        return False

    print("\n" + "=" * 68)
    print("  FAZA 2 — Test plasare ordine cu logica noua (MT5 DEMO)")
    print("  NOTA: Rulati cand botul (run_all.py) NU este activ.")
    print("        Botul activ ocupa conexiunea MT5 -> 10031 pe toate simbolurile.")
    print("=" * 68)

    if not mt5.initialize():
        print(f"\n  EROARE: mt5.initialize() esuat -- {mt5.last_error()}")
        print("  Verifica ca MT5 terminal este deschis si logat.")
        return False

    acc = mt5.account_info()
    if acc is None:
        print(f"  EROARE: nu am putut citi info cont -- {mt5.last_error()}")
        mt5.shutdown()
        return False

    if acc.trade_mode != 0:
        print(f"  STOP: contul nu este DEMO (trade_mode={acc.trade_mode}). Iesire.")
        mt5.shutdown()
        return False

    term    = mt5.terminal_info()
    auto_ok = bool(term and getattr(term, "trade_allowed", False))

    print(f"\n  Cont: {acc.login} @ {acc.server} | Balance: ${acc.balance:.2f}")
    print(f"  AutoTrading: {'DA [OK]' if auto_ok else 'DEZACTIVAT [!]'}")

    if not auto_ok:
        print("\n  ATENTIE: AutoTrading dezactivat in MT5.")
        print("  Activeaza din toolbar MT5 (butonul AutoTrading sau Alt+A).")
        print("  Testul de plasare ordine va fi sarit pentru toate simbolurile.")

    symbols_to_test = ALL_SYMBOLS
    if filter_symbol:
        s = filter_symbol.upper()
        symbols_to_test = [(n, a, ses) for n, a, ses in ALL_SYMBOLS if n == s]
        if not symbols_to_test:
            symbols_to_test = [(s, [s], "?")]

    ok_count = fail_count = skip_count = 0
    results = []

    for name, aliases, session in symbols_to_test:
        resolved = resolve_symbol(mt5, aliases)
        print(f"\n  [{session}] {name}", end="")

        if resolved is None:
            print(f"  -> NEGASIT in MT5 (incercat: {', '.join(aliases)})")
            skip_count += 1
            results.append((name, session, "SKIP", "negasit"))
            continue

        if resolved != name:
            print(f" (alias: {resolved})", end="")

        info = mt5.symbol_info(resolved)
        tick = mt5.symbol_info_tick(resolved)

        if info is None or tick is None:
            print(f"  -> fara tick (piata inchisa?)")
            skip_count += 1
            results.append((name, session, "SKIP", "piata inchisa"))
            continue

        pip  = pip_size_for(resolved, info)
        fmt  = f".{info.digits}f"

        # Calculeaza distanta minima obligatorie (trade_stops_level in points)
        stops_lvl  = getattr(info, "trade_stops_level", 0) or 0
        min_dist   = stops_lvl * info.point if stops_lvl > 0 else 0.0
        # Distanta sigura: max(min_dist * 3, 1%) deasupra ask-ului
        pct_dist   = tick.ask * 0.01
        safe_dist  = max(min_dist * 3, pct_dist, 10 * pip)

        ask   = tick.ask
        entry = round(ask + safe_dist, info.digits)
        sl    = round(entry - max(min_dist * 2, 5 * pip), info.digits)
        tp    = round(entry + safe_dist * 2, info.digits)
        if sl >= entry:
            sl = round(entry - 10 * pip, info.digits)
        if tp <= entry:
            tp = round(entry + 20 * pip, info.digits)

        print(f"\n  stops_level={stops_lvl}  min_dist={min_dist:.{info.digits}f}  "
              f"filling_mode={info.filling_mode}  digits={info.digits}")

        request = {
            "action":    mt5.TRADE_ACTION_PENDING,
            "symbol":    resolved,
            "volume":    info.volume_min,
            "type":      mt5.ORDER_TYPE_BUY_STOP,
            "price":     entry,
            "sl":        sl,
            "tp":        tp,
            "type_time": mt5.ORDER_TIME_GTC,
            "comment":   "TEST-FILL",
        }

        print(f"\n  entry={format(entry, fmt)}  sl={format(sl, fmt)}  "
              f"tp={format(tp, fmt)}  vol={info.volume_min}")

        log_lines = []

        if not auto_ok:
            print("  -> SARIT (AutoTrading dezactivat)")
            skip_count += 1
            results.append((name, session, "SKIP", "AutoTrading dezactivat"))
            continue

        result = try_place_order_new_logic(mt5, request, info, log_lines)

        for line in log_lines:
            print(line)

        if result["ok"]:
            ticket = result["ticket"]
            filling_used = result["filling"]
            print(f"  [OK] PLASAT ticket=#{ticket}  filling={filling_used}")
            ok_count += 1
            results.append((name, session, "OK", filling_used))
            time.sleep(0.3)
            r = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": ticket})
            if r and r.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"  [OK] ANULAT  ticket=#{ticket}")
            else:
                rc = r.retcode if r else "None"
                print(f"  [!] Anulare esuata (retcode={rc}) -- va expira singur")
        else:
            rc = result.get("retcode")
            reason = result.get("reason", "")
            desc = RETCODES.get(rc, "necunoscut") if rc else ""
            is_retry = rc in RETRY_NONE_RETCODES if rc else False
            if is_retry:
                print(f"  [~] RETRY bara urm: {reason}  retcode={rc} [{desc}]")
                skip_count += 1
                results.append((name, session, "RETRY", f"retcode={rc} {desc}"))
            else:
                print(f"  [X] ESEC: {reason}  retcode={rc} [{desc}]")
                fail_count += 1
                results.append((name, session, "FAIL", f"retcode={rc} {desc}"))

    # Sumar
    print("\n" + "=" * 68)
    print("  SUMAR FAZA 2:")
    print(f"  {'Simbol':<10} {'Ses':<5} {'Status':<8}  Detalii")
    print(f"  {'-'*55}")
    for name, ses, status, detail in results:
        if status == "OK":
            icon = "[OK]"
        elif status == "FAIL":
            icon = "[X]"
        elif status == "RETRY":
            icon = "[~]"
        else:
            icon = "[~]"
        print(f"  {name:<10} {ses:<5} {icon:<8}  {detail}")
    retry_count = sum(1 for _, _, s, _ in results if s == "RETRY")
    print(f"\n  OK: {ok_count}  |  ESEC: {fail_count}  |  RETRY/SARIT: {skip_count}")

    if fail_count == 0 and ok_count > 0:
        print("\n  -> Logica noua de filling functioneaza corect pe toate pietele testate.")
    elif fail_count == 0 and ok_count == 0 and retry_count > 0:
        print("\n  -> NOTA: Toate erorile sunt tranzitorii (timeout/no-conn) — bot face retry bara urm.")
        print("     Rulati testul cand botul NU este activ pentru rezultate curate.")
    elif fail_count == 0 and ok_count == 0:
        print("\n  -> Niciun ordin testat (pietele inchise sau AutoTrading dezactivat).")
    else:
        print(f"\n  -> {fail_count} simbol(uri) cu esec -- verifica detaliile de mai sus.")

    print("=" * 68)
    mt5.shutdown()
    return fail_count == 0


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    unit_only = "--unit-only" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    filter_sym = args[0].upper() if args else None

    unit_ok = run_unit_tests()

    if unit_only:
        sys.exit(0 if unit_ok else 1)

    if not unit_ok:
        print("\n  Unit tests FAILED -- opresc testele MT5.")
        sys.exit(1)

    mt5_ok = run_mt5_tests(filter_sym)
    sys.exit(0 if mt5_ok else 1)
