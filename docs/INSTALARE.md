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

Deschide **doua ferestre de terminal** si ruleaza:

```bash
# Terminal 1 — Session 1 (EUR pairs, Marti-Vineri 10:00-18:00)
python live/session1_m15_long.py

# Terminal 2 — Session 2 (EUR + JPY pairs, Luni-Vineri 02:00-18:00)
python live/session2_m5_both.py
```

Oprire: `Ctrl+C` in fiecare terminal.

---

## Orarul botului

| Sesiune | Zile | Ore (Romania EET) |
|---|---|---|
| **Session 1** | Marti – Vineri | 10:00 – 18:00 |
| **Session 2 (EUR)** | Luni – Vineri | 10:00 – 18:00 |
| **Session 2 (JPY)** | Luni – Vineri | 02:00 – 10:00 |

Recomandat: lasa ambele sesiuni pornite **non-stop Luni–Vineri**.  
Engine-ul doarme intre bare (~15 min), consum de resurse foarte mic.

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

Deschide **doua terminale** si ruleaza simultan:

```bash
# Terminal 1
python live/session1_m15_long.py

# Terminal 2
python live/session2_m5_both.py
```

Ambele trebuie sa ruleze in paralel pentru a acumula date din ambele sesiuni.

---

## Troubleshooting frecvent

| Problema | Solutie |
|---|---|
| `MT5 initialize() failed` | Deschide MT5 si logheaza-te pe demo |
| `FileNotFoundError: EURUSD_M15.csv` | Ruleaza `python scripts/descarca_date.py` |
| `ModuleNotFoundError: MetaTrader5` | Ruleaza `pip install MetaTrader5` |
| `Python not found` | Reinstaleaza Python cu "Add to PATH" bifat |
| Sesiunea nu genereaza semnale | Normal — citeste `docs/SESIUNI_LIVE.md` sectiunea 6 |
