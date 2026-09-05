"""
Design system.

One place for every colour, typeface and measurement in the interface, so the
app looks like it was designed rather than assembled. Nothing here draws
anything — widgets ask for a token and get a value.

Colours are CustomTkinter (light, dark) pairs. Declaring both halves at the
point of definition is what keeps the dark theme an equal citizen instead of
an inverted afterthought: there is no way to add a colour and forget one.

The palette is warm paper and ink with a single deep accent — restrained on
purpose. Gold appears only as a hairline or a small mark, never as a fill;
used sparingly it reads as considered, used broadly it reads as costume.
"""

import platform

import customtkinter as ctk

_IS_MAC = platform.system() == "Darwin"
_IS_WIN = platform.system() == "Windows"


# ---------------------------------------------------------------------------
# Typefaces
# ---------------------------------------------------------------------------
# A serif for the wordmark and page titles, a neutral sans for everything the
# user actually operates, a mono for their text. The mix is what stops a
# utility looking like a form.
if _IS_MAC:
    SERIF = "Iowan Old Style"
    SANS = "SF Pro Text"
    MONO = "Menlo"
elif _IS_WIN:
    SERIF = "Georgia"
    SANS = "Segoe UI"
    MONO = "Consolas"
else:
    SERIF = "DejaVu Serif"
    SANS = "DejaVu Sans"
    MONO = "DejaVu Sans Mono"

# role -> (family, size, weight, slant)
_TYPE = {
    "wordmark":   (SERIF, 21, "bold",   "roman"),
    "display":    (SERIF, 28, "normal", "roman"),
    "page_title": (SERIF, 22, "normal", "roman"),
    "card_title": (SANS,  14, "bold",   "roman"),
    "subtitle":   (SANS,  12, "normal", "roman"),
    "body":       (SANS,  13, "normal", "roman"),
    "body_bold":  (SANS,  13, "bold",   "roman"),
    "small":      (SANS,  11, "normal", "roman"),
    "small_bold": (SANS,  11, "bold",   "roman"),
    "micro":      (SANS,  10, "normal", "roman"),
    "eyebrow":    (SANS,  10, "bold",   "roman"),
    "button":     (SANS,  13, "normal", "roman"),
    "metric":     (SERIF, 26, "normal", "roman"),
    "metric_sm":  (SERIF, 18, "normal", "roman"),
    "mono":       (MONO,  12, "normal", "roman"),
    "mono_sm":    (MONO,  11, "normal", "roman"),
    "editor":     (MONO,  13, "normal", "roman"),
}

_font_cache = {}


def font(role):
    """A CTkFont for a named role. Requires a Tk root to already exist."""
    if role not in _font_cache:
        family, size, weight, slant = _TYPE[role]
        _font_cache[role] = ctk.CTkFont(family=family, size=size,
                                        weight=weight, slant=slant)
    return _font_cache[role]


def reset_fonts():
    """Drop cached fonts — needed if the Tk root is ever rebuilt."""
    _font_cache.clear()


# ---------------------------------------------------------------------------
# Neutrals — the paper and the ink
# ---------------------------------------------------------------------------
# (light, dark)
CANVAS       = ("#F3F1EC", "#0F1015")   # the desk the cards sit on
SURFACE      = ("#FFFFFF", "#171922")   # a card
SURFACE_ALT  = ("#FAF8F3", "#1C1F29")   # a well, an input, a nested panel
SURFACE_SUNK = ("#EFEDE7", "#101219")   # editor gutter, progress trough
BORDER       = ("#E4DFD5", "#2B2F3C")   # hairline
BORDER_STRONG = ("#D2CBBD", "#3A3F4F")

INK          = ("#15151C", "#EDEBE5")   # primary text
INK_2        = ("#565663", "#A6A9B6")   # secondary text
INK_3        = ("#8A8A97", "#71748A")   # captions, hints, disabled

# Semantic
OK      = ("#2C6A4F", "#5AA783")
WARN    = ("#8A6410", "#CCA044")
ERR     = ("#97292B", "#E0797B")
OK_SOFT   = ("#E8F1EC", "#16241E")
WARN_SOFT = ("#F6EFDD", "#241F13")
ERR_SOFT  = ("#F7E9E9", "#241618")


