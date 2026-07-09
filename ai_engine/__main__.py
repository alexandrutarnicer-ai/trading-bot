"""Entry point: python -m ai_engine"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_engine.engine import run

if __name__ == "__main__":
    run()
