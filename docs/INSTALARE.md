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

> **Important:** Daca ai **cont Microsoft** (nu cont local), foloseste Metoda 2 — registry.
> Metoda netplwiz nu functioneaza pe Windows 11 cu cont Microsoft online.

**Metoda 1 — netplwiz** (conturi locale / Windows 10):
1. `Win + R` → tasteaza `netplwiz` → Enter
2. Selecteaza contul tau de utilizator
3. Debifeza **"Users must enter a user name and password"**
4. Aplica → introdu parola de cont de doua ori → OK
5. Reporneste si verifica ca porneste fara PIN

**Metoda 2 — Registry** (Windows 11 cu cont Microsoft — metoda confirmata):
1. `Win + R` → `regedit` → Enter
2. Naviga la: `HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon`
3. Verifica / seteaza valorile `String` (click dreapta → New → String Value daca nu exista):
   - `AutoAdminLogon` = `1`
   - `DefaultUserName` = `<numele_tau_de_utilizator>` (ex: `alext`)
   - `DefaultPassword` = `<parola_ta_Microsoft>` ← **trebuie creata manual daca lipseste**
4. Reporneste si verifica

> Parola este stocata in plain text in registry — acceptabil pe un PC personal de acasa,
> nu pe un PC partajat.

> **Nota:** Daca nu stii parola contului Microsoft, reseteaz-o la `account.live.com/password/reset`
> de pe telefon, apoi seteaz-o in registry.

---

### Pas B — Task Scheduler (MT5 + bot la login)

Task Scheduler necesita **PowerShell ca Administrator**. Doua optiuni:

**Optiunea 1 — Script automat** (recomandat la reinstalare):
```
Win → cauta "PowerShell" → click dreapta → "Run as administrator"
```
Apoi in fereastra Administrator:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "c:\trading-bot\scripts\setup_autostart.ps1"
```

**Optiunea 2 — Comenzi manuale** (daca scriptul nu merge):

Deschide PowerShell ca Administrator (`Win` → `powershell` → click dreapta → Run as administrator), apoi:

```powershell
# 1. Creeaza start_bot.bat
$py = (Get-Command python).Source
@"
@echo off
title Trading Bot -- Sesiuni Live
timeout /t 45 /nobreak
cd /d "c:\trading-bot"
"$py" live\run_all.py
pause
"@ | Set-Content "c:\trading-bot\live\start_bot.bat" -Encoding UTF8

# 2. Task pentru run_all.py (obligatoriu)
$bat = "c:\trading-bot\live\start_bot.bat"
$a = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`""
$t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Days 2)
Register-ScheduledTask -TaskName "TradingBot-RunAll" -Action $a -Trigger $t -Settings $s -RunLevel Highest -Force

# 3. Task pentru MT5 — ajusteaza calea daca e diferita
$mt5 = "C:\Program Files\MetaTrader 5 IC Markets EU\terminal64.exe"
$a2 = New-ScheduledTaskAction -Execute $mt5
$t2 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$s2 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName "TradingBot-MT5" -Action $a2 -Trigger $t2 -Settings $s2 -RunLevel Highest -Force
```

**La urmatoarea pornire Windows:**
- Windows se logheaza automat (fara PIN)
- MT5 porneste automat si se conecteaza la broker (memoreaza credentialele)
- Dupa 45 secunde: o fereastra CMD se deschide cu `run_all.py` activ
- Botul ruleaza non-stop fara nicio interventie

**Verificare task-uri (PowerShell normal):**
```powershell
Get-ScheduledTask -TaskName "TradingBot-*" | Select-Object TaskName, State
```
Trebuie sa apara: `TradingBot-MT5` si `TradingBot-RunAll` cu State = `Ready`.

**Stergere task-uri (daca vrei sa dezactivezi):**
```powershell
Unregister-ScheduledTask -TaskName "TradingBot-MT5" -Confirm:$false
Unregister-ScheduledTask -TaskName "TradingBot-RunAll" -Confirm:$false
```

---

## Notificari pe telefon (Telegram)

Botul trimite notificari Telegram la fiecare semnal detectat — functioneaza de oriunde,
nu depinde de Bluetooth sau retea locala.

### Setup Telegram Bot (o singura data)

**Pas 1 — Creaza bot-ul (din aplicatia Telegram pe telefon):**
1. Cauta `@BotFather` → Start
2. Trimite `/newbot` → alege un nume + username (ex: `tradingalext_bot`)
3. Copiaza **token-ul** primit (format: `1234567890:ABCdef...`)

**Pas 2 — Obtine chat_id:**
1. Cauta bot-ul tau in Telegram → Start → trimite orice mesaj
2. Deschide in browser: `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Copiaza valoarea `"id"` din `"chat"` (numar intreg)

**Pas 3 — Seteaza variabilele de mediu in Windows (PowerShell normal):**
```powershell
[Environment]::SetEnvironmentVariable("TELEGRAM_TOKEN", "<token-ul-tau>", "User")
[Environment]::SetEnvironmentVariable("TELEGRAM_CHAT_ID", "<chat-id-ul-tau>", "User")
```

> `"User"` = salvat permanent pentru contul tau Windows, persista la restart.
> Nu folosi `"Machine"` (necesita Administrator si se aplica tuturor utilizatorilor).

**Pas 4 — Verifica ca sunt setate corect:**
```powershell
[Environment]::GetEnvironmentVariable("TELEGRAM_TOKEN", "User")
[Environment]::GetEnvironmentVariable("TELEGRAM_CHAT_ID", "User")
```
Trebuie sa apara token-ul si chat_id-ul — nu mesaj gol.

**Pas 5 — Testeaza (deschide un terminal NOU dupa Pas 3):**
```powershell
python -c "from live.signal_generator import _send_telegram; _send_telegram('Test bot trading'); print('Trimis')"
```
Verifica telefonul — trebuie sa primesti mesajul in ~2 secunde.

**Actualizare token (daca il regenerezi din BotFather):**
```powershell
[Environment]::SetEnvironmentVariable("TELEGRAM_TOKEN", "<token-nou>", "User")
```
Reporneste botul (`run_all.py`) dupa actualizare — procesele existente au token-ul vechi in memorie.

**Stergere (daca vrei sa dezactivezi notificarile):**
```powershell
[Environment]::SetEnvironmentVariable("TELEGRAM_TOKEN", $null, "User")
[Environment]::SetEnvironmentVariable("TELEGRAM_CHAT_ID", $null, "User")
```

> Token-ul si chat_id-ul NU sunt stocate in cod — doar in variabile de mediu Windows.
> Nu le posta public (git, chat, etc). Daca le-ai expus, regenereaza cu `/revoke` la `@BotFather`.

**Format notificare primita pe telefon:**
```
Signal LONG EURUSD
Entry: 1.08450
SL:    1.08200
TP:    1.09000
R/R:   2.5R
S1-M15-LONG
```

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
| PC restartat noaptea | Windows Update — configureaza auto-login (Pas A) + task-uri (Pas B) |
| Auto-login nu functioneaza | Cont Microsoft: verifica `DefaultPassword` in regedit (Winlogon) — trebuie creat manual |
| Notificarile nu apar pe telefon | Verifica Phone Link conectat + TradingBot activat in Settings → Notifications |
| MT5 nu porneste la startup | Verifica task 'TradingBot-MT5' in Task Scheduler — a fost creat cu Run as Administrator? |
| `Register-ScheduledTask: Access denied` | PowerShell nu e deschis ca Administrator — Win → powershell → click dreapta → Run as administrator |
