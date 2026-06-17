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
    signals_total: int
    last_signal_time: Optional[str]
    outcomes_total: int
    wins: int
    losses: int


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


class BotStatus(BaseModel):
    running: bool
    pid: Optional[int]
    sessions_active: int


class EquityCurvePoint(BaseModel):
    date: str
    cumulative_r: float
    session_id: str
