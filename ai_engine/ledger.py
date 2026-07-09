"""
ai_engine.ledger — memoria persistenta a motorului AI (SQLite).

Tot ce percepe, gandeste si decide motorul e inregistrat aici, ca sa putem
raspunde ulterior la intrebarea "are valoare acest creier?" cu date, nu impresii:
  snapshots  — starea pietei la fiecare convocare de consiliu
  councils   — transcriptul complet al dezbaterii (fiecare rol, verbatim)
  decisions  — decizia finala structurata + statusul executiei
  outcomes   — rezultatul real al fiecarei decizii executate (R, pnl)
"""

from __future__ import annotations

import os
import json
import sqlite3
from datetime import datetime

from ai_engine.config import AI_DATA

DB_PATH = os.path.join(AI_DATA, "ledger.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    data       TEXT NOT NULL            -- JSON: snapshot complet
);
CREATE TABLE IF NOT EXISTS councils (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    trigger     TEXT NOT NULL,          -- ce a convocat consiliul
    snapshot_id INTEGER,
    transcript  TEXT NOT NULL,          -- JSON: {role: raspuns} per agent
    duration_s  REAL
);
CREATE TABLE IF NOT EXISTS decisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    council_id  INTEGER,
    action      TEXT NOT NULL,          -- OPEN_LONG / OPEN_SHORT / CLOSE / WAIT
    order_type  TEXT,                   -- market / stop
    entry       REAL, sl REAL, tp REAL,
    risk_pct    REAL,
    confidence  INTEGER,
    rationale   TEXT,
    exec_status TEXT NOT NULL,          -- shadow / placed / rejected / failed / skipped
    exec_detail TEXT,                   -- ticket sau motiv respingere
    ticket      INTEGER
);
CREATE TABLE IF NOT EXISTS outcomes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    decision_id INTEGER NOT NULL,
    symbol      TEXT NOT NULL,
    status      TEXT NOT NULL,          -- TP / SL / closed / expired / cancelled
    exit_price  REAL,
    result_r    REAL,
    pnl_usd     REAL
);
CREATE INDEX IF NOT EXISTS idx_dec_symbol ON decisions(symbol, ts);
CREATE INDEX IF NOT EXISTS idx_out_dec    ON outcomes(decision_id);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Ledger:
    def __init__(self, path: str = DB_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.executescript(_SCHEMA)
        self.con.commit()

    def close(self):
        self.con.close()

    # ── scriere ──────────────────────────────────────────────────────────

    def add_snapshot(self, symbol: str, data: dict) -> int:
        cur = self.con.execute(
            "INSERT INTO snapshots (ts, symbol, data) VALUES (?,?,?)",
            (_now(), symbol, json.dumps(data, default=str)))
        self.con.commit()
        return cur.lastrowid

    def add_council(self, symbol: str, trigger: str, snapshot_id: int,
                    transcript: dict, duration_s: float) -> int:
        cur = self.con.execute(
            "INSERT INTO councils (ts, symbol, trigger, snapshot_id, transcript, duration_s) "
            "VALUES (?,?,?,?,?,?)",
            (_now(), symbol, trigger, snapshot_id,
             json.dumps(transcript, ensure_ascii=False, default=str), round(duration_s, 1)))
        self.con.commit()
        return cur.lastrowid

    def add_decision(self, symbol: str, council_id: int, d: dict,
                     exec_status: str, exec_detail: str = "",
                     ticket: int | None = None) -> int:
        cur = self.con.execute(
            "INSERT INTO decisions (ts, symbol, council_id, action, order_type, entry, sl, tp, "
            "risk_pct, confidence, rationale, exec_status, exec_detail, ticket) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (_now(), symbol, council_id, d.get("action", "WAIT"), d.get("order_type"),
             d.get("entry"), d.get("sl"), d.get("tp"), d.get("risk_pct"),
             d.get("confidence"), d.get("rationale", ""), exec_status, exec_detail, ticket))
        self.con.commit()
        return cur.lastrowid

    def add_outcome(self, decision_id: int, symbol: str, status: str,
                    exit_price: float | None, result_r: float | None,
                    pnl_usd: float | None) -> None:
        self.con.execute(
            "INSERT INTO outcomes (ts, decision_id, symbol, status, exit_price, result_r, pnl_usd) "
            "VALUES (?,?,?,?,?,?,?)",
            (_now(), decision_id, symbol, status, exit_price, result_r, pnl_usd))
        self.con.commit()

    def set_exec(self, decision_id: int, exec_status: str,
                 exec_detail: str = "", ticket: int | None = None,
                 entry: float | None = None) -> None:
        if entry is not None:
            # ordinele market: pretul real de executie inlocuieste entry-ul null
            self.con.execute(
                "UPDATE decisions SET exec_status=?, exec_detail=?, ticket=?, entry=? WHERE id=?",
                (exec_status, exec_detail, ticket, entry, decision_id))
        else:
            self.con.execute(
                "UPDATE decisions SET exec_status=?, exec_detail=?, ticket=? WHERE id=?",
                (exec_status, exec_detail, ticket, decision_id))
        self.con.commit()

    # ── citire ───────────────────────────────────────────────────────────

    def last_council_ts(self, symbol: str) -> str | None:
        row = self.con.execute(
            "SELECT ts FROM councils WHERE symbol=? ORDER BY id DESC LIMIT 1",
            (symbol,)).fetchone()
        return row[0] if row else None

    def open_decisions(self) -> list[dict]:
        """Decizii plasate care nu au inca outcome (pozitii/ordine active)."""
        rows = self.con.execute(
            "SELECT d.id, d.symbol, d.action, d.order_type, d.entry, d.sl, d.tp, "
            "d.risk_pct, d.ticket, d.ts FROM decisions d "
            "WHERE d.exec_status='placed' "
            "AND NOT EXISTS (SELECT 1 FROM outcomes o WHERE o.decision_id = d.id)"
        ).fetchall()
        cols = ["id", "symbol", "action", "order_type", "entry", "sl", "tp",
                "risk_pct", "ticket", "ts"]
        return [dict(zip(cols, r)) for r in rows]

    def daily_loss_R(self, day_iso: str) -> float:
        """Suma R negative + pozitive din ziua data (pentru stop zilnic)."""
        row = self.con.execute(
            "SELECT COALESCE(SUM(result_r), 0) FROM outcomes "
            "WHERE ts LIKE ? AND result_r IS NOT NULL", (day_iso + "%",)).fetchone()
        return float(row[0])

    def scorecard(self) -> dict:
        """Statistici agregate pentru evaluarea creierului."""
        row = self.con.execute(
            "SELECT COUNT(*), COALESCE(SUM(result_r),0), COALESCE(AVG(result_r),0), "
            "SUM(CASE WHEN result_r > 0 THEN 1 ELSE 0 END) "
            "FROM outcomes WHERE result_r IS NOT NULL").fetchone()
        n, total_r, avg_r, wins = row
        n_dec = self.con.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        n_wait = self.con.execute(
            "SELECT COUNT(*) FROM decisions WHERE action='WAIT'").fetchone()[0]
        return {
            "decisions": n_dec, "waits": n_wait, "closed_trades": n,
            "total_R": round(total_r, 2), "expectancy_R": round(avg_r, 3),
            "win_rate": round(wins / n, 3) if n else None,
        }
