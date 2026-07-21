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
    # /edit persista in config — in teste il stubuim ca sa NU atingem fisierul real
    router_mod.config.set_config_value = lambda k, v: rec.calls.append(("set_config", k, v))


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

    # /edit on|off — comuta allow_writes live + persistat (cfg izolat pt test)
    rec.calls.clear()
    _cfg_e = dict(cfg); _cfg_e["allow_writes"] = False
    _tg_e = FakeTG(); _r_e = SyncRouter(_cfg_e, state, _tg_e, "123")
    _r_e.handle("/edit on", 1, None)
    check("/edit on → allow_writes True + persistat",
          _cfg_e["allow_writes"] is True
          and ("set_config", "allow_writes", True) in rec.calls
          and "ACTIVAT" in _tg_e.joined())
    _r_e.handle("/edit off", 2, None)
    check("/edit off → allow_writes False",
          _cfg_e["allow_writes"] is False
          and ("set_config", "allow_writes", False) in rec.calls)
    _r_e.handle("/edit", 3, None)
    check("/edit (fara arg) → arata starea", "EDIT" in _tg_e.last())

    # claude! cu Claude INDISPONIBIL → editor de REZERVA (aider) prin plan→CONFIRM
    rec2 = _Recorder()
    _sav_hc = router_mod.executors.handle_claude
    _sav_rn = getattr(router_mod.executors, "reserve_editor_name", None)
    _sav_rr = getattr(router_mod.executors, "run_reserve_editor", None)
    router_mod.executors.handle_claude = lambda cfg, prompt, resume=None, mode="read": (
        RunResult(text="Claude indisponibil", level="local", is_error=True))
    router_mod.executors.reserve_editor_name = lambda cfg: "aider"
    router_mod.executors.run_reserve_editor = lambda cfg, backend, prompt: (
        rec2.calls.append(("reserve", backend, prompt)) or RunResult(text="editat cu aider", level="aider"))
    _cfgw = dict(cfg); _cfgw["allow_writes"] = True
    _tgw = FakeTG(); _rw = SyncRouter(_cfgw, state, _tgw, "123")
    _rw.handle("claude! fixeaza bug X", 1, None)
    _m = re.search(r"CONFIRM (\d{6})", _tgw.joined())
    check("claude! fara Claude → ofera rezerva «aider» + cod",
          _m is not None and "aider" in _tgw.joined())
    if _m:
        _rw.handle(f"CONFIRM {_m.group(1)}", 2, None)
        check("CONFIRM rezerva → run_reserve_editor(aider) apelat",
              any(c[0] == "reserve" and c[1] == "aider" for c in rec2.calls))
    router_mod.executors.handle_claude = _sav_hc
    if _sav_rn: router_mod.executors.reserve_editor_name = _sav_rn
    if _sav_rr: router_mod.executors.run_reserve_editor = _sav_rr

    try: os.remove(path)
    except OSError: pass


def test_whitelist():
    print("[whitelist]")
    cfg = dict(config.DEFAULTS); cfg["allowed_chat_ids"] = ["555", "666"]
    check("allowed_ids din config", config.allowed_ids(cfg) == {"555", "666"})


def test_editors():
    print("[editors]")
    from telegram_bridge import executors as ex
    cfg = config.load_config()

    # aider command construction
    cfg2 = dict(cfg); cfg2["aider_binary"] = "aider"; cfg2["aider_model"] = "groq/llama-3.3-70b-versatile"
    import telegram_bridge.executors as exmod
    _orig_which = exmod.shutil.which
    # forteaza detectia aider "instalat" doar pt constructie
    exmod.shutil.which = lambda name: "/usr/bin/aider" if name == "aider" else None
    check("aider_binary detectat cand exista", ex.aider_binary(cfg2) is not None)
    eds = ex.available_editors(cfg2)
    check("available_editors: aider True", eds["aider"] is True)
    check("reserve_editor_name → aider cand aider prezent", ex.reserve_editor_name(cfg2) == "aider")
    exmod.shutil.which = lambda name: None
    check("reserve_editor_name → None cand nimic instalat", ex.reserve_editor_name(cfg2) is None)
    check("editor_fallback_enabled=False → fara rezerva",
          ex.reserve_editor_name(dict(cfg2, editor_fallback_enabled=False)) is None)
    exmod.shutil.which = _orig_which

    # env injection: model groq → GROQ_API_KEY din providers (mock)
    from ai_engine import config as aicfg
    _lk = aicfg.load_keys
    aicfg.load_keys = lambda: {"groq": "gsk_test"}
    try:
        env = ex._aider_env({"aider_model": "groq/llama-3.3-70b"})
        check("aider env: GROQ_API_KEY injectat din providers", env.get("GROQ_API_KEY") == "gsk_test")
    finally:
        aicfg.load_keys = _lk


def test_matrix():
    print("[matrix]")
    from telegram_bridge.matrix_io import MatrixClient, _strip_html

    check("matrix_ready: off by default", config.matrix_ready({"matrix_enabled": False}) is False)
    _orig = config.load_matrix_token
    config.load_matrix_token = lambda: "tok123"
    check("matrix_ready: enabled+hs+room+token → True",
          config.matrix_ready({"matrix_enabled": True, "matrix_homeserver": "https://hs",
                               "matrix_room_id": "!r:hs"}) is True)
    check("matrix_ready: enabled dar fara room → False",
          config.matrix_ready({"matrix_enabled": True, "matrix_homeserver": "https://hs",
                               "matrix_room_id": ""}) is False)
    config.load_matrix_token = _orig

    check("strip_html", _strip_html("<b>hi</b> &lt;x&gt; &amp;") == "hi <x> &")

    # sync parsing (mock _req)
    c = MatrixClient("https://hs", "tok", "!room:hs")
    c.user_id = "@bot:hs"
    fake = {"next_batch": "s2", "rooms": {"join": {"!room:hs": {"timeline": {"events": [
        {"type": "m.room.message", "sender": "@me:hs",
         "content": {"msgtype": "m.text", "body": "/status"}, "origin_server_ts": 1000},
        {"type": "m.room.message", "sender": "@bot:hs",
         "content": {"msgtype": "m.text", "body": "echo propriu"}, "origin_server_ts": 1001},
        {"type": "m.room.message", "sender": "@me:hs",
         "content": {"msgtype": "m.image", "body": "poza"}, "origin_server_ts": 1002},
    ]}}}}}
    c._req = lambda *a, **k: fake
    nb, msgs = c.sync(None, 0)
    check("sync: next_batch extras", nb == "s2")
    check("sync: doar TEXT de la user (ignora ecoul botului + non-text)",
          len(msgs) == 1 and msgs[0]["text"] == "/status" and msgs[0]["sender"] == "@me:hs")

    # send payload (mock _req)
    sent = []
    c2 = MatrixClient("https://hs", "tok", "!room:hs")
    c2._req = lambda method, path, params=None, body=None, timeout=40: (sent.append((method, path, body)) or {})
    c2.send("!room:hs", "<b>salut</b>", parse_mode="HTML")
    check("send: PUT pe m.room.message", bool(sent) and sent[0][0] == "PUT"
          and "send/m.room.message" in sent[0][1])
    check("send: body plain (HTML stripat) + formatted_body HTML",
          sent[0][2]["body"] == "salut" and sent[0][2].get("formatted_body") == "<b>salut</b>")


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
    test_editors()
    test_matrix()
    print()
    if _fails:
        print(f"[FAIL] {len(_fails)} teste PICATE: {_fails}")
        return 1
    print("[PASS] Toate testele au trecut.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
