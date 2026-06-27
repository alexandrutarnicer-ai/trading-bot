"""
Fusul orar activ al botului — Romania sau Germania.

Citit din data/timezone_config.json la fiecare apel (fara cache),
astfel incat schimbarile din UI iau efect la bara urmatoare fara restart.

Default: Europe/Bucharest (comportament identic cu cel existent).
"""
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "timezone_config.json")
_DEFAULT = "Europe/Bucharest"

SUPPORTED_TIMEZONES: dict[str, str] = {
    "Europe/Bucharest": "România (EET/EEST, UTC+2/UTC+3)",
    "Europe/Berlin":    "Germania (CET/CEST, UTC+1/UTC+2)",
}


def get_configured_tz_name() -> str:
    """Returneaza numele fusului orar activ (ex: 'Europe/Bucharest')."""
    try:
        with open(_CONFIG_FILE, encoding="utf-8") as f:
            name = json.load(f).get("timezone", _DEFAULT)
        if name in SUPPORTED_TIMEZONES:
            return name
    except Exception:
        pass
    return _DEFAULT


def get_configured_tz() -> ZoneInfo:
    """Returneaza ZoneInfo pentru fusul orar activ."""
    return ZoneInfo(get_configured_tz_name())


def now_local() -> datetime:
    """
    Ora curenta in fusul orar configurat, naive (fara tzinfo).
    Inlocuieste datetime.now() in tot codul live.
    Cand TZ=Romania: identic cu datetime.now() pe o masina setata pe Romania.
    Cand TZ=Germania: cu 1 ora mai putin (UTC+2/UTC+1 vs UTC+3/UTC+2).
    """
    return datetime.now(get_configured_tz()).replace(tzinfo=None)
