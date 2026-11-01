"""
Noisy Engine — consultarea Trading Council (consiliul AI al aplicatiei, aceleasi surse si roluri ca
AI Engine: ollama / gemini dupa role_assignments). CONSULTATIV — nu decide nimic, nu plaseaza nimic.

Fiecare rol primeste ACELEASI fapte masurate (data/research_noisy/*.json) si raspunde la intrebarile
din brief; Head Trader-ul vede si opiniile celorlalti si formuleaza recomandarea (inclusiv dezacordurile).

    python scripts/research_noisy/council_consult.py  ->  data/research_noisy/council.json
"""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "data", "research_noisy")
sys.stdout.reconfigure(encoding="utf-8")

QUESTIONS = ("Raspunde in ROMANA, concis (max 12 puncte scurte), folosind DOAR cifrele din fapte, copiate exact. "
             "Spune: (1) ce piata ai alege si de ce; (2) ce rezolutie de date / timeframe; (3) ce strategie / ce NU; "
             "(4) ce filtre obligatorii; (5) model de risc (trade/loss limits, buget); (6) cum eviti overtrading si "
             "flip-flop Long/Short; (7) cand eviti piata (stiri, rollover, deschideri); (8) cand opresti engine-ul; "
             "(9) daca AI trebuie folosit si unde; (10) ce metrici urmaresti; (11) verdictul tau: GO / GO WITH "
             "CONDITIONS / NO-GO, cu conditiile exacte. Daca datele nu sustin ideea, spune-o direct.")

ROLES = {
    "technical": "Esti Analistul Tehnic al unui consiliu de trading. Te concentrezi pe microstructura pretului, "
                 "timeframe, semnale, momentum vs mean reversion, regim de piata.",
    "macro": "Esti Analistul Macro al unui consiliu de trading. Te concentrezi pe stiri (CPI, NFP, FOMC, BCE), "
             "sesiuni, lichiditate, comportamentul pietelor in jurul evenimentelor.",
    "risk": "Esti Risk Manager-ul unui consiliu de trading, cu drept de veto. Te concentrezi pe costuri de executie, "
            "drawdown, buget izolat, limite, protectii globale, scenarii de pierdere rapida. Contul e REAL, ~$206, "
            "partajat cu alte 3 engine-uri.",
}
HEAD = ("Esti Head Trader-ul consiliului. Ai primit faptele si opiniile Analistului Tehnic, Analistului Macro si "
        "Risk Manager-ului. Sintetizeaza: unde sunt de acord, unde NU (Opinia A -> Opinia B -> recomandarea ta), "
        "apoi recomandarea finala: GO / GO WITH CONDITIONS / NO-GO cu conditiile exacte. ROMANA, concis.")


def facts() -> dict:
    m = json.load(open(os.path.join(OUT, "market_metrics.json"), encoding="utf-8"))
    mk = []
    for s in m["symbols"]:
        if "spread_median" not in s:
            continue
        mk.append({"piata": s["symbol"], "lot_min": s["vol_min"], "marja_lot_min_usd": round(s["margin_min_lot"] or 0, 1),
                   "cost_dus_intors_lot_min_usd": round(s["cost_rt_usd_min_lot"], 3),
                   "cost_fata_de_range_M1": round(s["cost_vs_m1_range"], 3),
                   "tickuri_pe_minut": s["ticks_per_min_median"],
                   "spread_p99_minut_fata_de_median": round(s["spread_minute_p99_over_median"] or 0, 1)})
    edge = {}
    for tag in ("M1_A", "M1_B", "M5_A"):
        fn = {"M1_A": "edge_results_A.json", "M1_B": "edge_results_B.json", "M5_A": "edge_results_M5_A.json"}[tag]
        p = os.path.join(OUT, fn)
        if not os.path.exists(p):
            continue
        rows = []
        for r in json.load(open(p, encoding="utf-8")):
            for k in ("MOM", "MR", "TRD"):
                s = r.get(k) or {}
                if "net_R" in s:
                    rows.append({"piata": r["symbol"], "strategie": k, "trade_pe_zi": round(s["per_day"], 1),
                                 "brut_R": round(s["gross_R"], 3), "cost_R": round(s["cost_R"], 3),
                                 "net_R": round(s["net_R"], 3), "net_R_test": round(s["test"]["net_R"], 3)})
        edge[tag] = rows
    return {
        "context": ("Aplicatie de trading pe MT5, broker ICMarketsEU, cont REAL ~$206 partajat cu 3 engine-uri "
                    "(Custom pe reguli, AI Engine pe consiliu LLM, Daily ORB in shadow). Propunere: Noisy Engine = "
                    "engine de frecventa mare, 1 piata, multe trade-uri doar cand conditiile o justifica. "
                    "Python <-> terminal: ~0.013 ms per apel; latenta ordin catre server NEMASURATA (cont real, fara "
                    "ordine de test). Depth of Market: indisponibil pe toate simbolurile. Volum real: indisponibil "
                    "(doar tick volume). Istoric tick-uri: FX/metale din 2023-07, indici/crypto din 2023-11. "
                    "Comision in istoricul contului: 0 (spread median EURUSD 0.1 pip)."),
        "strategii_testate": ("Fixate dinainte, neoptimizate. MOM = breakout Donchian 20 bare, SL 1xATR, TP 1.5xATR. "
                              "MR = mean reversion EMA20 +/- 2xATR, TP la EMA20, SL 1.5xATR. TRD = continuare trend "
                              "EMA20/EMA100 dupa pullback, SL 1xATR, TP 2xATR. 12 luni, ore lichide, cost = spread "
                              "real pe ora + comision + slippage 25% spread x2. A = costuri masurate pe cont; B = + "
                              "comision Raw $7/lot pe FX/metale. R = multiplu din riscul (SL) trade-ului."),
        "piete": mk,
        "rezultate_edge": edge,
        "verificare_candidati_M5_mean_reversion": _cands(),
        "constrangeri_cont": ("Equity ~$206. Limita globala de risc pe trade 2%. XAUUSD: marja lotului minim ~$194 "
                              "(aproape tot contul), risc la SL tipic M5 (1.5xATR) ~ $5.5 = ~2.7% > limita 2%. "
                              "USDJPY/EURUSD: marja ~$33-37, risc lot minim ~$0.4. Pragul de semnificatie corectat "
                              "pentru 72 de combinatii testate: t >= 2.98."),
    }


