# Raport — Special Engine și Daily Engine: pregătirea pentru Live, rapoarte, audit (2026-11-12)

> Pentru: tine, înainte de review-ul commit-urilor și de orice activare Live. Nimic nu e pornit pe Live și nu s-a făcut
> push. Toate piețele Daily și Special sunt în SHADOW; Profit Lock e oprit peste tot; Noisy rămâne SHADOW.

## Statusuri

| Engine | Status | Pe scurt |
|---|---|---|
| Custom Engine | Ready for Live (neschimbat) | Rulează deja live; regresia trece; nu l-am modificat. |
| AI Engine | Conditionally Ready (neschimbat) | Rulează deja live; nicio piață cu edge dovedit; nu l-am modificat. |
| **Daily Engine — DE40** | **Conditionally Ready** | Tehnic gata. Riscul real la lotul minim e ~3%, nu 1%; ocupă 76% din marjă; edge-ul de test e pozitiv dar nesemnificativ. |
| Daily Engine — US500 | Conditionally Ready, recomandat Shadow | Edge mic (+0,046R), test ~0. |
| **Special Engine — JP225** | **Conditionally Ready** | Încape în cont (risc ~0,8%, marjă 19 $); edge-ul A e confirmat doar în backtest walk-forward. |
| Special Engine — USTEC | Not Ready (pe contul actual) | Lotul minim cu SL-ul de protecție riscă ~16% din cont → blocat corect de limite. |
| Noisy Engine | Shadow Only | Neatins. |

## Special Engine

**Implementat:**
- **Mod per piață** (Live / Shadow / Pauză): implicit Shadow; o piață nouă din selecția trimestrială intră tot în Shadow.
- **Execuție reală** prin `special_engine/executor.py`, singurul fișier care trimite ordine (magic 660001). Pe cont real
  rulează doar cu „Special Engine” deblocat în Trading LIVE.
- **Capital și risc proprii**, în tab-ul Special Engine; Setările Globale se aplică peste ele.
- **Integrare:** card în Dashboard, carduri de performanță, atribuirea tranzacțiilor din MT5, Engine Lifecycle,
  watchdog (repornire automată — cauza incidentului din 06.11), audit, notificări, sincronizare PC ↔ laptop.

**Alocarea capitalului (contul actual, 195,53 $):**
- **Plafoane:** capitalul engine-ului = equity × 100%; risc 1% / trade = 1,96 $; risc total deschis ≤ 2% = 3,91 $;
  maxim 2 poziții; marja contului ≤ 80%.
- **JP225:** riscul la lotul minim e 1,6 $, deci ordinul se plasează.
- **USTEC:** riscul la lotul minim e 32 $, deci e blocat de limita globală (5%) și de riscul total deschis.
- **Simultaneitate:** cele două piețe nu se suprapun în timp (02:00–08:00 RO față de 16:30–23:00 RO).
- Detalii: `docs/SPECIAL_ENGINE.md` §7.

**Teste:**
- `special_engine.selftest`: 43, incluzând o zi USTEC și o zi JP225 reale pe MT5 simulat; ordinele reale sunt plasate
  și închise, iar R-ul virtual e identic cu backtestul.
- `test_special_api.py`: 19.

## Daily Engine

**17 trade-uri în raport față de ~13 în engine.** Nu era o eroare de numărare:
- cardurile arătau doar piețele din sloturi: DE40 9 + US500 4 = 13;
- raportul includea și GBPUSD, scos din slot (4).
- **Remediere:** pagina arată acum rândul „Piețe scoase din configurație” (carduri + piețe scoase = total).
- **Pierderea de date:** 2 trade-uri din 06.11 au fost pierdute la un „Sync Recovery” manual (Copilot, 09.11). Le-am
  recuperat din istoric, deci totalul real e 19 (3 câștigate, 16 pierdute).
- **Sync reparat:** jurnalele în care doar se adaugă rânduri se unesc acum automat, fără pierderi.

**DE40:**

| | R/trade | t | DD |
|---|---|---|---|
| Tot istoricul (3428) | +0,095 | 2,47 | −66R |
| Test din 08.2023 (1029) | +0,058 | 0,87 | −55R |
| Shadow (10) | +0,89 | — | −5R |

- **Pe ani:** 2023 −0,13R, 2024 +0,01R, 2025 +0,29R.
- **Costuri:** +1 punct de slippage înjumătățește edge-ul, +2 puncte îl anulează.
- Detalii: `docs/DAILY_ENGINE_PLAN.md` §13.

**Profit Lock** (opțional per piață, oprit implicit):

