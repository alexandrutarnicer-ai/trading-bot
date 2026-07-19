"""
telegram_bridge — punte Telegram → App → Claude / surse AI.

Daemon STANDALONE, complet aditiv: nu importa si nu modifica nimic din botul pe
reguli (live/), motorul AI (ai_engine/) sau API (api/) in mod care sa le afecteze
starea. Reutilizeaza DOAR:
  - ai_engine.providers / ai_engine.config  (read-only, pentru raspunsurile "ai ...")
  - fisierele de stare deja scrise de sistem  (data/ai/status.json, data/*.pid)
  - API-ul local prin HTTP                     (localhost:8000/api/*, cache-uit deja)

Nu deschide o a doua conexiune MT5, nu atinge ledger-ul motorului la scriere, nu
consuma getUpdates-ul nimanui (nimic altceva din proiect nu foloseste getUpdates —
tot restul codului trimite DOAR sendMessage). Pornit manual:  python -m telegram_bridge
"""

__version__ = "0.1.0"
