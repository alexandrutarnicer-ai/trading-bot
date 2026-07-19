"""
telegram_bridge.selftest — verificari OFFLINE (fara Telegram, fara MT5, fara Ollama,
fara a rula claude cu adevarat). Testeaza logica pura: rutare, whitelist, chunking,
ciclul de confirmare, constructia comenzii CLI.

  python -m telegram_bridge.selftest
"""

from __future__ import annotations

import os
import re
import sys
import tempfile

from . import config
from .telegram_io import _chunk, BridgeState, TG_MAX
from .executors import RunResult, _build_cmd, _parse_cli_output
from . import router as router_mod


_fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'[OK]' if cond else '[XX]'} {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


# ── fake-uri ───────────────────────────────────────────────────────────────────

class FakeTG:
    def __init__(self):
        self.sent: list[str] = []
        self._id = 1000

    def send(self, chat_id, text, parse_mode=None, reply_to=None):
        self.sent.append(text)
        self._id += 1
        return self._id

    def last(self) -> str:
        return self.sent[-1] if self.sent else ""

    def joined(self) -> str:
        return "\n".join(self.sent)


class SyncRouter(router_mod.Router):
    """Router care ruleaza task-urile grele SINCRON (fara thread) pentru testare."""
    def _spawn(self, target, *args):
        target(*args)
        return True


def _mk_router(cfg, state, tg):
    return SyncRouter(cfg, state, tg, chat_id="123")


# ── monkeypatch-uri ──────────────────────────────────────────────────────────

class _Recorder:
    def __init__(self):
        self.calls: list[tuple] = []


def _install_fakes(rec: _Recorder):
    def fake_ai_answer(cfg, q):
        rec.calls.append(("ai", q))
        return ("raspuns ai fake", "cerebras")

    def fake_handle_claude(cfg, prompt, resume=None, mode="read"):
        rec.calls.append(("claude", prompt, resume, mode))
        if mode == "plan":
            return RunResult(text="PLAN: pasul 1, pasul 2", level="claude-cli",
                             source="claude-code", session_id="sess-PLAN", cost_usd=0.01)
        if mode == "write":
            return RunResult(text="Am aplicat modificarea.", level="claude-cli",
                             source="claude-code", session_id="sess-PLAN", cost_usd=0.02)
        return RunResult(text="analiza fake", level="claude-cli", source="claude-code",
                         session_id="sess-READ", cost_usd=0.005, num_turns=2)

    class FakeCommands:
        @staticmethod
        def cmd_status(cfg): rec.calls.append(("cmd_status",)); return "STATUS"
        @staticmethod
        def cmd_report(cfg): rec.calls.append(("cmd_report",)); return "RAPORT"
        @staticmethod
        def cmd_markets(cfg): rec.calls.append(("cmd_markets",)); return "PIETE"
        @staticmethod
        def cmd_help(cfg): rec.calls.append(("cmd_help",)); return "AJUTOR"
        @staticmethod
        def cmd_pause(cfg, arg, resume=False):
            rec.calls.append(("cmd_pause", arg, resume)); return "PAUZA"

    router_mod.ai_answer = fake_ai_answer
    router_mod.executors.handle_claude = fake_handle_claude
    router_mod.commands = FakeCommands


# ── teste ──────────────────────────────────────────────────────────────────────

def test_chunking():
    print("[chunking]")
    check("text scurt = 1 chunk", _chunk("salut") == ["salut"])
    big = "x" * (TG_MAX * 3 + 17)
    parts = _chunk(big)
    check("chunk-uri <= 4096", all(len(p) <= TG_MAX for p in parts), str([len(p) for p in parts]))
    check("nu pierde caractere (fara \\n adaugat)", sum(len(p) for p in parts) == len(big))
    multiline = "\n".join(["linie " + str(i) for i in range(2000)])
    parts2 = _chunk(multiline)
    check("multiline: toate <= 4096", all(len(p) <= TG_MAX for p in parts2))


def test_state():
    print("[state]")
    fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd); os.remove(path)
    s = BridgeState(path)
    s.offset = 42
    s.remember_session(500, "sess-A")
    s.add_pending("111222", "sess-A", "fa ceva", ttl_s=300)
    s.save()
    s2 = BridgeState(path)
    check("offset persistat", s2.offset == 42)
    check("sesiune per reply", s2.session_for_reply(500, 3600) == "sess-A")
    check("sesiune expirata → None", s2.session_for_reply(500, 0) is None)
    check("last_claude_session", s2.last_claude_session == "sess-A")
    rec = s2.pop_valid_confirm("111222")
    check("confirm valid", rec is not None and rec["session_id"] == "sess-A")
    check("confirm consumat o singura data", s2.pop_valid_confirm("111222") is None)
    s3 = BridgeState(path); s3.add_pending("999", "x", "y", ttl_s=-1)
    check("confirm expirat → None", s3.pop_valid_confirm("999") is None)
    try: os.remove(path)
    except OSError: pass


