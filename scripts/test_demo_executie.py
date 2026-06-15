"""
test_demo_executie.py -- Verificare executie ordine pe cont Demo MT5
=====================================================================
Plaseaza un ordin BUY_STOP minimal pe fiecare piata, confirma plasarea
si il anuleaza imediat. Afiseaza diagnostic complet la orice eroare.

Utilizare:
  python scripts/test_demo_executie.py               # testeaza toate pietele
  python scripts/test_demo_executie.py EURUSD        # testeaza un singur simbol
  python scripts/test_demo_executie.py --check-only  # verifica disponibilitate fara ordine

Ordine plasate: BUY_STOP la 0.3% deasupra ask-ului curent (nu se triggereaza).
Fiecare ordin este anulat imediat dupa confirmare.
"""

import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import MetaTrader5 as mt5
except ImportError:
    print("EROARE: MetaTrader5 nu e instalat. Ruleaza: pip install MetaTrader5")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Retcodes comune MT5 pentru diagnostic
# ---------------------------------------------------------------------------
RETCODES = {
    10004: "Requote",
    10006: "Cerere respinsa",
    10007: "Cerere anulata de trader",
    10008: "Ordin plasat",
    10009: "Cerere finalizata (DONE)",
    10010: "Executat partial",
    10011: "Eroare procesare cerere",
    10012: "Cerere expirata",
    10013: "Pret invalid",
    10014: "Stop-uri invalide (SL/TP prea aproape de pret)",
    10015: "Volum invalid",
    10016: "Stop-uri invalide",
    10017: "Tranzactionare dezactivata",
    10018: "Piata inchisa",
    10019: "Fonduri insuficiente",
    10020: "Pret schimbat",
    10021: "Nu exista cotatii",
    10022: "Ordin invalid",
    10023: "Expirare invalida",
    10024: "Prea multe ordine",
    10025: "Tip operatiune neacceptat",
    10026: "AutoTrading dezactivat de SERVER",
    10027: "AutoTrading dezactivat de CLIENT (butonul din MT5)",
    10028: "Ordin blocat pentru procesare",
    10029: "Anulat deja",
    10030: "Tip umplere (filling) nepermis",
    10031: "Fara conexiune",
    10032: "Operatiune permisa numai la piete deschise",
    10033: "Prea multe ordine pending",
    10034: "Volum total ordine depasit",
    10035: "Tipul de ordin incorect",
    10036: "Pozitia modificata deja",
    10038: "Pozitia inchisa deja",
    10039: "Ordine de inchidere duplicat",
}

