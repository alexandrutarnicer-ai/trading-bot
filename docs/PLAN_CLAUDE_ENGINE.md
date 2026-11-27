# Plan — „Claude Engine”: un engine monitorizat și condus de Claude (27.11.2026)

Doar plan și analiză. Nimic din acest document nu e implementat.

## 1. Răspunsul scurt

**Da, se poate construi, iar o mare parte din infrastructură există deja.** AI Engine are deja: consiliu de roluri,
surse AI cu failover, reguli fixe de risc în cod, executor pe magic propriu, jurnal (ledger) și Telegram. Există și un
adaptor `anthropic` în `ai_engine/providers.py`. Un „Claude Engine” ar fi în principal **o nouă combinație de roluri și
de ritm**, nu un sistem nou de la zero.

Trei lucruri trebuie spuse cinstit înainte de orice decizie:

1. **Nu sunt un trader care „a făcut milioane”, iar un „consiliu de traderi milionari” nu există aici.** Pot juca roluri
   (analist, risk manager, head trader), dar asta e structură de raționament, nu experiență reală pe piață. Ce contează e
   ce se poate **măsura**: backtest fără lookahead, shadow, apoi rezultate reale.
2. **Experiența de până acum e un avertisment.** AI Engine (LLM care alege singur trade-urile) a făcut −28R pe 103
   trade-uri reale. Regulile din 22.11 l-au disciplinat, dar profitabilitatea nu e dovedită. Un model mai bun (Claude)
   raționează mai bine decât qwen3:8b, dar **un raționament mai bun nu înseamnă automat un edge statistic**.
3. **Eu nu rulez continuu.** O sesiune Claude Code pornește când o deschizi tu. Pentru un engine care rulează singur
   toată ziua există doar două variante tehnice (vezi §3), iar fiecare are costuri și limite.

## 2. Ce ar face concret

Propun **două roluri separate**, nu unul singur care face tot:

| Rol | Ce face | Cât de des | Plasează ordine? |
|---|---|---|---|
| **Supervisor (monitorizare)** | verifică toate engine-urile: stare, erori, poziții peste fereastră, divergențe shadow vs live, incidente; raport dimineața + seara pe Telegram | la 15–30 min + 2 rapoarte / zi | **NU**: doar observă și te anunță |
| **Trader (decizii)** | analizează 2–4 piețe la momente fixe (deschiderea Londrei / NY) și propune un trade complet (intrare, SL, TP, motiv, ce l-ar invalida) | 2–6 decizii / zi | doar prin regulile fixe din cod |

Supervisor-ul e partea cu valoare sigură: ar fi prins azi-noapte poziția DE40 rămasă peste noapte, la 23:00, nu la
01:05. Trader-ul e partea cu risc și trebuie tratat ca orice strategie nouă (§5).

**Ce rămâne mereu în cod, nu la Claude:** lotul și riscul (`position_sizing`, Setări Globale, limita de risc pe trade),
geometria SL / TP, stopul zilnic, numărul maxim de poziții, închiderea de vineri / weekend / sărbători, deblocarea contului
real. Claude propune; codul decide dacă și cât.

## 3. Cum s-ar conecta Claude (două variante)

| | **A. Claude API** (`anthropic`, deja suportat) | **B. Claude Code în mod headless** (`claude -p`, abonamentul tău) |
|---|---|---|
| Cum | engine-ul apelează API-ul la fiecare decizie, ca pe Gemini / Ollama acum | engine-ul pornește `claude -p "…"` cu acces doar de citire (ca puntea Telegram) |
| Cost | se plătește pe token, separat de abonament. Estimare: ~0,02–0,06 $ / decizie (Sonnet), deci ~1–3 $ / zi la 30–50 de apeluri; supervisor-ul încă ~0,5–1 $ / zi | inclus în abonament, dar în **limitele de utilizare ale abonamentului**; la depășire, apelurile sunt refuzate până la resetare |
| Fiabilitate | mare, cu timeout și failover existente (Ollama ca plasă) | depinde de PC, de CLI și de limite; mai fragil pentru ceva ce rulează toată ziua |
| Potrivit pentru | Trader + Supervisor | Supervisor + rapoarte; nu aș pune decizii de trading pe el |

Recomandare: **A** pentru decizii (previzibil, măsurabil, cost mic și cunoscut), iar **B** opțional pentru rapoartele
supervisor-ului. Pe durata abonamentului, cheia API rămâne în `data/ai/providers.json` (gitignored, ca acum).

## 4. Cât ar dura

| Etapă | Ce | Durată estimată |
|---|---|---|
| 1. Supervisor | reguli de verificare + raport Telegram + incidente; fără ordine | 1–2 zile |
| 2. Claude Engine în SHADOW | roluri noi, sursa Claude, magic propriu (ex. 550001), jurnal, card în Dashboard, Ritm de tranzacționare | 2–4 zile |
| 3. Observare în SHADOW | rulează pe prețuri reale, fără ordine; comparat cu regulile din cod | **minim 4–6 săptămâni** |
| 4. Live mic | doar dacă etapa 3 trece criteriile; lot minim, o piață, risc ≤ 1% | decizia ta |

Partea de cod e scurtă (~1 săptămână). Partea lungă și obligatorie e **dovada** (etapa 3): fără ea ar fi aceeași greșeală
ca la AI Engine.

## 5. Criterii înainte de bani reali (aceleași ca M0)

- minim 30–50 de trade-uri în SHADOW, cu expectancy > 0 **după costuri** (spread-ul real al contului Standard);
- P(edge > 0) ≥ 95% pe bootstrap, ≥ 60% din perioade pozitive;
- să nu fie doar un clon al Daily / Special (aceleași intrări); altfel nu aduce nimic nou;
- drawdown-ul din shadow să încapă în cont (~270 $ acum) la riscul ales.

Dacă nu trece, rămâne **doar Supervisor**, care e util oricum.

## 6. Riscuri

- **Cost și limite:** API-ul costă bani mici, dar zilnic; headless-ul poate fi refuzat la limită → orice eroare = WAIT
  (ca la AI Engine), niciodată „trade din reflex”.
- **Halucinații / aritmetică:** știri inventate, TP greșit (văzut la qwen: „TP −813R”) → regulile din cod rămân obligatorii.
- **Două instanțe pe același cont** (PC + laptop): același guard ca la AI Engine (mutex + detecție cross-mașină).
- **Dependență de un furnizor:** dacă API-ul pică, engine-ul nu deschide nimic; pozițiile rămân pe SL / TP la broker.

## 7. Recomandarea mea

1. Încep cu **Supervisor** (fără ordine): valoare imediată, risc zero, 1–2 zile.
2. În paralel, **Claude Engine în SHADOW** pe 2 piețe, 4–6 săptămâni.
3. Live doar dacă trece criteriile din §5, cu lot minim, decizia ta.
