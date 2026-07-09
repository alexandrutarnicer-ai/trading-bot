# M0 — Metoda de audit statistic (explicat pe intelesul tuturor)

Acest document explica **ce face M0 si de ce**, fara jargon. Rezultatele concrete
sunt in [M0_RESULTS.md](M0_RESULTS.md). Contextul general: [AI_ENGINE_FEASIBILITY.md](AI_ENGINE_FEASIBILITY.md).

## Problema pe care o rezolva M0

Cand testezi multe configuratii de strategie si o pastrezi pe cea mai buna, castigatoarea
arata bine **si din noroc**. Analogie: daca 100 de oameni dau cu banul de 10 ori, cineva
va nimeri 8 steme — dar acel om nu e priceput la aruncat banul, doar a fost norocos.
Istoricul tau de research a testat zeci de configuratii per piata si a promovat sesiunile
dupa cea mai buna fereastra de test. Cu cat cauti mai mult, cu atat e mai probabil ca
"castigatoarea" sa fie zgomot.

Semn de alarma existent: la S1/S2, perioada de **train pierde** (−0.156R / −0.014R) iar
perioada de **test castiga**. Un edge real apare de obicei in ambele. Train-negativ /
test-pozitiv sugereaza adesea ca fereastra de test a prins doar un regim favorabil, nu un
efect durabil.

M0 pune, pentru fiecare sesiune, o singura intrebare: **"Edge-ul e real, sau e un artefact
al cat de mult am cautat?"** — cu trei unelte standard din literatura.

## Cum ruleaza (fara sa atinga nimic live)

M0 e **read-only**. Pentru fiecare sesiune ia parametrii din profil (`data/profiles/standard.json`),
ruleaza **exact acelasi motor de backtest** ca dashboard-ul (`engine.portfolio.run_portfolio`)
pe toata istoria CSV, si obtine seria de trade-uri cu R-ul realizat (`pnl_usd / risk_usd`).
Corectitudinea mecanica e dovedita: cu parametrii din `portfolio_backtest.py`, runner-ul
reproduce exact baseline-ul documentat (284 trade-uri) — vezi `m0/validate_runner.py`.

Apoi aplica trei teste pe seria de R.

## Unealta 1 — Bootstrap (edge-ul e distinct de zgomot?)

Backtestul da o expectancy, de ex. +0.11R/trade. Dar cu un numar finit de trade-uri,
cat de sigur poti fi ca adevarata expectancy e peste zero si nu doar noroc de esantion?

**Stationary block bootstrap** (Politis-Romano): re-esantioneaza seria de trade-uri de mii
de ori, in **blocuri** (nu trade individual), ca sa pastreze faptul ca trade-urile vin in
clustere de regim. Din distributia mediilor re-esantionate obtinem:

- **P(edge>0)** — increderea ca expectancy adevarat e pozitiv. ≥95% = edge distinct de zgomot.
- **Interval de incredere 95%** pe expectancy — daca include zero (sau e negativ), edge-ul
  nu e stabilit.

Aceasta e cifra cea mai importanta si mai bine fundamentata (foloseste date complete).

## Unealta 2 — Deflated Sharpe / "trial-uri de breakeven" N* (robust la cautare?)

**Probabilistic Sharpe Ratio** (Bailey & Lopez de Prado) si extensia lui **Deflated Sharpe
Ratio** corecteaza scorul pentru **cat de mult ai cautat**. Intuitie: +0.3R din 1 incercare
= impresionant; +0.3R din 40 de incercari = de asteptat chiar daca toate 40 erau inutile.

Fiindca fisierele de scan cu numarul real de configuratii testate nu mai exista, M0
raporteaza in schimb **N\*** = *de cate variante independente ai fi avut nevoie ca edge-ul
sa devina explicabil prin noroc de cautare*:

- **N\* mare** (sute/mii) → ar fi trebuit o cautare enorma ca sa fie noroc → solid.
- **N\* mic** (cateva) → chiar si o cautare modesta il explica → fragil, tratat ca avertizare.

N\* foloseste o dispersie de trial-uri **estimata** (1/T), pe care n-o putem calibra exact
fara datele de scan. De aceea N\* **nu decide singur verdictul** — e un semnal secundar de
"cat de sensibil e la multiple testing", afisat ca nota de avertizare.

## Unealta 3 — Consistenta pe fold-uri (stabil in timp sau un singur regim?)

Validarea existenta e **o singura taietura**: primele 70% train, ultimele 30% test. Verdictul
depinde complet de ce regim a nimerit in ultimele 30%.

M0 imparte in schimb istoricul in **8 sub-perioade contigue** si se uita la expectancy in
fiecare. Doua cifre:

- **Fold+** — fractia de sub-perioade pozitive. Aproape de 100% = edge stabil peste regimuri.
- **Trend (Spearman)** — daca expectancy creste sistematic de la fold-urile vechi la cele
  noi, edge-ul poate depinde de un regim **recent** (exact tiparul train-negativ/test-pozitiv).
  Un trend puternic pozitiv + fold-uri timpurii negative = steag rosu.

## Cum se decide verdictul

Regulile sunt mecanice (in `m0/audit.py::classify`), nu opinii:

| Verdict | Conditie |
|---|---|
| 🟢 **KEEP** | expectancy > 0 **si** P(edge>0) ≥ 95% **si** ≥60% din fold-uri pozitive |
| 🔴 **DEMOTE** | expectancy ≤ 0 **sau** P(edge>0) < 75% |
| 🟡 **OBSERVE** | orice altceva (semnal ambiguu) |
| ⚪ **INSUFF** | sub 30 de trade-uri — nu se poate concluziona |

N\* mic, trend de regim si train-negativ apar ca **note de avertizare** chiar si pe KEEP/OBSERVE.

## Ce faci cu rezultatul

- **KEEP** → sesiuni cu edge real, candidate pentru amplificare cu stratul AI (M3–M7).
- **OBSERVE** → pune pe `execute_trades=False` (ca session20 acum) si strange mai multe date.
- **DEMOTE** → pune pe pauza / opreste; nu mai plateste spread, comision si buget de risc pe
  un ne-edge. Beneficiu imediat, independent de partea AI.

Motivul pentru care M0 e **primul** pas: tot stratul AI (regime + meta-labeling) e un
**amplificator**. Amplificarea unui semnal care e de fapt zgomot da doar zgomot bine
calibrat. M0 spune care sesiuni merita amplificate.

## Reproductibilitate

```bash
python -m m0.validate_runner        # dovada ca runner-ul reproduce baseline-ul (284 trade-uri)
python -m m0.audit                  # audit complet, toate sesiunile
python -m m0.audit --sessions S1,S3 # doar unele
python -m m0.audit --quick          # bootstrap redus, pentru test rapid
```

Iesiri: `data/m0_audit.csv` (o linie per sesiune, toate metricile brute) si
`docs/M0_RESULTS.md` (raport citibil). Seed fix (42) → rezultate reproductibile.
