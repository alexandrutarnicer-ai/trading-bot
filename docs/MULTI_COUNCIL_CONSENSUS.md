# Multi-Council Consensus + Roluri AI suplimentare

Extinderea zonei de „consiliu" a motorului AI cu doua capabilitati **optionale**,
**dezactivate by default** si **complet backward-compatible**:

1. **Multi-Council Consensus** — pana la 3 consilii AI independente, fiecare pe o
   sursa AI diferita, analizeaza acelasi trade; increderile lor se combina intr-un
   verdict unic.
2. **Roluri AI suplimentare** — doua roluri noi (Analist Cantitativ, Avocatul
   Diavolului) care se adauga oricarui consiliu inainte de Head Trader.

Cu ambele oprite, filtrul pe reguli si motorul autonom se comporta **identic** cu
versiunea de dinainte (verificat: `scripts/test_ai_filter.py` 55/55, baseline-uri
neschimbate).

---

## 1. Arhitectura — ce se reutilizeaza

Un **consiliu** = dezbaterea de roluri (Technical → Macro → Risk → [Quant] →
[Devil's Advocate] → Head Trader) rulata pe un set de surse AI. Doi consumatori ai
consiliului existau deja si sunt reutilizati integral:

| | Motor autonom (`council.convene`) | Filtru Pre-Trade (`trade_filter.evaluate`) |
|---|---|---|
| Ruleaza pe | piete (`ai_engine/config.json`) | **sesiuni** (`ai_filter_*` per sesiune) |
| Produce | un trade complet (actiune + geometrie) | approve + confidence vs prag |
| La eroare | fail-**safe** → WAIT | fail-**open** → trade permis |

Componente noi, minime, fara duplicare:

- **`ai_engine/consensus.py`** — logica de combinare, **pura** (fara MT5/LLM):
  `CouncilOpinion`, `ConsensusVerdict`, `combine()`, `resolve_sources()`.
- **`ai_engine/council.py::DebateRunner`** — rularea rolurilor cu buget de timp +
  transcript, rutata fie **pinned** pe o sursa (fara failover — consilii de consens
  independente), fie via `role_assignments` cu failover (un singur consiliu, ca
  inainte). Reutilizat de `convene` SI de consiliul de revizie din `trade_filter`.
- **`ai_engine/providers.py::ProviderRegistry.call_role_pinned`** — apel pe EXACT o
  sursa, fara failover (altfel un consiliu ar deveni duplicatul altuia).
- **`ai_engine/orchestrator.py`** — consensul pentru motorul autonom: primarul
  propune, revizorii confirma.

---

## 2. Strategia de consens — media increderilor efective + veto absolut

Aleasa dintre {medie simpla, medie ponderata, vot majoritar, ponderare pe incredere}.

```
pentru fiecare consiliu participant i:
    approved_i  = head aproba SI fara veto valid
    effective_i = confidence_i daca approved_i altfel 0     # dizidenta conteaza

daca ORICE consiliu participant ridica un veto HARD valid → RESPINS (absolut)
altfel: APROBAT  ⟺  media(effective_i) >= prag              # prag implicit 70
```

**De ce media (nu ponderare / vot):**

- **Explicabila** — un singur numar, usor de justificat in notificare/UI.
- **Fara ponderi necalibrate** — nu avem inca outcome-uri reale ca sa justificam
  „Claude conteaza 2x cat Ollama"; ponderile arbitrare strica exact explicabilitatea.
  Strategia e izolata in `combine()`, deci se poate inlocui cu o versiune ponderata
  cand ledger-ul are date reale.
- **Dizidenta conteaza** — un consiliu care respinge aduce 0 la medie, deci trage
  decizia in jos (conservator, corect pentru risc).
- **Siguranta inainte de toate** — orice veto hard valid respinge, indiferent de medie
  (consistent cu „veto-ul Risk Manager e absolut" din codul existent).
- **Backward-compatible prin constructie** — media unui singur consiliu = increderea
  lui; regula se reduce EXACT la comportamentul de dinainte de feature.

**Toleranta la erori:** consiliile care esueaza nu se numara (`participated=False`).
Daca cel putin unul raspunde, decizia se ia pe cele ramase. Daca **niciunul** nu
raspunde → `all_failed` si apelantul aplica politica lui (filtru = fail-open →
permite; motor autonom = decide primarul / WAIT).

---

## 3. Cum ruleaza consensul la fiecare consumator

### Filtru Pre-Trade (per sesiune) — consilii simetrice

Toate consiliile revizuiesc acelasi semnal deja format. `evaluate()` planifica
sursele din `session_cfg` (`_plan_councils`), ruleaza fiecare consiliu (pinned) si
`combine()`. Fara secondary/tertiary → un singur consiliu distribuit pe roluri
(identic cu inainte).

```
semnal bot → [consiliu ollama] [consiliu claude] [consiliu gemini]
                        └──────── combine (media + veto) ────────┘
                        media >= prag ? → ordinul merge in MT5 : respins
```

### Motor autonom — consilii asimetrice (primar + revizori)

Consiliul **primar** construieste trade-ul (`convene`, produce geometrie). Daca sunt
configurate surse secundare/tertiare, acele consilii **revizuiesc** trade-ul propus
(aceleasi prompturi de revizie ca filtrul, via `trade_filter.review_trade`) si emit
fiecare o incredere. `orchestrator.decide` combina primarul + revizorii; sub prag sau
veto → decizia devine WAIT.

```
primar (ollama) → OPEN_LONG @ geometrie, conf 85
                       │  revizori pe trade-ul propus:
                       ├─ [claude] aproba 80
                       └─ [gemini] aproba 70
             combine([85, 80, 70]) = 78 >= 70 → EXECUTA
```

Daca revizorii pica → decide singur primarul (esecul unui consiliu optional nu
blocheaza niciodata trading-ul).

---

## 4. Roluri AI suplimentare

Ambele **dezactivate by default**, inserate inainte de Head Trader (care le vede in
prompt). Cand sunt oprite, secventa e EXACT cea de 4 roluri de dinainte.

| Rol | Responsabilitate | De ce complementar |
|---|---|---|
| 🧮 **Analist Cantitativ / Volatilitate** | Presiune pe NUMERE: e R/R justificat de o probabilitate de castig realista? E SL sensibil vs ATR/percentila? E EV (≈ win_prob·R − (1−win_prob)) pozitiv? | Analistul Tehnic vede structura, Risk Manager-ul vede expunerea hard; niciunul nu contesta matematica EV. |
| 😈 **Avocatul Diavolului** | Construieste cazul CONTRA + pre-mortem („presupune ca a atins SL — ce l-a omorat?"). | Contracareaza biasul de confirmare al mesei; Risk Manager-ul veteaza doar conditii hard, nu contesta teza. |

Rolurile se distribuie pe surse ca celelalte (`role_assignments` are chei `quant` /
`devils_advocate`) si costa cate un apel LLM in plus per consiliu.

---

## 5. Configurare

### Filtru (per sesiune, in profil / tab-ul Profile → „Filtru AI Pre-Trade")

| Camp | Default | Ce face |
|---|---|---|
| `ai_filter_enabled` | `false` | activeaza filtrul |
| `ai_filter_level` | `balanced` | pragul (permissive 50 / balanced 70 / strict 85) |
| `ai_filter_primary_source` | `null` | sursa consiliului 1 (`null` = distribuit pe roluri) |
| `ai_filter_secondary_source` | `null` | sursa consiliului 2 (optional, distincta) |
| `ai_filter_tertiary_source` | `null` | sursa consiliului 3 (optional, distincta) |
| `ai_role_quant_enabled` | `false` | Analist Cantitativ |
| `ai_role_devils_advocate_enabled` | `false` | Avocatul Diavolului |

### Motor autonom (`ai_engine/config.json`, tab-ul AI Engine)

| Camp | Default | Ce face |
|---|---|---|
| `council_primary_source` | `null` | sursa consiliului primar (`null` = distribuit pe roluri) |
| `council_secondary_source` | `null` | revizor 1 (optional, distinct) |
| `council_tertiary_source` | `null` | revizor 2 (optional, distinct) |
| `consensus_threshold` | `70` | media increderilor >= prag → executa (clamp 50–90) |
| `role_quant_enabled` | `false` | Analist Cantitativ |
| `role_devils_advocate_enabled` | `false` | Avocatul Diavolului |

**Reguli de validare (API `PUT /ai/config`, si UI):**
- fiecare consiliu foloseste o sursa **distincta** (scopul e opinia independenta);
- consiliu multiplu necesita **cel putin 2 surse AI active**;
- sursele trebuie sa existe si sa fie enabled.

**Setup surse AI:** din tab-ul AI Engine → cardul **Surse AI**, adaugi/activezi surse
(Claude, Gemini, orice API compatibil OpenAI) si le pui cheile. Apoi le alegi ca
Consiliu 2/3. Vezi [PLAN_SURSE_AI_MULTI_PROVIDER.md](PLAN_SURSE_AI_MULTI_PROVIDER.md).

Toate schimbarile se aplica la **urmatorul consiliu** (hot-reload, fara restart).

---

## 6. Vizibilitate

- **Jurnal filtru** `data/live_signals/<sesiune>/ai_filter.jsonl`: `n_councils`,
  `consensus_confidence`, `sources`, `councils[]` (per consiliu: sursa, approved,
  confidence, veto) + transcriptul consiliului primar.
- **Ledger motor** `data/ai/ledger.db`: transcriptul consiliului primar + cheile
  `_consensus` / `_reviewers` (verdict + opinii per revizor).
- **Notificari Telegram** „Ordin plasat": sufix „consens N consilii (surse)".
- **UI:** SessionEditor (config filtru), tab-ul AI Engine (cardul „Consiliu multiplu +
  roluri" + blocul de consens in transcriptul deciziei), Rapoarte/Tranzactii
  (`ai_n_councils`, `ai_consensus`).

---

## 7. Teste

- `scripts/test_multi_council.py` — 44 teste: `combine` (1/2/3 consilii, dizidenta,
  veto, fault tolerance, all-failed), `resolve_sources`, `call_role_pinned` (fara
  failover), `evaluate` end-to-end multi-council, surse duplicate, roluri optionale,
  `orchestrator.decide` (primar+revizori, veto, revizori picati, primar WAIT).
- `scripts/test_ai_filter.py` — 55 teste de **regresie** (comportament identic cu 1
  consiliu, fail-open, jurnal, integrare in signal_generator).
- `ai_engine/selftest.py` — `test_consensus` (combine + surse pinned) + consiliul LIVE.
