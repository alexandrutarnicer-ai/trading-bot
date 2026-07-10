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
    outcomes_total: int
    outcomes_today: int = 0
    outcomes_yesterday: int = 0
    wins: int
    losses: int
    wins_today: int = 0
    wins_yesterday: int = 0
    losses_today: int = 0
    losses_yesterday: int = 0
    paused: bool = False
    news_paused: bool = False
    news_events: list = []
    pnl_usd_today: Optional[float] = None
    pnl_usd_yesterday: Optional[float] = None
    pnl_usd_total: Optional[float] = None
    pnl_count: Optional[int] = None


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


class Outcome(BaseModel):
    signal_id: str
    time_check: str
    symbol: str
    direction: int
    status: str
    entry: float
    sl: float
    tp: float
    r_ratio: float
    triggered_at: Optional[str]
    exit_price: Optional[float]
    exit_time: Optional[str]
    result_r: float
    pnl_usd: Optional[float] = None
    # Filtru AI Pre-Trade — None cand filtrul nu a participat la acest semnal
    ai_approved: Optional[bool] = None
    ai_confidence: Optional[float] = None


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


class EquityCurvePoint(BaseModel):
    date: str
    cumulative_r: float
    session_id: str
