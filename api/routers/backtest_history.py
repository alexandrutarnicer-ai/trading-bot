import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

HISTORY_FILE = Path("data/backtest_history.json")
router = APIRouter()


def _read() -> List[Dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text("utf-8"))
    except Exception:
        return []


def _write(data: List[Dict]):
    HISTORY_FILE.parent.mkdir(exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


class SaveHistoryRequest(BaseModel):
    session_id: str
    session_label: str
    markets: List[str]
    entry_tf: str
    trend_tf: str
    direction: str
    start_balance: float
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    results: Dict[str, Any]
    session_snapshot: Optional[Dict[str, Any]] = None


@router.get("/backtest/history")
def get_history(session_id: Optional[str] = None, limit: int = 50):
    history = _read()
    if session_id:
        history = [h for h in history if h.get("session_id") == session_id]
    history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return history[:limit]


@router.post("/backtest/history")
def save_history(req: SaveHistoryRequest):
    history = _read()
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        **req.model_dump(),
    }
    history.append(entry)
    history = history[-200:]
    _write(history)
    return {"id": entry["id"]}


@router.delete("/backtest/history/{entry_id}")
def delete_history(entry_id: str):
    history = _read()
    history = [h for h in history if h.get("id") != entry_id]
    _write(history)
    return {"ok": True}
