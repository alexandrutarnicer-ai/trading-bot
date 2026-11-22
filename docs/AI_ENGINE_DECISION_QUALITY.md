# AI Engine — calitatea deciziilor: diagnostic + propunere (22.11.2026, pentru verificare)

> Nimic din acest document nu e implementat în producție. Propunerea e pentru decizia ta.

Date: ledger-ul real (`data/ai/ledger.db`, iul–nov 2026): 2.284 de consilii, 676 de decizii OPEN, 199 de ordine plasate,
486 respinse de rails, **103 trade-uri închise = −28,1R**. Scripturi (doar citire): `scripts/research_ai/ai_decision_quality.py`,
`ai_guard_replay.py`, `ai_council_replay.py`.

## 1. Diagnostic — unde se pierd banii

| Constatare | Date | Impact |
|---|---|---|
| **Înclinație masivă spre LONG** | oct: 401 LONG / 2 SHORT · nov: 41 / 0 (iul: 10 / 11) · 55 din 86 de LONG-uri închise au fost CONTRA trendului D1 | modelul nu mai „vede” piața în scădere |
| **Regim CHOPPY** | 28 de trade-uri, **−0,63R / trade = 63% din pierdere**; NEUTRAL −0,23; TRENDING +0,01 | instrucțiunea „preferă WAIT în chop” din prompt NU e respectată |
| **Ollama (qwen3:8b) în rolurile cheie** | head = Ollama: −0,42R / trade (58, 88% din pierdere); head = Gemini −0,09 · tehnic = Ollama −0,41 | modelul local e veriga slabă |
| **Geometrie greșită** | 297 din 486 de respingeri: BUY_STOP sub preț (117), LONG invalid (112), breakout deja ratat (67), SELL_STOP peste preț (13) | consilii irosite; LLM-ul greșește aritmetica |
| **SL prea strâns** | SL ≤ 1,5 ATR: −0,60R / trade (28) · 3–5 ATR: −0,03 | stop-uri luate de zgomot |
| **Încrederea nu prezice nimic** | 60–70%: −0,27 · 70–80%: −0,28 · 80%+: −0,26 | pragul de 80% nu filtrează calitatea |
| Direcția cu / contra trend | ambele negative (−0,25 / −0,30) | nu e cauza principală |

## 2. Ce am verificat (echipa + consiliul)

**Re-simulare pe barele M5 reale a celor 103 trade-uri** (baza simulată −32,4R ≈ real −28,1R → simularea e credibilă):

| Reguli în cod | Rezultat | n |
|---|---|---|
| baza (SL / TP-ul consiliului) | −32,4R | 103 |
| G1: fără intrări în CHOPPY | −17,3R | 75 |
| G2: SL minim 2,5 × ATR (TP la același RR) | −27,7R | 103 |
| **G1 + G2** | **−6,6R** | 75 |
| G1 + G2, doar trade-urile cu regim etichetat (după 08.08) | **+3,3R** (+0,056R / trade) | 59 |

Pe jumătăți: prima −14,0 → **+2,3R**, a doua −18,4 → −8,9R (îmbunătățire pe ambele). Atenție: regulile sunt deduse din
aceleași date (risc de supra-ajustare) — efectul real va fi mai mic.

**Reluarea consiliului pe snapshot-urile reale** (20 de trade-uri: 10 CHOPPY + 10 NEUTRAL / TRENDING, configurația de azi):
din 10 CHOPPY consiliul de azi ar fi deschis doar 1 (−1,0R) din −6,7R → prompturile cu regim + pragul de 80% ajută,
dar pe TRENDING a repetat toate cele 5 LONG-uri (−2,9R), toate cu analistul tehnic pe Ollama.

**Reluarea cu analistul tehnic pe Gemini**: pe cele 6 snapshot-uri pe care Gemini a apucat să răspundă (toate CHOPPY,
5 pierderi + 1 câștig, total −2,5R) a dat de fiecare dată „neutral” → WAIT, deci a evitat toate pierderile (și câștigul de
+2,0R). Pe aceleași 6, Ollama dăduse „long” de fiecare dată. Apoi cota zilnică gratuită Gemini s-a epuizat (HTTP 429) și
restul au rulat pe Ollama (motorul trece automat) — eșantionul cu Gemini e mic (6), dar direcția e clară.

## 4. Constrângerea Gemini (important)

Cota GRATUITĂ Gemini s-a epuizat azi după ~70–90 de apeluri de test. Consiliul face ~6 consilii / zi cu 2 piețe (maxim 17)
→ cu 4 piețe ~12–35 / zi; cu tehnic + head pe Gemini = ~25–70 de apeluri / zi — la limita cotei gratuite. Când cota se
termină, head-ul și tehnicul trec pe Ollama (exact sursa cea mai slabă). Variante:
- **cheie Gemini plătită** (gemini-2.5-flash costă de ordinul cenților / zi la acest volum) — recomandat dacă mutăm
  tehnicul pe Gemini;
- tehnicul rămâne pe Ollama, iar calitatea vine din regulile din cod (Nivelul 1) — fără cost, efect mai mic;
- la 429 pe Gemini, motorul să facă WAIT în loc să treacă pe Ollama pentru head (configurabil).


## 3. Propunerea echipei (în ordinea impactului / siguranței)

**Nivelul 1 — reguli în COD (deterministe, testabile, reversibile, comutabile din config):**
1. **Poarta de regim**: în regim CHOPPY nicio intrare nouă (`validate_decision` respinge OPEN; pozițiile existente
   rămân gestionate). Astăzi e doar o rugăminte în prompt, pe care Ollama o ignoră.
