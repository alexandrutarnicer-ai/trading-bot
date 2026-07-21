"""
telegram_bridge.telegram_io — I/O Telegram + stare persistenta.

TelegramClient: getUpdates (long-poll) + sendMessage propriu (urllib), chunking la
4096 caractere. BridgeState: offset persistat + harta reply→sesiune-claude + pending
confirmari, in data/telegram_bridge_state.json (supravietuieste restart).

IMPORTANT — getUpdates: restul proiectului trimite DOAR sendMessage (outbound), deci
puntea e SINGURUL consumator de getUpdates. Telegram permite un singur consumator per
token; un 409 Conflict inseamna ca ruleaza doua instante ale puntii — tratat explicit.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from . import config

TG_MAX = 4096   # limita hard Telegram per mesaj


class TelegramClient:
    def __init__(self, token: str):
        self.token = token
        self._base = f"https://api.telegram.org/bot{token}"

    def _api(self, method: str, params: dict, timeout: int) -> dict:
        req = urllib.request.Request(
            f"{self._base}/{method}",
            data=json.dumps(params).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def get_updates(self, offset: int, timeout_s: int) -> list[dict]:
        """Long-poll. Ridica RuntimeError('conflict') daca alta instanta polleaza."""
        try:
            # HTTP timeout > long-poll timeout, ca sa nu taie conexiunea prematur.
            out = self._api("getUpdates", {
                "offset": offset,
                "timeout": timeout_s,
                "allowed_updates": ["message"],
            }, timeout=timeout_s + 15)
        except urllib.error.HTTPError as e:
            if e.code == 409:
                raise RuntimeError("conflict") from e
            raise
        if not out.get("ok"):
            if out.get("error_code") == 409:
                raise RuntimeError("conflict")
            return []
        return out.get("result", [])

    def send(self, chat_id: str, text: str, parse_mode: str | None = None,
             reply_to: int | None = None) -> int | None:
        """
        Trimite text (spart automat la 4096). parse_mode=None → text simplu (safe
        pentru continut arbitrar de la AI/Claude, care ar strica HTML). Returneaza
        message_id-ul ULTIMULUI chunk (folosit ca ancora pentru reply→resume).
        """
        last_id: int | None = None
        for i, chunk in enumerate(_chunk(text)):
            params: dict = {"chat_id": chat_id, "text": chunk,
                            "disable_web_page_preview": True}
            if parse_mode:
                params["parse_mode"] = parse_mode
            if reply_to and i == 0:
                params["reply_to_message_id"] = reply_to
            try:
                res = self._api("sendMessage", params, timeout=15)
                last_id = (res.get("result") or {}).get("message_id", last_id)
            except urllib.error.HTTPError:
                # daca HTML strica parsarea, reincearca ca text simplu
                if parse_mode:
                    params.pop("parse_mode", None)
                    try:
                        res = self._api("sendMessage", params, timeout=15)
                        last_id = (res.get("result") or {}).get("message_id", last_id)
                    except Exception:
                        pass
            except Exception:
                pass
        return last_id


def _chunk(text: str, limit: int = TG_MAX) -> list[str]:
    """Sparge textul la `limit`, preferand granite de linie; taie liniile uriase."""
    text = text or "(gol)"
    if len(text) <= limit:
        return [text]
    out, buf = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if buf:
                out.append(buf); buf = ""
            out.append(line[:limit]); line = line[limit:]
        if len(buf) + len(line) + 1 > limit:
            out.append(buf); buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf:
        out.append(buf)
    return out


# ── Stare persistenta ────────────────────────────────────────────────────────

class BridgeState:
    """
    offset               — urmatorul update_id de cerut (nu reprocesa la restart)
    sessions[msg_id]     — {session_id, ts}: reply la acel mesaj continua sesiunea
    pending_confirm[code]— {session_id, prompt, expires_at}: fluxul de scriere in 2 pasi
    last_claude_session  — ultima sesiune claude (pentru claude+)
    """

    def __init__(self, path: str = config.STATE_PATH):
        self.path = path
        self.offset: int = 0
        self.sessions: dict[str, dict] = {}
        self.pending_confirm: dict[str, dict] = {}
        self.last_claude_session: str | None = None
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self.offset = int(d.get("offset", 0))
            self.sessions = d.get("sessions", {}) or {}
            self.pending_confirm = d.get("pending_confirm", {}) or {}
            self.last_claude_session = d.get("last_claude_session")
        except Exception:
            pass

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({
                    "offset": self.offset,
                    "sessions": self.sessions,
                    "pending_confirm": self.pending_confirm,
                    "last_claude_session": self.last_claude_session,
                }, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception:
            pass

    # -- sesiuni claude legate de mesaje --

    def remember_session(self, message_id: int | None, session_id: str | None) -> None:
        if message_id and session_id:
            self.sessions[str(message_id)] = {"session_id": session_id, "ts": time.time()}
            self.last_claude_session = session_id
            self._trim_sessions()
            self.save()

    def session_for_reply(self, reply_to_message_id: int | None, window_s: int) -> str | None:
        if not reply_to_message_id:
            return None
        rec = self.sessions.get(str(reply_to_message_id))
        if rec and (time.time() - rec.get("ts", 0)) <= window_s:
            return rec.get("session_id")
        return None

    def _trim_sessions(self, keep: int = 50) -> None:
        if len(self.sessions) > keep:
            for k in sorted(self.sessions, key=lambda k: self.sessions[k].get("ts", 0))[:-keep]:
                self.sessions.pop(k, None)

    # -- confirmari scriere --

    def add_pending(self, code: str, session_id: str | None, prompt: str, ttl_s: int,
                    backend: str = "claude") -> None:
        self.pending_confirm[code] = {"session_id": session_id, "prompt": prompt,
                                      "backend": backend, "expires_at": time.time() + ttl_s}
        self.save()

    def pop_valid_confirm(self, code: str) -> dict | None:
        self._purge_confirms()
        rec = self.pending_confirm.pop(code, None)
        self.save()
        if rec and time.time() <= rec.get("expires_at", 0):
            return rec
        return None

    def _purge_confirms(self) -> None:
        now = time.time()
        for k in [k for k, v in self.pending_confirm.items() if now > v.get("expires_at", 0)]:
            self.pending_confirm.pop(k, None)
