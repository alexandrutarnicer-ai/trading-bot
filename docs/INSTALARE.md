# Ghid instalare — Trading Bot pe laptop nou

**Timp estimat:** 20–30 minute (inclus download date ~10 min)

---

## Cerinte minime

| Cerinta | Detaliu |
|---|---|
| **Sistem operare** | Windows 10 / 11 (MetaTrader5 nu exista pe Mac/Linux) |
| **Python** | 3.11 sau mai nou |
| **Git** | orice versiune recenta |
| **MetaTrader5** | instalat + logat pe contul DEMO IC Markets |
| **Internet** | necesar la descarcare date + rulare live |
| **RAM** | minim 4 GB (recomandat 8 GB) |

---

## Pasii de instalare

### Pas 1 — Instaleaza Python (daca nu ai)

Descarca de la [python.org](https://www.python.org/downloads/) versiunea 3.11 sau 3.12.  
**Bifat la instalare:** `Add Python to PATH`

Verifica:
```
python --version
```
Trebuie sa apara `Python 3.11.x` sau mai nou.

---

### Pas 2 — Instaleaza MetaTrader5

Descarca MT5 de la brokerul tau (IC Markets).  
Logheaza-te pe **contul DEMO** (nu pe cel real).  
Lasa MT5 deschis si logat — botul se conecteaza la el.

---

### Pas 3 — Cloneaza repository-ul

```bash
git clone https://github.com/<user>/trading-bot.git
cd trading-bot
```

> Inlocuieste `<user>` cu username-ul tau de GitHub.

---

### Pas 4 — Instaleaza dependentele Python

```bash
pip install -r requirements.txt
```

Instaleaza: `pandas`, `numpy`, `MetaTrader5`.  
Dureaza 1–2 minute.

---

### Pas 5 — Descarca datele istorice din MT5

> **MT5 trebuie sa fie deschis si logat** pentru acest pas.

```bash
python scripts/descarca_date.py
```

Descarca ~200.000 bare M15 + M30 pentru fiecare pereche.  
**Dureaza ~10 minute.** Fisierele se salveaza in `data/`.

> Datele nu sunt in git (`.gitignore`) — trebuie descarcate pe fiecare masina separat.

---

### Pas 6 — Verifica instalarea

```bash
python scripts/verifica_instalare.py
```

Verifica automat:
- Python si pachete
- Structura proiectului
- Datele istorice (M15/M30)
- Conexiunea la MT5
- Importul tuturor modulelor
- Un backtest smoke test rapid

**Rezultat asteptat:**
```
  REZULTAT: TOTUL OK — botul este pregatit de rulare
```

Daca apar erori, scriptul indica exact ce lipseste si cum se rezolva.

---

### Pas 7 — Porneste sesiunile live

> **MT5 trebuie sa fie deschis si logat pe DEMO.**

```bash
python live/run_all.py
```

Porneste toate 4 sesiunile simultan si afiseaza status la fiecare 5 minute.
Oprire: `Ctrl+C` in terminal.

---

## Orarul botului

| Sesiune | Zile | Ore (Romania vara, EEST) | Note |
|---|---|---|---|
| **S1** FX Long | Marti – Vineri | 13:00 – 21:00 | EUR/GBP/JPY LONG |
| **S2** FX Both | Luni – Vineri | 05:00 – 21:00 | EUR + JPY, BOTH |
| **S3** BTC Both | Luni – Vineri + Dum | 03:00 – 12:00 + 18:00 – 21:00 | crypto, skip Sambata |
| **S4** GER40+US30 | Marti – Duminica | 12:00 – 00:00 | LONG only, demo execution |

Recomandat: lasa `run_all.py` pornit **non-stop**. Engine-ul doarme intre bare (~15 min), consum de resurse foarte mic.
Detalii complete: `SESIUNI.md` din radacina proiectului.

---

---

## Pornire automata la restart PC

Daca PC-ul reporneste (ex. Windows Update), botul si MT5 se pot relansa automat.
Necesita **doua configurari**: auto-login (fara PIN) + Task Scheduler.

### Pas A — Auto-login (fara PIN la pornire)

> Recomandat doar pentru PC/laptop de acasa. Nu faci asta pe un PC de birou.

**Metoda 1 — netplwiz** (Windows 10 / unele versiuni Windows 11):
1. `Win + R` → tasteaza `netplwiz` → Enter
2. Selecteaza contul tau de utilizator
3. Debifeza **"Users must enter a user name and password"**
4. Aplica → introdu parola de cont de doua ori → OK
5. Reporneste si verifica ca porneste fara PIN

**Metoda 2 — Registry** (Windows 11 22H2+ daca netplwiz nu arata optiunea):
1. `Win + R` → `regedit` → Enter
2. Naviga la: `HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon`
3. Seteaza / creeaza urmatoarele valori `String`:
   - `AutoAdminLogon` = `1`
   - `DefaultUserName` = `<numele_tau_de_utilizator>`
   - `DefaultPassword` = `<parola_ta>`
4. Reporneste si verifica

> Parola este stocata in plain text in registry — acceptabil pe un PC personal de acasa,
> nu pe un PC partajat.

---

### Pas B — Task Scheduler (MT5 + bot la login)

Ruleaza scriptul de setup (o singura data, dupa care task-urile persista):

```
click dreapta pe: scripts\setup_autostart.ps1
→ "Run with PowerShell"  (sau "Run as Administrator" daca cere)
```

Scriptul face automat:
1. Gaseste MT5 si creeaza task `TradingBot-MT5` — porneste la login
2. Creeaza `live\start_bot.bat` si task `TradingBot-RunAll` — porneste la 45s dupa login

**La urmatoarea pornire Windows:**
- MT5 porneste automat si se conecteaza la broker (memoreaza credentialele)
- Dupa 45 secunde: o fereastra CMD se deschide cu `run_all.py` activ
- Botul ruleaza non-stop fara nicio interventie

**Verificare task-uri:**
```
Start menu → cauta "Task Scheduler" → Task Scheduler Library
Trebuie sa apara: TradingBot-MT5  si  TradingBot-RunAll
```

**Stergere task-uri (daca vrei sa dezactivezi):**
```powershell
Unregister-ScheduledTask -TaskName "TradingBot-MT5" -Confirm:$false
Unregister-ScheduledTask -TaskName "TradingBot-RunAll" -Confirm:$false
```

---

## Notificari pe telefon (Phone Link)

Botul trimite notificari Windows Toast la fiecare semnal detectat.
Prin **Phone Link** (Microsoft) aceste notificari pot fi redirectate pe telefonul Android.

### Setup Phone Link

**Pe PC (Windows 11 — pre-instalat):**
1. Start → cauta `Phone Link` → deschide
2. Selecteaza `Android` → conecteaza-te cu contul Microsoft
3. Urmeaza instructiunile QR code

**Pe telefon (Android):**
1. Instaleaza **"Link to Windows"** din Play Store
2. Conecteaza-te cu acelasi cont Microsoft
3. Scaneaza QR code-ul de pe PC

**Activare notificari in Phone Link:**
1. In app Phone Link pe PC: `Settings` → `Features` → `Notifications` → ON
2. Prima data cand botul detecteaza un semnal, apare `TradingBot` in lista de aplicatii
3. Asigura-te ca `TradingBot` este activat:
   - Windows Settings → System → Notifications → scroll jos → `TradingBot` → ON
   - In Phone Link Settings → Notifications → `TradingBot` → ON (sau "Sync all")

**Rezultat:** cand botul detecteaza un semnal, primesti notificare pe telefon cu:
- Simbolul si directia (ex: `Signal SHORT NZDJPY`)
- Entry / SL / TP si R ratio

> Phone Link necesita ambele dispozitive conectate la internet si Bluetooth activ pe telefon.

---

## Comenzi utile

```bash
# Verifica instalarea
python scripts/verifica_instalare.py

# Backtest Session 1 (reproduce baseline oficial: 284 trades, +0.025R)
python portfolio_backtest.py

# Backtest Session 2 (reproduce: 1022 trades, +0.029R)
python session2_backtest.py

# Backtest combinat (ambele sesiuni + sumar)
python combined_backtest.py

# Analiza date acumulate din OBSERVE
python scripts/analiza_observe.py

# Descarca date noi din MT5 (dupa o pauza lunga)
python scripts/descarca_date.py
```

---

## Structura datelor generate de sesiuni

```
data/live_signals/
├── session1/
│   ├── signals.csv     ← semnalele generate (un rand per semnal)
│   ├── outcomes.csv    ← rezultatele (TP / SL / expirat)
│   ├── state.pkl       ← stare persistenta intre reporniri
│   └── generator.log  ← log complet cu timestamp
└── session2/
    └── (aceleasi fisiere)
```

Dupa ~13 saptamani (Session 2) sau ~43 saptamani (Session 1), ruleaza:
```bash
python scripts/analiza_observe.py
```
pentru a compara performanta live cu backtestul.

---

## Pornire rapida (dupa instalare)

```bash
python live/run_all.py
```

Porneste toate 4 sesiunile simultan. Status la fiecare 5 min. Ctrl+C opreste tot.

Sau cu autostart configurat (dupa `setup_autostart.ps1`): reporneste PC-ul — totul porneste singur.

---

## Troubleshooting frecvent

| Problema | Solutie |
|---|---|
| `MT5 initialize() failed` | Deschide MT5 si logheaza-te pe demo |
| `FileNotFoundError: EURUSD_M15.csv` | Ruleaza `python scripts/descarca_date.py` |
| `ModuleNotFoundError: MetaTrader5` | Ruleaza `pip install MetaTrader5` |
| `Python not found` | Reinstaleaza Python cu "Add to PATH" bifat |
| Sesiunea nu genereaza semnale | Normal — citeste `docs/SESIUNI_LIVE.md` sectiunea 6 |
| PC restartat noaptea | Windows Update — configureaza auto-login + setup_autostart.ps1 |
| Notificarile nu apar pe telefon | Verifica Phone Link conectat + TradingBot activat in Settings → Notifications |
| MT5 nu porneste la startup | Verifica task 'TradingBot-MT5' in Task Scheduler — Run as Administrator |
