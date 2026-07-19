"""Entrypoint: python -m telegram_bridge"""

import sys

from .bridge import entry

if __name__ == "__main__":
    sys.exit(entry())
