"""
Test: sizing pe LOT FIX per sesiune pentru BOT (live/signal_generator.py).

Ruleaza din radacina proiectului:
    python scripts/test_bot_fixed_lots.py

Ce verifica:
1. _fixed_lots_active — toggle ON + valoare > 0 (si toate cazurile de OFF)
2. _snap_lots_to_broker — floor la volume_step (fara trap-ul float 0.5), clamp min/max
3. _fixed_lot_size — snap + risc USD corect + auto-reducere la marja + notificare
4. _resolve_order_lots — ruteaza corect fix vs dinamic; modul dinamic e BYTE-IDENTIC
   cu _calc_lots (zero schimbare cand lotul fix e oprit = default)
5. _lot_reduction_note — sufix Telegram doar cand s-a redus
6. _apply_profile_overrides — copiaza fixed_lots_enabled / fixed_lots din profil
7. Profilul standard real (fara campuri fixed_lots) → modul dinamic (backward-compat)
"""

import os, sys, json

# Consola Windows e cp1252 — fortam UTF-8 ca mesajele cu →/× sa nu strice printul.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live.signal_generator as sg
from live.signal_generator import (
    _fixed_lots_active, _snap_lots_to_broker, _fixed_lot_size,
    _resolve_order_lots, _lot_reduction_note, _calc_lots, _apply_profile_overrides,
)

PASS = 0
FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {msg}")
    else:
        FAIL += 1
        print(f"  FAIL  {msg}")


class MockLog:
    def info(self, *a): pass
    def debug(self, *a): pass
    def warning(self, msg): print(f"      (log.warning) {msg}")


log = MockLog()


# ---------------------------------------------------------------------------
# Mock MT5 (doar ce folosesc helper-ele de sizing)
# ---------------------------------------------------------------------------

class _Info:
    def __init__(self, vmin=0.01, vstep=0.01, vmax=100.0,
                 tick_value=1.0, tick_size=0.00001, digits=5):
        self.volume_min = vmin
        self.volume_step = vstep
        self.volume_max = vmax
        self.trade_tick_value = tick_value
        self.trade_tick_size = tick_size
        self.digits = digits


class _Acc:
    def __init__(self, margin_free, equity=None):
        self.margin_free = margin_free
        self.equity = equity if equity is not None else margin_free


class FakeMt5:
    """MT5 fals: marja LINIARA in volum (margin_rate $/lot)."""
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1

    def __init__(self, info=None, margin_free=100000.0, margin_rate=3600.0):
        self._info = info or _Info()
        self._acc = _Acc(margin_free)
        self._margin_rate = margin_rate

    def symbol_info(self, symbol):
        return self._info

    def account_info(self):
        return self._acc

    def order_calc_margin(self, otype, symbol, lots, price):
        return lots * self._margin_rate


def _set_mt5(fake):
    sg._mt5_exec = fake


def _restore_mt5(orig):
    sg._mt5_exec = orig


_ORIG_MT5 = sg._mt5_exec


# ---------------------------------------------------------------------------
# Test 1: _fixed_lots_active
# ---------------------------------------------------------------------------
print("\n[Test 1] _fixed_lots_active — toggle + valoare")
check(_fixed_lots_active({"fixed_lots_enabled": True, "fixed_lots": 0.5}) is True,
      "ON + 0.5 → activ")
check(_fixed_lots_active({"fixed_lots_enabled": True, "fixed_lots": 0}) is False,
      "ON + 0 → INACTIV (valoare nula)")
check(_fixed_lots_active({"fixed_lots_enabled": False, "fixed_lots": 0.5}) is False,
      "OFF + 0.5 → INACTIV (toggle oprit)")
check(_fixed_lots_active({}) is False, "camp lipsa → INACTIV (default)")
check(_fixed_lots_active({"fixed_lots_enabled": True, "fixed_lots": None}) is False,
      "ON + None → INACTIV")
check(_fixed_lots_active({"fixed_lots_enabled": True, "fixed_lots": "abc"}) is False,
      "ON + valoare invalida → INACTIV (fara exceptie)")


