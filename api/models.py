from typing import Optional
from pydantic import BaseModel


class SessionStatus(BaseModel):
    id: str
    label: str
    markets: list[str]
    direction: str
    tf: str
    hours: str
    validated: bool
    execute: bool
    capital_pct: float
    running: bool
    pid: Optional[int]
    signals_today: int
    signals_yesterday: int = 0
    signals_total: int
    last_signal_time: Optional[str]
    # Rezultatele tranzactiilor (trades/wins/P&L) NU mai sunt aici — sursa unica
    # e MT5 (/mt5/sessions, /mt5/stats). Sesiunea expune doar starea Bot Engine.
    paused: bool = False
    news_paused: bool = False
    news_events: list = []


class Signal(BaseModel):
    signal_id: str
    time: str
    symbol: str
    direction: int
    dir_str: str
    entry: float
    sl: float
    tp: float
    r_ratio: float
    status: Optional[str] = None   # starea semnalului din jurnalul Bot Engine (ai_reject, expirat, TP...)


class BotStatus(BaseModel):
    running: bool
    pid: Optional[int]
    sessions_active: int
    sessions_paused: int = 0
    sessions_total: int = 0
    active_profile_id: Optional[str] = None
    active_profile_name: Optional[str] = None
    active_profile_start_balance: Optional[float] = None
    last_started_at: Optional[str] = None
    last_stopped_at: Optional[str] = None
