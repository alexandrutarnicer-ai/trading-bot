import os
import json
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Optional

router = APIRouter(prefix="/profiles", tags=["profiles"])

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)
CHANGES_LOG_FILE = os.path.join(DATA_DIR, "session_changes_log.json")

PROFILES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "profiles",
)

AVAILABLE_MARKETS = [
    "EURUSD", "GBPUSD", "EURJPY", "USDJPY", "AUDJPY", "NZDJPY",
    "USDCHF", "USDCAD", "AUDUSD", "NZDUSD", "EURGBP", "GBPJPY",
    "BTCUSD", "ETHUSD", "XRPUSD", "LTCUSD",
    "GER40", "US30", "US500", "UK100", "XAUUSD",
]

TIMEFRAMES    = ["M5", "M15", "M30", "H1", "H4", "D1"]
TREND_TFS     = ["M15", "M30", "H1", "H4", "D1"]
DIRECTIONS    = ["LONG", "BOTH", "SHORT"]
WEEKDAY_NAMES = {0: "Luni", 1: "Marti", 2: "Miercuri", 3: "Joi", 4: "Vineri", 5: "Sambata", 6: "Duminica"}


def _profile_path(profile_id: str) -> str:
    return os.path.join(PROFILES_DIR, f"{profile_id}.json")


def _load_profile(profile_id: str) -> dict:
    path = _profile_path(profile_id)
    if not os.path.exists(path):
        raise HTTPException(404, f"Profil negasit: {profile_id}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_profile(profile: dict) -> None:
    os.makedirs(PROFILES_DIR, exist_ok=True)
    profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
    with open(_profile_path(profile["id"]), "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)


def _log_profile_change(profile_id: str, profile_name: str, old_profile: dict, new_profile: dict) -> None:
    """Inregistreaza diferentele dintre profilul vechi si cel nou."""
    try:
        changes = []
        old_sessions = {s.get("id", ""): s for s in old_profile.get("sessions", [])}
        new_sessions = {s.get("id", ""): s for s in new_profile.get("sessions", [])}

        for sess_id, new_s in new_sessions.items():
            old_s = old_sessions.get(sess_id, {})
            diffs = {}
            for key, new_val in new_s.items():
                old_val = old_s.get(key)
                if old_val != new_val and key not in ("updated_at",):
                    diffs[key] = {"from": old_val, "to": new_val}
            if diffs:
                changes.append({
                    "session_id":    sess_id,
                    "session_label": new_s.get("label", sess_id),
                    "markets":       new_s.get("markets", []),
                    "changes":       diffs,
                })

        if not changes and old_profile.get("name") == new_profile.get("name"):
            return  # Nimic modificat relevant

        entry = {
            "id":           str(uuid.uuid4())[:8],
            "time":         datetime.now().isoformat(timespec="seconds"),
            "profile_id":   profile_id,
            "profile_name": profile_name,
            "sessions_changed": changes,
        }
        os.makedirs(DATA_DIR, exist_ok=True)
        entries = []
        if os.path.exists(CHANGES_LOG_FILE):
            try:
                with open(CHANGES_LOG_FILE, encoding="utf-8") as f:
                    entries = json.load(f)
            except Exception:
                entries = []
        entries.append(entry)
        if len(entries) > 500:
            entries = entries[-500:]
        with open(CHANGES_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=None, separators=(",", ":"))
    except Exception:
        pass


@router.get("")
def list_profiles():
    if not os.path.exists(PROFILES_DIR):
        return []
    profiles = []
    for fname in sorted(os.listdir(PROFILES_DIR)):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(PROFILES_DIR, fname), encoding="utf-8") as f:
                    p = json.load(f)
                profiles.append({
                    "id":          p["id"],
                    "name":        p["name"],
                    "description": p.get("description", ""),
                    "updated_at":  p.get("updated_at"),
                    "sessions":    len(p.get("sessions", [])),
                })
            except Exception:
                pass
    return profiles


@router.get("/meta")
def get_meta():
    """Returneaza valorile disponibile pentru selectori din UI."""
    return {
        "available_markets": AVAILABLE_MARKETS,
        "timeframes":        TIMEFRAMES,
        "trend_timeframes":  TREND_TFS,
        "directions":        DIRECTIONS,
        "weekday_names":     WEEKDAY_NAMES,
    }


@router.get("/{profile_id}")
def get_profile(profile_id: str):
    return _load_profile(profile_id)


@router.put("/{profile_id}")
def update_profile(profile_id: str, body: dict):
    existing = _load_profile(profile_id)
    old_copy = json.loads(json.dumps(existing))  # deep copy pentru diff
    existing["name"]          = body.get("name", existing["name"])
    existing["description"]   = body.get("description", existing.get("description", ""))
    existing["sessions"]      = body.get("sessions", existing["sessions"])
    existing["start_balance"] = body.get("start_balance", existing.get("start_balance", 1000))
    existing["capital_protection_enabled"]       = body.get("capital_protection_enabled", existing.get("capital_protection_enabled", False))
    existing["capital_protection_threshold_pct"] = body.get("capital_protection_threshold_pct", existing.get("capital_protection_threshold_pct", 70.0))
    _log_profile_change(profile_id, existing["name"], old_copy, existing)
    _save_profile(existing)
    return existing


@router.delete("/{profile_id}")
def delete_profile(profile_id: str):
    if profile_id == "standard":
        raise HTTPException(403, "Profilul standard nu poate fi sters")
    path = _profile_path(profile_id)
    if not os.path.exists(path):
        raise HTTPException(404, f"Profil negasit: {profile_id}")
    os.remove(path)
    return {"deleted": profile_id}


@router.post("")
def create_profile(body: dict):
    profile_id = body.get("id", "").strip().lower().replace(" ", "_")
    if not profile_id:
        raise HTTPException(400, "id lipsa")
    if os.path.exists(_profile_path(profile_id)):
        raise HTTPException(409, f"Profil exista deja: {profile_id}")
    profile = {
        "id":            profile_id,
        "name":          body.get("name", profile_id),
        "description":   body.get("description", ""),
        "start_balance": 1000,
        "sessions":      [],
    }
    _save_profile(profile)
    return profile
