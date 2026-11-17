"""Shared style for PALET figures (book chapter: serif type, muted palette).

Every figure is exported as vector PDF and as PNG at 600 dpi.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib as mpl  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

PALETTE = {
    "primary": "#2C5F8A",      # dark blue
    "secondary": "#A9C4DE",    # light blue
    "accent": "#C8553D",       # brick red, for emphasis only
    "bar": "#6E6E6E",          # grey bars of the descriptive figures (by question, by year)
    "bar_light": "#C2C2C2",    # second category or incomplete year in those figures
    "ink": "#222222",
    "muted": "#6B6B6B",
    "box_main": "#EEF3F8",
    "box_side": "#F6F6F6",
    "box_final": "#E3EFE3",
}

FIG_WIDTH = 6.69               # inches: full text width of an A4 page
ASPECT_RATIO = 1.618


def apply_style() -> None:
    mpl.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "STIXGeneral", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 10,
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.8,
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "lines.linewidth": 1.5,
        "patch.linewidth": 0.8,
        "hatch.linewidth": 0.6,
        "figure.dpi": 150,
        "savefig.dpi": 600,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.05,
        "pdf.fonttype": 42,            # embed fonts as text, editable by the publisher
    })


def save(fig, path_without_extension) -> list[str]:
    """Export as PDF (vector) and PNG (600 dpi); returns the two paths."""
    paths = []
    for extension in ("pdf", "png"):
        path = f"{path_without_extension}.{extension}"
        fig.savefig(path, dpi=600 if extension == "png" else None)
        paths.append(path)
    plt.close(fig)
    return paths
