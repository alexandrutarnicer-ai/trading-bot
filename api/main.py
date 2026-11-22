"""
Trading Bot API — FastAPI backend
==================================
Ruleaza INDEPENDENT de run_all.py, citeste fisierele in read-only.
Nu interfereaza cu sesiunile live.

Pornire:
    python api/main.py
    sau
    uvicorn api.main:app --reload --port 8000

"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import bot, sessions, profiles, backtest, markets, data_download, settings, mt5status
from api.routers import backtest_history, notifications, reports, ai_engine
from api.routers import telegram_bridge
from api.routers import daily_engine
from api.routers import noisy_engine
from api import engine_lifecycle
from api.routers import dashboard
from api.routers import sizing
from api.watchdog import start_watchdog
from api.notifications import migrate_to_jsonl
from api.scheduled_reports import start_scheduler as start_reports_scheduler

app = FastAPI(title="Trading Bot API", version="1.0.0")


@app.on_event("startup")
def _startup():
    migrate_to_jsonl()   # converstie JSON array legacy → JSONL (one-time, idempotent)
    start_watchdog()
    start_reports_scheduler()
    try:                 # monitorizarea centrala (incidente, oprire necurata, sleep) — nu blocheaza pornirea API-ului
        from api import health_monitor
        health_monitor.start()
    except Exception:    # noqa: BLE001
        pass


@app.on_event("shutdown")
def _shutdown():
    try:                 # oprire CURATA → la urmatoarea pornire nu se raporteaza „oprire necurata”
        from api import health_monitor
        health_monitor.mark_clean_shutdown()
    except Exception:    # noqa: BLE001
        pass

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bot.router,           prefix="/api")
app.include_router(sessions.router,      prefix="/api")
app.include_router(profiles.router,      prefix="/api")
app.include_router(backtest.router,      prefix="/api")
app.include_router(markets.router,       prefix="/api")
app.include_router(data_download.router, prefix="/api")
app.include_router(settings.router,      prefix="/api")
app.include_router(mt5status.router,          prefix="/api")
app.include_router(backtest_history.router,   prefix="/api")
app.include_router(notifications.router,      prefix="/api")
app.include_router(reports.router,            prefix="/api")
app.include_router(ai_engine.router,          prefix="/api")
app.include_router(telegram_bridge.router,    prefix="/api")
app.include_router(daily_engine.router,       prefix="/api")
app.include_router(noisy_engine.router,       prefix="/api")
app.include_router(engine_lifecycle.router,   prefix="/api")
app.include_router(dashboard.router,          prefix="/api")
app.include_router(sizing.router,             prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/health/full")
def health_full():
    """Starea fiecarei componente (internet, MT5, Ollama, Gemini, engine-uri, disc, baza de date, Telegram, alimentare)
    + incidentele active / recente — din monitorizarea centrala (api/health_monitor.py)."""
    from api import health_monitor
    return health_monitor.status()


@app.post("/api/health/check")
def health_check_now():
    """Ruleaza imediat toate verificarile (butonul „Verifică acum” din Settings)."""
    from api import health_monitor
    return health_monitor.run_once()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
