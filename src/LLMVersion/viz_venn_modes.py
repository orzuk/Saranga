"""Venn diagrams for Distillation Mode vs Discovery Mode."""

import matplotlib.pyplot as plt
from matplotlib_venn import venn3

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))


def style_venn(v, center_label, ax, title):
    """Style a venn3 diagram: white regions, black triple intersection."""
    # Force all patches fully opaque white first
    for patch_id in ('100', '010', '001', '110', '101', '011', '111'):
        patch = v.get_patch_by_id(patch_id)
        if patch:
            patch.set_facecolor('white')
            patch.set_edgecolor('black')
            patch.set_linewidth(1.5)
            patch.set_alpha(1.0)

    # Black triple intersection
    triple = v.get_patch_by_id('111')
    if triple:
        triple.set_facecolor('black')
        triple.set_alpha(1.0)

    # Clear all subset number labels
    for patch_id in ('100', '010', '001', '110', '101', '011', '111'):
        label = v.get_label_by_id(patch_id)
        if label:
            label.set_text('')

    # Center label in white on black
    lbl = v.get_label_by_id('111')
    lbl.set_text(center_label)
    lbl.set_color('white')
    lbl.set_fontsize(9)
    lbl.set_fontweight('bold')

    # Style set labels
    for sl in v.set_labels:
        if sl:
            sl.set_fontsize(11)
            sl.set_fontweight('bold')

    ax.set_title(title, fontsize=14, fontweight='bold', pad=15)


# --- Distillation Mode ---
v1 = venn3(
    subsets=(1, 1, 1, 1, 1, 1, 1),
    set_labels=('Gold Standard\nExists', 'Manual Parser\nFN', 'LLM TP'),
    ax=ax1,
)
style_venn(v1, 'Dark\nKnowledge', ax1, 'Distillation Mode')

# --- Discovery Mode ---
v2 = venn3(
    subsets=(1, 1, 1, 1, 1, 1, 1),
    set_labels=('LLM$_1$ Found\nStructure', 'LLM$_2$ Found\nStructure', 'Manual Parser\nMissed'),
    ax=ax2,
)
style_venn(v2, 'Candidate\nRule', ax2, 'Discovery Mode')

plt.tight_layout()
plt.savefig('venn_modes.pdf', bbox_inches='tight', dpi=300)
plt.savefig('venn_modes.png', bbox_inches='tight', dpi=300)
print("Saved venn_modes.pdf and venn_modes.png")
