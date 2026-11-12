# Special Engine — portofoliu intraday adaptiv + noise area (SHADOW, 2026-11-05)

> **Stare (2026-11-12): pregătit pentru Live, doar pe `alex-live`.** Fiecare piață are modul ei (LIVE / SHADOW / PAUZĂ,
> implicit SHADOW). Ordinele reale trec DOAR prin `special_engine/executor.py` (magic 660001); pe cont real, doar cu
> „Special Engine” deblocat în Settings → Trading LIVE. Activarea e decizia ta — vezi §7.

## 1. De unde vine

**Cercetarea din 04.11** (`docs/SPECIAL_ENGINE_RESEARCH.md`):
- au fost respinse: perechea GBP/EUR opusă, RSI(2), efectul de sfârșit de lună și trend-following-ul pe CFD (swap-ul
  de ~7–10% pe an mănâncă tot);
- au rămas: ORB intraday și „Beat the Market” (Zarattini, Aziz, Barbon 2024, SFI WP 24-97);
- cea mai bună combinație: portofoliul walk-forward + filtrul Crabel NR4.

**Validarea dură din 05.11** (`scripts/research_special/validate_special.py`, rezultate în
`data/research_special/validate_special.json`):

| Verificare | Rezultat |
|---|---|
| Look-ahead în selecția trimestrială | niciunul: aserția trece pe fiecare trimestru (fiecare selecție vede doar trade-uri intrate înainte de începutul trimestrului) |
| Sensibilitate, 64 de configurații (fereastră 24 / 30 / 36 / 42 luni × t 1,25–2,0 × NR4 / NR5 / NR7 / fără) | **NR4 e singurul filtru robust:** toate cele 16 configurații sunt pozitive, mediana pe test e +0,026R. NR5 / NR7 sunt negative pe test. Configurația pre-înregistrată pe 04.11 (NR4, 36 luni, t ≥ 1,5) e în **platoul** pozitiv. |
| Stres de cost (−0,03 / −0,05 / −0,10R pe trade) | +0,071 / +0,051 / +0,001R: edge-ul e real, dar **subțire față de costuri** |
| Regimuri (volatilitatea US500, tercile) | A: +0,123 (mare) / +0,160 (medie) / **−0,005 (scăzută)**; B: stabil (+0,06…+0,07) |
| Benchmark | ORB pe toate componentele fără selecție: +0,008R; NOISE pe toate piețele: −0,004R → **selecția adaugă valoare** |
| Monte Carlo pe 12 luni la 0,5% risc | A+B: median **+13% pe an**, P(an negativ) 18%, P(DD > 20%) 3% |

**Rezultatul out-of-sample (walk-forward), cu toate costurile:**

| | Trade-uri/lună | R/trade | Test | DD | Luni + | La 0,5% risc / trade | Verdict M0 |
|---|---|---|---|---|---|---|---|
| A — adaptiv NR4 | 13,6 | +0,101 | +0,129 | −34,5R | 56% | ~0,7%/lună, DD −13,7% | KEEP |
| B — noise USTEC | 20,0 | +0,064\* | +0,022 | −25,6R | 60% | ~0,6%/lună, DD −11,7% | KEEP |
| **A + B** | **27,0** | **+0,083** | +0,048 | −40,5R | 58% | **~1,1%/lună, DD −16%** | KEEP |

\* Costul folosit în cercetare era pesimist (spread de seară, 3 puncte). La spread-ul sesiunii NY (1 punct), B iese
≈ +0,084R; diferența e exact 1,5 puncte pe trade, verificată în selftest.

**Pe ani (A+B, % la 0,5% risc):** 2018 +8,2 · 2019 +0,3 · 2020 +6,3 · 2021 +21,4 · 2022 +28,5 · 2023 +4,8 ·
2024 +32,5 · 2025 +3,2 · 2026 +7,4. Fiecare an e pozitiv.

**Ținta de 2–5% pe lună nu e atinsă la un risc prudent.** La 0,5% risc, media e ~1,1% pe lună. Ar trebui ~1% risc ca
să ajungă la ~2,2% pe lună, iar atunci Monte Carlo dă P(DD > 20%) ≈ 31%.

## 2. Strategii

- **A — portofoliu adaptiv.** La începutul fiecărui trimestru, din ultimele 36 de luni:
  - **Componente candidate:** ORB pe 10 piețe (DE40, STOXX50, UK100, US500, USTEC, US30, XAUUSD, JP225, AUS200,
    GBPUSD) × 6 variante (interval 5 / 15 / 30 min × breakout / direcție), plus NOISE pe 8 piețe.
  - **Alegere:** se aleg componentele cu t-stat ≥ 1,5, medie ≥ +0,05R și ≥ 60 de trade-uri, cel mult una pe piață și 6
    în total.
  - **Când tranzacționează:** doar în zilele **NR4** (range-ul zilei anterioare = minimul ultimelor 4 zile).
  - **Fără edge** → nu tranzacționează.
  - **Selecția pentru T4 2026**, calculată live din MT5 (25 s): `ORB:JP225:5/direction`. E identică cu cea din
    validare.