# ---------------------------------------------------------------------------
# Test 2: _snap_lots_to_broker
# ---------------------------------------------------------------------------
print("\n[Test 2] _snap_lots_to_broker — floor la step + clamp min/max")
info = _Info(vmin=0.01, vstep=0.01, vmax=100.0)
check(_snap_lots_to_broker(info, 0.5) == 0.5, "0.5 → 0.5 (fara trap float 0.5//0.01=49)")
check(_snap_lots_to_broker(info, 0.237) == 0.23, "0.237 → 0.23 (floor la step)")
check(_snap_lots_to_broker(info, 0.005) == 0.01, "0.005 → 0.01 (sub minim → minim)")
check(_snap_lots_to_broker(info, 200) == 100.0, "200 → 100 (peste max → max)")
info_xrp = _Info(vmin=100.0, vstep=1.0, vmax=10000.0)
check(_snap_lots_to_broker(info_xrp, 0.01) == 100.0,
      "XRPUSD: 0.01 introdus → 100 (volume_min mare domina)")


# ---------------------------------------------------------------------------
# Test 3: _fixed_lot_size — snap + risc USD + auto-reducere
# ---------------------------------------------------------------------------
print("\n[Test 3] _fixed_lot_size — normal (fara reducere)")
# EURUSD: entry 1.1000, sl 1.0950 → dist 0.005; tick_value/tick_size = 100000
fake = FakeMt5(_Info(), margin_free=100000.0, margin_rate=3600.0)
_set_mt5(fake)
lots, risk_usd, red = _fixed_lot_size("EURUSD", 1.1000, 1.0950, 1, 0.5, log)
check(lots == 0.5, f"lot fix pastrat = 0.5 (marja incape) [got {lots}]")
check(red is None, "reduction None cand marja incape")
check(abs(risk_usd - 250.0) < 1e-6, f"risc USD = 0.5×0.005×100000 = 250 [got {risk_usd}]")

print("\n[Test 3b] _fixed_lot_size — auto-reducere cand marja depaseste capitalul")
fake_small = FakeMt5(_Info(), margin_free=1000.0, margin_rate=3600.0)
_set_mt5(fake_small)
lots2, risk2, red2 = _fixed_lot_size("EURUSD", 1.1000, 1.0950, 1, 0.5, log)
# cap = 1000 * 0.80 = 800; need(0.5) = 1800 > 800; fitted = floor((800/3600)/0.01)*0.01 = 0.22
check(lots2 == 0.22, f"lot redus la 0.22 (incape sub 80% marja libera) [got {lots2}]")
check(red2 is not None, "reduction dict setat cand se reduce")
check(red2 and red2["requested"] == 0.5 and red2["final"] == 0.22,
      f"reduction {{requested:0.5, final:0.22}} [got {red2}]")
check(red2 and abs(red2["margin_need"] - 1800.0) < 1e-6,
      "reduction.margin_need = 1800 (marja pt lotul CERUT)")
check(abs(risk2 - (0.22 * 0.005 * 100000)) < 1e-6,
      f"risc USD recalculat pe lotul REDUS [got {risk2}]")

print("\n[Test 3c] _fixed_lot_size — MT5 indisponibil → fallback sigur")
_set_mt5(None)
lots3, risk3, red3 = _fixed_lot_size("EURUSD", 1.1000, 1.0950, 1, 0.5, log)
check(lots3 == 0.01 and risk3 is None and red3 is None,
      "MT5 None → (0.01, None, None) fara exceptie")
_set_mt5(fake)


# ---------------------------------------------------------------------------
# Test 4: _resolve_order_lots — rutare fix vs dinamic
# ---------------------------------------------------------------------------
print("\n[Test 4] _resolve_order_lots — dinamic (fix OFF) = _calc_lots BYTE-IDENTIC")
_set_mt5(FakeMt5(_Info(), margin_free=100000.0))
cfg_dyn = {"fixed_lots_enabled": False, "fixed_lots": 0.5}
res = _resolve_order_lots("EURUSD", 1.1000, 1.0950, 1, 1000.0, 0.01, cfg_dyn, log)
base = _calc_lots("EURUSD", 1.1000, 1.0950, 1000.0, 0.01)
check(res[0] == base[0] and res[1] == base[1],
      f"fix OFF → identic cu _calc_lots ({res[0]}, {res[1]}) == {base}")
check(res[2] is None, "fix OFF → reduction None (mereu)")