def _cands() -> dict:
    p = os.path.join(OUT, "candidates.json")
    if not os.path.exists(p):
        return {}
    c = json.load(open(p, encoding="utf-8"))
    return {sym: {k: {"net_R": round(v["net_R"], 3), "t_stat": round(v["t_stat"], 2), "P_edge_pozitiv": round(v["p_edge_pos_boot"], 2),
                      "trimestre_pozitive": v["quarters_pos"], "max_DD_R": round(v["max_dd_R"], 1),
                      "serie_max_pierderi": v["max_loss_streak"], "trade_pe_zi": round(v["per_day"], 1)}
                  for k, v in d.items()} for sym, d in c.items()}


def main() -> None:
    from ai_engine.config import load_config, load_keys
    from ai_engine.providers import ProviderRegistry
    cfg = load_config()
    reg = ProviderRegistry(cfg.get("providers", {}), load_keys())
    assign = cfg.get("role_assignments", {})
    usable = reg.usable_sources()
    f = facts()
    payload = json.dumps(f, ensure_ascii=False)

    all_gemini = os.environ.get("COUNCIL_ALL_GEMINI") == "1"

    def ask_gemini_full(system: str, user: str) -> str:
        """Gemini cu „gandirea” dezactivata si limita mare: adaptorul de productie (maxOutputTokens 2000)
        taie raspunsurile lungi ale gemini-2.5-flash (bugetul e consumat de gandire)."""
        from ai_engine.providers import _http_json
        inst = reg._instances["gemini"]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{inst.model}:generateContent"
        payload = {"system_instruction": {"parts": [{"text": system}]},
                   "contents": [{"role": "user", "parts": [{"text": user}]}],
                   "generationConfig": {"temperature": 0.3, "maxOutputTokens": 6000,
                                        "thinkingConfig": {"thinkingBudget": 0}}}
        out = _http_json(url, payload, {"x-goog-api-key": inst.api_key}, 180, "gemini")
        cand = out["candidates"][0]
        text = "".join(p.get("text", "") for p in cand["content"]["parts"]).strip()
        if cand.get("finishReason") != "STOP":
            text += f"\n[finishReason={cand.get('finishReason')}]"
        return text

    def ask(role_src: str, system: str, user: str) -> tuple[str, str]:
        if all_gemini:
            t0 = time.time()
            return ask_gemini_full(system, user), f"gemini-full ({time.time() - t0:.0f}s)"
        order = [role_src] + [s for s in usable if s != role_src]
        last = ""
        for name in order:
            inst = reg._instances.get(name)
            if inst is None:
                continue
            try:
                t0 = time.time()
                txt = inst.chat(system, user).strip()
                return txt, f"{name} ({time.time() - t0:.0f}s)"
            except Exception as e:
                last = f"{name}: {e}"
        return f"INDISPONIBIL ({last})", "-"

    out = {"facts": f, "opinions": {}}
    for role, system in ROLES.items():
        txt, src = ask(assign.get(role, "ollama"), system, "FAPTE:\n" + payload + "\n\n" + QUESTIONS)
        out["opinions"][role] = {"source": src, "text": txt}
        print(f"\n===== {role} [{src}] =====\n{txt}", flush=True)
    others = "\n\n".join(f"[{r}] {o['text']}" for r, o in out["opinions"].items())
    txt, src = ask(assign.get("head_trader", "gemini"), HEAD,
                   "FAPTE:\n" + payload + "\n\nOPINII:\n" + others + "\n\n" + QUESTIONS)
    out["opinions"]["head_trader"] = {"source": src, "text": txt}
    print(f"\n===== head_trader [{src}] =====\n{txt}", flush=True)
    with open(os.path.join(OUT, "council_gemini.json" if all_gemini else "council.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
