# Trading Bot — Ghid Instalare

Acest ghid te ajuta sa rulezi propria instanta a aplicatiei pe calculatorul tau Windows.
Fiecare persoana are instanta sa independenta: cont propriu MT5, semnale proprii, backtest pe datele proprii.

---

## Ce ai nevoie (prerequisite)

| Software | Versiune minima | Link download |
|----------|----------------|---------------|
| Windows  | 10 / 11        | — |
| Python   | 3.10+          | https://www.python.org/downloads/ |
| Node.js  | 18+ (LTS)      | https://nodejs.org/ |
| MetaTrader 5 | orice versiune | https://www.metatrader5.com/ |
| Git      | orice versiune | https://git-scm.com/ |

**Important la instalarea Python:** bifeaza `Add Python to PATH`.

**MetaTrader 5:** ai nevoie de un cont demo gratuit. Recomandare: [ICMarkets](https://www.icmarkets.com/) (Global sau EU) — spread mic, suport algorithmic trading. La inregistrare alege `Demo Account`.

---

## Instalare (o singura data)

### Pasul 1 — Cloneaza codul

Deschide Command Prompt sau PowerShell si ruleaza:

```powershell
cd C:\
git clone <URL_REPO> trading-bot
cd trading-bot
```

*(Cere link-ul repo de la cel care ti-a trimis acest ghid.)*

### Pasul 2 — Setup automat

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup_instance.ps1
```

Scriptul instaleaza automat toate dependentele Python si npm. Dureaza ~2 minute la primul run.

---

## Pornire aplicatie

### Deschide MT5 si conecteaza-te pe contul demo

Aplicatia are nevoie ca MT5 sa fie deschis si logat pentru a:
- vedea balance/equity in dashboard
- descarca date istorice pentru backteste
- rula botul live

### Porneste API + Frontend

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\start_app.ps1
```

Se deschid doua ferestre PowerShell (API pe portul 8000 si frontend pe 5173) si browserul se deschide automat la **http://localhost:5173**.

---

## Prima utilizare

### 1. Configureaza un profil

Mergi la tab-ul **Profile**. Profilul Standard este preconfigurat cu cele mai bune setari validate.

Poti modifica:
- **Piete** — ce perechi valutare urmaresti
- **Timeframe** — M15, H1, etc.
- **RSI / EMA alignment** — filtre de calitate semnal
- **R-ladder** — tinta profit per trade (ex: 2.5R pana la 5.5R)
- **Sesiune** — orele in care botul genereaza semnale

### 2. Ruleaza un backtest

In tab-ul **Profile**, selecteaza o sesiune si apasa **Ruleza Backtest**.
- Daca datele CSV lipsesc, aplicatia iti ofera optiunea de a le descarca direct din MT5.
- Rezultatele se salveaza automat in tab-ul **Istoric**.

### 3. Porneste botul live

Dupa ce esti multumit de parametri, apasa **Start** din dashboard.
Botul genereaza semnale, plaseaza ordine pending in MT5 si trimite notificari Telegram (daca e configurat).

### 4. Configureaza Telegram (optional)

In **Profile → Telegram Settings**: introdu token-ul botului si chat ID-ul tau.
Vei primi notificari la fiecare semnal nou, TP si SL.

---

## Acces remote (optional)

Daca vrei sa accesezi dashboard-ul de pe alt dispozitiv (telefon, laptop) cand esti plecat de acasa:

```powershell
# Instaleaza cloudflared
winget install Cloudflare.cloudflared

# Porneste un tunel catre frontend
cloudflared tunnel --url http://localhost:5173
```

Ti se genereaza un URL de forma `https://xxx.trycloudflare.com`. Acesta e temporar (dispare cand inchizi fereastra). Pentru un URL permanent, creeaza un cont gratuit la [Cloudflare](https://cloudflare.com) si configureza un named tunnel.

---

## Structura date generate

Toate datele tale sunt stocate local in `data/`:

```
data/
  profiles/         — profilele tale de configurare (JSON)
  live_signals/     — semnalele si rezultatele sesiunilor live
    session1/       — signals.csv, outcomes.csv, state.pkl, generator.log
    ...
  backtest_history.json   — istoricul backtestelor rulate
  telegram_config.json    — credentiale Telegram (nu partaja acest fisier)
```

Datele nu se trimit nicaieri — tot ruleaza local pe calculatorul tau.

---

## Probleme frecvente

**"MT5 nu e disponibil"**
→ Asigura-te ca MetaTrader 5 este deschis si logat pe cont. Botul necesita MT5 activ.

**"Eroare la pip install"**
→ Verifica conexiunea la internet si ca Python este adaugat in PATH.
→ Incearca: `python -m pip install --upgrade pip` apoi reia setup-ul.

**"npm: command not found"**
→ Node.js nu e instalat sau nu e in PATH. Reinstaleaza de la nodejs.org si reporneste PowerShell.

**Backtestele nu gasesc date CSV**
→ Normal la prima rulare — apasa "Descarca date din MT5" din interfata (MT5 trebuie deschis).

**Portul 8000 sau 5173 e ocupat**
→ Inchide alte aplicatii care folosesc aceste porturi, sau modifica portul in `api/main.py` si `frontend/vite.config.ts`.
