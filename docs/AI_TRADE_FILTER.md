# Filtrul AI Pre-Trade

Validarea finală, opțională, a fiecărui semnal generat de botul pe reguli — înainte ca
ordinul să fie trimis în MT5. Un strat de „second opinion" AI peste edge-ul statistic
existent, construit integral pe infrastructura motorului AI (`ai_engine/`).

**Dezactivat by default.** Cu filtrul oprit, botul se comportă identic byte-cu-byte cu
versiunea dinaintea acestui feature (verificat prin teste de regresie — vezi mai jos).

> **Consiliu multiplu (consens) + roluri suplimentare** — optional, per sesiune:
> filtrul poate rula **până la 3 consilii** pe surse AI distincte, combinând
> încrederile prin medie (un veto valid respinge oricum), și poate activa rolurile
> **Analist Cantitativ** și **Avocatul Diavolului**. Un singur consiliu (default) →
> comportament identic. Detalii: [MULTI_COUNCIL_CONSENSUS.md](MULTI_COUNCIL_CONSENSUS.md).

---

## Fluxul ordinului

```
_check_signals() detectează setup          (neschimbat)
        │
        ▼
dedup signals.csv + pending                 (neschimbat)
        │
        ▼
┌─ ai_filter_enabled? ── NU ──────────────► fluxul normal (identic cu înainte)
│        │ DA
│        ▼
│  Consiliul AI de revizie (4 roluri, 10–60s)
│  briefing = perception.build_snapshot()   (aceiași ochi ca motorul AI)
│        │
│        ├─ APROBAT (încredere ≥ prag) ───► semnal → pending → _place_order → MT5
│        │                                   · verdict stocat în pending (state.pkl)
│        │                                   · notificările Ordin plasat / ACTIVAT /
│        │                                     PROFIT / PIERDERE primesc sufixul
│        │                                     „🤖 Filtru AI: aprobat — încredere N%"
│        │                                   · badge BOT·AI în Ordine Active, AI✓ în Rapoarte
│        │
│        ├─ RESPINS (încredere < prag / veto) ► semnal scris în signals.csv (audit)
│        │                                   · outcome imediat status=ai_reject, R=0
│        │                                   · NU intră în pending → zero ordine MT5
│        │                                   · Telegram „⛔ Filtru AI: RESPINS" cu
│        │                                     motivul + scorul + pragul
│        │
│        └─ EROARE AI (Ollama picat etc.) ──► FAIL-OPEN: trade permis, notat în log
│                                             + sufix „indisponibil la plasare"
└──────────────────────────────────────────────────────────────────────────────
```

Fiecare verdict (inclusiv transcriptul complet al dezbaterii) se scrie în
`data/live_signals/<sesiune>/ai_filter.jsonl` — citit de API pentru UI.

## De ce fail-open (nu fail-closed)

Edge-ul principal este al botului pe reguli (validat pe 8 ani de backtest). Filtrul e un
strat suplimentar de calitate, nu o dependință critică. Dacă infrastructura AI cade
(Ollama oprit, quota epuizată la toate sursele), oprirea tranzacționării ar transforma o
pană de AI într-o pană de bot. Prin contrast, motorul AI autonom face fail-safe → WAIT,
pentru că acolo AI-ul E strategia. Ambele comportamente sunt intenționate și diferite.

## Nivelurile de încredere

| Nivel | Prag | Când îl folosești |
|---|---|---|
| `permissive` | ≥ 50% | Vrei doar să tai setup-urile pe care consiliul le consideră clar slabe |
| `balanced` (default) | ≥ 70% | Recomandat — peste nivelul 55 pe care motorul AI îl tratează ca „acționabil normal" |
| `strict` | ≥ 85% | Doar convingere reală. Atenție: modelele mici raportează rar >85 pe date ambigue — puține trade-uri vor trece |

**De ce nu 50/75/90:** distribuția reală de confidence a LLM-urilor mici (qwen3:8b) se
aglomerează în banda 60–85; un prag de 90% ar respinge aproape tot (echivalentul
paraliziei 29/29 veto observate la motorul AI pe 2026-07-08/09, rezolvată atunci prin
veto-uri calificate). 85 păstrează semantica „doar excepționalul", dar rămâne atingibil.
Pragurile sunt definite în `ai_engine/trade_filter.py::FILTER_LEVELS`.

