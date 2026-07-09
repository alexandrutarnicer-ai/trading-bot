"""
ai_engine — motor de trading autonom bazat pe AI (separat de botul pe reguli).

Arhitectura (vezi docs/AI_ENGINE.md):
  perception.py — snapshot numeric al pietei la fiecare bara M15 (gratuit, local)
  triggers.py   — decide CAND se convoaca consiliul AI (regime flip, structura,
                  volatilitate, stiri, heartbeat) — nu la fiecare bara
  council.py    — "grupul de traderi" AI: Analist Tehnic, Analist Macro/Stiri,
                  Risk Manager, Head Trader — ruleaza local pe Ollama (gratuit)
  executor.py   — plaseaza ordine DOAR pe cont DEMO MT5, namespace propriu
                  (magic number + prefix comment), rails de siguranta hard
  ledger.py     — SQLite: snapshots, transcripturi consiliu, decizii, outcomes
  engine.py     — bucla principala M15

Complet independent de live/signal_generator.py — nu citeste si nu scrie
nimic din state-ul sesiunilor pe reguli.
"""

__version__ = "0.1.0"
