"""
telegram_bridge.router — rutare mesaje, flux de confirmare, single-task.

Instant (in bucla, <1s): comenzile /...
Grele (thread separat, ca bucla de poll sa ramana responsiva): "ai ...", "claude ...",
"copilot ...", si pasul de executie al confirmarii. Un singur task greu simultan
(single_task) — restul primesc "ocupat".

Fluxul de scriere in 2 pasi:
  "claude! <cerere>"  → ruleaza in PLAN mode (read-only) → trimite planul + un cod
  "CONFIRM <cod>"      → reia sesiunea planului in mod write → executa
Gated de allow_writes (OFF by default).
"""

from __future__ import annotations

import random
import threading
import time
import logging

from . import commands, executors
from .ai_fast import answer as ai_answer

log = logging.getLogger("telegram_bridge.router")


def _footer(res: executors.RunResult) -> str:
    bits = []
    label = {"claude-cli": "Claude Code", "claude-api": "Claude API",
             "ai-sources": res.source or "surse AI", "copilot": "Copilot",
             "local": "local"}.get(res.level, res.level)
    bits.append(f"via {label}")
    if res.cost_usd is not None:
        bits.append(f"${res.cost_usd:.4f}")
    if res.num_turns:
        bits.append(f"{res.num_turns} ture")
    fr = res.meta.get("fallback_reason")
    if fr and res.level != "claude-cli":
        bits.append(f"fallback: {fr}")
    return "— " + " · ".join(bits)