- **B — noise area pe USTEC.** Parametrii din lucrare, fără selecție, zilnic, în sesiunea NY.
  - **Intrare:** la fiecare :00 / :30, prețul e în afara benzii max/min(open, close_ieri) × (1 ± σ14).
  - **Ieșire:** la revenirea sub max(bandă, VWAP), sau la închiderea sesiunii.

Toate pozițiile sunt intraday și se închid la finalul sesiunii, deci nu există nopți și nici swap.

## 3. Arhitectură

| Fișier | Rol |
|---|---|
| `special_engine/strategies.py` | funcții PURE: `orb_day` (= `daily_engine.strategy.evaluate_day`), `noise_day` (copie fidelă a cercetării), `nr_flag` |
| `special_engine/data.py` | sesiunea bursei (`market_tools.server_to_exchange`), istoricul componentelor (`orb_history`, `noise_history`), `select` (anti look-ahead) |
| `special_engine/engine.py` | bucla shadow, cu selecția trimestrială în fundal |
| `special_engine/config.py` | parametrii pre-înregistrați; `mode` forțat pe shadow |
| `api/routers/special_engine.py` | `/special/status`, `start`, `stop`, `trades`, `selection`, `selection/refresh`, `config`, `logs` |
| `frontend/src/pages/SpecialEnginePage.tsx` | tab-ul „Special Engine”: hook-urile și tipurile stau în pagină |

Modul de lucru al buclei:
- recalculează ziua de la zero din barele M5 ÎNCHISE;
- trade-urile închise ajung în `data/special_engine/trades.jsonl`, o singură dată (`state.json::events`);
- starea fiecărei componente ajunge în `status.json`;
- trimite pe Telegram: pornirea, selecția nouă și rezumatul zilei (23:00 RO);
- trade-urile individuale sunt oprite implicit (`notify_trades`).

**Infrastructură partajată, nemodificată:** `daily_engine.strategy` (ORB), `daily_engine.market_tools`
(conversia orei), `safe_io`, `api.telegram`, `m0.robustness`.

**Fișiere urmărite modificate (necomise):**
- `api/main.py`: include routerul într-un `try` (lipsa pachetului nu afectează API-ul);
- `frontend/src/App.tsx` + `frontend/src/components/NavBar.tsx`: tab-ul.

## 4. Teste

`python -m special_engine.selftest` (15):
- **Doar shadow:** mod forțat; nicio funcție de ordin în pachet.
- **Echivalență cu cercetarea:**
  - ORB DE40 + XAUUSD, 6 variante, identic (n, ΣR);
  - NOISE USTEC: 1 359 de trade-uri identice, intrare + R.
- **Selecție:** o componentă pe piață, fără edge = exclus, „viitorul perfect” nu schimbă selecția, NR4.
- **Engine-ul LIVE reluat pe zile istorice** (MT5 simulat) = backtestul pe 25 de zile. Fără dubluri la restart, zero
  ordine, doar bare închise.

## 5. Ce trebuie urmărit în shadow (criterii înainte de orice ban real)

- **Volum:** ≥ 3 luni și ≥ 60 de trade-uri B + ≥ 20 de trade-uri A.
- **Rezultat:** R/trade în intervalul de încredere 90% al backtestului (A+B ≈ +0,08R). Luni pozitive ≥ 50%.
- **Costuri reale:** spread-ul live al indicilor în sesiune. Edge-ul dispare la +0,10R cost pe trade.
- **Contul de ~206 $:**
  - lotul minim pe indici (0,1) cu stop-urile ORB / noise înseamnă 1–3% risc pe trade, nu 0,5%;
  - marja DE40 e ~145 $;
  - în real ar fi nevoie de un cont de ≥ 1000 $ sau de o selecție de piețe cu lot mic.

## 6. Limite

- **Istoricul MT5 pe M5 începe în ~2021 pentru majoritatea piețelor** (STOXX50 din 2018). Primele trimestre au mai
  puține componente.
- **Costurile sunt fixe** (măsurate pe 04.11, contul Standard, în sesiune). Slippage-ul real la știri nu e modelat.
- **Selecția s-a făcut dintr-o grilă de ~64 de configurații;** configurația folosită a fost aleasă înainte de validare
  (04.11), deci validarea a confirmat-o, nu a ales-o. Rămâne risc de supra-ajustare: shadow-ul e testul real.
- **Primul trade B** (05.11, USTEC short +10,1R, ziua de −5% a Nasdaq) **a fost reconstruit după închiderea
  sesiunii.** Engine-ul a pornit la 23:51 RO; nu e o observație live.

## 7. Pregătirea pentru Live (2026-11-12)

### Alocarea capitalului — exemplu pe contul actual (equity 195,53 $)

