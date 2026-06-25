"""Test rapid AUDJPY + USDCHF"""
import sys, os, json, math
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backtest import DATA_DIR
from adapters.csv_source import CsvDataSource
from strategy.preparation import prepare_symbol_tf
from engine.portfolio import run_portfolio
import strategy.structure as _struct
import pandas as pd, numpy as np

with open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       'config', 'standard_profile.json')) as f:
    BASE_CFG = json.load(f)

SPREADS = {'AUDJPY': 1.2, 'USDCHF': 1.0}
src = CsvDataSource(DATA_DIR)

def score(te, tt, dd):
    if te <= 0 or tt < 20: return -999.0
    return te * math.sqrt(tt) - max(0, (-dd-35)*0.015)

def make_cfg(rsi_en):
    cfg = json.loads(json.dumps(BASE_CFG))
    cfg['optional_criteria']['rsi']['enabled'] = rsi_en
    if rsi_en:
        cfg['optional_criteria']['rsi']['buy_min'] = 40
        cfg['optional_criteria']['rsi']['buy_max'] = 65
        cfg['optional_criteria']['rsi']['sell_min'] = 35
        cfg['optional_criteria']['rsi']['sell_max'] = 60
    cfg['optional_criteria']['ema_alignment']['enabled'] = True
    cfg['optional_criteria']['body_strength'] = {'enabled': False, 'min_atr_ratio': 0.15}
    cfg['reward_ladder']['rr_if_3_criteria'] = 2.5
    cfg['reward_ladder']['rr_if_4_criteria'] = 3.5
    cfg['reward_ladder']['rr_if_5_criteria'] = 4.5
    cfg['reward_ladder']['rr_if_6_criteria'] = 5.5
    cfg['reward_ladder']['threshold_mid'] = 1
    cfg['reward_ladder']['threshold_top'] = 2
    cfg['reward_ladder']['threshold_max'] = 3
    cfg['account']['risk_per_trade_pct'] = 1.0
    cfg['account']['risk_per_trade_pct_all_criteria'] = 1.2
    return cfg

def make_params(symbol, direction, pw, flag, ib, be=False):
    return {
        'spread_pips': {symbol: SPREADS.get(symbol, 1.5)},
        'leverage': 30, 'start_balance': 1000,
        'expire_bars': 4, 'pullback_window': pw,
        'depth_range': None, 'skip_monday': False,
        'skip_hours': (), 'atr_max_pips': {},
        'max_day_consec_losses': 3, 'corr_pairs': {},
        'max_pos_per_symbol': 1, 'min_bars_between_same_symbol': 0,
        'symbol_sessions': {}, 'symbol_skip_hours': {},
        'skip_weekdays': set(), 'only_long': (direction == 'LONG'),
        'be_cfg': {'enabled': be, 'phase2_enabled': True, 'trigger_pct': 80,
                   'lock1_pct': 30, 'lock2_pct': 50, 'phase2_zone_pct': 40},
        'flag_cfg':       {'enabled': flag, 'r_ratio': 2.5, 'risk_pct': 0.01},
        'inside_bar_cfg': {'enabled': ib,   'r_ratio': 2.0, 'risk_pct': 0.01},
    }

def run_test(symbol, df, cfg, params):
    try:
        trades, equity, bal, _, _, _, split = run_portfolio({symbol: df}, cfg, params, verbose=False)
        if not trades: return None
        df_t = pd.DataFrame(trades)
        df_t['R']       = df_t['pnl_usd'] / df_t['risk_usd']
        df_t['entry_t'] = pd.to_datetime(df_t['time'])
        train = df_t[df_t['entry_t'] < split]
        test  = df_t[df_t['entry_t'] >= split]
        if len(df_t) < 40: return None
        eq = np.array([e['balance'] for e in equity])
        pk = np.maximum.accumulate(eq)
        dd = float(((eq-pk)/pk).min()*100) if len(eq) > 1 else 0.0
        te = float(test['R'].mean()) if len(test) else 0.0
        sig = df_t['signal_type'].value_counts().to_dict() if 'signal_type' in df_t.columns else {}
        return {
            'total': len(df_t), 'test_t': len(test), 'train_t': len(train),
            'train_exp': round(float(train['R'].mean()) if len(train) else 0, 4),
            'test_exp': round(te, 4), 'dd': round(dd, 1),
            'score': round(score(te, len(test), dd), 4),
            'pb': sig.get('pullback',0), 'fl': sig.get('flag',0), 'ib': sig.get('inside_bar',0),
            'split': str(split.date()),
        }
    except:
        return None

