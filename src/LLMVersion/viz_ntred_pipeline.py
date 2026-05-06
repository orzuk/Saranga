"""
NtRED Pipeline: Optimization → Evaluation → Distillation
Minimal black-and-white academic figure.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

fig, ax = plt.subplots(figsize=(15.5, 4.5))
ax.set_xlim(0, 15.5)
ax.set_ylim(0, 4.5)
ax.axis('off')

# ── colours (grayscale only) ──────────────────────────────────────
PHASE_FILL = '#f2f2f2'
PHASE_EDGE = '#333333'
BOX_FILL   = '#ffffff'
BOX_EDGE   = '#555555'
ARR_CLR    = '#333333'
LBL_CLR    = '#000000'
SUB_CLR    = '#444444'

# ── helpers ───────────────────────────────────────────────────────
def phase_box(x, y, w, h, title):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.15",
        facecolor=PHASE_FILL, edgecolor=PHASE_EDGE, lw=1.5, zorder=1))
    ax.text(x + w/2, y + h - 0.22, title,
            ha='center', va='top', fontsize=11.5, fontweight='bold',
            color=LBL_CLR, zorder=5)

def inner_box(x, y, w, h, lines, fs=8):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.08",
        facecolor=BOX_FILL, edgecolor=BOX_EDGE, lw=0.8, zorder=2))
    ax.text(x + w/2, y + h/2, '\n'.join(lines),
            ha='center', va='center', fontsize=fs,
            color=SUB_CLR, linespacing=1.4, zorder=5)

def arrow(x1, y1, x2, y2, lw=1.1):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=ARR_CLR,
                                lw=lw, shrinkA=2, shrinkB=2), zorder=4)

def big_arrow(x1, x2, y):
    ax.annotate('', xy=(x2, y), xytext=(x1, y),
                arrowprops=dict(arrowstyle='-|>', color=ARR_CLR,
                                lw=2.0, shrinkA=0, shrinkB=0,
                                mutation_scale=14), zorder=4)

# ── layout constants ──────────────────────────────────────────────
pw, ph = 4.0, 3.5
gap = 0.95
py = 0.45

x1 = 0.45
x2 = x1 + pw + gap
x3 = x2 + pw + gap

# ══════════════════════════════════════════════════════════════════
# Phase 1 — Optimization
# ══════════════════════════════════════════════════════════════════
phase_box(x1, py, pw, ph, 'Phase 1: Optimization')

bw1, bh1 = 1.6, 1.0   # inner box size
pad = 0.22

# top row
b1x, b1y = x1 + pad, py + 1.8
b2x, b2y = x1 + pw - pad - bw1, py + 1.8
# bottom row
b3x, b3y = x1 + pad, py + 0.3
b4x, b4y = x1 + pw - pad - bw1, py + 0.3

inner_box(b1x, b1y, bw1, bh1, ['Extract with', 'current prompt'])
inner_box(b2x, b2y, bw1, bh1, ['Evaluate on', 'gold standard'])
inner_box(b3x, b3y, bw1, bh1, ['Meta-LLM', 'rewrites prompt'])
inner_box(b4x, b4y, bw1, bh1, ['Error analysis', '(FN, FP, near-miss)'])

# clockwise loop arrows
arrow(b1x + bw1, b1y + bh1/2, b2x, b2y + bh1/2)          # extract → evaluate
arrow(b2x + bw1/2, b2y, b4x + bw1/2, b4y + bh1)           # evaluate ↓ error
arrow(b4x, b4y + bh1/2, b3x + bw1, b3y + bh1/2)           # error ← meta
arrow(b3x + bw1/2, b3y + bh1, b1x + bw1/2, b1y)           # meta ↑ extract

# ══════════════════════════════════════════════════════════════════
# Phase 2 — Evaluation
# ══════════════════════════════════════════════════════════════════
phase_box(x2, py, pw, ph, 'Phase 2: Evaluation')

tw, th = 1.6, 1.2   # teacher / student boxes
inner_box(x2 + 0.2, py + 1.7, tw, th,
          ['LLM Teachers', '(Anthropic, OpenAI,', 'HuggingFace)'])
inner_box(x2 + pw - 0.2 - tw, py + 1.7, tw, th,
          ['Rule Student', '(regex parser)'])

cw, ch = 3.0, 0.85
cx = x2 + (pw - cw)/2
cy = py + 0.3
inner_box(cx, cy, cw, ch,
          ['Compare all providers against', 'gold standard  →  P / R / F1'])

# down arrows
arrow(x2 + 0.2 + tw/2, py + 1.7, cx + cw*0.3, cy + ch)
arrow(x2 + pw - 0.2 - tw/2, py + 1.7, cx + cw*0.7, cy + ch)

# ══════════════════════════════════════════════════════════════════
# Phase 3 — Distillation
# ══════════════════════════════════════════════════════════════════
phase_box(x3, py, pw, ph, 'Phase 3: Distillation')

# top: dark knowledge
dkw, dkh = 3.5, 0.7
dkx = x3 + (pw - dkw)/2
dky = py + 2.25
inner_box(dkx, dky, dkw, dkh,
          ['Detect dark knowledge:', 'student FN  $\\cap$  teacher TP'], fs=8)

# middle row
mw, mh = 1.55, 0.7
m1x = x3 + 0.2
m2x = x3 + pw - 0.2 - mw
my = py + 1.2
inner_box(m1x, my, mw, mh, ['Mine LaTeX', 'pattern → rule'])
inner_box(m2x, my, mw, mh, ['Apply rule to', 'student parser'])

# bottom: validate
vw, vh = 2.6, 0.55
vx = x3 + (pw - vw)/2
vy = py + 0.25
inner_box(vx, vy, vw, vh, ['Validate: re-evaluate F1'], fs=8)

# arrows inside phase 3
arrow(dkx + dkw*0.3, dky, m1x + mw/2, my + mh)      # dk → mine
arrow(m1x + mw, my + mh/2, m2x, my + mh/2)           # mine → apply
arrow(m2x + mw/2, my, vx + vw*0.65, vy + vh)          # apply → validate

# feedback loop: validate back up to dark-knowledge (dashed)
ax.annotate('', xy=(dkx + dkw*0.85, dky),
            xytext=(vx + vw*0.85, vy + vh),
            arrowprops=dict(arrowstyle='->', color=ARR_CLR,
                            lw=0.9, linestyle='dashed',
                            shrinkA=2, shrinkB=2,
                            connectionstyle='arc3,rad=-0.3'), zorder=4)
ax.text(x3 + pw - 0.15, py + 1.05, 'iterate',
        ha='right', va='center', fontsize=6.5, fontstyle='italic',
        color=SUB_CLR, rotation=90)

# ══════════════════════════════════════════════════════════════════
# Big inter-phase arrows + labels
# ══════════════════════════════════════════════════════════════════
mid_y = py + ph/2
big_arrow(x1 + pw + 0.04, x2 - 0.04, mid_y)
big_arrow(x2 + pw + 0.04, x3 - 0.04, mid_y)

ax.text((x1 + pw + x2)/2, mid_y + 0.18, 'optimized',
        ha='center', va='bottom', fontsize=7.5, fontstyle='italic', color=SUB_CLR)
ax.text((x1 + pw + x2)/2, mid_y - 0.18, 'prompts',
        ha='center', va='top', fontsize=7.5, fontstyle='italic', color=SUB_CLR)

ax.text((x2 + pw + x3)/2, mid_y + 0.18, 'evaluation',
        ha='center', va='bottom', fontsize=7.5, fontstyle='italic', color=SUB_CLR)
ax.text((x2 + pw + x3)/2, mid_y - 0.18, 'results',
        ha='center', va='top', fontsize=7.5, fontstyle='italic', color=SUB_CLR)

# ── Title ─────────────────────────────────────────────────────────
ax.text(15.5/2, 4.35, 'Neural-to-Rule Ensemble Distillation (NtRED) Pipeline',
        ha='center', va='top', fontsize=14, fontweight='bold', color=LBL_CLR)

plt.tight_layout(pad=0.2)
plt.savefig('ntred_pipeline.pdf', bbox_inches='tight', dpi=300)
plt.savefig('ntred_pipeline.png', bbox_inches='tight', dpi=300)
print('Saved  ntred_pipeline.pdf  and  ntred_pipeline.png')
