# -*- coding: utf-8 -*-
"""
Teste pentru modul liniste al notificarilor Telegram ("Doar notificari importante").

Cand flag-ul `important_only` din data/telegram_config.json e activ, se trimit pe
Telegram DOAR notificarile de trading + conexiune + lifecycle bot; restul
(sanatatea surselor AI, pauze manuale, mesaje de sistem) NU se mai trimit pe
telefon, dar raman logate in tab-ul Notificari.

Verificam:
  - _categorize da categoria corecta pentru mesajele reale din cod
  - is_important_notification() = KEEP/SUPPRESS corect
  - should_push_telegram() respecta flag-ul (off = trimite tot; on = doar importante)
  - fail-open: flag necitibil / eroare => trimite (nu suprima din greseala)

Rulare:
    python scripts/test_notification_quiet_mode.py     # offline, zero dependinte
"""

import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from api import notifications as N

_passed = 0
_failed = 0


def check(cond: bool, msg: str) -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  OK  {msg}")
    else:
        _failed += 1
        print(f"  XX  {msg}")


# ── Mesaje REALE din cod (verbatim, ca sa nu divergem de productie) ───────────
# (mesaj, categorie asteptata, important?)   important => trimis si in modul liniste
CASES = [
    # --- AI Engine ---
    ("🛑 <b>AI Engine — TOATE sursele AI indisponibile!</b>\n"
     "Nicio sursă sănătoasă (quota epuizată / picate / Ollama defect): ollama:server_error\n"
     "Consiliul dă WAIT la tot până revine cel puțin o sursă.", "system", False),
    ("✅ <b>AI Engine — sursele AI și-au revenit</b>\n"
     "Disponibile acum: ollama, groq. Deciziile se reiau normal.", "system", False),
    ("🤖 AI Engine — conexiune MT5 pierduta, reconectez...", None, True),
    ("🤖 AI Engine — EURUSD TP: +2.00R +50.00$\n(decizia #12)", "trade", True),
    ("🤖 AI Engine pornit — mode=demo, model=qwen3:8b, piete: EURUSD, XRPUSD", "bot", True),
    ("🤖 AI Engine oprit.", "bot", True),
    ("🤖📅 AI Engine — EURUSD: pozitie inchisa pentru weekend (Vineri 22:00).", "trade", True),
    ("🤖 AI Engine — CLOSE EURUSD\nMotiv: regim schimbat.", "trade", True),
    ("🤖⛔ AI Engine — pornirea unei A DOUA instante a fost BLOCATA.", "system", False),

    # --- Sanatatea surselor AI (providers.py::_notify, per sursa) — SUPRIMATE ---
    # Contin "Sursa AI «...»" => _categorize le pune in "ai", DAR sunt zgomot
    # operational, nu trading. Astea le primea userul desi activase modul liniste.
    ("🤖 ✅ Sursa AI «groq» si-a revenit — rutare normala.", "ai", False),
    ("🤖 🛑 Sursa AI «gemini» defecta (server) — llama-server binary not found", "ai", False),
    ("🤖 ⚠ Sursa AI «gemini» in pauza (quota, ~360 min) — rolurile ei trec temporar pe alta sursa.", "ai", False),
    ("🤖 🔑 Sursa AI «openai» dezactivata: cheie invalida. Repar-o din tab-ul AI Engine si apasa Testeaza.", "ai", False),
    ("🤖 🛑 SAFETY-NET «ollama» DEFECT — backend defect. Motorul ramane fara plasa de failover pana repari Ollama.", "system", False),

    # --- Bot pe reguli ---
    ("Ordin plasat #123: BUY_STOP EURUSD @ 1.0850 | SL 1.0820 | TP 1.0910", "order", True),
    ("ACTIVAT #123: LONG EURUSD @ 1.0850 | SL 1.0820 | TP 1.0910 (3.5R)", "order", True),
    ("EURUSD +3.5R TP (+175 USD)", "trade", True),
    ("EURUSD -1R SL (-50 USD)", "trade", True),
    ("⛔ Filtru AI: RESPINS — EURUSD long (consens 40%)", "ai", True),
    ("📰 Protectie stiri activa pentru EURUSD — pauza automata (NFP).", "news", True),

    # --- API / sistem ---
    ("🔴 <b>Bot Trading pornit</b> — profil standard, 18 sesiuni active.", "bot", True),
    ("Bot Trading oprit neasteptat! PID-ul nu mai e viu.", "bot", True),
    ("⚠️ MT5 deconectat de peste 5 min — ordinele nu pot fi plasate.", None, True),
]


