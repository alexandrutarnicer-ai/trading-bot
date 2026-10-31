src = open(r"C:\trading-bot\scripts\research_daily\orb_test.py", encoding="utf-8").read()
exec(src.split("rows = []")[0])
import pandas as pd
base = dict(COST)
for sym, tz, oh, ch, n, mode, rr in [("US30","America/New_York","09:30","15:45",1,"brk",3.0),
                                     ("GER40","Europe/Berlin","09:00","17:15",1,"brk",None),
                                     ("US500","America/New_York","09:30","15:45",1,"brk",2.0)]:
    d = load(sym, tz)
    for mult in (0, 1, 1.5, 2, 3):
        COST[sym] = base[sym] * mult
        t = run(d, sym, oh, ch, n, mode, rr)
        s = summ(t)
        y = t.groupby(t.day.dt.year).r.agg(["count","mean"]).round(3)
        print(f"{sym} cost x{mult}: n={s['n']} exp={s['exp']:+.3f} train={s['train']:+.3f} test={s['test']:+.3f} t={s['tstat']:.2f} yrs={s['yrs_pos']}")
        if mult == 1: print("   pe ani:", dict(zip(y.index, y["mean"])), " | risc mediu (pret):", round((t.r*0+1).sum(),0))
