# Special Engine + propunere de engine nou — cercetare (2026-11-04)

Analiza a fost făcută din patru unghiuri: statistical arbitrage, risc / portofoliu, execuție / costuri și cercetare
cantitativă. Toate testele folosesc aceleași reguli dure:
- date MT5 reale;
- costuri reale: spread live + 25% slippage + markup-ul contului + swap pe fiecare noapte;
- intrare la bara următoare (fără să vadă viitorul);
- train / test 70 / 30, verdict M0, rezultat pe ani și pe luni;
- toate variantele raportate, nu doar cea mai bună.

Ținta userului: **2–5% pe lună, cu probabilitate ridicată.**

## 1. Special Engine — de ce nu merge perechea opusă GBPUSD / EURUSD

Detalii în `docs/PAIR_HEDGE_RESEARCH.md`. Pe scurt:
- GBP long + EUR short e practic un short pe EURGBP, plătit cu două spread-uri;
- cele două piețe se mișcă aproape la fel, deci câștigul unui picior anulează pierderea celuilalt;
- trailing-ul până la 10R nu se folosește aproape niciodată.

Rezultat: −0,20R … 0R pe pereche, DEMOTE pe toate cele 6 variante.

**Îmbunătățiri testate:**

| Versiune | Ideea | Cel mai bun rezultat | Verdict |
|---|---|---|---|
| v2 | pairs trading pe EURGBP D1 (abatere de la medie, revenire) | +0,056R, 1,6 trade-uri/lună | OBSERVE |
| v3 confirm | GBPUSD Custom doar când EURUSD e în același trend (fără hedge) | +0,042R (test +0,097), 1,7/săpt | DEMOTE |
| v3 forță relativă | intrare doar pe moneda mai puternică | EURUSD +0,030R, 1,8/săpt | DEMOTE |
| v4 | EURGBP direct, pe H1 / H4 / D1 | H1 −0,08R; H4 ~0; D1 +0,05R | DEMOTE / OBSERVE |

**Concluzie Special Engine:** relația GBP/EUR conține puțină informație. Cel mai util e ca **filtru de confirmare** peste
Custom: drawdown-ul scade de la −35R la −25R, iar rezultatul trece de la −0,003R la +0,042R. Nu e destul pentru un
engine separat.

## 2. Căutarea unui engine nou

| # | Candidat | Sursa | Rezultat |
|---|---|---|---|
| A | RSI(2) mean reversion pe indici (D1) | Connors | portofoliu −0,002R; doar STOXX50 KEEP, 0,6 trade-uri/lună |
| B | Efectul de sfârșit / început de lună pe indici | literatura de anomalii de calendar | −0,06R, DEMOTE peste tot |
| C | Trend following Donchian 55/20, 21 de piețe | Turtle / CTA | −0,42R: **finanțarea overnight a CFD-urilor (~7–10%/an) distruge pozițiile ținute luni de zile** |
| F | ORB intraday la deschiderea fiecărei burse (logica Daily) | Crabel / Daily Engine | KEEP pe USTEC, XAUUSD, DE40, JP225; dar **2026 negativ pe aproape tot** |
| G | „Beat the Market” noise area | Zarattini, Aziz, Barbon 2024 (SFI 24-97), parametrii din lucrare | **USTEC KEEP, fiecare an 2021–2026 pozitiv**; US500 slăbit în 2025–2026; non-US ~0 / negativ |
| WF | **Portofoliu intraday adaptiv walk-forward** (68 de componente ORB + noise; trimestrial alege doar ce are edge pe trecut) | — | vezi mai jos |

**Walk-forward, complet out-of-sample** (nicio decizie nu folosește viitorul):

| Variantă | R/trade | Trade-uri/lună | La 0,5% risc: %/lună | DD | Ani pozitivi |
|---|---|---|---|---|---|
| regula centrală (24 luni, t ≥ 2) | +0,048 | 24 | 0,6% | −24% | 5/9 |
| 36 luni, t ≥ 1,5 | +0,048 | 59 | 1,4% | −39% | 7/9 |
| **+ filtru Crabel NR4, 36 luni** | **+0,101** (test +0,13) | 14 | **0,7%** | **−14%** | **8/9** |
| + fără zile după o zi foarte largă, 36 luni | +0,057 | 44 | 1,3% | −32% | 6/9 |

## 3. Verdict cinstit

- **Ținta de 2–5% pe lună „cu probabilitate ridicată” nu e atinsă de nicio variantă testată.** Cu riscul urcat la
  1–1,5% pe trade, media ajunge la 2–4% pe lună, dar doar ~55% din luni sunt pozitive, iar drawdown-ul e de 33–99%.
  2026 ar fi pierdut 18–80% din cont. Nu e un sistem de recomandat.
- **Cel mai bun raport randament / risc: walk-forward + NR4.** Dă ~0,7% pe lună la 0,5% risc (~1,4% pe lună la 1%),
  cu drawdown −14% / −27% și 8 din 9 ani pozitivi.
  - E ales dintre ~20 de variante, deci rezultatul live trebuie așteptat mai slab.
  - Recomandare: **SHADOW cel puțin 3 luni** înainte de orice ban real.
- **Constrângerea contului de ~206 $:** lotul minim pe indici (0,1) cu stop-uri ORB tipice înseamnă 1–3% risc pe
  trade, iar marja DE40 e ~145 $. Riscul de 0,5% nu se poate respecta pe acest cont; ar fi nevoie de ~1000 $+.

Scripturi: `scripts/research_special/` (common, daily_candidates, intraday_orb, orb_portfolio, noise_area,
walkforward, crabel_filter, special_v4) + `scripts/research_pair/special_v3.py`.
Rezultate brute: `data/research_special/*.json` (local).
