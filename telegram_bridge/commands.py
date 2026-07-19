"""
telegram_bridge.commands — comenzi INSTANT (fara AI, <1s).

Raspund din fisierele de stare + API-ul local, formatat pentru telefon. Nimic aici
nu ruleaza un model si nu blocheaza bucla de poll.

  /status   — bot + motor AI + MT5 (equity, pozitii, algo trading)
  /raport   — scorecardul motorului AI (azi/total) + rezumat sesiuni bot
  /piete    — clasament W/L + R per piata (din status.json)
  /pauza X  — pune pe pauza o sesiune a botului (proxy la endpoint-ul existent)
  /reia X   — reia o sesiune
  /ajutor   — lista completa de comenzi si cuvinte cheie
"""

from __future__ import annotations

import urllib.request

from . import status as st
from . import config


def _fmt_usd(v) -> str:
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _pct(v) -> str:
    try:
        return f"{float(v) * 100:.0f}%"
    except (TypeError, ValueError):
        return "—"


def cmd_status(cfg: dict) -> str:
    bot_on, bot = st.bot_running(cfg)
    ai_on, ai = st.ai_running()
    mt5 = st.mt5_snapshot(cfg)
    orders = st.orders_snapshot(cfg)

    lines = ["📟 STARE SISTEM", ""]

    if bot_on:
        na = bot.get("sessions_active", "?")
        nt = bot.get("sessions_total", "?")
        pz = bot.get("sessions_paused", 0)
        prof = bot.get("active_profile_name", "?")
        lines.append(f"🟢 Bot: ACTIV — {na}/{nt} sesiuni" + (f" ({pz} pauza)" if pz else ""))
        lines.append(f"   profil: {prof} · pid {bot.get('pid', '?')}")
    else:
        lines.append("🔴 Bot: OPRIT")

    if ai_on:
        sc = ai.get("scorecard", {})
        lines.append(f"🟢 Motor AI: ACTIV — {ai.get('model', '?')} · pid {ai.get('pid', '?')}")
        lines.append(f"   decizii {sc.get('decisions', 0)} · trade-uri {sc.get('closed_trades', 0)}"
                     f" · R {sc.get('total_R', 0)}")
    else:
        lines.append("🔴 Motor AI: OPRIT")

    lines.append("")
    if mt5.get("connected"):
        kind = "DEMO" if mt5.get("is_demo") else "🔴 LIVE"
        lines.append(f"💰 Cont {kind} {mt5.get('account', '')} @ {mt5.get('server', '')}")
        lines.append(f"   equity {_fmt_usd(mt5.get('equity'))} · balance {_fmt_usd(mt5.get('balance'))}")
        if mt5.get("algo_trading_enabled") is False:
            lines.append("   ⚠️ AutoTrading DEZACTIVAT in MT5 (ordinele nu se plaseaza!)")
    else:
        lines.append("💰 MT5: neconectat" + (f" ({mt5.get('error')})" if mt5.get("error") else ""))

    if orders.get("connected"):
        acc = orders.get("account", {})
        npos = len(orders.get("positions", []))
        npend = len(orders.get("pending", []))
        lines.append(f"📊 Pozitii deschise: {npos} · pending: {npend}"
                     f" · P&L flotant {_fmt_usd(acc.get('floating_pnl'))}")
        for p in orders.get("positions", [])[:8]:
            side = p.get("type") or p.get("direction") or ""
            lines.append(f"   • {p.get('symbol', '?')} {side} "
                         f"{_fmt_usd(p.get('profit', p.get('pnl')))} [{p.get('source', '?')}]")

    return "\n".join(lines)


