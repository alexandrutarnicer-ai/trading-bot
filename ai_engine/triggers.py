"""
ai_engine.triggers — decide CAND se convoaca consiliul AI.

Perceptia ruleaza la fiecare bara M15 (gratuit); consiliul (LLM) doar cand
se intampla ceva demn de analiza — cum un trader profesionist monitorizeaza
continuu dar isi reface teza doar pe evenimente:

  regime_flip     — trend M30 sau D1 si-a schimbat directia fata de snapshotul anterior
  breakout_tension— pretul e la <0.5*ATR de extrema range-ului de 20 bare
  vol_spike       — ATR a intrat in percentila >90 (nu era inainte)
  news_window     — eveniment High impact in urmatoarele 60 min
  position_review — pozitie AI deschisa + N ore de la ultimul consiliu
  heartbeat       — minim un consiliu / piata / N ore (default 24)

Cooldown: dupa un consiliu pe o piata, nu se convoaca altul X minute (default 120),
cu exceptia news_window si position_review.
"""

from __future__ import annotations

from datetime import datetime


def evaluate(snapshot: dict, prev_snapshot: dict | None,
             last_council_ts: str | None, has_open_position: bool,
             cfg: dict) -> str | None:
    """Returneaza numele trigger-ului sau None daca nu e cazul de consiliu."""
    now = datetime.now()

    # cooldown de la ultimul consiliu
    mins_since = None
    if last_council_ts:
        try:
            mins_since = (now - datetime.fromisoformat(last_council_ts)).total_seconds() / 60
        except Exception:
            mins_since = None

    def _cooldown_ok() -> bool:
        return mins_since is None or mins_since >= cfg["council_cooldown_min"]

    # 1. stiri iminente (ignora cooldown — trebuie decisa pozitionarea)
    for ev in snapshot.get("news", []):
        if ev["impact"] == "High" and 0 <= ev["in_min"] <= 60:
            if mins_since is None or mins_since >= 45:
                return f"news_window:{ev['currency']}:{ev['title'][:40]}"

    # 2. review pozitie deschisa (interval propriu)
    if has_open_position and mins_since is not None \
            and mins_since >= cfg["position_review_hours"] * 60:
        return "position_review"

    # 3. regime flip
    if prev_snapshot is not None and _cooldown_ok():
        if snapshot["trend_m30"] != prev_snapshot["trend_m30"] and snapshot["trend_m30"] != 0:
            return f"regime_flip:M30:{prev_snapshot['trend_m30']}->{snapshot['trend_m30']}"
        if snapshot["trend_d1"] != prev_snapshot["trend_d1"]:
            return f"regime_flip:D1:{prev_snapshot['trend_d1']}->{snapshot['trend_d1']}"

    # 4. tensiune de breakout
    if _cooldown_ok():
        atr = snapshot["atr"]
        if atr and atr > 0:
            near_high = (snapshot["high_20"] - snapshot["price"]) < 0.5 * atr
            near_low  = (snapshot["price"] - snapshot["low_20"])  < 0.5 * atr
            if near_high or near_low:
                return f"breakout_tension:{'high' if near_high else 'low'}"

    # 5. spike de volatilitate
    if prev_snapshot is not None and _cooldown_ok():
        p_now  = snapshot.get("atr_pctile")
        p_prev = prev_snapshot.get("atr_pctile")
        if p_now is not None and p_prev is not None and p_now > 90 >= p_prev:
            return "vol_spike"

    # 6. heartbeat — minim un consiliu pe piata la N ore
    if mins_since is None or mins_since >= cfg["heartbeat_hours"] * 60:
        return "heartbeat"

    return None
