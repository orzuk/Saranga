"""
Minimal academic figure: NtRED pipeline overview.
Horizontal flow: Prompt Optimization → Evaluation → Distillation
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

fig, ax = plt.subplots(figsize=(10, 2.8))
ax.set_xlim(0, 10)
ax.set_ylim(0, 3)
ax.axis('off')

# Box style
box_kw = dict(
    boxstyle='round,pad=0.4',
    facecolor='white',
    edgecolor='black',
    linewidth=1.2,
)

# Phase positions (x_center, y_center)
phases = [
    (1.5, 1.5, 'Prompt\nOptimization'),
    (5.0, 1.5, 'Multi-Provider\nEvaluation'),
    (8.5, 1.5, 'Rule\nDistillation'),
]

# Draw boxes
for x, y, label in phases:
    ax.text(x, y, label, ha='center', va='center',
            fontsize=11, fontfamily='serif',
            bbox=box_kw)

# Arrows between boxes
arrow_kw = dict(
    arrowstyle='->', color='black', lw=1.2,
    connectionstyle='arc3,rad=0',
)

ax.annotate('', xy=(3.6, 1.5), xytext=(2.7, 1.5), arrowprops=arrow_kw)
ax.annotate('', xy=(7.1, 1.5), xytext=(6.2, 1.5), arrowprops=arrow_kw)

# Subtle sub-labels below each box
sub_kw = dict(ha='center', va='top', fontsize=7.5, fontfamily='serif', color='0.35')
ax.text(1.5, 0.55, 'Meta-LLM rewrites\nextraction prompts', **sub_kw)
ax.text(5.0, 0.55, 'P / R / F1 per provider\nagainst gold standard', **sub_kw)
ax.text(8.5, 0.55, 'LLM-TP ∩ Rule-FN → \nnew regex rules', **sub_kw)

# Feedback arrow (distillation back to evaluation)
ax.annotate(
    '', xy=(6.2, 2.35), xytext=(7.1, 2.35),
    arrowprops=dict(arrowstyle='->', color='black', lw=0.8,
                    connectionstyle='arc3,rad=-0.3', linestyle='dashed'),
)
ax.text(6.65, 2.75, 'iterate', ha='center', va='center',
        fontsize=7.5, fontfamily='serif', fontstyle='italic', color='0.35')

plt.tight_layout()
plt.savefig('pipeline_figure.pdf', bbox_inches='tight', dpi=300)
plt.savefig('pipeline_figure.png', bbox_inches='tight', dpi=300)
print('Saved pipeline_figure.pdf and pipeline_figure.png')
