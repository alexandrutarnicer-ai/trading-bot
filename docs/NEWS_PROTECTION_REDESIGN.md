# News Protection + Intelligent Mode — Analiză, Redesign și Cercetare

**Data:** 2026-07-17  
**Autor:** Claude (Opus 4.8)  
**Scope:** `live/news_guard.py`, `live/signal_generator.py` (protecția la știri + Modul Inteligent)

---

## 1. Ce am descoperit (cum funcționa)

### Arhitectura veche (două componente, ambele lente)

1. **News Guard** (`news_guard.py`) — thread daemon pornit de `run_all.py`. La fiecare **300s (5 min)**:
   - descarcă calendarul (ForexFactory → MT5 → Finnhub),
   - pentru fiecare sesiune activă apela `active_events_for(now)` care întorcea evenimentele a căror fereastră `[event − pre, event + post]` conținea `now`,
   - **scria în `news_auto_paused.json` un verdict înghețat**: „sesiunea e/nu e pe pauză ACUM".

2. **Sesiunea** (`signal_generator.py`) — la fiecare bară (`_sleep_to_next_bar`):
   - `_is_news_paused()` citea fișierul și returna `True` dacă sesiunea era prezentă (verdict înghețat al guardului),
   - pe tranziția `False→True` rula `_news_close_check` (închide/anulează sau, în Modul Inteligent, păstrează pozițiile aliniate cu știrea + deschide în direcția ei).

### Modul Inteligent (smart_news)

Când `smart_news_enabled=True`, în loc de închidere oarbă:
- păstrează pozițiile **aliniate** cu sentimentul știrii (`actual` vs `forecast`),
- închide pozițiile **contra** sentimentului,
- plasează un ordin STOP în **direcția** știrii (`_smart_news_place_order`),
- trailing SL pe ordinele de știre (3R → mută SL, 4R → mută SL).

---

## 2. Problemele identificate (de ce eșua)

| # | Problemă | Cauză | Efect |
|---|----------|-------|-------|
| **P1** | **Activare non-deterministică** | Guardul decide activ/inactiv la **momentul poll-ului** (la 5 min) și îngheață verdictul. | O fereastră `pre` < 5 min poate cădea **între două poll-uri** → protecția nu se activează niciodată. |
| **P2** | **Granularitate pe timeframe** | Sesiunea reacționează doar la **închiderea barei** (15 min M15, **60 min H1**). | O sesiune H1 verifică știrile o dată/oră → o fereastră de 30 min poate cădea integral între două bare și e ratată complet. |
| **P3** | **Verdict înghețat, nu re-evaluat** | `_is_news_paused` doar citea prezența în fișier; nu recalcula fereastra față de timpul curent. | Activarea/dezactivarea era legată de cadența guardului, nu de timpul real. |
| **P4** | **Sentiment inversat greșit** | `_calc_sentiment` presupunea mereu `actual > forecast → valută mai puternică`. | Pentru șomaj / jobless claims (mai mare = mai rău), direcția Modului Inteligent era **inversă**. |
| **P5** | **`actual` apare doar după eveniment** | Sentimentul are nevoie de `actual`, publicat la/după ora evenimentului + cache 4.5 min. | Ordinul „în direcția știrii" nu putea fi plasat pre-eveniment (corect), dar întârzierea combinată (cache + poll + bară) rata mișcarea inițială. |

