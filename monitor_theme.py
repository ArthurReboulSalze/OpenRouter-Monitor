"""Small vector-style UI icons for the supplied dark and amber design."""

import math
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageDraw

BACKGROUND = "#0b0e10"
SURFACE = "#11161a"
SURFACE_RAISED = "#171d22"
BORDER = "#354047"
MUTED = "#9aa5ae"
TEXT = "#eef1f4"
AMBER = "#ff9b21"
GOLD = "#ffd66b"
GREEN = "#22d77c"


class HoverTip:
    def __init__(self, widget, text=None):
        self.widget = widget
        self.pending = None
        self.window = None
        self.text = None
        if text:
            widget.bind('<Enter>', lambda event: self.schedule(text, event.x_root, event.y_root), add='+')
            widget.bind('<Leave>', lambda _event: self.hide(), add='+')
            widget.bind('<Button-1>', lambda _event: self.hide(), add='+')

    def schedule(self, text, x, y):
        if text == self.text:
            return
        self.hide()
        self.text = text
        self.pending = self.widget.after(650, lambda: self._show(text, x, y))

    def _show(self, text, x, y):
        self.pending = None
        self.window = tk.Toplevel(self.widget)
        self.window.overrideredirect(True)
        tk.Label(self.window, text=text, bg=SURFACE_RAISED, fg=TEXT, justify='left',
                 font=('Segoe UI', 10), wraplength=460, padx=12, pady=9,
                 highlightthickness=1, highlightbackground=BORDER).pack()
        self.window.update_idletasks()
        x = max(0, min(x + 14, self.widget.winfo_screenwidth() - self.window.winfo_width()))
        y = max(0, min(y + 20, self.widget.winfo_screenheight() - self.window.winfo_height()))
        self.window.geometry(f'+{x}+{y}')

    def hide(self):
        if self.pending:
            self.widget.after_cancel(self.pending)
            self.pending = None
        if self.window:
            self.window.destroy()
            self.window = None
        self.text = None


def make_icon(kind, size=28, color=AMBER):
    scale = 4
    image = Image.new("RGBA", (size * scale, size * scale))
    draw = ImageDraw.Draw(image)
    unit = size * scale / 32

    def line(points, width=2):
        draw.line([(x * unit, y * unit) for x, y in points], fill=color, width=round(width * unit), joint="curve")

    def ellipse(box, width=2, fill=None):
        draw.ellipse([v * unit for v in box], fill=fill, outline=color, width=round(width * unit))

    if kind == "settings":
        points = []
        for index in range(48):
            angle = index * math.tau / 48
            radius = 13 if index % 6 in (1, 2, 3, 4) else 10
            points.append(((16 + radius * math.cos(angle)) * unit, (16 + radius * math.sin(angle)) * unit))
        draw.polygon(points, fill=color)
        draw.ellipse([12 * unit, 12 * unit, 20 * unit, 20 * unit], fill=SURFACE)
    elif kind == "trash":
        line([(8, 9), (10, 28), (23, 28), (25, 9)])
        line([(6, 7), (27, 7)])
        line([(12, 7), (12, 3), (21, 3), (21, 7)])
        for x in (13, 17, 21):
            line([(x, 13), (x, 23)], 1.5)
    elif kind == "refresh":
        draw.arc([4 * unit, 4 * unit, 28 * unit, 28 * unit], start=40, end=320, fill=color, width=round(3 * unit))
        draw.polygon([(26 * unit, 3 * unit), (26 * unit, 13 * unit), (17 * unit, 10 * unit)], fill=color)
    elif kind == "list":
        for y in (7, 16, 25):
            ellipse((3, y - 2, 7, y + 2), fill=color)
            line([(12, y), (29, y)])
    elif kind == "cube":
        line([(16, 3), (28, 9), (28, 23), (16, 29), (4, 23), (4, 9), (16, 3)])
        line([(4, 9), (16, 15), (28, 9)])
        line([(16, 15), (16, 29)])
    elif kind == "credits":
        ellipse((3, 3, 22, 11), fill=color)
        for y in (10, 15, 20):
            draw.arc([3 * unit, (y - 4) * unit, 22 * unit, (y + 4) * unit], 0, 180, fill=color, width=round(2 * unit))
        line([(3, 7), (3, 20)], 2)
        ellipse((16, 19, 30, 27), fill=color)
    elif kind == "ring":
        ellipse((4, 4, 28, 28), 4)
    elif kind == "search":
        ellipse((3, 3, 22, 22), 2.5)
        line([(21, 21), (29, 29)], 3)
    elif kind == "key":
        ellipse((3, 3, 17, 17), 3)
        line([(15, 15), (28, 28), (30, 24)], 3)
        line([(21, 21), (25, 17)], 3)
    return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))
