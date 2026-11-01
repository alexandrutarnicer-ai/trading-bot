"""
Jurnale cu rotatie pentru engine-urile care ruleaza continuu (Custom / AI) — inainte cresteau la
nesfarsit. La LOG_MAX_BYTES fisierul devine .1 (vechile .1 → .2 …), se pastreaza LOG_BACKUPS copii.

Pe Windows redenumirea esueaza daca alt proces tine fisierul deschis chiar atunci (ex. dashboard-ul
citeste jurnalul): rotatia se amana la mesajul urmator, fara eroare si fara pierdere de linii.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

LOG_MAX_BYTES = 5_000_000
LOG_BACKUPS = 3


class SafeRotatingFileHandler(RotatingFileHandler):
    def doRollover(self) -> None:
        try:
            super().doRollover()
        except OSError:
            # fisier tinut deschis de alt proces → continua in acelasi fisier, reincearca mai tarziu
            if self.stream is None:
                self.stream = self._open()


def rotating_handler(path: str, max_bytes: int = LOG_MAX_BYTES, backups: int = LOG_BACKUPS) -> logging.Handler:
    return SafeRotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8", delay=False)
