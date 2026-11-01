"""
Audit piete ↔ MT5 (DOAR citire, zero ordine): toate pietele folosite de Custom / AI / Daily / Noisy.

Per piata: simbolul real la broker (si alias-ul, ex. GER40 → DE40), daca e tranzactionabil
(trade_mode FULL), specificatiile MT5 (lot min/pas, tick size/value, digits, stops level, filling,
marja la lotul minim) COMPARATE cu constantele din cod folosite de backtest (strategy/signals._INDEX_PIP,
strategy/costs._INDEX_TICK / _CRYPTO_TICK), datele CSV pentru backtest (exista? ultima data) si
fereastra de istoric M1/M5 disponibila in terminal.

    python scripts/audit_markets_mt5.py          -> data/market_audit.json + rezumat in consola
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import MetaTrader5 as mt5  # noqa: E402

from strategy.signals import _INDEX_PIP, pip_size  # noqa: E402
from strategy.costs import _INDEX_TICK, _CRYPTO_TICK  # noqa: E402

ALIASES = {"GER40": ["GER40", "DE40", "DAX40"], "US100": ["US100", "USTEC", "NAS100"], "US30": ["US30", "DJ30"],
           "UK100": ["UK100", "FTSE100"], "JPN225": ["JPN225", "JP225"]}
TF_FILES = {"M15+M30": ["M15", "M30"], "H1+D1": ["H1", "D1"]}


def engine_markets() -> dict[str, list[str]]:
    """{simbol: [engine/sesiune, ...]} din configurarile ACTIVE."""
    out: dict[str, list[str]] = {}

    def add(sym, who):
        out.setdefault(sym, []).append(who)
    try:
        prof = json.load(open(os.path.join(ROOT, "data", "profiles", "standard.json"), encoding="utf-8"))
        for s in prof.get("sessions", []):
            for m in s.get("markets", []):
                add(m, f"Custom {s.get('id')} ({s.get('entry_tf')}+{s.get('trend_tf')}, "
                       f"{'LIVE' if s.get('execute_trades') else 'OBS'})")
    except Exception as e:
        print(f"[!] profil: {e}")
    try:
        ai = json.load(open(os.path.join(ROOT, "ai_engine", "config.json"), encoding="utf-8"))
        for m in ai.get("markets", []):
            add(m if isinstance(m, str) else m.get("symbol"), "AI Engine")
    except Exception as e:
        print(f"[!] ai config: {e}")
    try:
        from daily_engine.config import load_config as dl
        for m in dl()["markets"]:
            add(m["symbol"], f"Daily ({'activ' if m.get('enabled', True) else 'oprit'})")
    except Exception as e:
        print(f"[!] daily config: {e}")
    try:
        from noisy_engine.config import load_config as nl
        n = nl()
        add(n["symbol"], f"Noisy ({n['timeframe']}, {n['mode']})")
    except Exception as e:
        print(f"[!] noisy config: {e}")
    return out


def resolve(sym: str):
    for c in ALIASES.get(sym, [sym]):
        if mt5.symbol_info(c) is not None:
            return c
    return None


def csv_info(sym: str, entry_tf: str | None) -> dict:
    files = sorted(glob.glob(os.path.join(ROOT, "data", f"{sym}_*.csv")))
    tfs = {os.path.basename(f)[len(sym) + 1:-4]: f for f in files}
    last = {}
    for tf, f in tfs.items():
        try:
            with open(f, "rb") as fh:
                fh.seek(max(0, os.path.getsize(f) - 200))
                tail = fh.read().decode("utf-8", "ignore").strip().splitlines()[-1]
            last[tf] = tail.split(",")[0][:10]
        except Exception:
            last[tf] = "?"
    return {"tfs": sorted(tfs), "last": last}


def main() -> None:
    assert mt5.initialize(), mt5.last_error()
    acc = mt5.account_info()
    print(f"Cont {acc.login} {acc.server} {'DEMO' if acc.trade_mode == 0 else 'REAL'} · equity {acc.equity} · 1:{acc.leverage}")
    ti = mt5.terminal_info()
    print(f"Terminal: connected={ti.connected} trade_allowed={ti.trade_allowed} build={getattr(ti, 'build', '?')}")
    rows, problems = [], []
    for sym, users in sorted(engine_markets().items()):
        real = resolve(sym)
        r = {"symbol": sym, "broker_symbol": real, "used_by": users}
        if real is None:
            r["error"] = "simbol INEXISTENT la broker"
            problems.append(f"{sym}: inexistent la broker ({', '.join(users)})")
            rows.append(r)
            continue
        mt5.symbol_select(real, True)
        i = mt5.symbol_info(real)
        tick = mt5.symbol_info_tick(real)
        price = (tick.ask + tick.bid) / 2 if tick and tick.ask else None
        try:
            margin = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, real, i.volume_min, price) if price else None
        except Exception:
            margin = None
        r.update(trade_mode=i.trade_mode, tradable=i.trade_mode == 4, digits=i.digits, point=i.point,
                 tick_size=i.trade_tick_size, tick_value=i.trade_tick_value, vol_min=i.volume_min, vol_step=i.volume_step,
                 vol_max=i.volume_max, stops_level=i.trade_stops_level, freeze_level=i.trade_freeze_level,
                 filling=i.filling_mode, spread_pts=i.spread, margin_min_lot=round(margin, 2) if margin else None,
                 currency_profit=i.currency_profit, path=i.path)
        if not r["tradable"]:
            problems.append(f"{sym}: trade_mode={i.trade_mode} (nu e FULL) — {', '.join(users)}")
        # pip / tick folosite de backtest vs MT5
        code_pip = pip_size(sym)
        forexlike = sym not in _INDEX_PIP
        r["code_pip"] = code_pip
        if forexlike:
            exp = 0.01 if "JPY" in sym else 0.0001
            if abs(i.point * 10 - exp) > 1e-12 and abs(i.point - exp) > 1e-12:
                problems.append(f"{sym}: point MT5 {i.point} nu se potriveste cu pip-ul forex din cod {exp}")
        else:
            if sym in _INDEX_TICK:
                ts, tv = _INDEX_TICK[sym]
                r["code_tick"] = (ts, tv)
                if abs(ts - i.trade_tick_size) > 1e-12:
                    problems.append(f"{sym}: tick_size cod {ts} ≠ MT5 {i.trade_tick_size}")
                if i.trade_tick_value and abs(tv - i.trade_tick_value) / i.trade_tick_value > 0.10:
                    problems.append(f"{sym}: tick_value cod {tv} vs MT5 {i.trade_tick_value} (>10% — doar $ in backtest)")
            elif sym in _CRYPTO_TICK:
                r["code_tick"] = _CRYPTO_TICK[sym]
                if abs(_INDEX_PIP.get(sym, 0) - i.trade_tick_size) > 1e-12:
                    problems.append(f"{sym}: pip/tick in cod {_INDEX_PIP.get(sym)} ≠ tick_size MT5 {i.trade_tick_size} "
                                    f"(contract schimbat la broker? lot min {i.volume_min}) — afecteaza DOAR backtestul; live-ul citeste MT5")
                if i.trade_tick_value and abs(_CRYPTO_TICK[sym] - i.trade_tick_value) / i.trade_tick_value > 0.10:
                    problems.append(f"{sym}: tick_value in cod {_CRYPTO_TICK[sym]} ≠ MT5 {i.trade_tick_value} — doar backtest")
            elif any(u.startswith("Custom") for u in users):
                problems.append(f"{sym}: non-forex fara intrare in _INDEX_TICK/_CRYPTO_TICK (sizing gresit in backtest)")
        # date pentru backtest
        tfs = set()
        for u in users:
            if u.startswith("Custom"):
                tfs |= set(TF_FILES.get(u.split("(")[1].split(",")[0], []))
        ci = csv_info(sym, None)
        r["csv"] = ci
        missing = sorted(tfs - set(ci["tfs"]))
        if missing:
            problems.append(f"{sym}: CSV lipsa pentru backtest: {missing}")
        for tfn in ("M1", "M5"):
            rr = mt5.copy_rates_from_pos(real, getattr(mt5, f"TIMEFRAME_{tfn}"), 0, 1)
            r[f"has_{tfn}"] = rr is not None and len(rr) > 0
        rows.append(r)
        print(f"{'OK ' if r['tradable'] else '!! '}{sym:9s}→{real:9s} lot {i.volume_min}/{i.volume_step} · tick {i.trade_tick_size}/"
              f"{i.trade_tick_value:.5g} · marja min {r['margin_min_lot']} · stops {i.trade_stops_level} · CSV {','.join(ci['tfs']) or '—'} "
              f"(ultima {max(ci['last'].values()) if ci['last'] else '—'}) · {'; '.join(users)}")
    json.dump({"at": datetime.now().isoformat(timespec="seconds"), "account": acc.login, "markets": rows, "problems": problems},
              open(os.path.join(ROOT, "data", "market_audit.json"), "w", encoding="utf-8"), indent=1, default=str)
    print("\nPROBLEME:" if problems else "\nNicio problema de aliniere.")
    for p in problems:
        print("  - " + p)


if __name__ == "__main__":
    main()