# ---------------------------------------------------------------------------
# Toate pietele noastre cu fallback-uri (ca in sesiunile live)
# ---------------------------------------------------------------------------
ALL_MARKETS = [
    # (name, [alias1, alias2, ...], session_label, category)
    ("EURUSD", ["EURUSD"],                                                 "S1",    "FX"),
    ("GBPUSD", ["GBPUSD"],                                                 "S1",    "FX"),
    ("EURJPY", ["EURJPY"],                                                 "S1",    "FX"),
    ("USDJPY", ["USDJPY"],                                                 "S2",    "FX"),
    ("AUDJPY", ["AUDJPY"],                                                 "S2",    "FX"),
    ("NZDJPY", ["NZDJPY"],                                                 "S2",    "FX"),
    ("USDCHF", ["USDCHF"],                                                 "S5",    "FX"),
    ("BTCUSD", ["BTCUSD", "BTC/USD", "BTCUSDT"],                          "S3",    "CRYPTO"),
    ("GER40",  ["GER40", "GER40.cash", "DAX40", "DAX30", "DE30", "DE40"], "S4/S5", "INDEX"),
    ("US30",   ["US30", "US30.cash", "DJ30", "DJIA", "DJI30"],            "S6",    "INDEX"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resolve_symbol(fallbacks):
    """Gaseste primul alias disponibil si selectabil in MT5."""
    for alias in fallbacks:
        if mt5.symbol_select(alias, True):
            info = mt5.symbol_info(alias)
            if info is not None:
                return alias
    return None


def pip_size(symbol, info):
    """Marimea minima relevanta pentru calcule de distanta."""
    if any(x in symbol for x in ("BTC", "ETH", "LTC", "XRP")):
        return info.trade_tick_size if info.trade_tick_size > 0 else 0.01
    if any(x in symbol for x in ("GER", "DAX", "DE30", "DE40", "US30", "DJ", "DJIA")):
        return 1.0
    if symbol.endswith("JPY"):
        return 0.01
    return 0.0001


def build_test_order(resolved, info, tick):
    """
    Construieste parametrii unui ordin BUY_STOP de test.
    Entry = ask + 0.3% (nu se va triggera in cateva minute).
    SL = entry - 0.2%, TP = entry + 0.4%.
    """
    if tick is None or info is None:
        return None

    ask = tick.ask
    d   = info.digits

    entry = round(ask * 1.003, d)
    sl    = round(entry * 0.998, d)
    tp    = round(entry * 1.004, d)

    pip = pip_size(resolved, info)
    if entry <= ask:
        entry = round(ask + 10 * pip, d)
    if sl >= entry:
        sl = round(entry - 10 * pip, d)
    if tp <= entry:
        tp = round(entry + 20 * pip, d)

    return {
        "action":    mt5.TRADE_ACTION_PENDING,
        "symbol":    resolved,
        "volume":    info.volume_min,
        "type":      mt5.ORDER_TYPE_BUY_STOP,
        "price":     entry,
        "sl":        sl,
        "tp":        tp,
        "type_time": mt5.ORDER_TIME_GTC,
        "comment":   "TEST-DEMO",
    }


def try_place_order(request):
    """
    Incearca plasarea ordinului cu toate modurile de umplere.
    Returneaza dict cu rezultatul complet.
    """
    fill_modes = [
        ("RETURN", mt5.ORDER_FILLING_RETURN),
        ("FOK",    mt5.ORDER_FILLING_FOK),
        ("IOC",    mt5.ORDER_FILLING_IOC),
    ]

    last_retcode = None
    last_comment = ""
    last_error   = None

    for fill_name, fill_val in fill_modes:
        request["type_filling"] = fill_val
        res = mt5.order_send(request)

        if res is None:
            err = mt5.last_error()
            last_error = err
            print(f"    filling={fill_name:<6} -> None  last_error={err}")
            continue

        last_retcode = res.retcode
        last_comment = res.comment
        last_error   = mt5.last_error()

        if res.retcode == mt5.TRADE_RETCODE_DONE:
            return {"ok": True, "ticket": res.order, "filling": fill_name}

        desc = RETCODES.get(res.retcode, "eroare necunoscuta")
        print(f"    filling={fill_name:<6} -> retcode={res.retcode}  ({res.comment})  [{desc}]")

        if res.retcode != 10030:
            break

    # Ultima sansa: fara type_filling (MT5 alege implicit)
    req_no_fill = {k: v for k, v in request.items() if k != "type_filling"}
    res = mt5.order_send(req_no_fill)
    if res is not None:
        last_retcode = res.retcode
        last_comment = res.comment
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            return {"ok": True, "ticket": res.order, "filling": "NONE(implicit)"}
        desc = RETCODES.get(res.retcode, "eroare necunoscuta")
        print(f"    filling=NONE   -> retcode={res.retcode}  ({res.comment})  [{desc}]")
    else:
        last_error = mt5.last_error()
        print(f"    filling=NONE   -> None  last_error={last_error}")

    return {
        "ok":         False,
        "retcode":    last_retcode,
        "comment":    last_comment,
        "last_error": last_error,
    }


def cancel_order(ticket):
    """Anuleaza un ordin pending dupa ticket."""
    res = mt5.order_send({
        "action": mt5.TRADE_ACTION_REMOVE,
        "order":  ticket,
    })
    return res is not None and res.retcode == mt5.TRADE_RETCODE_DONE


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    check_only = "--check-only" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if args:
        target = args[0].upper()
        markets_to_test = [(n, f, s, c) for (n, f, s, c) in ALL_MARKETS if n == target]
        if not markets_to_test:
            markets_to_test = [(target, [target], "?", "?")]
    else:
        markets_to_test = ALL_MARKETS

    print("=" * 72)
    print("  TEST EXECUTIE DEMO -- MT5")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    # --- Conectare MT5 ---
    if not mt5.initialize():
        print(f"\n  EROARE: mt5.initialize() esuat -- {mt5.last_error()}")
        print("  Verifica ca MT5 terminal este deschis si logat.")
        sys.exit(1)

    acc = mt5.account_info()
    if acc is None:
        print(f"\n  EROARE: nu am putut citi info cont -- {mt5.last_error()}")
        mt5.shutdown()
        sys.exit(1)

    tip = "DEMO [OK]" if acc.trade_mode == 0 else "!!! LIVE -- STOP !!!"
    print(f"\n  Cont:     {acc.login} @ {acc.server}")
    print(f"  Tip:      {tip}")
    print(f"  Balance:  ${acc.balance:.2f}   Equity: ${acc.equity:.2f}")
    print(f"  Currency: {acc.currency}")

    if acc.trade_mode != 0:
        print("\n  STOP: contul nu este DEMO. Iesire pentru siguranta.")
        mt5.shutdown()
        sys.exit(1)

    # --- AutoTrading check ---
    term     = mt5.terminal_info()
    auto_ok  = bool(term and getattr(term, "trade_allowed", False))
    conn_ok  = bool(term and getattr(term, "connected", False))

    print(f"\n  Conexiune MT5:  {'DA [OK]' if conn_ok else 'NU [X]'}")
    print(f"  AutoTrading:    {'DA [OK]' if auto_ok else 'NU [X]  <- BUTONUL AutoTrading din MT5 e DEZACTIVAT!'}")
    print(f"  Trade allowed:  {'DA [OK]' if acc.trade_allowed else 'NU [X]'}")

    if not auto_ok:
        print()
        print("  ATENTIE: AutoTrading dezactivat in terminal MT5.")
        print("  Activeaza: toolbar MT5 -> butonul [AutoTrading] (sau Alt+A)")
        print("  Sau: Tools -> Options -> Expert Advisors -> 'Allow automated trading'")
        print("  Ordine de test NU vor putea fi plasate pana la activare.")

    # ---------------------------------------------------------------------------
    # Faza 1: Verificare disponibilitate simboluri
    # ---------------------------------------------------------------------------
    print()
    print(f"  {'#':<3} {'Piata':<10} {'Ses':<6} {'Cat':<7} {'Rezolvat':<14} "
          f"{'Bid':<13} {'Ask':<13} {'Spread':>6}  {'VolMin':>7}  Digits  Status")
    print(f"  {'-'*100}")

    sym_data = {}

    for idx, (name, fallbacks, session, category) in enumerate(markets_to_test, 1):
        resolved = resolve_symbol(fallbacks)

        if resolved is None:
            tried = " / ".join(fallbacks)
            print(f"  {idx:<3} {name:<10} {session:<6} {category:<7} {'---':<14} "
                  f"{'---':<13} {'---':<13} {'---':>6}  {'---':>7}  {'---':>6}  "
                  f"[X] NEGASIT (incercat: {tried})")
            sym_data[name] = {"resolved": None, "available": False}
            continue

        info = mt5.symbol_info(resolved)
        tick = mt5.symbol_info_tick(resolved)

        bid_s    = f"{tick.bid:.{info.digits}f}" if tick and info else "---"
        ask_s    = f"{tick.ask:.{info.digits}f}" if tick and info else "---"
        spread_s = f"{info.spread}"    if info else "---"
        vol_s    = f"{info.volume_min}" if info else "---"
        digits_s = f"{info.digits}"    if info else "---"

        issues = []
        if tick is None:
            issues.append("piata inchisa/fara tick")
        if info and info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
            issues.append("trade_mode=DISABLED")

        if not issues:
            status = "OK"
        else:
            status = "[!] " + " | ".join(issues)

        display_resolved = resolved if len(resolved) <= 13 else resolved[:13]
        alias_tag = f" ({resolved})" if resolved != name else ""

        print(f"  {idx:<3} {name:<10} {session:<6} {category:<7} {display_resolved:<14} "
              f"{bid_s:<13} {ask_s:<13} {spread_s:>6}  {vol_s:>7}  {digits_s:>6}  {status}{alias_tag}")

        sym_data[name] = {
            "resolved":  resolved,
            "info":      info,
            "tick":      tick,
            "available": tick is not None and (
                info is None or info.trade_mode != mt5.SYMBOL_TRADE_MODE_DISABLED
            ),
        }

    if check_only:
        print()
        available = sum(1 for v in sym_data.values() if v.get("available"))
        print(f"  SUMAR: {available}/{len(sym_data)} piete disponibile (--check-only, fara ordine)")
        mt5.shutdown()
        return

    # ---------------------------------------------------------------------------
    # Faza 2: Plasare + anulare ordine test
    # ---------------------------------------------------------------------------
    print()
    print("=" * 72)
    print("  PLASARE ORDINE TEST  (BUY_STOP minimal, anulare imediata)")
    print("  Entry la 0.3% deasupra pretului curent -- nu se triggereaza")
    print("=" * 72)

    ok_count   = 0
    fail_count = 0
    skip_count = 0

    for name, fallbacks, session, category in markets_to_test:
        data = sym_data.get(name, {})
        print(f"\n  [{name}]  ({session}  {category})")

        if not data.get("resolved"):
            print(f"  -> SARIT -- simbol negasit in MT5")
            skip_count += 1
            continue

        resolved = data["resolved"]
        info     = data["info"]
        tick     = data["tick"]

        if not data.get("available"):
            print(f"  -> SARIT -- tick indisponibil (piata probabil inchisa)")
            skip_count += 1
            continue

        if not auto_ok:
            print(f"  -> SARIT -- AutoTrading dezactivat in MT5 terminal")
            skip_count += 1
            continue

        request = build_test_order(resolved, info, tick)
        if request is None:
            print(f"  -> SARIT -- nu am putut construi ordinul (info/tick lipsa)")
            skip_count += 1
            continue

        fmt = f".{info.digits}f"
        print(f"  Ordin: BUY_STOP  vol={info.volume_min}  "
              f"entry={format(request['price'], fmt)}  "
              f"SL={format(request['sl'], fmt)}  "
              f"TP={format(request['tp'], fmt)}")
        print(f"  (ask curent={format(tick.ask, fmt)}  "
              f"spread={info.spread}  filling_mode={info.filling_mode})")

        result = try_place_order(request)

        if result["ok"]:
            ticket = result["ticket"]
            ok_count += 1
            print(f"  [OK] PLASAT   ticket=#{ticket}  filling={result['filling']}")
            time.sleep(0.3)
            if cancel_order(ticket):
                print(f"  [OK] ANULAT   ticket=#{ticket}  (test complet OK)")
            else:
                err = mt5.last_error()
                print(f"  [!] Anulare esuata (last_error={err}) -- va expira singur in ~3 min")
        else:
            fail_count += 1
            retcode = result.get("retcode")
            desc    = RETCODES.get(retcode, "necunoscut") if retcode else "---"
            print(f"  [X] ESEC PLASARE")
            print(f"      retcode:    {retcode}  [{desc}]")
            print(f"      comment:    {result.get('comment', '---')}")
            print(f"      last_error: {result.get('last_error', '---')}")
            if retcode == 10026:
                print(f"      -> AutoTrading dezactivat SERVER: contacteaza brokerul")
            elif retcode == 10027:
                print(f"      -> AutoTrading dezactivat CLIENT: butonul AutoTrading din MT5 toolbar")
            elif retcode == 10018:
                print(f"      -> Piata inchisa: normal in afara orelor de tranzactionare")
            elif retcode == 10013:
                print(f"      -> Pret invalid: entry prea aproape de pretul curent (min stops distance)")
            elif retcode in (10014, 10016):
                print(f"      -> Stop-uri invalide: SL/TP prea aproape de entry")
            elif retcode == 10030:
                print(f"      -> Filling: brokerul nu accepta niciunul din RETURN/FOK/IOC")
            elif retcode == 10017:
                print(f"      -> Tranzactionare dezactivata pentru acest simbol")

    print()
    print("=" * 72)
    print(f"  SUMAR FINAL:")
    print(f"    [OK] Plasat + anulat: {ok_count}")
    print(f"    [X]  Esec:            {fail_count}")
    print(f"    [~]  Sarit:           {skip_count}")
    if fail_count == 0 and ok_count > 0:
        print(f"  -> Executia demo functioneaza corect pe toate pietele testate.")
    elif fail_count == 0 and ok_count == 0:
        print(f"  -> Niciun ordin plasat (pietele inchise sau AutoTrading dezactivat).")
    else:
        print(f"  -> {fail_count} piata/piete cu probleme -- vezi detaliile de mai sus.")
    print("=" * 72)
    print()

    mt5.shutdown()


if __name__ == "__main__":
    main()