def cmd_report(cfg: dict) -> str:
    ai_on, ai = st.ai_running()
    sc = ai.get("scorecard", {})
    lines = ["📈 RAPORT MOTOR AI", ""]
    if not sc:
        lines.append("(fara date — status.json gol sau motorul nu a rulat)")
    else:
        wr = _pct(sc.get("win_rate"))
        lines += [
            f"Decizii: {sc.get('decisions', 0)}  (WAIT {sc.get('waits', 0)})",
            f"Trade-uri inchise: {sc.get('closed_trades', 0)}  →  "
            f"{sc.get('wins', 0)}W / {sc.get('losses', 0)}L  (WR {wr})",
            f"Total R: {sc.get('total_R', 0)}   ·   Expectancy: {sc.get('expectancy_R', 0)}R",
            f"Equity: {_fmt_usd(ai.get('equity'))}",
        ]
        provs = ai.get("providers", {})
        if provs:
            bad = [n for n, h in provs.items() if h.get("status") != "healthy"]
            lines.append("")
            lines.append(f"Surse AI: {len(provs)} activate"
                         + (f" · ⚠️ {', '.join(bad)}" if bad else " · toate sanatoase"))

    bot_on, bot = st.bot_running(cfg)
    if bot_on:
        lines += ["", f"🤖 Bot: {bot.get('sessions_active', '?')}/{bot.get('sessions_total', '?')} "
                      f"sesiuni pe «{bot.get('active_profile_name', '?')}»"]
    return "\n".join(lines)


def cmd_markets(cfg: dict) -> str:
    _, ai = st.ai_running()
    by = ai.get("scorecard_by_symbol", {}) or {}
    if not by:
        return "🗺 Fara date per piata inca (status.json gol)."
    rows = []
    for sym, d in by.items():
        ct = d.get("closed_trades", 0)
        rows.append((d.get("total_R", 0), sym, ct, d.get("wins", 0), d.get("losses", 0)))
    rows.sort(reverse=True)
    lines = ["🗺 PIETE (motor AI) — dupa R", ""]
    for r, sym, ct, w, l in rows:
        medal = ""
        lines.append(f"{medal}{sym:8s}  R {r:+.2f}   {ct}t ({w}W/{l}L)")
    return "\n".join(lines)


def _resolve_session(arg: str) -> str | None:
    """'S7' / 's7' / 'session7' / '7' → 'session7'."""
    a = (arg or "").strip().lower()
    if not a:
        return None
    if a.startswith("session") and a[7:].isdigit():
        return a
    if a.startswith("s") and a[1:].isdigit():
        return f"session{a[1:]}"
    if a.isdigit():
        return f"session{a}"
    return None


def _api_post(cfg: dict, path: str) -> tuple[bool, str]:
    try:
        url = cfg["api_base"].rstrip("/") + path
        req = urllib.request.Request(url, data=b"{}",
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=cfg.get("api_timeout_s", 6)) as r:
            r.read()
        return True, ""
    except Exception as e:
        return False, str(e)[:150]


def cmd_pause(cfg: dict, arg: str, resume: bool = False) -> str:
    sid = _resolve_session(arg)
    verb = "reia" if resume else "pune pe pauza"
    if not sid:
        return f"Foloseste: /{'reia' if resume else 'pauza'} S7  (sau session7)"
    ok, err = _api_post(cfg, f"/sessions/{sid}/{'resume' if resume else 'pause'}")
    if ok:
        return f"{'▶️' if resume else '⏸'} {sid} — {verb} OK (efect la bara urmatoare)."
    return f"⚠️ Nu am putut {verb} {sid}: {err}"


def cmd_help(cfg: dict) -> str:
    kw = lambda k: cfg.get(k)
    aw = "ACTIVAT" if cfg.get("allow_writes") else "dezactivat"
    return "\n".join([
        "🤖 PUNTE TELEGRAM — comenzi",
        "",
        "Instant (fara AI):",
        "  /status — bot + motor AI + cont MT5 + pozitii",
        "  /raport — scorecardul motorului AI",
        "  /piete  — clasament per piata",
        "  /pauza S7 · /reia S7 — pauza/reia o sesiune",
        "  /ajutor — acest mesaj",
        "",
        "AI rapid (~5-30s):",
        f"  {kw('kw_ai')} <intrebare>  — raspuns de la sursele AI existente",
        "     ex: ai de ce e XRPUSD pe WAIT?",
        "",
        "Claude (agent complet, read-only):",
        f"  {kw('kw_claude')} <cerere>  — citeste cod, ruleaza teste, face rapoarte",
        f"  {kw('kw_claude_resume')} <mesaj> — continua ultima conversatie",
        "     (sau raspunde direct la un mesaj al lui Claude)",
        "",
        f"Modificari de cod ({aw}):",
        f"  {kw('kw_claude_write')} <cerere> — propune un plan + cod de confirmare",
        f"  {kw('kw_confirm')} <cod> — executa planul (in {cfg.get('confirm_timeout_s', 300)//60} min)",
        "",
        "Mesajele fara cuvant cheie sunt ignorate.",
    ])