| Nivel | Regula | Valoare |
|---|---|---|
| Contul MT5 | equity sincronizat la fiecare ordin | 195,53 $ |
| Capitalul Special Engine | equity × fracție (100%) — sau sumă fixă plafonată la equity | 195,53 $ |
| Risc pe trade (țintă) | 1% din capitalul engine-ului | 1,96 $ |
| Risc total deschis (toate piețele) | ≤ 2% din capital | 3,91 $ |
| Poziții + ordine Special | ≤ 2 | |
| Marja contului după ordin | ≤ 80% din equity (cu pozițiile TUTUROR engine-urilor) | 156,42 $ |

Nicio piață nu folosește singură tot capitalul: riscul TOTAL deschis e plafonat la nivel de engine, iar marja la nivel de
cont. Peste toate: Setările Globale (limita de risc / trade 5%, Capital Protection, circuit breaker, știri, vineri).

| | JP225 (A — ORB 5 min direcție) | USTEC (B — noise area) |
|---|---|---|
| SL tipic | ~265 puncte (marginea opusă a intervalului) | SL de protecție 2 × unitatea ≈ 324 puncte |
| Risc la lotul minim | 1 lot × ~0,006 $/punct ≈ **1,6 $ (0,8%)** | 0,1 lot × 1 $/punct ≈ **32 $ (16,6%)** |
| Lot calculat | 1,96 $ ÷ 1,6 $ → 1 lot (minimul) | 1,96 $ ÷ 324 $ → sub minim → 0,1 |
| Limita globală 5% (9,78 $) | trece | **BLOCAT** |
| Risc total deschis ≤ 3,91 $ | trece (1,6 $) | **BLOCAT** |
| Marja (19 $ / 142 $) | trece | 73% din cont — trece doar fără alte poziții |
| Rezultat | **ordinul se plasează** | **ordinul NU se plasează** (motivul în Notificări + Audit) |
| Program (RO) | 02:00–08:00 | 16:30–23:00 |

Cele două piețe nu se suprapun în timp, deci în practică nu au poziții simultan; plafonul de risc total deschis acoperă
cazul în care selecția trimestrială alege o piață din aceeași sesiune.

### Execuția (`special_engine/engine.py::_execute`)

- Intrările oglindesc semnalele virtuale (aceleași funcții pure ca backtestul):
  - **ORB:** direcție → ordin la piață la formarea intervalului; breakout → BUY_STOP + SELL_STOP pe margini (OCO); SL
    pe marginea opusă.
  - **NOISE:** ordin la piață la închiderea lumânării care dă semnalul, cu SL de protecție la `noise_stop_mult` ×
    unitatea R (strategia iese la bandă / VWAP; dimensionarea e pe distanța până la acest SL).
- Ieșiri:
  - când strategia iese (virtual), poziția reală se închide;
  - la finalul sesiunii bursei și la închiderea de vineri globală, totul se închide;
  - o poziție din altă zi se închide imediat (`sweep_stale`). Nimic peste noapte.
- Siguranță:
  - un semnal vechi (restart târziu) nu plasează nimic;
  - acelasi semnal nu se plasează niciodată de două ori (`state.json::events`);
  - PAUZĂ = fără intrări noi, pozițiile rămân gestionate;
  - o piață nouă din selecția trimestrială intră în SHADOW.
- Notificări pentru orice ordin, închidere sau blocare (trimise și când rezumatul Telegram e oprit), audit în
  `data/audit_log.jsonl`.
- Supraveghere: watchdog-ul API îl repornește dacă moare fără Stop din UI (max 3/oră). Incidentul din 06.11: oprit odată
  cu dashboard-ul, a rămas oprit 2 ore.

### Teste

`python -m special_engine.selftest` (43) și `python scripts/test_special_api.py` (19):
- moduri per piață; ordine doar în `executor.py`;
- o zi USTEC reală și o zi JP225 reală pe MT5 simulat: ordinul real e plasat și închis, R-ul virtual e identic cu
  backtestul;
- SHADOW / PAUZĂ / cont REAL nedeblocat = zero ordine;
- restart târziu; cont mic (riscul total); marjă; poziții din altă zi; alte magic-uri neatinse; vineri globală;
- API: moduri independente, setări plafonate, audit, Stop = oprire voită, atribuire MT5, Engine Lifecycle, Trading LIVE.

### Status

| Piață | Status | De ce |
|---|---|---|
| JP225 (selecția T4 2026) | **Conditionally Ready** | Încape în cont (risc ~0,8%, marjă 19 $). Edge-ul A e confirmat doar în backtest walk-forward; shadow-ul nu are încă trade-uri A. Selecția se schimbă la 01.01 (poate alege o piață care nu încape). |
| USTEC (B) | **Not Ready pe contul actual** | Lotul minim cu SL-ul de protecție riscă ~16% din cont → blocat de limita globală și de riscul total deschis (comportament corect). Rămâne SHADOW până la un cont de ~3000 $. |