def test_categorize_and_importance() -> None:
    print("[1] _categorize + is_important_notification pe mesaje reale")
    for text, exp_cat, exp_imp in CASES:
        got_cat = N._categorize(text)
        if exp_cat is not None:
            check(got_cat == exp_cat,
                  f"categorie {got_cat!r} (asteptat {exp_cat!r}) :: {text[:48]!r}")
        got_imp = N.is_important_notification(text)
        tag = "KEEP" if exp_imp else "SUPPRESS"
        check(got_imp == exp_imp,
              f"{tag} (got important={got_imp}) :: {text[:48]!r}")


def test_source_health_suppressed() -> None:
    print("[2] Sanatatea surselor AI e SUPRIMATA (tinta explicita a userului)")
    down = "🛑 AI Engine — TOATE sursele AI indisponibile!"
    up = "✅ AI Engine — sursele AI și-au revenit"
    check(not N.is_important_notification(down), "sursele indisponibile => SUPPRESS")
    check(not N.is_important_notification(up), "sursele revenite => SUPPRESS")


def test_connection_always_kept() -> None:
    print("[3] Conexiunea e mereu importanta (chiar daca ar cadea in system)")
    for t in ["conexiune MT5 pierduta, reconectez",
              "MT5 deconectat", "IPC send failed la XRPUSD",
              "AutoTrading dezactivat"]:
        check(N.is_important_notification(t), f"conexiune KEEP :: {t!r}")


def _with_temp_config(important_only):
    """Context manager simplu: redirijeaza TG_CONFIG_FILE catre un fisier temp."""
    class _Ctx:
        def __enter__(self):
            self._orig = N.TG_CONFIG_FILE
            fd, self._path = tempfile.mkstemp(suffix=".json")
            os.close(fd)
            if important_only is None:
                os.remove(self._path)  # simuleaza fisier lipsa
            else:
                with open(self._path, "w", encoding="utf-8") as f:
                    json.dump({"token": "t", "chat_id": "c",
                               "important_only": important_only}, f)
            N.TG_CONFIG_FILE = self._path
            return self
        def __exit__(self, *a):
            N.TG_CONFIG_FILE = self._orig
            try:
                os.remove(self._path)
            except OSError:
                pass
    return _Ctx()


def test_should_push_flag_off() -> None:
    print("[4] Flag OFF => se trimite TOT (comportament identic cu inainte)")
    with _with_temp_config(False):
        check(N.telegram_important_only() is False, "telegram_important_only() == False")
        for text, _, _ in CASES:
            check(N.should_push_telegram(text) is True,
                  f"push=True :: {text[:48]!r}")


def test_should_push_flag_on() -> None:
    print("[5] Flag ON => push doar pentru importante; restul suprimat")
    with _with_temp_config(True):
        check(N.telegram_important_only() is True, "telegram_important_only() == True")
        for text, _, exp_imp in CASES:
            got = N.should_push_telegram(text)
            check(got == exp_imp,
                  f"push={got} (asteptat {exp_imp}) :: {text[:48]!r}")


def test_fail_open_missing_file() -> None:
    print("[6] Fail-open: fisier lipsa / eroare => trimite (nu suprima)")
    with _with_temp_config(None):  # fisier sters
        check(N.telegram_important_only() is False, "flag necitibil => False (fail-open)")
        down = "🛑 AI Engine — TOATE sursele AI indisponibile!"
        check(N.should_push_telegram(down) is True,
              "chiar si un mesaj neimportant se trimite cand flag-ul nu poate fi citit")


def main() -> None:
    print("=" * 70)
    print("TESTE — mod liniste notificari Telegram (Doar notificari importante)")
    print("=" * 70)
    test_categorize_and_importance()
    test_source_health_suppressed()
    test_connection_always_kept()
    test_should_push_flag_off()
    test_should_push_flag_on()
    test_fail_open_missing_file()
    print("=" * 70)
    print(f"REZULTAT: {_passed} OK, {_failed} esuate")
    print("=" * 70)
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