print("\n[Test 4b] _resolve_order_lots — fix ON → foloseste lotul fix, NU fractia/risc")
cfg_fix = {"fixed_lots_enabled": True, "fixed_lots": 0.5}
res_fix = _resolve_order_lots("EURUSD", 1.1000, 1.0950, 1, 1000.0, 0.01, cfg_fix, log)
check(res_fix[0] == 0.5, f"fix ON → 0.5 loturi (ignora capital×risc care ar da 0.02) [got {res_fix[0]}]")
check(res_fix[0] != base[0], "fix ON produce alt lot decat sizing-ul dinamic")


# ---------------------------------------------------------------------------
# Test 5: _lot_reduction_note
# ---------------------------------------------------------------------------
print("\n[Test 5] _lot_reduction_note")
check(_lot_reduction_note(None) == "", "None → string gol (fara sufix)")
note = _lot_reduction_note({"requested": 0.5, "final": 0.22,
                            "margin_need": 1800.0, "free_margin": 1000.0})
check("redus automat" in note and "0.5" in note and "0.22" in note,
      "reduction → sufix cu 'redus automat' + valorile")


# ---------------------------------------------------------------------------
# Test 6: _apply_profile_overrides copiaza fixed_lots_enabled / fixed_lots
# ---------------------------------------------------------------------------
print("\n[Test 6] _apply_profile_overrides — campurile fixed_lots ajung in session_cfg")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
RUNTIME_FILE = os.path.join(DATA_DIR, "active_profile_runtime.json")
_backup = None
if os.path.exists(RUNTIME_FILE):
    with open(RUNTIME_FILE, encoding="utf-8") as f:
        _backup = f.read()

try:
    profile = {
        "name": "test-fixedlots",
        "sessions": [{
            "session_key": "session1",
            "direction": "LONG",
            "fixed_lots_enabled": True,
            "fixed_lots": 0.30,
        }],
    }
    with open(RUNTIME_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f)

    base_cfg_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "standard_profile.json")
    with open(base_cfg_path, encoding="utf-8") as f:
        strat_cfg = json.load(f)

    session_cfg = {"session_key": "session1", "execute_trades": True}
    _apply_profile_overrides(session_cfg, strat_cfg, log)
    check(session_cfg.get("fixed_lots_enabled") is True,
          "fixed_lots_enabled copiat din profil")
    check(session_cfg.get("fixed_lots") == 0.30,
          f"fixed_lots copiat din profil [got {session_cfg.get('fixed_lots')}]")
    check(_fixed_lots_active(session_cfg) is True,
          "session_cfg rezultat → _fixed_lots_active True")

    # 6b: profil FARA campuri fixed_lots → dinamic (backward-compat)
    profile2 = {"name": "no-fixed", "sessions": [{"session_key": "session1", "direction": "LONG"}]}
    with open(RUNTIME_FILE, "w", encoding="utf-8") as f:
        json.dump(profile2, f)
    session_cfg2 = {"session_key": "session1", "execute_trades": True}
    _apply_profile_overrides(session_cfg2, json.loads(json.dumps(strat_cfg)), log)
    check("fixed_lots_enabled" not in session_cfg2,
          "profil fara camp → fixed_lots_enabled ABSENT (nu injectat)")
    check(_fixed_lots_active(session_cfg2) is False,
          "profil fara camp → sizing dinamic (backward-compat)")
finally:
    if _backup is not None:
        with open(RUNTIME_FILE, "w", encoding="utf-8") as f:
            f.write(_backup)
    elif os.path.exists(RUNTIME_FILE):
        os.remove(RUNTIME_FILE)


# ---------------------------------------------------------------------------
# Test 7: profilul standard real nu are fixed_lots activ (backward-compat)
# ---------------------------------------------------------------------------
print("\n[Test 7] Profil standard real — nu activeaza lotul fix nicaieri")
std_path = os.path.join(DATA_DIR, "profiles", "standard.json")
if os.path.exists(std_path):
    with open(std_path, encoding="utf-8") as f:
        std = json.load(f)
    any_active = any(
        bool(s.get("fixed_lots_enabled")) and float(s.get("fixed_lots") or 0) > 0
        for s in std.get("sessions", []))
    check(not any_active,
          "nicio sesiune din profilul standard nu are lot fix activ (comportament neschimbat)")
else:
    print("  SKIP  standard.json absent")


_restore_mt5(_ORIG_MT5)

# ---------------------------------------------------------------------------
print(f"\n{'='*60}")
print(f"REZULTAT: {PASS} PASS / {FAIL} FAIL")
print('='*60)
sys.exit(1 if FAIL else 0)
