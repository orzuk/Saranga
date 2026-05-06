"""
Academic figure: Classical KD (Hinton 2015) vs NtRED (Ours).
Two-row comparison, black-and-white, minimal.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

fig, axes = plt.subplots(2, 1, figsize=(10, 5.2),
                         gridspec_kw={'height_ratios': [1, 1]})

for ax in axes:
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3)
    ax.axis('off')

# ── Shared styles ──
box_kw = dict(boxstyle='round,pad=0.45', facecolor='white',
              edgecolor='black', linewidth=1.2)
arrow_kw = dict(arrowstyle='->', color='black', lw=1.2)
label_kw = dict(ha='center', va='center', fontsize=10.5, fontfamily='serif')
sub_kw = dict(ha='center', va='top', fontsize=7.5, fontfamily='serif', color='0.4')
tag_kw = dict(ha='center', va='center', fontsize=7.5, fontfamily='serif',
              bbox=dict(boxstyle='round,pad=0.25', facecolor='0.92',
                        edgecolor='0.6', linewidth=0.6))

# ════════════════════════════════════════
# Row 0 — Classical KD (Hinton et al.)
# ════════════════════════════════════════
ax = axes[0]

ax.text(0.15, 2.75, '(a)  Classical Knowledge Distillation  (Hinton et al., 2015)',
        ha='left', va='top', fontsize=10, fontfamily='serif',
        fontstyle='italic', color='0.25')

# Teacher
ax.text(1.5, 1.35, 'Teacher\nNetwork', **label_kw, bbox=box_kw)
ax.text(1.5, 0.25, 'large neural net', **sub_kw)

# Arrow + knowledge label
ax.annotate('', xy=(4.4, 1.35), xytext=(2.7, 1.35), arrowprops=arrow_kw)
ax.text(3.55, 1.9, 'soft probabilities', **tag_kw)
ax.text(3.55, 0.25,
        r'$p_i = \frac{\exp(z_i / T)}{\sum_j \exp(z_j / T)}$',
        ha='center', va='top', fontsize=8, fontfamily='serif', color='0.4')

# Student
ax.text(5.6, 1.35, 'Student\nNetwork', **label_kw, bbox=box_kw)
ax.text(5.6, 0.25, 'small neural net', **sub_kw)

# Arrow + output
ax.annotate('', xy=(7.8, 1.35), xytext=(6.8, 1.35), arrowprops=arrow_kw)
ax.text(8.8, 1.35, 'Neural\nClassifier', **label_kw, bbox=box_kw)
ax.text(8.8, 0.25, 'opaque weights', **sub_kw)

# Span label
ax.plot([0.4, 9.8], [2.55, 2.55], color='0.7', lw=0.6)
ax.text(5.1, 2.65, 'neural  \u2192  neural', ha='center', va='bottom',
        fontsize=7.5, fontfamily='serif', color='0.5')

# ════════════════════════════════════════
# Row 1 — NtRED (Ours)
# ════════════════════════════════════════
ax = axes[1]

ax.text(0.15, 2.75,
        '(b)  Neural-to-Rule Ensemble Distillation  (NtRED, ours)',
        ha='left', va='top', fontsize=10, fontfamily='serif',
        fontstyle='italic', color='0.25')

# Teacher ensemble — stacked shadow effect
for dx, dy, fc, ec, al in [(0.12, 0.12, '0.95', '0.55', 0.35),
                             (0.06, 0.06, '0.95', '0.55', 0.35),
                             (0, 0, 'white', 'black', 1.0)]:
    bkw = dict(boxstyle='round,pad=0.45', facecolor=fc,
               edgecolor=ec, linewidth=1.2)
    ax.text(1.5 + dx, 1.35 + dy, 'LLM\nTeacher', **label_kw,
            bbox=bkw, alpha=al)
ax.text(1.5, 0.15, '\u00d73 providers', **sub_kw)

# Arrow + knowledge label
ax.annotate('', xy=(4.4, 1.35), xytext=(2.7, 1.35), arrowprops=arrow_kw)
ax.text(3.55, 1.9, 'dark knowledge', **tag_kw)
ax.text(3.55, 0.15, 'LLM-TP \u2229 Rule-FN\npatterns', **sub_kw)

# Student
ax.text(5.6, 1.35, 'Pattern\nMining', **label_kw, bbox=box_kw)
ax.text(5.6, 0.15, 'human-in-the-loop', **sub_kw)

# Arrow + output
ax.annotate('', xy=(7.8, 1.35), xytext=(6.8, 1.35), arrowprops=arrow_kw)
ax.text(8.8, 1.35, 'Symbolic\nRules', **label_kw, bbox=box_kw)
ax.text(8.8, 0.15, 'interpretable,\ndeterministic', **sub_kw)

# Span label
ax.plot([0.4, 9.8], [2.55, 2.55], color='0.7', lw=0.6)
ax.text(5.1, 2.65, 'neural  \u2192  symbolic', ha='center', va='bottom',
        fontsize=7.5, fontfamily='serif', color='0.5')

plt.tight_layout(h_pad=1.2)
plt.savefig('kd_vs_ntred.pdf', bbox_inches='tight', dpi=300)
plt.savefig('kd_vs_ntred.png', bbox_inches='tight', dpi=300)
print('Saved kd_vs_ntred.pdf and kd_vs_ntred.png')
