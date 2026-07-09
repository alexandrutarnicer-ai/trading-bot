"""
ai_engine.report — vizualizare rapida a activitatii motorului AI.

Rulare:
  python -m ai_engine.report              # scorecard + ultimele decizii
  python -m ai_engine.report --councils   # + rationamentul complet al ultimelor consilii
"""

from __future__ import annotations

import json
import argparse

from ai_engine.ledger import Ledger


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--councils", action="store_true", help="afiseaza transcripturi")
    ap.add_argument("--limit", type=int, default=15)
    args = ap.parse_args()

    led = Ledger()
    sc = led.scorecard()
    print("=== SCORECARD AI ENGINE ===")
    for k, v in sc.items():
        print(f"  {k:14s}: {v}")

    print(f"\n=== ULTIMELE {args.limit} DECIZII ===")
    rows = led.con.execute(
        "SELECT id, ts, symbol, action, entry, sl, tp, confidence, exec_status, "
        "exec_detail, rationale FROM decisions ORDER BY id DESC LIMIT ?",
        (args.limit,)).fetchall()
    for r in rows:
        (did, ts, sym, act, entry, sl, tp, conf, st, detail, rat) = r
        line = f"  #{did} {ts} {sym:7s} {act:10s} conf={conf}% [{st}]"
        if entry:
            line += f" entry={entry} sl={sl} tp={tp}"
        print(line)
        print(f"      {(rat or '')[:150]}")
        if detail and st != "placed":
            print(f"      -> {detail[:120]}")

    out = led.con.execute(
        "SELECT o.ts, o.symbol, o.status, o.result_r, o.pnl_usd FROM outcomes o "
        "ORDER BY o.id DESC LIMIT ?", (args.limit,)).fetchall()
    if out:
        print(f"\n=== ULTIMELE OUTCOMES ===")
        for (ts, sym, st, rr, pnl) in out:
            rr_s  = f"{rr:+.2f}R" if rr is not None else "?"
            pnl_s = f"{pnl:+.2f}$" if pnl is not None else ""
            print(f"  {ts} {sym:7s} {st:9s} {rr_s} {pnl_s}")

    if args.councils:
        print(f"\n=== ULTIMELE CONSILII (transcript) ===")
        rows = led.con.execute(
            "SELECT id, ts, symbol, trigger, transcript, duration_s FROM councils "
            "ORDER BY id DESC LIMIT 3").fetchall()
        for (cid, ts, sym, trig, tr, dur) in rows:
            print(f"\n--- consiliu #{cid} {ts} {sym} (trigger: {trig}, {dur}s) ---")
            try:
                t = json.loads(tr)
                for role, view in t.items():
                    print(f"  [{role.upper()}]")
                    if isinstance(view, dict):
                        for k, v in view.items():
                            print(f"    {k}: {v}")
                    else:
                        print(f"    {view}")
            except Exception:
                print(f"  {tr[:500]}")
    led.close()


if __name__ == "__main__":
    main()
