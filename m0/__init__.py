"""
M0 — Audit statistic al sesiunilor (Deflated Sharpe + robustete temporala).

Milestone 0 din planul AI Engine (docs/AI_ENGINE_FEASIBILITY.md).
Scop: determina care dintre cele 20 de sesiuni au un edge real, distinct de
noroc de cautare, INAINTE de a construi orice strat AydeAI peste ele.

Read-only: nu atinge nimic din sistemul live. Reutilizeaza exact acelasi
engine de backtest (engine.portfolio.run_portfolio) ca dashboard-ul.
"""
