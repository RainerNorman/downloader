import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageDraw, ImageFilter, ImageTk


CANVAS = "#EEF4F6"
SURFACE = "#FFFFFF"
INK = "#18313B"
MUTED = "#49636F"
BORDER = "#D7E4E8"
FIELD = "#F5F9FA"
RAIL = "#C6F1F4"
ACCENT = "#0A7678"
SELECTION = "#CAEDEB"
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
    style.configure("Rail.TFrame", background=CANVAS)
    style.configure("Card.TFrame", background=CANVAS)
    style.configure("Brand.TLabel", background=RAIL, foreground=INK, font=(FONT, 14, "bold"))
    style.configure("RailTitle.TLabel", background=RAIL, foreground=MUTED, font=(FONT, 9, "bold"))
    style.configure("Heading.TLabel", background=CANVAS, font=(DISPLAY_FONT, 27, "bold"))
    style.configure("Intro.TLabel", background=CANVAS, foreground=MUTED)
    style.configure("FieldLabel.TLabel", font=(FONT, 10, "bold"))
    style.configure("Help.TLabel", foreground=MUTED, font=(FONT, 10))
    style.configure("Percent.TLabel", foreground=ACCENT, font=(FONT, 10, "bold"))

    _panel_surface(root, style)
    style.layout("Card.TFrame", [("Panel.surface", {"sticky": "nswe"})])
    _surface(root, style, "Rail.surface", 44, 16, (RAIL, "#AEE3E8"))
    style.layout("Rail.TFrame", [("Rail.surface", {"sticky": "nswe"})])

    _surface(root, style, "Navigation.surface", 36, 9, (RAIL, RAIL), [
        ("focus", "#E2FAFC", "#318C93"),
        ("selected", "#F3FDFD", "#A4DFE3"),
        ("active", "#DDF7F9", "#B9E8EC"),
    ], backdrop=RAIL)
    style.layout("Source.TRadiobutton", _layout("Navigation.surface", "Radiobutton"))
    style.configure("Source.TRadiobutton", padding=(10, 8), background=RAIL, foreground=MUTED)
    style.map("Source.TRadiobutton", foreground=[("selected", INK), ("active", INK)])

    _surface(root, style, "Secondary.surface", 40, 9, ("#EDF6F7", "#D6E7EA"), [
        ("disabled", "#F0F3F4", "#DDE7EA"),
        ("pressed", "#D5EBEE", "#A8D4DA"),
        ("focus", "#ECF8FA", "#45999C"),
        ("active", "#E1F2F4", "#BDDDE2"),
    ])
    style.layout("TButton", _layout("Secondary.surface", "Button"))
    style.configure("TButton", padding=(13, 7), foreground=INK)
    style.map("TButton", foreground=[("disabled", "#677D87")])

    _surface(root, style, "Primary.surface", 44, 11, ("#87E7E4", "#64CFCE"), [
        ("disabled", "#E3F0F1", "#D4E5E7"),
        ("pressed", "#60CECA", "#48BAB7"),
        ("focus", "#87E7E4", "#27777D"),
        ("active", "#A2F0EC", "#69D2D1"),
    ])
    style.layout("Primary.TButton", _layout("Primary.surface", "Button"))
    style.configure("Primary.TButton", padding=(15, 8), foreground="#123B44",
                    font=(FONT, 11, "bold"))
    style.map("Primary.TButton", foreground=[("disabled", MUTED)])

    _surface(root, style, "Input.surface", 40, 9, (FIELD, BORDER), [
        ("focus", FIELD, "#469FA4"),
    ])
    _surface(root, style, "Input.focusSurface", 40, 9, (FIELD, "#469FA4"))
    style.layout("Input.TFrame", [("Input.surface", {"sticky": "nswe"})])
    style.layout("InputFocus.TFrame", [("Input.focusSurface", {"sticky": "nswe"})])
    style.layout("TEntry", [("Input.surface", {"sticky": "nswe", "children": [
        ("Entry.padding", {"sticky": "nswe", "children": [
            ("Entry.textarea", {"sticky": "nswe"}),
        ]}),
    ]})])
    style.layout("TCombobox", [("Input.surface", {"sticky": "nswe", "children": [
        ("Combobox.downarrow", {"side": "right", "sticky": "ns"}),
        ("Combobox.padding", {"sticky": "nswe", "children": [
            ("Combobox.textarea", {"sticky": "nswe"}),
        ]}),
    ]})])
    for field_style in ("TEntry", "TCombobox"):
        style.configure(field_style, fieldbackground=FIELD, background=FIELD,
                        padding=(11, 7), insertcolor=INK,
                        selectbackground=SELECTION, selectforeground=INK)
        style.map(field_style, fieldbackground=[("!disabled", FIELD)],
                  foreground=[("readonly", INK)])
    style.configure("TCombobox", arrowcolor=MUTED, arrowsize=13, bordercolor=FIELD,
                    lightcolor=FIELD, darkcolor=FIELD)

    _surface(root, style, "Choice.surface", 34, 8, ("#F2F7F8", "#DBE7EA"), [
        ("focus", "#E7F6F7", "#40989C"),
        ("selected", "#DDF6F5", "#9CD8D8"),
        ("active", "#E9F4F6", "#C9E2E6"),
    ])
    _format_indicator(root, style)
    style.layout("Choice.TRadiobutton", _layout("Choice.surface", "Radiobutton"))
    style.layout("Choice.TCheckbutton", _layout("Choice.surface", "Checkbutton", "Format.indicator"))
    for name in ("Choice.TRadiobutton", "Choice.TCheckbutton"):
        style.configure(name, padding=(12, 6), foreground=MUTED)
        style.map(name, foreground=[("selected", ACCENT), ("active", INK)])

    style.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns",
        "children": [("Vertical.Scrollbar.thumb", {"sticky": "nswe"})]})])
    style.configure("Vertical.TScrollbar", background="#ACCDD1", troughcolor=FIELD, width=7,
                    bordercolor=FIELD, lightcolor="#ACCDD1", darkcolor="#ACCDD1")


