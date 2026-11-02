# No Trading — Instalare și pornire

Fiecare calculator are instanța lui: contul MT5 propriu, datele proprii, configurările proprii.
Fluxul are **patru pași** și **trei scripturi**:

```
Prima instalare  →  setup.bat  →  start_ui.bat  →  stop_ui.bat / start_ui.bat (restart)
   (o dată)          (o dată, sau     (de fiecare        (oprire / repornire
                      ca reparare)     dată)              dashboard)
```

---

## 1. Prima instalare

1. **MetaTrader 5** — instalează terminalul brokerului (ex. ICMarkets), loghează-te și activează **Algo Trading**.
   Implicit aplicația lucrează doar pe cont **DEMO**; un cont REAL trebuie deblocat explicit, per engine,
   în *Settings → Trading LIVE*.
2. **Codul** — `git clone <URL_REPO> C:\trading-bot` (sau copiază folderul).
   Dacă nu ai Git, `setup.bat` îl instalează; rulează-l din folderul copiat.

## 2. Setup — `setup.bat` (dublu-click)

Un singur script, cap-coadă. Poate fi rulat oricând din nou: nu șterge și nu suprascrie nimic (profil,
configurări, date). Folosește-l și ca **reparare** când ceva lipsește.

| Pas | Ce face |
|-----|---------|
| Prerechizite | instalează / verifică prin `winget`: **Python 3.10+**, **Node.js 20.19 / 22.12+** (Vite 8 nu pornește pe Node 18), **Git** — dacă instalează ceva, continuă singur într-o fereastră nouă (PATH proaspăt) |
| 1/8 | verifică versiunile |
| 2/8 | `pip install -r requirements.txt` (inclusiv `tzdata` — fusurile orare pe Windows) |
| 3/8 | `npm install` în `frontend/` |
| 4/8 | creează directoarele de date care lipsesc (`data/live_signals/session1..22`, `data/ai`, `data/daily_engine`, `data/noisy_engine`, …) |
| 5/8 | verifică că fișierele de configurare existente sunt JSON valid (un fișier corupt e numit explicit) |
| 6/8 | MetaTrader 5 — **doar citire**: terminal pornit, cont logat, DEMO / REAL, Algo Trading |
| 7/8 | AI Engine (opțional) — întreabă dacă instalează **Ollama** + modelul din `ai_engine/config.json` (~5 GB) |
| 8/8 | verificare finală: toate modulele (API + cele 4 engine-uri) se încarcă, porturile 8000 / 5173 |

La final scrie **GATA** sau lista exactă cu ce lipsește și cum se repară.

Opțiuni: `setup.bat --with-ai` (AI fără întrebare) · `setup.bat --no-ai` · `setup.bat --check` (doar verifică).
Scurtăturile vechi `setupFirst.bat` și `setup_ai_engine.bat` apelează acum `setup.bat` (respectiv `--with-ai`).

## 3. Pornire — `start_ui.bat` (dublu-click, de fiecare dată)

Verifică întâi că setup-ul a fost făcut (altfel spune „rulează setup.bat”), oprește o instanță veche, pornește
**API-ul** (fereastra `TradingBotAPI`, port 8000) și **dashboard-ul** (`TradingBotUI`, port 5173), apoi deschide
browserul la <http://localhost:5173>.

**Engine-urile** (Custom / AI / Daily / Noisy) se pornesc și se opresc din **Dashboard** (cardul fiecăruia, cu
Start / Stop verificat și autostart opțional). Nu e nevoie de alte scripturi.

## 4. Oprire / restart

- **Oprire dashboard:** `stop_ui.bat` (sau închide ferestrele `TradingBotAPI` / `TradingBotUI`).
  Engine-urile sunt procese separate și **nu** se opresc odată cu dashboard-ul — oprește-le din Dashboard înainte,
  dacă vrei să le oprești.
- **Restart (ex. după un update de cod):** `start_ui.bat` din nou — oprește singur instanța veche. Engine-urile
  pornite încarcă codul nou abia după Stop + Start din Dashboard.

---

## Update-uri

| Branch | Script |
|--------|--------|
| `main` | `update_bot.bat` |
| `vlad-live` | `update-vlad-live.bat` (păstrează configurările locale) |
| `alex-live` (PC ↔ laptop) | `sync_data.bat` |

După un update cu dependențe noi: `setup.bat` (repară instalarea), apoi `start_ui.bat`.

---

## Date generate (rămân local)

```
data/
  profiles/          — profilul Custom Engine (standard.json)
  live_signals/      — semnalele și jurnalul sesiunilor Custom Engine
  ai/                — ledger-ul AI Engine, sursele AI (cheile API — nu partaja)
  daily_engine/      — trade-urile / starea Daily Engine
  noisy_engine/      — trade-urile / starea Noisy Engine
  telegram_config.json — credențiale Telegram (nu partaja)
```

---

## Probleme frecvente

| Simptom | Cauză / remediere |
|---------|-------------------|
| `start_ui.bat`: „Dependentele nu sunt instalate” | rulează `setup.bat` |
| Fereastra `TradingBotUI` se închide imediat | Node.js prea vechi (necesar 20.19 / 22.12+) — `setup.bat` îl actualizează |
| „MT5 nu e disponibil” / dashboard fără cont | deschide MetaTrader 5, loghează-te, activează Algo Trading |
| Engine-ul refuză contul | cont REAL nedeblocat — *Settings → Trading LIVE* (deblocare per engine, cu confirmare) |
| `setup.bat`: „fisiere corupte: …” | repară fișierul numit sau șterge-l (se recreează cu valorile implicite) |
| Portul 8000 / 5173 ocupat | `stop_ui.bat`, apoi `start_ui.bat` |
| Backtestele nu găsesc CSV-uri | normal la prima rulare — descarcă datele din interfață (MT5 deschis) |
| AI Engine: Ollama nu răspunde | `setup.bat --with-ai`, apoi `py -m ai_engine.doctor` |