# ---------------------------------------------------------------------------
# Accents — five restrained choices, no neon
# ---------------------------------------------------------------------------
ACCENTS = {
    "Royal": {
        "accent":       ("#2B3A67", "#8095DC"),
        "accent_hover": ("#3A4C85", "#9AACE8"),
        "accent_soft":  ("#E9ECF6", "#1B2138"),
        "accent_ink":   ("#FFFFFF", "#0F1015"),
        "gold":         ("#9C7B3A", "#C9A461"),
    },
    "Graphite": {
        "accent":       ("#2E3138", "#9CA3B4"),
        "accent_hover": ("#43474F", "#B3BAC9"),
        "accent_soft":  ("#ECECEE", "#20232B"),
        "accent_ink":   ("#FFFFFF", "#0F1015"),
        "gold":         ("#8C7A50", "#BFAE84"),
    },
    "Emerald": {
        "accent":       ("#1F4D3D", "#63B294"),
        "accent_hover": ("#2C6551", "#7CC4A9"),
        "accent_soft":  ("#E7F0EC", "#152520"),
        "accent_ink":   ("#FFFFFF", "#0F1015"),
        "gold":         ("#947C3C", "#C4A765"),
    },
    "Burgundy": {
        "accent":       ("#5E2233", "#C4808F"),
        "accent_hover": ("#7A2F43", "#D296A3"),
        "accent_soft":  ("#F3E9EC", "#251519"),
        "accent_ink":   ("#FFFFFF", "#0F1015"),
        "gold":         ("#9A7A3C", "#CBA966"),
    },
    "Slate": {
        "accent":       ("#28454F", "#7FAAB9"),
        "accent_hover": ("#365C69", "#98BECB"),
        "accent_soft":  ("#E8EEF0", "#162227"),
        "accent_ink":   ("#FFFFFF", "#0F1015"),
        "gold":         ("#8E7A45", "#BFA76E"),
    },
}

DEFAULT_ACCENT = "Royal"

_active = dict(ACCENTS[DEFAULT_ACCENT])


def set_accent(name):
    """Switch the accent family. Widgets must be re-coloured by the caller."""
    global _active
    _active = dict(ACCENTS.get(name, ACCENTS[DEFAULT_ACCENT]))
    return _active


def accent(token="accent"):
    """One of: accent, accent_hover, accent_soft, accent_ink, gold."""
    return _active[token]


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------
# A 4pt rhythm. Using the scale instead of arbitrary numbers is most of what
# makes spacing look deliberate.
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 18, "xl": 26, "xxl": 38}

RADIUS_CARD = 12
RADIUS_CONTROL = 8
RADIUS_PILL = 999

RAIL_WIDTH = 236
INSPECTOR_WIDTH = 268
CARD_PAD = 22

HEIGHT_BUTTON = 36
HEIGHT_BUTTON_LG = 42
HEIGHT_INPUT = 34
HAIRLINE = 1


# ---------------------------------------------------------------------------
# Widget recipes — so a "secondary button" is one thing everywhere
# ---------------------------------------------------------------------------
def card_kwargs():
    return dict(fg_color=SURFACE, corner_radius=RADIUS_CARD,
                border_width=HAIRLINE, border_color=BORDER)


def well_kwargs():
    return dict(fg_color=SURFACE_ALT, corner_radius=RADIUS_CONTROL,
                border_width=HAIRLINE, border_color=BORDER)


def primary_button_kwargs():
    return dict(fg_color=accent("accent"), hover_color=accent("accent_hover"),
                text_color=accent("accent_ink"), corner_radius=RADIUS_CONTROL,
                height=HEIGHT_BUTTON, font=font("button"), border_width=0)


def secondary_button_kwargs():
    return dict(fg_color="transparent", hover_color=SURFACE_ALT,
                text_color=INK, corner_radius=RADIUS_CONTROL,
                height=HEIGHT_BUTTON, font=font("button"),
                border_width=HAIRLINE, border_color=BORDER_STRONG)


def ghost_button_kwargs():
    return dict(fg_color="transparent", hover_color=SURFACE_ALT,
                text_color=INK_2, corner_radius=RADIUS_CONTROL,
                height=HEIGHT_BUTTON, font=font("button"), border_width=0)


def quiet_button_kwargs():
    """A destructive or rarely-wanted action: present but not inviting."""
    return dict(fg_color="transparent", hover_color=ERR_SOFT,
                text_color=INK_3, corner_radius=RADIUS_CONTROL,
                height=HEIGHT_BUTTON, font=font("small"), border_width=0)


def entry_kwargs():
    return dict(fg_color=SURFACE_ALT, border_color=BORDER,
                border_width=HAIRLINE, corner_radius=RADIUS_CONTROL,
                text_color=INK, height=HEIGHT_INPUT, font=font("body"))


def switch_kwargs():
    return dict(progress_color=accent("accent"), button_color=SURFACE,
                button_hover_color=SURFACE, fg_color=BORDER_STRONG,
                text_color=INK, font=font("body"))


def slider_kwargs():
    return dict(progress_color=accent("accent"), button_color=accent("accent"),
                button_hover_color=accent("accent_hover"), fg_color=BORDER,
                height=16)


def segmented_kwargs():
    return dict(fg_color=SURFACE_ALT, selected_color=accent("accent"),
                selected_hover_color=accent("accent_hover"),
                unselected_color=SURFACE_ALT, unselected_hover_color=BORDER,
                text_color=INK, text_color_disabled=INK_3,
                corner_radius=RADIUS_CONTROL, border_width=2,
                font=font("body"))


def option_menu_kwargs():
    return dict(fg_color=SURFACE_ALT, button_color=SURFACE_ALT,
                button_hover_color=BORDER, text_color=INK,
                dropdown_fg_color=SURFACE, dropdown_text_color=INK,
                dropdown_hover_color=accent("accent_soft"),
                corner_radius=RADIUS_CONTROL, height=HEIGHT_INPUT,
                font=font("body"), dropdown_font=font("body"))