def _layout(surface, widget, indicator=None):
    children = [(f"{widget}.label", {"sticky": "nswe"})]
    if indicator:
        children.insert(0, (indicator, {"side": "left", "sticky": ""}))
    return [(surface, {"sticky": "nswe", "children": [
        (f"{widget}.padding", {"sticky": "nswe", "children": children}),
    ]})]


def _surface(root, style, name, size, radius, default, states=(), *, backdrop=None):
    def render(fill, outline):
        layer = Image.new("RGBA", (size * 4, size * 4), backdrop)
        ImageDraw.Draw(layer).rounded_rectangle((0, 0, size * 4 - 1, size * 4 - 1),
                                                radius=radius * 4, fill=fill, outline=outline, width=4)
        photo = ImageTk.PhotoImage(layer.resize((size, size), Image.Resampling.LANCZOS),
                                   master=root)
        root.theme_images.append(photo)
        return photo

    images = [(state, render(fill, outline)) for state, fill, outline in states]
    style.element_create(name, "image", render(*default), *images,
                         border=radius + 1, padding=0, sticky="nswe")


def _panel_surface(root, style):
    layer = Image.new("RGBA", (192, 192))
    ImageDraw.Draw(layer).rounded_rectangle((8, 13, 183, 182), radius=57, fill=(41, 81, 97, 35))
    layer = layer.filter(ImageFilter.GaussianBlur(6))
    ImageDraw.Draw(layer).rounded_rectangle((8, 4, 183, 175), radius=56,
                                            fill=SURFACE, outline=BORDER, width=4)
    photo = ImageTk.PhotoImage(layer.resize((48, 48), Image.Resampling.LANCZOS), master=root)
    root.theme_images.append(photo)
    style.element_create("Panel.surface", "image", photo, border=18, padding=0, sticky="nswe")


def _format_indicator(root, style):
    photos = []
    for selected in (False, True):
        layer = Image.new("RGBA", (88, 56))
        draw = ImageDraw.Draw(layer)
        draw.rounded_rectangle((1, 1, 53, 53), radius=11, outline=ACCENT if selected else "#7896A1",
                               fill=ACCENT if selected else "#F7FBFC", width=4)
        if selected:
            draw.line([(14, 28), (23, 37), (40, 19)], fill=SURFACE, width=6, joint="curve")
        photos.append(ImageTk.PhotoImage(layer.resize((22, 14), Image.Resampling.LANCZOS),
                                        master=root))
    root.theme_images.extend(photos)
    style.element_create("Format.indicator", "image", photos[0], ("selected", photos[1]))


class ProgressTrack(tk.Canvas):
    def __init__(self, parent, variable):
        super().__init__(parent, width=1, height=8, background=SURFACE,
                         borderwidth=0, highlightthickness=0)
        self.variable = variable
        self.track = self.create_line(0, 0, 0, 0, width=5, fill="#E0EDEF", capstyle="round")
        self.fill = self.create_line(0, 0, 0, 0, width=5, fill=ACCENT, capstyle="round")
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
        brand = Image.new("RGBA", (47, 38))
        brand.paste(ico.convert("RGBA").resize((38, 38), Image.Resampling.LANCZOS))

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
    }
    icons = {"brand": ImageTk.PhotoImage(brand, master=root)}
    for name, paths in strokes.items():
        image = Image.new("RGBA", (80, 80))
        draw = ImageDraw.Draw(image)
        color = "#18515B" if name == "download" else "#2D7480"
        for path in paths:
            draw.line([(x * 4, y * 4) for x, y in path], fill=color, width=6, joint="curve")
        padded = Image.new("RGBA", (27, 20))
        padded.paste(image.resize((20, 20), Image.Resampling.LANCZOS))
        icons[name] = ImageTk.PhotoImage(padded, master=root)
    return icons
