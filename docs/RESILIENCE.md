# Reziliența aplicației — incidente, recuperare, pornire automată (23.11.2026)

Pe scurt: aplicația **detectează** problemele (internet, MT5, Ollama, engine-uri căzute / blocate, disc, bază de date,
Sleep, restart Windows, oprire necurată), te **notifică o singură dată** pe Telegram (cu reamintiri rare cât persistă și
un mesaj de **recuperare confirmată** cu durata) și **recuperează automat** ce se poate recupera în siguranță. Nimic din
acest mecanism nu plasează, nu închide și nu modifică ordine; pozițiile deschise rămân mereu protejate de SL / TP la broker.

## 1. Componente

| Componentă | Fișier | Rol |
|---|---|---|
| Incidente centrale | `incidents.py` | un incident activ pe problemă; confirmare înainte de prima notificare; reamintiri 10 / 30 / 60 min (max 6); recuperare cu durata; outbox persistent |
| Monitorizare | `api/health_monitor.py` | verificări la 30 s în procesul API; `/api/health/full`, `/api/health/check` |
| Watchdog engine-uri | `api/watchdog.py` | repornește Daily / Special (max 3 / oră); Custom doar alertă (poziții reale); AI are watchdog propriu |
| Pornire condiționată | `startup_gate.py` | autostart la login: pornește engine-ul DOAR după verificarea dependențelor |
| UI | Settings → Sănătatea aplicației / Pornire automată; Dashboard → banner (doar cu incidente active) | |

## 2. Ce se întâmplă când…

| Situație | Detectare | Ce face aplicația | Intervenția ta |
|---|---|---|---|
| **Internet căzut** | TCP + DNS, confirmat după 90 s | incident critic; engine-urile nu pot plasa ordine (MT5 deconectat); Telegram așteaptă în outbox | nu, dacă revine; mesaj de recuperare cu durata |
| **MT5 închis / crash / delogat** | terminal + cont, confirmat după 5 min | incident; engine-urile se reconectează singure (`_ensure_ipc` / `_ensure_terminal`) și re-citesc pozițiile / ordinele proprii din MT5 | redeschide MT5 dacă nu repornește singur |
| **MT5 deconectat de la broker** | `terminal_info().connected`, 5 min | incident; Daily / Noisy sar iterațiile (fără decizii pe date înghețate) | nu, de regulă |
| **AutoTrading oprit** | `trade_allowed` | incident (doar cu engine-uri pornite) | Alt+A în MT5 |
| **Ollama oprit / blocat** | `/api/tags`, doar cu AI pornit, 2 min | **pornește automat `ollama serve`** (max 3 / oră); AI nu deschide nimic nou (WAIT la erori); pozițiile rămân pe SL / TP + închiderea de weekend | dacă nu revine: reinstalează / `python -m ai_engine.doctor` |
| **Model Ollama lipsă** | lista de modele | incident cu comanda `ollama pull` | da |
| **Gemini: cotă epuizată / indisponibil** | registrul surselor | un singur mesaj informativ; rolurile lui trec pe Ollama (aceleași reguli de risc); revine singur | nu |
| **Engine oprit neașteptat** | PID mort + „stare dorită” | Daily / Special: repornit automat (max 3 / oră, apoi incident critic); AI: watchdog-ul AI; Custom: incident (fără repornire automată) | Custom: pornește-l din Dashboard după verificare |
| **Engine blocat** | heartbeat vechi (Daily 5 min, Special 10, AI 45, Custom 3 h) | incident „pare blocat” | oprește / pornește din Dashboard |
| **Disc aproape plin** | < 2 GB / < 0,5 GB | incident | eliberează spațiu |
| **Baza de date AI** | citire ledger | incident | verifică fișierul / antivirusul |
| **Sleep / Hibernate / StandBy / capac închis** | ceasul sare peste interval | mesaj „sistemul a fost suspendat N min” — engine-urile NU au rulat; la trezire se reconectează | verifică pozițiile; vezi §4 |
| **Restart Windows / pană de curent / crash / kill** | la pornirea API: heartbeat fără marcaj de oprire curată + ora pornirii Windows | mesaj „oprire NECURATĂ” cu durata întreruperii și engine-urile de verificat | doar dacă autostart-ul nu e activ |
| **Telegram indisponibil** | trimitere eșuată | mesajele rămân în outbox (persistat), retrimise o dată / minut, marcate „întârziat” cu ora reală | nu |