**Concluzia utilizatorului („nu se activează când ar trebui") = P1 + P2 + P3 combinate:** fereastra configurată, momentul real de activare și momentul intervenției erau decuplate de cadența lentă (poll 5 min + bară 15–60 min).

---

## 3. Ce am schimbat și de ce

### Principiul de redesign: **separă DETECȚIA de ACTIVARE**

> Guardul (lent) doar ține **lista de evenimente proaspătă**. Sesiunea (rapid) **decide activarea** re-evaluând ferestrele față de timpul **curent**.

Fereastra unei protecții e o **funcție pură** de `(evenimente, now, config)` — nu trebuie să depindă de când rulează guardul.

### Schimbări concrete

1. **Logică pură de fereastră** (`news_guard.py`): `event_window`, `events_active_at`, `upcoming_relevant_for`, `market_currencies` — pure, testabile fără MT5/rețea, deterministice la secundă.

2. **Guardul scrie evenimentele în avans** (`upcoming_relevant_for`, orizont **180 min** ≫ poll 5 min): în loc de un boolean înghețat, scrie **toate evenimentele relevante apropiate** (active acum SAU care încep în orizont) + config (`pre/post/impact/markets`). Astfel sesiunea are mereu evenimentul imediat în cache, chiar dacă guardul n-a mai poll-at recent.

3. **Sesiunea re-evaluează la timpul curent** (`_is_news_paused`): parsează evenimentele din fișier și rulează `events_active_at(now_utc)`. **Activarea devine exactă la secundă**, independentă de cadența guardului sau de offset-urile `pre/post` (chiar `pre=1 min` e onorat).

4. **Watch sub-bară** (`_sleep_watching_news` + `_news_watch_tick`): între bare, sesiunea se trezește la fiecare **30s** și rulează DOAR protecția la știri (re-evaluare + închidere pe tranziție + trailing). **Generarea de semnale rămâne aliniată la bară** (corect — semnalele se formează pe bare închise). Rezultat: o sesiune H1 reacționează la știri în ~30s, nu o dată/oră.

5. **Sentiment corect pentru indicatori inversați** (`_calc_sentiment` + `_INVERTED_INDICATORS`): șomaj, jobless claims, claimant count, stocuri de țiței/gaz → semnul surprizei e răsturnat.

---

## 4. Cum funcționează intern acum

```
NEWS GUARD (thread, poll 5 min)                SESIUNE (buclă, bară + sub-bară 30s)
──────────────────────────────                 ──────────────────────────────────────
fetch calendar (FF/MT5/Finnhub)
  │
  ├─ upcoming_relevant_for(now, horizon=180m)   _news_watch_tick()  ← la bară ȘI la 30s
  │    → evenimente active acum SAU              │
  │      care încep în 3h + config                ├─ _is_news_paused(sk)
  │                                               │    └─ events_active_at(now_utc)  ← RE-EVALUARE
  └─ scrie news_auto_paused.json ────────────────┤       (deterministic, la secundă)
       {sk: {pre,post,impact,markets,events[]}}   │
                                                  ├─ tranziție False→True?
                                                  │    └─ _news_close_check (Mod Inteligent:
                                                  │        păstrează aliniat / închide contra /
                                                  │        deschide în direcția știrii)
                                                  └─ trailing SL ordine de știre
```

**Contractul de date** (`news_auto_paused.json`, format nou):
```json
{ "session9": {
    "updated_at": "2026-07-17T12:00:00", "pre": 15, "post": 15, "impact": 3,
    "markets": ["USDJPY"],
    "events": [ {"title":"CPI","currency":"USD","impact":"High",
                 "event_time":"2026-07-17T12:30:00","actual":"3.1","forecast":"3.0","sentiment":1} ]
} }
```
Backward-compat: fișier în format vechi (fără `pre`) → prezența = pauză (comportamentul de dinainte).

---

## 5. Edge case-uri acum acoperite

- ✅ **`pre` mic (1 min)** — activare exactă la intrarea în fereastră, nu ratată de poll-ul de 5 min (testat: activ EXACT la 12:02, nu la 12:00/12:01).
- ✅ **Sesiuni H1** — reacție în ~30s, nu o dată/oră.
- ✅ **Granițe exacte** — `start ≤ now ≤ end` inclusiv; testat la fiecare graniță.
- ✅ **Eveniment trecut dincolo de `post`** — nu se mai activează.
- ✅ **Impact sub prag** — ignorat; prag configurabil respectat.
- ✅ **Valută irelevantă** pentru piață — ignorată.
- ✅ **Indicatori inversați** (șomaj, jobless) — sentiment corect.
- ✅ **Evenimente suprapuse / conflict pe aceeași valută** — direcție netă 0 (nu tranzacționează pe semnal neclar).
- ✅ **Timezone** — tot lanțul e UTC-naiv (event_time parsat la UTC, `now = datetime.utcnow()`); nicio mixare cu ora locală în math-ul ferestrei.
- ✅ **Guard picat / fișier lipsă / corupt** — fail-safe: nepauză (nu blochează botul), best-effort la scriere.
- ✅ **Restart bot** — guardul resetează starea la pornire; sesiunea re-evaluează din evenimentele proaspete.
- ✅ **Format vechi de fișier** — backward-compat.

---

## 6. Cercetare — best practices pentru News Protection în trading algoritmic

Sinteză din practici uzuale (broker feeds, ForexFactory, econ calendars) + principiile aplicate aici:

| Temă | Risc / capcană | Cum e tratat aici |
|------|----------------|-------------------|
| **Detecție vs activare** | A decide „activ acum" la momentul unui poll lent = ferestre ratate. | Detecția (guard lent) e separată de activare (sesiune re-evaluează la timpul curent). |
| **Timezone** | Amestec de ore server-broker / locală / UTC → ferestre deplasate cu ore. | Tot math-ul de fereastră e UTC-naiv, o singură convenție (event_time UTC, `utcnow`). |
| **Granularitate reacție** | Buclă legată de timeframe → reacție de ordinul timeframe-ului. | Watch sub-bară (30s) DOAR pentru protecție; semnalele rămân pe bară. |
| **DST / schimbare de oră** | Ferestre deplasate la trecerea DST. | UTC nu are DST; parsarea offset-urilor din calendar normalizează la UTC. |
| **Evenimente suprapuse** | Două știri în ferestre care se ating → flicker pauză/reluare. | Uniunea ferestrelor; direcție netă agregată; conflict → 0. |
| **Indicatori inversați** | Șomaj/claims tratate ca „mai mare = mai bine". | Listă de indicatori inversați, semn răsturnat. |
| **Sentiment pre-eveniment** | `actual` nu există înainte de release → direcție 0 pre-eveniment. | Corect by design: pre-eveniment = protejează (pauză/închide); post-eveniment (actual known) = intrare opțională. |
| **Race condition pe fișierul de stare** | Guard scrie / sesiune citește concurent. | Scriere full-file (aproape atomică); citire fail-safe (except → nepauză). Risc rezidual mic; o îmbunătățire viitoare = scriere în fișier temporar + `os.replace`. |
| **Sursă calendar picată** | O singură sursă = single point of failure. | Cascadă FF → MT5 → Finnhub; cache TTL. |
| **Latența `actual`** | Cache + poll întârzie `actual` cu minute → ratezi mișcarea. | Watch sub-bară reduce latența de reacție; cache TTL 4.5 min < poll 5 min. Rezidual: dependent de cât de repede publică sursa `actual`. |

### Recomandări viitoare (nu implementate acum, low priority)
- Scriere `news_auto_paused.json` prin `os.replace` (atomic) pentru zero-risc de citire parțială.
- Poll adaptiv: mai des (ex. 60s) în ferestrele apropiate de un eveniment high-impact, pentru `actual` mai proaspăt.
- Indicatori inversați extinși (parsare din direcția „better/worse" a calendarului dacă sursa o oferă).

---

## 7. Testare

`scripts/test_news_protection.py` — **36 teste, toate PASS**, fără MT5/rețea:
- ferestre pure + **determinism** (inclusiv `pre=1` activat exact la graniță),
- `upcoming_relevant_for` cu orizont,
- sentiment + indicatori inversați,
- direcție netă (forex/index/conflict),
- `_is_news_paused` re-evaluat la timpul curent (monkeypatch pe ceas) + backward-compat,
- **ORDINE FALSE end-to-end** (MT5 simulat): Modul Inteligent păstrează poziția aliniată, închide contra-poziția, plasează ordinul în direcția știrii.

Zero regresii în restul suitelor (news + capital + AI filter + multi-council + market + capital + live-guard).
