"""
Previzualizarea dimensionarii pozitiei (acelasi calcul ca la ordine — position_sizing) pentru UI.

  GET /sizing/preview?symbol=EURUSD&fraction=0.2&risk_pct=0.01[&fixed_lots=0.05][&sl_distance=0.002]

Intoarce, separat:
  - account  : valorile SINCRONIZATE din MT5 (read-only): balance, equity, marja, moneda, levier, tip cont
  - symbol   : specificatiile simbolului din MT5: lot min/max/pas, tick, contract, stops level
  - inputs   : ce e CONFIGURAT manual (fractie, risc%, lot fix)
  - sl       : distanta SL folosita pentru exemplu (mediana SL-urilor reale recente pe simbol, din
               MT5; altfel ATR(14) M15 × 1.5; sau valoarea data)
  - result   : lantul complet capital -> risc tinta -> lot brut -> lot final -> risc real + marja
"""
from __future__ import annotations

import statistics
from datetime import datetime

from fastapi import APIRouter, HTTPException

import position_sizing as ps
from api import mt5_pool

router = APIRouter(prefix="/sizing", tags=["sizing"])


def _typical_sl(mt5, symbol: str) -> tuple[float | None, str]:
    try:
        tr = [t for t in mt5_pool.get_closed_trades(120)
              if t["symbol"] == symbol and t.get("sl") and t.get("entry_price")]
        d = [abs(t["entry_price"] - t["sl"]) for t in tr][-30:]
        if len(d) >= 3:
            return statistics.median(d), f"mediana SL-urilor reale ({len(d)} trade-uri MT5 pe {symbol})"
    except Exception:
        pass
    try:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 1, 60)
        if rates is not None and len(rates) > 15:
            trs = [max(r["high"], p["close"]) - min(r["low"], p["close"]) for p, r in zip(rates[:-1], rates[1:])]
            atr = sum(trs[-14:]) / 14
            return atr * 1.5, "ATR(14) M15 × 1.5 (fără trade-uri reale recente pe simbol)"
    except Exception:
        pass
    return None, "indisponibil"


@router.get("/preview")
def sizing_preview(symbol: str, fraction: float = 1.0, risk_pct: float = 0.01,
                   fixed_lots: float | None = None, sl_distance: float | None = None,
                   capital_sync_mt5: bool = True, capital_usd: float | None = None):
    symbol = symbol.strip().upper()
    try:
        with mt5_pool._LOCK:
            mt5 = mt5_pool._ensure_mt5()
            mt5.symbol_select(symbol, True)
            si = mt5.symbol_info(symbol)
            acc = mt5.account_info()
            tick = mt5.symbol_info_tick(symbol)
            sl_d, sl_src = (sl_distance, "valoare introdusă") if sl_distance else _typical_sl(mt5, symbol)
            price = (tick.ask if tick else None) or (si.ask if si else None) or 0
            margin_1 = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, symbol, 1.0, price) if price else None
    except mt5_pool.Mt5Unavailable as e:
        return {"connected": False, "error": str(e)}
    if si is None:
        raise HTTPException(404, f"Simbol inexistent în contul MT5 curent: {symbol}")

    account = None
    if acc is not None:
        account = {"balance": acc.balance, "equity": acc.equity, "margin": acc.margin,
                   "free_margin": acc.margin_free, "currency": acc.currency, "leverage": acc.leverage,
                   "is_demo": acc.trade_mode == 0, "login": acc.login, "server": acc.server,
                   "margin_call_pct": acc.margin_so_call, "stop_out_pct": acc.margin_so_so}
    vpu = ps.value_per_price_unit(si)
    symbol_spec = {"volume_min": si.volume_min, "volume_max": si.volume_max, "volume_step": si.volume_step,
                   "tick_size": si.trade_tick_size, "tick_value": si.trade_tick_value,
                   "contract_size": si.trade_contract_size, "digits": si.digits,
                   "stops_level_points": si.trade_stops_level, "currency_profit": si.currency_profit,
                   "value_per_price_unit": vpu, "price": price, "margin_per_lot": margin_1}

    equity = acc.equity if acc else None
    base = ps.capital_base(capital_sync_mt5, capital_usd, equity)
    frac = ps.clamp_fraction(fraction)
    capital = base * frac
    result: dict = {"capital_base": round(base, 2), "fraction": frac, "capital": round(capital, 2),
                    "mode": "fixed" if fixed_lots else "risk"}
    if sl_d:
        entry = price or 1.0
        sl = entry - sl_d
        r = ps.size_fixed(si, fixed_lots, entry, sl) if fixed_lots else ps.size_by_risk(si, entry, sl, capital, risk_pct)
        result.update(r)
        if fixed_lots:
            result["target_money"] = round(capital * risk_pct, 4)
        if margin_1 and r.get("lots"):
            result["margin_need"] = round(margin_1 * r["lots"], 2)
            if acc and acc.margin_free:
                result["margin_pct_free"] = round(100 * margin_1 * r["lots"] / acc.margin_free, 1)
        try:
            from live.global_guard import risk_cap_pct
            cap = risk_cap_pct()
        except Exception:
            cap = None
        result["risk_cap_pct"] = cap
        if cap and r.get("lots"):
            lots2, why = ps.apply_risk_cap(si, r["lots"], entry, sl, equity, cap)
            if why:
                vpu2 = ps.value_per_price_unit(si)
                result.update(lots=lots2, risk_cap_note=why,
                              risk_money=(lots2 * sl_d * vpu2) if (lots2 and vpu2) else None,
                              reason=why if not lots2 else result.get("reason"))
        if equity and result.get("risk_money"):
            result["risk_pct_equity"] = round(100 * result["risk_money"] / equity, 2)
        # lotul minim: cat ar trebui sa fie contul ca tinta sa ajunga la lotul minim
        if vpu and risk_pct > 0 and frac > 0:
            result["equity_for_target"] = round(si.volume_min * sl_d * vpu / (risk_pct * frac), 0)
    return {"connected": True, "error": None, "symbol": symbol, "synced_at": datetime.now().isoformat(timespec="seconds"),
            "account": account, "spec": symbol_spec,
            "inputs": {"fraction": frac, "risk_pct": risk_pct, "fixed_lots": fixed_lots,
                       "capital_sync_mt5": capital_sync_mt5, "capital_usd": capital_usd},
            "sl": {"distance": sl_d, "source": sl_src}, "result": result}
