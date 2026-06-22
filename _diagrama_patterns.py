"""
Genereaza diagrame candlestick pentru Bull Flag si Inside Bar Breakout.
Salveaza PNG-uri in data/
Ruleaza: python _diagrama_patterns.py
"""

import sys, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

OUT_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUT_DIR, exist_ok=True)

BG       = "#0d1117"
PANEL    = "#161b22"
BULL     = "#26a69a"
BEAR     = "#ef5350"
NEUTRAL  = "#6e7681"
ENTRY_C  = "#f0c040"
SL_C     = "#ef5350"
TP_C     = "#26a69a"
TEXT_C   = "#e6edf3"
GRID_C   = "#21262d"
ANNOT_C  = "#8b949e"


def draw_candle(ax, x, o, h, l, c, width=0.55):
    color = BULL if c >= o else BEAR
    body_bot = min(o, c)
    body_h   = max(abs(c - o), 0.00005)
    rect = mpatches.Rectangle(
        (x - width / 2, body_bot), width, body_h,
        facecolor=color, edgecolor=color, linewidth=0, zorder=3,
    )
    ax.add_patch(rect)
    ax.plot([x, x], [l, h], color=color, linewidth=1.4, zorder=2)


def style_ax(ax, title, xlim, ylim):
    ax.set_facecolor(PANEL)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_title(title, color=TEXT_C, fontsize=13, fontweight="bold", pad=14)
    ax.tick_params(colors=ANNOT_C, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(GRID_C)
    ax.yaxis.grid(True, color=GRID_C, linewidth=0.5, linestyle="--", alpha=0.6)
    ax.set_axisbelow(True)
    ax.xaxis.set_visible(False)


def hline(ax, y, color, label, xmin, xmax, lw=1.5, ls="--", xtext=None, yoff=0):
    ax.hlines(y, xmin, xmax, colors=color, linewidths=lw, linestyles=ls, zorder=5)
    xt = xtext if xtext is not None else xmax + 0.15
    ax.text(xt, y + yoff, label, color=color, fontsize=8.5,
            va="center", ha="left", fontweight="bold",
            bbox=dict(facecolor=PANEL, edgecolor="none", alpha=0.8, pad=1))


def bracket(ax, x, y_bot, y_top, color, label, side="right"):
    mid = (y_bot + y_top) / 2
    bw  = 0.12
    xb  = x + bw if side == "right" else x - bw
    ax.annotate("", xy=(xb, y_top), xytext=(xb, y_bot),
                arrowprops=dict(arrowstyle="<->", color=color, lw=1.3))
    ax.text(xb + (0.12 if side == "right" else -0.12), mid, label,
            color=color, fontsize=8, va="center",
            ha="left" if side == "right" else "right")


# ─────────────────────────────────────────────────────────────────────────────
#  DIAGRAMA 1 — BULL FLAG
# ─────────────────────────────────────────────────────────────────────────────

candles_flag = [
    # x,    open,   high,   low,    close
    # Context
    (1,  1.1000, 1.1008, 1.0993, 1.1005),
    (2,  1.1005, 1.1014, 1.0998, 1.1002),
    (3,  1.1002, 1.1009, 1.0994, 1.1007),
    # Pol — 3 bare bullish puternice
    (4,  1.1005, 1.1030, 1.1003, 1.1028),
    (5,  1.1028, 1.1057, 1.1026, 1.1053),
    (6,  1.1053, 1.1080, 1.1051, 1.1077),
    # Flag — 4 bare mici bearish (consolidare < 50% din pol)
    (7,  1.1074, 1.1079, 1.1059, 1.1062),
    (8,  1.1062, 1.1068, 1.1053, 1.1057),
    (9,  1.1057, 1.1065, 1.1050, 1.1060),
    (10, 1.1060, 1.1067, 1.1052, 1.1055),
    # Bara j — breakout (inchide > flag_high)
    (11, 1.1057, 1.1088, 1.1054, 1.1083),
    # Bara j+1 — triggereaza BUY_STOP
    (12, 1.1084, 1.1096, 1.1081, 1.1092),
]

flag_high  = 1.1079    # max al flag-ului
flag_low   = 1.1050    # min al flag-ului
bar_j_high = 1.1088
buf        = 0.0002
entry      = bar_j_high + buf
sl         = flag_low  - buf
risk       = entry - sl
r_ratio    = 2.0
tp         = entry + risk * r_ratio

fig1, ax = plt.subplots(figsize=(12, 7))
fig1.patch.set_facecolor(BG)
style_ax(ax, "Bull Flag — Intrare BUY_STOP", xlim=(0.3, 14.5), ylim=(1.0985, 1.1155))

for c in candles_flag:
    draw_candle(ax, *c)

# Zona flag — umbrire
ax.axvspan(6.5, 10.5, alpha=0.07, color="#f0c040", zorder=1)
ax.text(8.5, 1.1043, "FLAG\n(consolidare)", color="#f0c040", fontsize=8,
        ha="center", va="top", alpha=0.7)

# Zona pol — umbrire
ax.axvspan(3.5, 6.5, alpha=0.07, color=BULL, zorder=1)
ax.text(5, 1.1015, "POL\n(3 bare bullish)", color=BULL, fontsize=8,
        ha="center", va="bottom", alpha=0.7)

# Linii cheie
xmin_full = 0.5
xmax_lbl  = 12.5

hline(ax, flag_high, "#f0c040", "flag_high", 6.5, 10.5,
      lw=1, ls=":", yoff=-0.0004)
hline(ax, flag_low, "#f0c040", "flag_low", 6.5, 10.5,
      lw=1, ls=":", yoff=0.0004)
hline(ax, bar_j_high, ANNOT_C, "bar_j.high", 10.5, xmax_lbl,
      lw=1, ls=":", yoff=0.0003)

hline(ax, entry, ENTRY_C, f"ENTRY  BUY_STOP  = bar_j.high + 2pip  ({entry:.4f})",
      xmin_full, xmax_lbl, lw=2, ls="-", yoff=0.0003)
hline(ax, sl, SL_C, f"SL  = flag_low − 2pip  ({sl:.4f})",
      xmin_full, xmax_lbl, lw=2, ls="-", yoff=-0.0004)
hline(ax, tp, TP_C, f"TP  = {r_ratio:.0f}R  ({tp:.4f})",
      xmin_full, xmax_lbl, lw=2, ls="-", yoff=0.0003)

# Sageata trigger pe bara j+1
ax.annotate("Trigger\nbara j+1", xy=(12, entry + 0.0003),
            xytext=(12.5, entry + 0.0030),
            color=ENTRY_C, fontsize=8, ha="center",
            arrowprops=dict(arrowstyle="-|>", color=ENTRY_C, lw=1.2))

# Etichete bare
for xi, label in [(4, "P1"), (5, "P2"), (6, "P3"),
                  (7, "F1"), (8, "F2"), (9, "F3"), (10, "F4"),
                  (11, "j"), (12, "j+1")]:
    ax.text(xi, 1.0990, label, color=ANNOT_C, fontsize=7.5,
            ha="center", va="bottom")

# Bracket Risk/Reward
bx = 13.2
ax.annotate("", xy=(bx, tp), xytext=(bx, entry),
            arrowprops=dict(arrowstyle="<->", color=TP_C, lw=1.3))
ax.text(bx + 0.1, (tp + entry) / 2, f"{r_ratio:.0f}R\nreward",
        color=TP_C, fontsize=8, va="center")
ax.annotate("", xy=(bx, entry), xytext=(bx, sl),
            arrowprops=dict(arrowstyle="<->", color=SL_C, lw=1.3))
ax.text(bx + 0.1, (entry + sl) / 2, "1R\nrisk",
        color=SL_C, fontsize=8, va="center")

fig1.tight_layout(pad=1.2)
out1 = os.path.join(OUT_DIR, "diagrama_flag.png")
fig1.savefig(out1, dpi=140, facecolor=BG)
print(f"  Salvat: {out1}")
plt.close(fig1)


# ─────────────────────────────────────────────────────────────────────────────
#  DIAGRAMA 2 — INSIDE BAR BREAKOUT
# ─────────────────────────────────────────────────────────────────────────────

candles_ib = [
    # Context bars (trend ascendent)
    (1,  1.1000, 1.1012, 1.0993, 1.1010),
    (2,  1.1010, 1.1025, 1.1005, 1.1022),
    (3,  1.1022, 1.1035, 1.1018, 1.1030),
    (4,  1.1030, 1.1042, 1.1025, 1.1038),
    # Mother bar — range larg
    (5,  1.1035, 1.1085, 1.1020, 1.1050),
    # Inside bar — complet in interiorul mother
    (6,  1.1048, 1.1075, 1.1032, 1.1042),
    # Bara j — breakout deasupra inside bar high
    (7,  1.1044, 1.1088, 1.1040, 1.1082),
    # Bara j+1 — triggereaza BUY_STOP
    (8,  1.1083, 1.1098, 1.1080, 1.1095),
]

mother_high  = 1.1085
mother_low   = 1.1020
inside_high  = 1.1075
inside_low   = 1.1032
bar_j_high_ib = 1.1088
buf_ib       = 0.0002
entry_ib     = bar_j_high_ib + buf_ib
sl_ib        = inside_low - buf_ib
risk_ib      = entry_ib - sl_ib
r_ratio_ib   = 2.0
tp_ib        = entry_ib + risk_ib * r_ratio_ib

fig2, ax2 = plt.subplots(figsize=(10, 7))
fig2.patch.set_facecolor(BG)
style_ax(ax2, "Inside Bar Breakout — Intrare BUY_STOP", xlim=(0.2, 10.5), ylim=(1.0988, 1.1165))

for c in candles_ib:
    draw_candle(ax2, *c)

# Umbrire inside bar range
ax2.axhspan(inside_low, inside_high, alpha=0.06, color="#f0c040", zorder=1)

# Umbrire mother bar range (mai subtil)
ax2.axhspan(mother_low, mother_high, alpha=0.03, color=BULL, zorder=0)

# Linii cheie
xmin2 = 0.4
xmax2 = 8.5

hline(ax2, mother_high, ANNOT_C, "mother_high", 4.5, 5.5, lw=1, ls=":", yoff=0.0003)
hline(ax2, mother_low,  ANNOT_C, "mother_low",  4.5, 5.5, lw=1, ls=":", yoff=-0.0003)

hline(ax2, inside_high, "#f0c040", "inside_high", 5.5, 7.5, lw=1, ls=":", yoff=0.0003)
hline(ax2, inside_low,  "#f0c040", "inside_low",  5.5, 7.5, lw=1, ls=":", yoff=-0.0003)

hline(ax2, bar_j_high_ib, ANNOT_C, "bar_j.high", 6.5, xmax2, lw=1, ls=":", yoff=0.0003)

hline(ax2, entry_ib, ENTRY_C,
      f"ENTRY  BUY_STOP  = bar_j.high + 2pip  ({entry_ib:.4f})",
      xmin2, xmax2, lw=2, ls="-", yoff=0.0003)
hline(ax2, sl_ib, SL_C,
      f"SL  = inside_low − 2pip  ({sl_ib:.4f})",
      xmin2, xmax2, lw=2, ls="-", yoff=-0.0004)
hline(ax2, tp_ib, TP_C,
      f"TP  = {r_ratio_ib:.0f}R  ({tp_ib:.4f})",
      xmin2, xmax2, lw=2, ls="-", yoff=0.0003)

# Sageata trigger
ax2.annotate("Trigger\nbara j+1", xy=(8, entry_ib + 0.0003),
             xytext=(8.5, entry_ib + 0.0030),
             color=ENTRY_C, fontsize=8, ha="center",
             arrowprops=dict(arrowstyle="-|>", color=ENTRY_C, lw=1.2))

# Etichete bare
for xi, label in [(5, "mother bar"), (6, "inside bar"), (7, "j  (breakout)"), (8, "j+1")]:
    ax2.text(xi, 1.0993, label, color=ANNOT_C, fontsize=7.5,
             ha="center", va="bottom")

# Marcaj "inside complet in interior"
ax2.annotate("inside bar\ncomplet în\ninteriorul\nmother bar",
             xy=(6, (inside_high + inside_low) / 2),
             xytext=(3.0, (inside_high + inside_low) / 2),
             color="#f0c040", fontsize=8, va="center", ha="center",
             arrowprops=dict(arrowstyle="-|>", color="#f0c040", lw=1.0, alpha=0.7))

# Bracket R/R
bx2 = 9.5
ax2.annotate("", xy=(bx2, tp_ib), xytext=(bx2, entry_ib),
             arrowprops=dict(arrowstyle="<->", color=TP_C, lw=1.3))
ax2.text(bx2 + 0.1, (tp_ib + entry_ib) / 2, f"{r_ratio_ib:.0f}R\nreward",
         color=TP_C, fontsize=8, va="center")
ax2.annotate("", xy=(bx2, entry_ib), xytext=(bx2, sl_ib),
             arrowprops=dict(arrowstyle="<->", color=SL_C, lw=1.3))
ax2.text(bx2 + 0.1, (entry_ib + sl_ib) / 2, "1R\nrisk",
         color=SL_C, fontsize=8, va="center")

fig2.tight_layout(pad=1.2)
out2 = os.path.join(OUT_DIR, "diagrama_inside_bar.png")
fig2.savefig(out2, dpi=140, facecolor=BG)
print(f"  Salvat: {out2}")
plt.close(fig2)

print("\nGata. Deschide imaginile din data/")