def test_cli_cmd():
    print("[cli-cmd]")
    cfg = config.load_config()
    read = _build_cmd(cfg, "prompt X", None, "read")
    check("read: -p prezent", "-p" in read and "prompt X" in read)
    check("read: output json", "--output-format" in read and "json" in read)
    check("read: fara permission-mode", "--permission-mode" not in read)
    check("read: allowedTools prezent", "--allowedTools" in read)
    check("read: fara Edit/Write in allowlist",
          not any(t in ("Edit", "Write") for t in cfg["claude_readonly_tools"]))
    plan = _build_cmd(cfg, "p", None, "plan")
    check("plan: permission-mode plan", "plan" in plan and plan[plan.index("--permission-mode") + 1] == "plan")
    write = _build_cmd(cfg, "p", "sess-1", "write")
    check("write: resume prezent", "--resume" in write and "sess-1" in write)
    check("write: acceptEdits", write[write.index("--permission-mode") + 1] == "acceptEdits")
    check("write: Edit in allowlist", "Edit" in cfg["write_tools"])
    out = _parse_cli_output('{"result":"salut","session_id":"abc","total_cost_usd":0.01}')
    check("parse output json", out.get("result") == "salut" and out.get("session_id") == "abc")
    check("parse output gol → {}", _parse_cli_output("") == {})


def test_routing():
    print("[routing]")
    cfg = config.load_config()
    cfg["allow_writes"] = False
    rec = _Recorder(); _install_fakes(rec)
    fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd); os.remove(path)
    state = BridgeState(path)

    def fresh():
        tg = FakeTG(); r = _mk_router(cfg, state, tg); return tg, r

    tg, r = fresh(); r.handle("/status", 1, None)
    check("/status → cmd_status", ("cmd_status",) in rec.calls and tg.last() == "STATUS")

    tg, r = fresh(); r.handle("/ajutor", 1, None)
    check("/ajutor → cmd_help", ("cmd_help",) in rec.calls)

    tg, r = fresh(); r.handle("/pauza S7", 1, None)
    check("/pauza S7 → cmd_pause(S7)", ("cmd_pause", "S7", False) in rec.calls)

    rec.calls.clear(); tg, r = fresh(); r.handle("ai de ce WAIT?", 1, None)
    check("ai … → nivel ai", ("ai", "de ce WAIT?") in rec.calls)

    rec.calls.clear(); tg, r = fresh(); r.handle("claude analizeaza S7", 1, None)
    check("claude … → read/resume None",
          any(c[0] == "claude" and c[2] is None and c[3] == "read" for c in rec.calls))

    rec.calls.clear(); state.last_claude_session = "sess-PREV"
    tg, r = fresh(); r.handle("claude+ continua", 1, None)
    check("claude+ → resume last",
          any(c[0] == "claude" and c[2] == "sess-PREV" for c in rec.calls))

    rec.calls.clear(); tg, r = fresh(); r.handle("claude! schimba X", 1, None)
    check("claude! cu allow_writes=false → blocat",
          "DEZACTIVATE" in tg.joined() and not any(c[0] == "claude" for c in rec.calls))

    # flux complet de scriere cu allow_writes=true
    cfg2 = dict(cfg); cfg2["allow_writes"] = True
    rec.calls.clear()
    tg = FakeTG(); r = SyncRouter(cfg2, state, tg, "123")
    r.handle("claude! adauga un comentariu", 1, None)
    check("claude! plan → mode plan",
          any(c[0] == "claude" and c[3] == "plan" for c in rec.calls))
    m = re.search(r"CONFIRM (\d{6})", tg.joined())
    check("plan → cod de confirmare emis", m is not None, tg.joined()[:100])
    if m:
        code = m.group(1); rec.calls.clear()
        r.handle(f"CONFIRM {code}", 2, None)
        check("CONFIRM → executie mode write",
              any(c[0] == "claude" and c[3] == "write" for c in rec.calls))
        rec.calls.clear()
        r.handle(f"CONFIRM {code}", 3, None)
        check("CONFIRM refolosit → invalid",
              "invalid" in tg.last().lower() and not rec.calls)

    tg, r = fresh(); r.handle("CONFIRM 000000", 1, None)
    check("CONFIRM cod inexistent → invalid", "invalid" in tg.last().lower())

    # reply la un mesaj al lui Claude (fara keyword) → resume
    rec.calls.clear()
    state.remember_session(777, "sess-REPLY")
    tg, r = fresh(); r.handle("si de ce asa?", 1, reply_to=777)
    check("reply la Claude → resume",
          any(c[0] == "claude" and c[2] == "sess-REPLY" for c in rec.calls))

    # fara keyword, fara reply → ignorat (niciun send)
    rec.calls.clear(); tg, r = fresh(); r.handle("salut ce faci", 1, None)
    check("mesaj fara keyword → ignorat", tg.sent == [] and rec.calls == [])

    tg, r = fresh(); r.handle("/foo", 1, None)
    check("/comanda necunoscuta → mesaj", "necunoscuta" in tg.last().lower())

    try: os.remove(path)
    except OSError: pass


def test_whitelist():
    print("[whitelist]")
    cfg = dict(config.DEFAULTS); cfg["allowed_chat_ids"] = ["555", "666"]
    check("allowed_ids din config", config.allowed_ids(cfg) == {"555", "666"})


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # consola cp1252-safe
    except Exception:
        pass
    print("=== telegram_bridge selftest ===")
    test_chunking()
    test_state()
    test_cli_cmd()
    test_routing()
    test_whitelist()
    print()
    if _fails:
        print(f"[FAIL] {len(_fails)} teste PICATE: {_fails}")
        return 1
    print("[PASS] Toate testele au trecut.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