**Limitare onestă:** la o pană de curent / crash, procesul nu mai poate trimite nimic în acel moment. Aplicația
raportează întreruperea **la următoarea pornire**, pe baza datelor persistate (ultimul semn de viață, ora pornirii Windows).

## 3. Pornire automată (Autostart) per engine

**Oprită implicit pentru toate.** Se activează separat, din Settings → Pornire automată sau din cardul engine-ului (UAC).

| Engine | Autostart | Mecanism |
|---|---|---|
| Custom Engine | da | task `TradingBot-RunAll` (scriptul dedicat, profilul activ) |
| AI Engine | da | `startup_gate` — internet + MT5 conectat + cont + **Ollama răspunde** (pornit automat o dată) |
| Daily Engine | da | `startup_gate` — internet + MT5 conectat + cont + configurație validă |
| Special Engine (alex-live) | da | `startup_gate` — la fel ca Daily |
| Aplicația (API + monitorizare) | da | `startup_gate --engine app` — fără ea, după un restart nu există watchdog / incidente / rapoarte |
| **Noisy Engine** | **NU** | exclus intenționat — doar pornire manuală, cu confirmare |

Secvența după login / restart: întârziere minimă (AI 75 s, Daily / Special 60 s, aplicația 20 s) → verificarea
dependențelor cu reîncercări tot mai rare (15 s → 60 s) → **pornire doar dacă totul e validat** → verificare că procesul
trăiește → Telegram „pornit automat” cu ce s-a verificat. Dacă dependențele nu vin în timpul maxim (Daily / Special 20 min,
AI 25 min), engine-ul **rămâne OPRIT** și primești un incident critic. Nu se pornește nimic „pentru că a trecut întârzierea”.
Engine-urile își refac singure starea din MT5 (pozițiile / ordinele proprii după magic + comment), piețele pe Pauză rămân
pe Pauză, Daily armează ziua doar înainte de formarea intervalului (o pornire târzie = zi Shadow, fără ordine). Setări:
`data/autostart_config.json` (opțional). Jurnal: `data/<engine>/autostart.log`.

**Migrare:** AI Engine folosea un `.bat` cu `ping` (îngheța la boot). Dacă autostart-ul AI era deja activ, dezactivează-l
și reactivează-l o dată, ca să treacă pe noul mecanism.

## 4. Sleep / StandBy / Hibernate — limitare importantă

În Sleep / Hibernate procesele **nu rulează**: niciun engine nu vede piața, nu închide la final de fereastră, nu aplică
închiderea de vineri. Singura protecție rămâne SL / TP-ul atașat ordinelor la broker. Aplicația:
- citește (doar citire, `powercfg`) setările de Sleep / Hibernare / capac și te avertizează o dată pe zi dacă un engine
  rulează și Windows poate intra singur în Sleep;
- detectează la trezire că sistemul a dormit și îți spune cât.

Aplicația **nu modifică** setările Windows. Pentru Live: Control Panel → Power Options → „Put the computer to sleep: Never”
(pe priză) și „When I close the lid: Do nothing”.

## 5. Cum se comportă pozițiile când o componentă cade

| Componentă căzută | Ordine noi | Poziții deschise |
|---|---|---|
| AI (Ollama + Gemini) | AI Engine: niciuna (WAIT); celelalte engine-uri: neafectate | SL / TP la broker + închiderea de weekend AI (deterministă) |
| MT5 / internet | niciun engine | SL / TP la broker; la revenire engine-urile re-citesc starea și evită dublurile (ordinele / trade-urile deja plasate sunt marcate în stare) |
| Telegram | neafectate | neafectate (mesajele așteaptă) |
| API (dashboard) | engine-urile rulează independent | neafectate; fără watchdog / incidente cât timp API-ul e oprit |

Teste: `scripts/test_incidents.py` (22), `scripts/test_health_monitor.py` (25), `scripts/test_startup_gate.py` (16),
`scripts/test_engine_lifecycle.py` (24), `scripts/test_mt5_health.py` (11).