for sym in ['AUDJPY', 'USDCHF']:
    print(f'\n{"="*100}')
    print(f'  {sym}  M15+M30  -- sweep pw/dir/RSI/strat')
    print(f'{"="*100}')

    df = prepare_symbol_tf(src, sym, BASE_CFG, 'M15', 'M30')
    print(f'  Bare M15: {len(df)}')

    results = []

    # Pullback sweep
    for direction in ['LONG', 'BOTH']:
        for rsi_en, rsi_name in [(True,'rsi_on'), (False,'rsi_off')]:
            cfg = make_cfg(rsi_en)
            for pw in [6,8,10,12,14]:
                for (fn,ib,bn) in [(False,False,'pb_only'),(True,False,'pb+flag'),(False,True,'pb+IB'),(True,True,'all')]:
                    params = make_params(sym, direction, pw, fn, ib)
                    r = run_test(sym, df, cfg, params)
                    if r:
                        r.update({'dir': direction, 'rsi': rsi_name, 'pw': pw, 'strat': bn, 'part':'pullback'})
                        results.append(r)

    # Standalone
    orig = _struct.detect_setup
    _struct.detect_setup = lambda *a, **k: None
    try:
        for direction in ['LONG', 'BOTH']:
            for rsi_en, rsi_name in [(True,'rsi_on'), (False,'rsi_off')]:
                cfg = make_cfg(rsi_en)
                for (fn,ib,bn) in [(True,False,'flag_only'),(True,True,'f+IB')]:
                    params = make_params(sym, direction, 10, fn, ib)
                    r = run_test(sym, df, cfg, params)
                    if r:
                        r.update({'dir': direction, 'rsi': rsi_name, 'pw': 0, 'strat': bn, 'part':'standalone'})
                        results.append(r)
    finally:
        _struct.detect_setup = orig

    if not results:
        print('  Niciun rezultat.')
        continue

    df_r = pd.DataFrame(results)
    top = df_r[df_r['test_exp'] > 0].nlargest(10, 'score')
    if top.empty:
        top = df_r.nlargest(5, 'score')

    print(f'  {"#":>2}  {"part":>10}  {"strat":>10}  {"pw":>3}  {"dir":>4}  {"RSI":>7}  {"TRAIN":>8}  {"TEST":>8}  {"Tt":>4}  {"DD":>6}  {"score":>7}  {"pb/fl/ib":>10}  TARGET')
    for i, (_, r) in enumerate(top.iterrows(), 1):
        tgt = '>>TARGET' if r['test_exp'] >= 0.4 else ''
        print(f'  {i:>2}. [{r["part"]:>10}]  {r["strat"]:>10}  {int(r["pw"]):>3}  {r["dir"]:>4}  {r["rsi"]:>7}  {r["train_exp"]:>+8.4f}R  {r["test_exp"]:>+8.4f}R  {r["test_t"]:>4}t  {r["dd"]:>5.1f}%  {r["score"]:>7.3f}  {r["pb"]}/{r["fl"]}/{r["ib"]}  {tgt}')

    best = top.iloc[0]
    print(f'\n  BEST: test={best["test_exp"]:+.4f}R  strat={best["strat"]}  pw={int(best["pw"])}  dir={best["dir"]}  RSI={best["rsi"]}')
    print(f'  Split: {best["split"]}  |  {best["pb"]} pullback + {best["fl"]} flag + {best["ib"]} IB trades')
