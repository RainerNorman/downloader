import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk


CANVAS = "#F1F1F3"
SURFACE = "#FFFFFF"
INK = "#19191C"
MUTED = "#57575E"
BORDER = "#DDDDDF"
FIELD = "#FAFAFB"
FIELD_BORDER = "#909097"
RAIL = "#18181A"
RAIL_TEXT = "#E7E7EB"
RAIL_MUTED = "#A8A8B0"
ACCENT = "#B82031"
SELECTION = "#DEDEE5"
FONT = "Segoe UI"
DISPLAY_FONT = "Segoe UI Variable Display"


def configure_theme(root):
    root.configure(background=CANVAS)
    root.option_add("*TCombobox*Listbox.font", (FONT, 11))
    root.option_add("*TCombobox*Listbox.background", SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", INK)
    root.option_add("*TCombobox*Listbox.selectBackground", SELECTION)
    root.option_add("*TCombobox*Listbox.selectForeground", INK)
    style = ttk.Style(root)
    style.theme_use("clam")
    root.theme_images = []
    style.configure(".", font=(FONT, 11), background=SURFACE, foreground=INK)
    style.configure("Workspace.TFrame", background=CANVAS)
    style.configure("Rail.TFrame", background=RAIL)
    style.configure("Brand.TLabel", background=RAIL, foreground=SURFACE, font=(FONT, 14, "bold"))
    style.configure("RailTitle.TLabel", background=RAIL, foreground=RAIL_MUTED, font=(FONT, 9, "bold"))
    style.configure("Heading.TLabel", background=CANVAS, font=(DISPLAY_FONT, 30, "bold"))
    style.configure("Intro.TLabel", background=CANVAS, foreground=MUTED)
    style.configure("FieldLabel.TLabel", font=(FONT, 10, "bold"))
    style.configure("Help.TLabel", foreground=MUTED, font=(FONT, 10))
    style.configure("Status.TLabel", background=CANVAS, foreground=MUTED, font=(FONT, 10))
    style.configure("Percent.TLabel", background=CANVAS, foreground=INK, font=(FONT, 10, "bold"))

    _surface(root, style, "Panel.surface", 40, 12, (SURFACE, BORDER))
    style.layout("Card.TFrame", [("Panel.surface", {"sticky": "nswe"})])

    _surface(root, style, "Navigation.surface", 36, 7, (RAIL, RAIL), [
        ("selected focus", "#36363B", "#BEBEC6"),
        ("focus", "#29292D", "#BEBEC6"),
        ("selected", "#36363B", "#4F4F55"),
        ("active", "#29292D", "#29292D"),
    ], mark_selection=True)
    style.layout("Source.TRadiobutton", _layout("Navigation.surface", "Radiobutton"))
    style.configure("Source.TRadiobutton", padding=(14, 9), background=RAIL, foreground=RAIL_TEXT)
    style.map("Source.TRadiobutton", foreground=[("selected", SURFACE), ("active", SURFACE)])

    _surface(root, style, "Secondary.surface", 36, 7, (SURFACE, FIELD_BORDER), [
        ("disabled", "#F2F2F3", BORDER),
        ("focus", FIELD, INK),
        ("pressed", "#E5E5E9", FIELD_BORDER),
        ("active", "#F0F0F2", FIELD_BORDER),
    ])
    style.layout("TButton", _layout("Secondary.surface", "Button"))
    style.configure("TButton", padding=(14, 9), foreground=INK)
    style.map("TButton", foreground=[("disabled", MUTED)])

    _surface(root, style, "Primary.surface", 40, 8, (ACCENT, ACCENT), [
        ("disabled", "#5B5B63", "#5B5B63"),
        ("focus", ACCENT, "#23040A"),
        ("pressed", "#821422", "#821422"),
        ("active", "#A51828", "#A51828"),
    ])
    style.layout("Primary.TButton", _layout("Primary.surface", "Button"))
    style.configure("Primary.TButton", padding=(16, 10), foreground=SURFACE,
                    font=(FONT, 11, "bold"))

    _surface(root, style, "Input.surface", 36, 7, (FIELD, FIELD_BORDER), [
        ("focus", SURFACE, INK),
    ])
    style.layout("TEntry", [("Input.surface", {"sticky": "nswe", "children": [
        ("Entry.padding", {"sticky": "nswe", "children": [
            ("Entry.textarea", {"sticky": "nswe"}),
        ]}),
    ]})])
    _combobox_arrow(root, style)
    style.layout("TCombobox", [("Input.surface", {"sticky": "nswe", "children": [
        ("CleanCombobox.downarrow", {"side": "right", "sticky": ""}),
        ("Combobox.padding", {"sticky": "nswe", "children": [
            ("Combobox.textarea", {"sticky": "nswe"}),
        ]}),
    ]})])
    for field_style in ("TEntry", "TCombobox"):
        style.configure(field_style, fieldbackground=FIELD, background=FIELD,
                        padding=(12, 9), insertcolor=INK,
                        selectbackground=SELECTION, selectforeground=INK)
        style.map(field_style, fieldbackground=[("!disabled", FIELD)],
                  foreground=[("readonly", INK)])

    _surface(root, style, "Choice.surface", 34, 7, (SURFACE, FIELD_BORDER), [
        ("selected focus", INK, "#828289"),
        ("focus", FIELD, INK),
        ("selected", INK, INK),
        ("active", "#F0F0F2", FIELD_BORDER),
    ])
    style.layout("Choice.TRadiobutton", _layout("Choice.surface", "Radiobutton"))
    style.configure("Choice.TRadiobutton", padding=(12, 9), foreground=INK)
    style.map("Choice.TRadiobutton", foreground=[("selected", SURFACE)])


def _layout(surface, widget):
    return [(surface, {"sticky": "nswe", "children": [
        (f"{widget}.padding", {"sticky": "nswe", "children": [(f"{widget}.label", {"sticky": "nswe"})]}),
    ]})]


def _surface(root, style, name, size, radius, default, states=(), *, mark_selection=False):
    def render(fill, outline, state=""):
        layer = Image.new("RGBA", (size * 4, size * 4))
        draw = ImageDraw.Draw(layer)
        state_flags = state.split()
        draw.rounded_rectangle((0, 0, size * 4 - 1, size * 4 - 1), radius=radius * 4,
                               fill=fill, outline=outline, width=8 if "focus" in state_flags else 4)
        if mark_selection and "selected" in state_flags:
            draw.rectangle((16, 10, 23, size * 4 - 11), fill=RAIL_TEXT)
        photo = ImageTk.PhotoImage(layer.resize((size, size), Image.Resampling.LANCZOS),
                                   master=root)
        root.theme_images.append(photo)
        return photo

    images = [(state, render(fill, outline, state)) for state, fill, outline in states]
    style.element_create(name, "image", render(*default), *images,
                         border=radius + 1, padding=0, sticky="nswe")


def _combobox_arrow(root, style):
    layer = Image.new("RGBA", (112, 72))
    ImageDraw.Draw(layer).line([(30, 29), (47, 45), (64, 29)], fill=MUTED, width=6, joint="curve")
    photo = ImageTk.PhotoImage(layer.resize((28, 18), Image.Resampling.LANCZOS), master=root)
    root.theme_images.append(photo)
    style.element_create("CleanCombobox.downarrow", "image", photo, sticky="")


class ProgressTrack(tk.Canvas):
    def __init__(self, parent, variable):
        super().__init__(parent, width=1, height=8, background=CANVAS,
                         borderwidth=0, highlightthickness=0)
        self.variable = variable
        self.track = self.create_line(0, 0, 0, 0, width=4, fill="#D9D9DF", capstyle="round")
        self.fill = self.create_line(0, 0, 0, 0, width=4, fill=INK, capstyle="round")
        self.bind("<Configure>", self._update)
        self.trace = variable.trace_add("write", self._update)
        self.bind("<Destroy>", lambda _: variable.trace_remove("write", self.trace))

    def _update(self, *_args):
        width = max(6, self.winfo_width())
        fraction = min(1, max(0, self.variable.get() / 100))
        self.coords(self.track, 3, 4, width - 3, 4)
        self.coords(self.fill, 3, 4, 3 + (width - 6) * fraction, 4)
        self.itemconfigure(self.fill, state="normal" if fraction else "hidden")


def make_icons(root):
    with Image.open(Path(__file__).with_name("downloader.ico")) as ico:
        brand = Image.new("RGBA", (39, 30))
        brand.paste(ico.convert("RGBA").resize((30, 30), Image.Resampling.LANCZOS))

    strokes = {
        "youtube": [[(3, 4), (17, 4), (17, 16), (3, 16), (3, 4)],
                    [(8, 7), (13, 10), (8, 13), (8, 7)]],
        "telegram": [[(2, 9), (18, 3), (14, 17), (10, 13), (2, 9)], [(10, 13), (15, 6)]],
        "sketchfab": [[(10, 2), (17, 6), (17, 14), (10, 18), (3, 14), (3, 6), (10, 2)],
                      [(3, 6), (10, 10), (17, 6)], [(10, 10), (10, 18)]],
        "adfocus": [[(3, 12), (2, 10), (7, 5), (10, 5), (12, 7)],
                    [(8, 13), (10, 15), (13, 15), (18, 10), (17, 8)], [(7, 13), (13, 7)]],
        "scribd": [[(5, 2), (12, 2), (16, 6), (16, 18), (5, 18), (5, 2)],
                   [(12, 2), (12, 6), (16, 6)], [(8, 10), (13, 10)], [(8, 14), (13, 14)]],
        "pages_pdf": [[(7, 2), (17, 2), (17, 14)], [(3, 6), (13, 6), (13, 18), (3, 18), (3, 6)],
                      [(6, 10), (10, 10)], [(6, 14), (10, 14)]],
        "download": [[(10, 3), (10, 13)], [(6, 9), (10, 13), (14, 9)], [(3, 16), (17, 16)]],
        "external": [[(11, 3), (17, 3), (17, 9)], [(17, 3), (9, 11)],
                     [(8, 4), (4, 4), (4, 16), (16, 16), (16, 12)]],
    }
    icons = {"brand": ImageTk.PhotoImage(brand, master=root)}
    for name, paths in strokes.items():
        image = Image.new("RGBA", (80, 80))
        draw = ImageDraw.Draw(image)
        color = SURFACE if name in ("download", "external") else RAIL_TEXT
        for path in paths:
            draw.line([(x * 4, y * 4) for x, y in path], fill=color, width=6, joint="curve")
        padded = Image.new("RGBA", (27, 20))
        padded.paste(image.resize((20, 20), Image.Resampling.LANCZOS))
        icons[name] = ImageTk.PhotoImage(padded, master=root)
    return icons