## Regulile aplicate în cod (LLM-ul propune, codul dispune)

1. Veto Risk Manager cu cod VALID (`NEWS_IMMINENT` / `EXTREME_VOL` / `WEEKEND_GAP` /
   `BAD_GEOMETRY`) → respins, indiferent de Head Trader.
2. Head Trader `approve=false` → respins.
3. `approve=true` dar `confidence < prag` → respins („sub prag").
4. Veto necalificat (fără cod valid) NU respinge — doar apare în motiv (anti-paralizie,
   aceeași regulă ca `council._sanitize`).
5. `DAILY_STOP` / `MAX_POSITIONS` nu sunt coduri de veto aici — botul pe reguli își
   gestionează singur limitele (circuit breaker, `max_concurrent_per_market`).

## Moștenirea configurației AI

Filtrul NU are configurare AI proprie. La FIECARE evaluare reîncarcă
`ai_engine/config.json` + `data/ai/providers.json` și face `registry.refresh()` —
exact ca motorul. Schimbi sursa/cheia/rolurile din tab-ul AI Engine → următoarea
evaluare le folosește, fără restart de bot. Failover-ul per sursă (quota → 6h pauză,
429 → 60s etc.) funcționează identic, în procesul fiecărei sesiuni.

## Configurare

Per sesiune, în tab-ul Profile → secțiunea „Filtru AI Pre-Trade":
- `ai_filter_enabled` (bool, default `false`)
- `ai_filter_level` (`permissive` / `balanced` / `strict`, default `balanced`)

Aplicate la runtime prin `active_profile_runtime.json` → `_apply_profile_overrides`
(ca orice alt parametru de sesiune). Sesiunile pornite din CLI fără profil folosesc
valorile din `SESSION_CONFIG` (unde lipsesc → dezactivat).

## Latență și cost

- 4 apeluri LLM secvențiale; pe Ollama/qwen3:8b tipic 10–60s total.
- Buget hard de timp: `TIME_BUDGET_S = 240` — verificat între roluri; depășit → fail-open.
- Entry-ul e un ordin STOP pending — prețul trebuie oricum să ajungă la nivel, deci
  întârzierea de evaluare nu strică execuția pe M15/H1.
- Semnalele sunt rare (~3-4/zi pe tot portofoliul) — impact de resurse neglijabil.
  Apelurile Ollama din mai multe sesiuni se serializează natural în server.

## Izolare față de motorul AI autonom

- Filtrul rulează ÎN procesul sesiunii live; motorul AI rulează în procesul lui.
  Se ating doar prin fișierele de config (read-only) și prin serverul Ollama (care
  serializează cererile).
- Filtrul NU scrie în ledger-ul motorului (`data/ai/ledger.db`) — are jurnalul lui
  JSONL per sesiune. Zero contenție SQLite cross-process.
- Magic number / poziții: filtrul nu plasează și nu atinge ordine — doar aprobă/respinge
  înainte de plasare. Ordinele rămân ale botului (comment = sig_id, fără magic AI).

## Fișiere

| Fișier | Rol |
|---|---|
| `ai_engine/trade_filter.py` | Consiliul de revizie + praguri + fail-open + jurnal |
| `live/signal_generator.py` | Integrarea în flux (`_ai_filter_check`, `_ai_note`) |
| `api/ai_filter_log.py` | Citirea jurnalelor pentru UI (cache pe mtime) |
| `api/routers/mt5status.py::/mt5/orders` | Badge BOT·AI (join pe comment[:16]) |
| `api/routers/reports.py::/reports/transactions` | Coloanele ai_approved/ai_confidence |
| `api/routers/sessions.py` (outcomes) | Câmpurile AI pe Outcome |
| `scripts/test_ai_filter.py` | Suita de teste (unit + integrare) |

## Statusul `ai_reject`

- Apare în `outcomes.csv` cu `result_r=0.0`, `triggered_at` gol.
- NU face parte din `_CLOSED_STATUSES` — nu intră în win-rate, expectancy, P&L,
  equity curve (ca `expirat`/`invalidat`).
- Vizibil în: SignalFeed („⛔ respins AI"), Rapoarte → Tranzacții (filtrul „Respins AI"),
  Notificări (categoria „Filtru AI").
