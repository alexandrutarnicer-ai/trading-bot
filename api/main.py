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
from api.routers import backtest_history, notifications, reports, mt5_sync
from api.watchdog import start_watchdog
from api.notifications import migrate_to_jsonl
from api.scheduled_reports import start_scheduler as start_reports_scheduler

app = FastAPI(title="Trading Bot API", version="1.0.0")


@app.on_event("startup")
def _startup():
    migrate_to_jsonl()   # converstie JSON array legacy → JSONL (one-time, idempotent)
    start_watchdog()
    start_reports_scheduler()

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
app.include_router(mt5_sync.router,           prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