class Router:
    def __init__(self, cfg: dict, state, tg, chat_id: str):
        self.cfg = cfg
        self.state = state
        self.tg = tg
        self.chat_id = chat_id
        self._busy = threading.Lock()

    # -- utilitare --

    def _reply(self, text: str, parse_mode: str | None = None,
               reply_to: int | None = None) -> int | None:
        return self.tg.send(self.chat_id, text, parse_mode=parse_mode, reply_to=reply_to)

    def _busy_reply(self) -> None:
        self._reply("⏳ Am deja un task in curs. Asteapta sa termin sau trimite /status.")

    def _spawn(self, target, *args) -> bool:
        """Porneste un task greu daca nu suntem ocupati. False → ocupat."""
        if self.cfg.get("single_task", True) and not self._busy.acquire(blocking=False):
            return False
        t = threading.Thread(target=self._guarded, args=(target, args), daemon=True)
        t.start()
        return True

    def _guarded(self, target, args) -> None:
        try:
            target(*args)
        except Exception as e:
            log.exception("task greu esuat")
            try:
                self._reply(f"⚠️ Task esuat: {e}")
            except Exception:
                pass
        finally:
            if self.cfg.get("single_task", True):
                try:
                    self._busy.release()
                except RuntimeError:
                    pass

    # ── intrare principala ────────────────────────────────────────────────────

    def handle(self, text: str, message_id: int | None, reply_to: int | None) -> None:
        raw = (text or "").strip()
        if not raw:
            return
        low = raw.lower()

        # 1. Comenzi instant
        if raw.startswith("/"):
            self._instant(raw)
            return

        # 2. CONFIRM <cod>
        kw_confirm = self.cfg.get("kw_confirm", "CONFIRM")
        if raw.split(None, 1)[0].upper() == kw_confirm.upper():
            self._handle_confirm(raw)
            return

        # 3. Cuvinte cheie (primul token)
        first = low.split(None, 1)[0]
        rest = raw[len(raw.split(None, 1)[0]):].strip()

        if first == self.cfg.get("kw_ai", "ai").lower():
            self._heavy_ai(rest)
            return
        if first == self.cfg.get("kw_claude_write", "claude!").lower():
            self._heavy_claude_plan(rest)
            return
        if first == self.cfg.get("kw_claude_resume", "claude+").lower():
            self._heavy_claude(rest, resume=self.state.last_claude_session)
            return
        if first == self.cfg.get("kw_claude", "claude").lower():
            self._heavy_claude(rest, resume=None)
            return
        if self.cfg.get("copilot_enabled") and first == self.cfg.get("kw_copilot", "copilot").lower():
            self._heavy_copilot(rest)
            return

        # 4. Reply la un mesaj al lui Claude (fara keyword) → continua conversatia
        sess = self.state.session_for_reply(reply_to, self.cfg.get("claude_resume_window_s", 1800))
        if sess:
            self._heavy_claude(raw, resume=sess)
            return

        # 5. Fara keyword → ignorat (nimic accidental nu porneste)
        log.info("mesaj fara keyword, ignorat: %r", raw[:60])

    # ── instant ───────────────────────────────────────────────────────────────

    def _instant(self, raw: str) -> None:
        parts = raw[1:].split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        try:
            if cmd in ("status", "s"):
                self._reply(commands.cmd_status(self.cfg))
            elif cmd in ("raport", "report", "r"):
                self._reply(commands.cmd_report(self.cfg))
            elif cmd in ("piete", "markets", "m"):
                self._reply(commands.cmd_markets(self.cfg))
            elif cmd == "pauza":
                self._reply(commands.cmd_pause(self.cfg, arg, resume=False))
            elif cmd == "reia":
                self._reply(commands.cmd_pause(self.cfg, arg, resume=True))
            elif cmd == "reset":
                self.state.last_claude_session = None
                self.state.save()
                self._reply("🔄 Conversatia Claude a fost resetata (urmatorul «claude» porneste curat).")
            elif cmd in ("ajutor", "help", "start", "h"):
                self._reply(commands.cmd_help(self.cfg))
            else:
                self._reply(f"Comanda necunoscuta: /{cmd}. Trimite /ajutor.")
        except Exception as e:
            self._reply(f"⚠️ Eroare la /{cmd}: {e}")

    # ── nivelul AI rapid ──────────────────────────────────────────────────────

    def _heavy_ai(self, question: str) -> None:
        if not question:
            self._reply("Foloseste: ai <intrebare>  (ex: ai de ce e XRPUSD pe WAIT?)")
            return
        if not self.cfg.get("level_ai_enabled", True):
            self._reply("Nivelul «ai» e dezactivat in config.")
            return
        if not self._spawn(self._task_ai, question):
            self._busy_reply()

    def _task_ai(self, question: str) -> None:
        txt, src = ai_answer(self.cfg, question)
        footer = f"\n\n— via {src}" if (src and self.cfg.get("announce_fallback", True)) else ""
        self._reply(f"{txt}{footer}")

    # ── nivelul Claude ────────────────────────────────────────────────────────

    def _heavy_claude(self, prompt: str, resume: str | None) -> None:
        if not prompt:
            self._reply("Foloseste: claude <cerere>  (ex: claude analizeaza de ce a picat S7 azi)")
            return
        if not self.cfg.get("level_claude_enabled", True):
            self._reply("Nivelul «claude» e dezactivat in config.")
            return
        if not self._spawn(self._task_claude, prompt, resume, "read"):
            self._busy_reply()

    def _task_claude(self, prompt: str, resume: str | None, mode: str) -> None:
        self._reply("🧠 Claude lucreaza… (poate dura pana la cateva minute)")
        res = executors.handle_claude(self.cfg, prompt, resume=resume, mode=mode)
        footer = ("\n\n" + _footer(res)) if self.cfg.get("announce_fallback", True) else ""
        mid = self._reply(f"{res.text}{footer}")
        # leaga mesajul trimis de sesiune → reply-ul userului la el continua firul
        if res.session_id:
            self.state.remember_session(mid, res.session_id)

    # ── flux de scriere (2 pasi) ──────────────────────────────────────────────

    def _heavy_claude_plan(self, prompt: str) -> None:
        if not prompt:
            self._reply("Foloseste: claude! <cerere de modificare>")
            return
        if not self.cfg.get("allow_writes", False):
            self._reply("🔒 Modificarile de cod sunt DEZACTIVATE. Ca sa le activezi, "
                        "seteaza \"allow_writes\": true in data/telegram_bridge.json "
                        "si reporneste puntea. (Recomandat abia dupa ce ai incredere in flux.)")
            return
        if not self._spawn(self._task_plan, prompt):
            self._busy_reply()

    def _task_plan(self, prompt: str) -> None:
        self._reply("📝 Pregatesc un plan (read-only)…")
        res = executors.handle_claude(self.cfg, prompt, resume=None, mode="plan")
        if res.level != "claude-cli" or not res.session_id:
            self._reply(f"{res.text}\n\n⚠️ Nu pot rula fluxul de scriere fara Claude CLI. "
                        "Modificarea nu a fost aplicata.")
            return
        code = f"{random.randint(0, 999999):06d}"
        ttl = self.cfg.get("confirm_timeout_s", 300)
        self.state.add_pending(code, res.session_id, prompt, ttl)
        self._reply(
            f"{res.text}\n\n"
            f"— {_footer(res)}\n\n"
            f"✅ Ca sa EXECUT acest plan, raspunde:\n   {self.cfg.get('kw_confirm', 'CONFIRM')} {code}\n"
            f"(valabil {ttl // 60} min · orice altceva anuleaza)")

    def _handle_confirm(self, raw: str) -> None:
        parts = raw.split()
        if len(parts) < 2:
            self._reply(f"Foloseste: {self.cfg.get('kw_confirm', 'CONFIRM')} <cod>")
            return
        code = parts[1].strip()
        rec = self.state.pop_valid_confirm(code)
        if not rec:
            self._reply("⛔ Cod invalid sau expirat. Reia cu «claude! …».")
            return
        if not self._spawn(self._task_write, rec):
            # pune codul inapoi ca sa nu-l pierzi daca esti ocupat
            self.state.add_pending(code, rec["session_id"], rec["prompt"],
                                   self.cfg.get("confirm_timeout_s", 300))
            self._busy_reply()

    def _task_write(self, rec: dict) -> None:
        self._reply("⚙️ Execut planul confirmat…")
        res = executors.handle_claude(
            self.cfg,
            "Executa EXACT planul pe care l-ai propus in mesajul anterior. "
            "Nu extinde scopul. La final, rezuma pe scurt ce ai modificat.",
            resume=rec["session_id"], mode="write")
        footer = ("\n\n" + _footer(res)) if self.cfg.get("announce_fallback", True) else ""
        mid = self._reply(f"{res.text}{footer}")
        if res.session_id:
            self.state.remember_session(mid, res.session_id)