| | fără | 3,5→3 | 4,5→4 | 5→4 |
|---|---|---|---|---|
| DE40 | **+0,095** | +0,046 | +0,072 | +0,095 (DD −57R față de −66R) |
| US500 | **+0,046** | +0,011 | +0,022 | +0,019 |

Nicio variantă nu e mai bună decât strategia actuală.

**Moduri per piață:** Live / Shadow / Pauză, independente și persistente la restart. Pauza păstrează pozițiile
gestionate, iar Live cere în continuare deblocarea din Trading LIVE. În plus:
- **limita de marjă:** marja totală după un ordin ≤ 80% din equity;
- **închiderea de vineri globală** se aplică acum și pe Daily (înainte US500 rămânea deschis până la 23:00 vineri).

**Teste:** `daily_engine.selftest` 99, `test_daily_markets` 47.

## Rapoarte

**Zilnic:**
- opțional, pornit implicit;
- trimis o singură dată pe zi, și după restart. Cauza dublurilor din 05.10 și 31.10: marcajul „trimis azi” era ținut
  doar în memorie.

**Săptămânal:**
- vineri de la 20:00 (vechiul implicit 23:30 a fost migrat; o oră aleasă explicit se păstrează);
- așteaptă închiderea de vineri (max 20 min) și istoricul MT5;
- fereastra merge până în momentul trimiterii, deci închiderile de vineri intră în raport;
- dacă laptopul e închis vineri, raportul se trimite la următoarea pornire, până luni la 12:00.

**Lunar:**
- codul trimitea deja doar luna încheiată;
- am adăugat o gardă care refuză orice altă perioadă.
- Raportul „pe noiembrie” primit devreme nu poate fi reprodus de aici; probabil vine din codul diferit de pe laptop
  (după acel „recovery”).

**Teste:** `test_reports` 69, care parcurg programatorul pas cu pas: restart, MT5 nepregătit, perioade goale,
laptop închis, schimbarea datei, fără trimiteri duble.

## Audit general

- **Piețe verificate în MT5** (DE40, US500, JP225, USTEC): tick, lot minim / pas, stops / freeze level 0 și filling
  sunt toate conforme cu ce folosesc engine-urile. Costurile configurate sunt egale cu spread-ul live sau mai prudente.
- **Probleme găsite și remediate:**
  - Daily nu respecta închiderea de vineri globală;
  - Daily nu avea limită de marjă;
  - Special nu avea watchdog;
  - sync-ul pierdea date;
  - raportul zilnic pleca dublu;
  - raportul săptămânal pleca după ora de închidere a laptopului;
  - testele scriau în jurnalul real de audit.
- **Test de durată API**, 5 minute, 15 endpoint-uri la ~2 s (mult mai des decât UI-ul):
  - 1815 cereri, 0 erori;
  - RAM 177 → 193 MB, maxim 235 MB, fără creștere continuă;
  - CPU în medie 11,7% dintr-un nucleu;
  - thread-uri 41 → 36 și handle-uri 277 → 266, deci nu se acumulează;
  - latența mediană 12–32 ms; maxim 1,9 s pe `/engines` (interogarea Task Scheduler, cache 30 s).
- **Regresie:** 43 de suite trec, plus tsc.

**Neefectuat:**
- selftest-ul AI cu consiliul LIVE pe Ollama;
- teste de execuție pe un cont DEMO real (pe acest PC terminalul e conectat doar la contul real);
- test de durată pe engine-uri (rulează pe laptop).

## Git

Toate commit-urile sunt pe alex-live, local, fără push.

**Doar alex-live** (mesaj cu „special” sau „alex-live”):
- `76aaca2` — recuperarea datelor din 06.11;
- `a77646d` — Special pregătit pentru Live;
- `884d358` — documentația Special;
- acest raport.

**Pentru main / vlad-live, după review:**
- `e7ae9c0` — sync fără pierderi;
- `b759980` — cercetarea Profit Lock;
- `4490588` — Daily: moduri per piață, Profit Lock, marjă, audit;
- `0e23d71` — rapoarte;
- `5d10626` — audit în Rapoarte;
- `09dde30` — Daily: închiderea de vineri;
- `f42df8b` — documentație;
- `66e4d0e` — testul `live_guard`.

## Ce trebuie să decizi tu

1. Push-ul, după review.
2. Activarea Live, per piață:
   - DE40 (Daily) și JP225 (Special) sunt cei doi candidați;
   - pe cont real, întâi deblocarea din Settings → Trading LIVE, apoi LIVE pe cardul pieței.
3. Profit Lock: rămâne oprit, cifrele nu îl justifică.
4. Pe laptop, după `sync_data.bat`, repornește dashboard-ul și engine-urile ca să preia codul nou.
