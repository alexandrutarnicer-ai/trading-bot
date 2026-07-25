"""
voice_bridge — canal VOCAL peste botul de trading (asistentul "EMA").

Al treilea canal, dupa Telegram si Matrix, care se conecteaza la ACELASI Router
(telegram_bridge.router.Router) — deci comenzile sunt identice logic, doar
transportul difera: microfon → Speech-to-Text → Router → Text-to-Speech.

Complet ADITIV si IZOLAT (ca telegram_bridge): proces standalone, nu importa /
modifica botul/motorul/API in mod care le schimba starea, nu deschide o a doua
conexiune MT5. Reutilizeaza logica de comenzi din telegram_bridge.

SIGURANTA: microfonul NU are whitelist (oricine e langa PC poate vorbi), deci
canalul vocal e FORTAT read-only — `allow_writes` e mereu False aici, iar
normalizatorul nu produce niciodata comenzi de scriere (`claude!`, `/edit`).
"""

__all__ = ["config", "normalize", "tts"]
