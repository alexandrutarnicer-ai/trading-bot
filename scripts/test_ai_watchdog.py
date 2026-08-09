"""
test_ai_watchdog.py — teste offline pentru logica de boot a watchdog-ului AI.

Redesign 2026-08-08: bat-ul de autostart ingheta pe pauzele `ping` la boot, deci
watchdog-ul (lansat DUPA acele pauze) nu pornea niciodata si nimic nu repornea
motorul. Fix: bat-ul lanseaza DOAR watchdog-ul, imediat; asteptarea MT5/Ollama e
mutata in watchdog (`_boot_phase`). Aceste teste verifica exact acea logica,
fara MT5/Ollama/procese reale — ceas fals + motor simulat, determinist.

Rulare:  python scripts/test_ai_watchdog.py
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_engine.watchdog as wd


class FakeClock:
    """Ceas virtual: sleep() nu asteapta real, doar avanseaza timpul."""
    def __init__(self, start=1000.0):
        self.t = start

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s


class EngineSim:
    """Motor simulat. `die_ats[i]` = varsta (s de la pornire) la care moare a
    (i+1)-a instanta pornita; None = supravietuieste. Modeleaza engine.run() care
    isi scrie PID-ul devreme (dupa `boot_delay`) apoi poate iesi daca MT5/Ollama
    nu-s gata."""
    def __init__(self, clock, die_ats, boot_delay=1.0, pre_started=False):
        self.clock = clock
        self.die_ats = die_ats
        self.boot_delay = boot_delay
        self.starts = 1 if pre_started else 0
        # motor "deja pornit" = lansat cu mult in trecut (a trecut de boot_delay,
        # deci e deja viu la prima verificare a watchdog-ului)
        self.started_at = (clock.time() - 100.0) if pre_started else None

    def start(self):
        self.started_at = self.clock.time()
        self.starts += 1

    def alive(self):
        if self.started_at is None:
            return False
        age = self.clock.time() - self.started_at
        if age < self.boot_delay:
            return False                      # inca nu si-a scris PID-ul
        idx = self.starts - 1
        die_at = self.die_ats[idx] if idx < len(self.die_ats) else None
        return not (die_at is not None and age >= die_at)


def _patch(monkey_targets, clock, engine):
    """Injecteaza ceasul fals + motorul simulat in modulul watchdog."""
    saved = {}
    saved["time"] = wd.time
    saved["_engine_alive"] = wd._engine_alive
    saved["_start_engine"] = wd._start_engine
    saved["_log"] = wd._log
    saved["_notify"] = wd._notify
    wd.time = types.SimpleNamespace(time=clock.time, sleep=clock.sleep)
    wd._engine_alive = engine.alive
    wd._start_engine = engine.start
    wd._log = lambda *a, **k: None
    wd._notify = lambda *a, **k: None
    return saved


def _restore(saved):
    for k, v in saved.items():
        setattr(wd, k, v)


def _run_boot(die_ats, pre_started=False):
    clock = FakeClock()
    engine = EngineSim(clock, die_ats, pre_started=pre_started)
    saved = _patch(None, clock, engine)
    try:
        t0 = clock.time()
        booted = wd._boot_phase()
        elapsed = clock.time() - t0
        return booted, engine.starts, elapsed
    finally:
        _restore(saved)


def _run_stable(die_at):
    clock = FakeClock()
    engine = EngineSim(clock, [die_at])
    saved = _patch(None, clock, engine)
    try:
        engine.start()
        clock.sleep(engine.boot_delay)        # a scris PID-ul
        return wd._engine_stable()
    finally:
        _restore(saved)


PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [ESUAT] {name}")


def main():
    print("=== test_ai_watchdog: logica de boot a watchdog-ului ===\n")

    # 1) Boot fericit: motorul porneste din prima si ramane viu.
    booted, starts, _ = _run_boot(die_ats=[None])
    check("boot fericit -> booted=True", booted is True)
    check("boot fericit -> exact 1 pornire", starts == 1)

    # 2) MT5 lent: prima instanta moare (age 40, in fereastra de stabilizare),
    #    a doua prinde. Exact ceea ce nu functiona inainte (nimic nu repornea).
    booted, starts, _ = _run_boot(die_ats=[40, None])
    check("MT5 lent -> booted=True", booted is True)
    check("MT5 lent -> a repornit (2 porniri)", starts == 2)

    # 3) MT5 lent x3 apoi prinde.
    booted, starts, _ = _run_boot(die_ats=[40, 40, 40, None])
    check("MT5 lent x3 -> booted=True", booted is True)
    check("MT5 lent x3 -> 4 porniri", starts == 4)

    # 4) Motorul nu prinde niciodata in fereastra -> booted=False (dar fara bucla
    #    infinita: se opreste la BOOT_WINDOW_S).
    booted, starts, elapsed = _run_boot(die_ats=[40] * 100)
    check("nu prinde niciodata -> booted=False", booted is False)
    check("nu prinde -> s-a oprit la ~BOOT_WINDOW_S (fara bucla infinita)",
          elapsed <= wd.BOOT_WINDOW_S + wd.STICK_S + 5)
    check("nu prinde -> a incercat de mai multe ori", starts >= 5)

    # 5) Motorul deja rula cand porneste watchdog-ul (start manual / din API):
    #    nu pornim o a doua instanta.
    booted, starts, _ = _run_boot(die_ats=[None], pre_started=True)
    check("motor deja pornit -> booted=True", booted is True)
    check("motor deja pornit -> ZERO porniri noi (fara dublura)", starts == 1)

    # 6) _engine_stable: viu tot timpul -> True.
    check("_engine_stable: viu peste prag -> True", _run_stable(die_at=None) is True)

    # 7) _engine_stable: moare in fereastra -> False (prinde crash-ul rapid).
    check("_engine_stable: moare devreme -> False", _run_stable(die_at=30) is False)

    print(f"\n=== {PASS} OK, {FAIL} esuate ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
