"""Selectia variantei Special TP pe TRAIN (imbunatatire fata de actual, mediata pe pietele cu TP fix) → raport pe TEST."""
import json, os
R = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "data", "research_tp", "tp_modes.json"), encoding="utf-8"))
fixed_tp = [k for k in R if k.startswith("Custom") or k.startswith("Noisy")]
names = [v for v in R[fixed_tp[0]] if v != "current"]
rows = []
for v in names:
    d_tr = [R[m][v]["train_exp"] - R[m]["current"]["train_exp"] for m in fixed_tp]
    d_te = [R[m][v]["test_exp"] - R[m]["current"]["test_exp"] for m in fixed_tp]
    dd = [R[m][v]["max_dd_R"] - R[m]["current"]["max_dd_R"] for m in fixed_tp]
    rows.append((sum(d_tr) / len(d_tr), min(d_tr), sum(d_te) / len(d_te), min(d_te), sum(dd) / len(dd), v))
rows.sort(reverse=True)
print("piete cu TP fix:", fixed_tp)
print(f"{'varianta':30} {'Δtrain med':>10} {'Δtrain min':>10} {'Δtest med':>10} {'Δtest min':>10} {'ΔDD med':>8}")
for a, b, c, d, e, v in rows:
    print(f"{v:30} {a:+10.4f} {b:+10.4f} {c:+10.4f} {d:+10.4f} {e:+8.1f}")
best = rows[0][-1]
print("\nALES pe train:", best)
for m in R:
    cur, b = R[m]["current"], R[m].get(best)
    if b:
        print(f"  {m:45} actual exp {cur['exp_R']:+.4f} (train {cur['train_exp']:+.4f} / test {cur['test_exp']:+.4f}) → "
              f"{b['exp_R']:+.4f} (train {b['train_exp']:+.4f} / test {b['test_exp']:+.4f}) | DD {cur['max_dd_R']}→{b['max_dd_R']} "
              f"| PF {cur['pf']}→{b['pf']} | avgW {cur['avg_win']}→{b['avg_win']} | ≥3R {cur['reach']['>=3R']}→{b['reach']['>=3R']}% "
              f"| exits {b['exits']} | giveback {b['giveback_R_on_locks']}")
json.dump({"ranking": rows, "chosen": best}, open(os.path.join(os.path.dirname(__file__), "..", "..", "data", "research_tp", "tp_select.json"), "w"), indent=1)
