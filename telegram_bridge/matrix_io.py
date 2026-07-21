"""
telegram_bridge.matrix_io — al doilea canal: Matrix / Element (EU, gratuit).

Reutilizeaza EXACT acelasi Router ca Telegram (comenzi identice: /status, ai …,
claude …, /edit …). MatrixClient imita semnatura TelegramClient.send, deci Router-ul
nu stie ce transport il foloseste. Ruleaza intr-un thread separat in acelasi proces,
pornit DOAR daca matrix_enabled + homeserver + room + token (altfel inexistent).

Client-Server API (fara SDK, doar urllib — ca restul puntii):
  - GET  /account/whoami                          → user_id-ul botului (ignora ecoul propriu)
  - GET  /sync?since=&timeout=                     → mesaje noi + next_batch (ca getUpdates)
  - PUT  /rooms/{room}/send/m.room.message/{txn}   → trimite mesaj

SECURITATE: camera trebuie sa fie un DM privat NEcriptat (bot + tu). Optional
whitelist pe matrix_allowed_users. E2E nu e suportat — foloseste o camera necriptata.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .telegram_io import _chunk


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


class MatrixConflict(RuntimeError):
    pass


class MatrixClient:
    def __init__(self, homeserver: str, token: str, room_id: str):
        self.base = homeserver.rstrip("/") + "/_matrix/client/v3"
        self.token = token
        self.room_id = room_id
        self._txn = int(time.time() * 1000)
        self.user_id: str | None = None

    def _req(self, method: str, path: str, params: dict | None = None,
             body: dict | None = None, timeout: int = 40) -> dict:
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def whoami(self) -> str:
        self.user_id = self._req("GET", "/account/whoami", timeout=15).get("user_id")
        return self.user_id or ""

    def sync(self, since: str | None, timeout_ms: int) -> tuple[str | None, list[dict]]:
        """(next_batch, mesaje-text-noi-din-camera). Ignora ecoul propriu al botului."""
        params: dict = {"timeout": timeout_ms}
        if since:
            params["since"] = since
        out = self._req("GET", "/sync", params=params, timeout=timeout_ms / 1000 + 20)
        next_batch = out.get("next_batch")
        msgs: list[dict] = []
        room = ((out.get("rooms", {}) or {}).get("join", {}) or {}).get(self.room_id) or {}
        for ev in (room.get("timeline", {}) or {}).get("events", []) or []:
            if ev.get("type") != "m.room.message":
                continue
            content = ev.get("content") or {}
            if content.get("msgtype") != "m.text":
                continue
            sender = ev.get("sender", "")
            if sender == self.user_id:
                continue   # nu procesa propriile mesaje (evita bucla)
            msgs.append({
                "sender": sender,
                "text": content.get("body", ""),
                "ts": ev.get("origin_server_ts", 0) / 1000.0,
                "event_id": ev.get("event_id"),
            })
        return next_batch, msgs

    def send(self, chat_id: str, text: str, parse_mode: str | None = None,
             reply_to: int | None = None) -> None:
        """Aceeasi semnatura ca TelegramClient.send (chat_id/reply_to ignorate)."""
        for chunk in _chunk(text or "(gol)"):
            self._txn += 1
            body: dict = {"msgtype": "m.text",
                          "body": _strip_html(chunk) if parse_mode == "HTML" else chunk}
            if parse_mode == "HTML":
                body["format"] = "org.matrix.custom.html"
                body["formatted_body"] = chunk
            try:
                room = urllib.parse.quote(self.room_id)
                self._req("PUT", f"/rooms/{room}/send/m.room.message/{self._txn}",
                          body=body, timeout=15)
            except Exception:
                pass
        return None