2. **SL minim 2,5 × ATR(M15)**: un SL mai strâns e lărgit, TP-ul recalculat la același RR (rail-ul existent de maxim
   5 × ATR rămâne). Riscul în bani rămâne 1% — lotul scade; dacă lotul minim depășește riscul → respins.
3. **Geometria calculată în cod**: LLM-ul decide DOAR direcția (și dacă se tranzacționează); intrarea stop = dincolo de
   marginea range-ului de 20 de bare (+0,1 ATR), SL = max(nivelul structural, 2,5 ATR), TP = 2R. Elimină cele ~300 de
   respingeri pe geometrie și erorile de aritmetică.

**Nivelul 2 — de-polarizarea prompturilor (efect probabil asupra înclinației LONG):**
4. Analistul tehnic citește ÎNTÂI trendul (câmpuri obligatorii `trend_m30_read` / `trend_d1_read`) și abia apoi dă bias-ul;
   ordinea opțiunilor în schema JSON neutră (`"short"|"neutral"|"long"` alternat) — modelele mici aleg des prima opțiune.
5. Regula „bias contra M30 = neutral, cu excepția unui motiv structural explicit” verificată în cod (nu în prompt).

**Nivelul 3 — sursele AI:**
6. Analistul tehnic pe Gemini (Ollama rămâne rezervă) — DOAR cu o cheie plătită sau cu regula „Gemini indisponibil →
   WAIT” (vezi secțiunea 4); altfel, la epuizarea cotei, deciziile cad pe Ollama.

**Nivelul 4 — măsurare:** fiecare regulă cu propriul flag în config + motivul respingerii în ledger, ca să se vadă după
o săptămână câte trade-uri a oprit fiecare și cum s-ar fi încheiat.

Recomandarea echipei: **Nivelul 1 (1 + 2) + Nivelul 2 + Nivelul 3**, apoi 1–2 săptămâni de observație a efectului;
Nivelul 1.3 (geometrie în cod) după, fiind cea mai mare schimbare a modului de lucru al consiliului.

## 5. IMPLEMENTAT (23.11.2026) — Ollama sursa principală, decizii disciplinate

**Prompturi noi (doar motorul autonom; filtrul pre-trade al Custom Engine păstrează prompturile vechi — praguri calibrate):**
- eliminate instrucțiunile care împingeau spre trade („OPEN la >= 55 = rezultatul normal”, „conflictul cu D1 nu forțează
  WAIT”, „un stop nu costă nimic, nu ai nevoie de certitudine”) — contraziceau „No trade e respectabil”;
- WAIT implicit; minim câteva confirmări INDEPENDENTE; niciodată un singur indicator; LONG și SHORT pe același standard;
- analistul tehnic lucrează în ordine fixă (trend M30 / D1 → regim → poziția în range → momentum → setup + invalidare)
  și raportează listele `for` / `against` / `missing`; ordinea opțiunilor din schema JSON nu mai începe cu „long”;
- încrederea = scorul calității setup-ului (50 ± 10 / confirmare / contradicție), peste 80 DOAR cu M30 + D1 + regim
  de acord — aliniată cu pragul de 80 al motorului (nu o probabilitate);
- știrile DOAR din briefing; calendarul indisponibil e scris explicit („UNAVAILABLE — event risk UNKNOWN”), nu mai apare
  ca „nicio știre”; analistul macro poate răspunde `event_risk: unknown`;
- briefing-ul primește nivelurile de REFERINȚĂ calculate în cod: poziția în range în ATR (intrare târzie vizibilă),
  intrarea BUY_STOP validă (deasupra prețului), SELL_STOP (dedesubt), distanța minimă a SL-ului.

**Reguli deterministe în cod** (`executor.apply_decision_gates`, config `gate_choppy` / `gate_counter_trend` /
`min_sl_atr` / `max_data_age_min`, toate comutabile): regim CHOPPY → nicio intrare; direcție contra AMBELOR trenduri
(M30 + D1) → respinsă; SL sub 2,5 × ATR → lărgit (TP la același RR); ultima bară mai veche de 45 min → fără consiliu.
Riscul (lot, limite, protecții) rămâne exclusiv în cod.

**Comparația A/B pe aceleași 40 de situații reale (doar Ollama, `scripts/research_ai/ai_prompt_ab.py`):**

| | Vechi | Nou (prompt + reguli) |
|---|---|---|
| Bias analist tehnic | 25 LONG / 15 SHORT | 18 LONG / 22 SHORT |
| Intrări propuse | 10 (toate LONG) | 3 |
| Contra trendului D1 | 8 din 10 | 1 din 3 |
| Oprite de reguli în cod | — | 12 CHOPPY, 8 contra ambelor trenduri |
| Rezultat simulat | +0,60R (5 executate, 2 câștiguri) | 0 executate (3 expirate) |

Concluzie: disciplina e clar mai bună (înclinația LONG dispărută, fără intrări în chop sau contra ambelor trenduri), dar
eșantionul e prea mic pentru o concluzie de profitabilitate (cele 4 trade-uri evitate care s-ar fi executat: +1,6R net).
Dovada principală pentru reguli rămâne re-simularea celor 103 trade-uri reale (−32,4R → −6,6R). Modelul local (qwen3:8b)
încă propune uneori LONG în trend descendent și calculează greșit TP-ul — regulile din cod și `_repair_tp` le prind.
Prima variantă (încredere plafonată la 70) a dat 0 intrări din 40 (conflict cu pragul de 80) — corectată înainte de commit.
Recomandare: 1–2 săptămâni de observare a efectului (motivele respingerilor sunt în ledger), apoi revizuire.
