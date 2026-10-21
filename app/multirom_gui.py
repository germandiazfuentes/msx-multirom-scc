"""
MSX MultiROM - interfaz grafica.

Ejecutar:  python multirom_gui.py
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

import analyze
import multirom as mr

APP_NAME = "MSX MultiROM"
APP_VERSION = "1.1"
APP_AUTHOR = "Germán Díaz / MSX Calamar"
APP_WEB = "https://msxcalamar.com"
ICON_ICO = os.path.join(mr.APP_DIR, "data", "calamar.ico")
ICON_PNG = os.path.join(mr.APP_DIR, "data", "calamar.png")
CONFIG = os.path.join(os.path.expanduser("~"), ".msx_multirom.json")
# Maquinas con BIOS real para el analisis en varias maquinas (si openMSX tiene sus ROMs)
MULTI_MACHINES = ["Sony_HB-75P", "Sony_HB-F1XD", "Panasonic_FS-A1WX", "Panasonic_FS-A1GT"]
PALETTE = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2", "#edc948",
           "#b07aa1", "#ff9da7", "#9c755f", "#86bcb6", "#d37295", "#a0cbe8"]
MAPPER_CHOICES = [mr.PLAIN, mr.KONAMI4, mr.KONAMI5, mr.ASCII8, mr.ASCII16, mr.GKONAMI, mr.GENERIC16]


def load_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    try:
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1)
    except OSError:
        pass


def find_openmsx():
    cands = [os.path.join(mr.APP_DIR, "..", "tools", "openmsx", "openmsx.exe"),
             os.path.join(mr.APP_DIR, "openmsx", "openmsx.exe"),
             r"C:\Program Files\openMSX\openmsx.exe"]
    if getattr(sys, "frozen", False):   # .exe: buscar junto al ejecutable
        exe_dir = os.path.dirname(sys.executable)
        cands[:0] = [os.path.join(exe_dir, "openmsx", "openmsx.exe"),
                     os.path.join(exe_dir, "..", "tools", "openmsx", "openmsx.exe")]
    for c in cands:
        if os.path.exists(c):
            return os.path.normpath(c)
    return ""


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MSX MultiROM - Konami5 / Yamanooto")
        try:
            self.iconbitmap(default=ICON_ICO)
        except tk.TclError:
            pass
        self.geometry("980x680")
        self.minsize(820, 560)
        self.cfg = load_config()
        self.games = []
        self.bases = []
        self.cart = tk.StringVar(value=self.cfg.get("cart", "k5"))
        self.size = tk.StringVar()
        self.menu_title = tk.StringVar(value=self.cfg.get("title", "MSX MULTIROM"))
        self.openmsx = self.cfg.get("openmsx") or find_openmsx()
        self.machine = tk.StringVar(value=self.cfg.get("machine", "C-BIOS_MSX2"))
        self.multi = tk.BooleanVar(value=self.cfg.get("multi", False))
        self._build_ui()
        self._cart_changed(initial=True)
        self.protocol("WM_DELETE_WINDOW", self._quit)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Treeview", rowheight=22)

        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Cartucho:").pack(side="left")
        self.cart_cb = ttk.Combobox(top, state="readonly", width=28,
                                    values=[mr.CARTS[k]["name"] for k in mr.CARTS])
        self.cart_cb.pack(side="left", padx=(4, 14))
        self.cart_cb.bind("<<ComboboxSelected>>", lambda e: self._cart_changed())
        ttk.Label(top, text="Tamaño:").pack(side="left")
        self.size_cb = ttk.Combobox(top, state="readonly", width=8, textvariable=self.size)
        self.size_cb.pack(side="left", padx=(4, 14))
        self.size_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Label(top, text="Título del menú:").pack(side="left")
        ttk.Entry(top, textvariable=self.menu_title, width=32).pack(side="left", padx=4)
        ttk.Button(top, text="Acerca de...", command=self.about).pack(side="right")

        # Lista de juegos + botones
        mid = ttk.Frame(self, padding=(10, 0))
        mid.pack(fill="both", expand=True)
        cols = ("n", "title", "mapper", "size", "bank", "stubs", "an", "status")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="extended")
        for c, txt, w, anchor in (("n", "#", 40, "e"), ("title", "Título (doble clic para editar)", 270, "w"),
                                  ("mapper", "Mapper", 140, "w"), ("size", "Tamaño", 70, "e"),
                                  ("bank", "Banco", 55, "e"), ("stubs", "Rutinas", 95, "w"),
                                  ("an", "Análisis", 70, "w"), ("status", "Estado", 280, "w")):
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor=anchor, stretch=c in ("title", "status"))
        self.tree.tag_configure("error", foreground="#c00000")
        self.tree.tag_configure("warn", foreground="#a06000")
        self.tree.tag_configure("nofit", background="#ffd8d8")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Double-1>", self._on_double)
        self.tree.bind("<Delete>", lambda e: self.remove())

        btns = ttk.Frame(mid, padding=(8, 0, 0, 0))
        btns.pack(side="right", fill="y")
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        for txt, cmd in (("Añadir ROMs...", self.add_files), ("Añadir carpeta...", self.add_folder),
                         ("Quitar", self.remove), (None, None),
                         ("Subir", lambda: self.move(-1)), ("Bajar", lambda: self.move(1)),
                         ("Ordenar A-Z", self.sort), (None, None),
                         ("Abrir lista...", self.load_list), ("Guardar lista...", self.save_list),
                         (None, None),
                         ("Analizar en openMSX", self.analyze_auto),
                         ("Analizar jugando...", self.analyze_play),
                         ("Borrar análisis", self.forget_analysis)):
            if txt is None:
                ttk.Separator(btns).pack(fill="x", pady=6)
            else:
                ttk.Button(btns, text=txt, command=cmd).pack(pady=2, fill="x")

        # Barra de ocupacion
        cap = ttk.Frame(self, padding=(10, 8, 10, 0))
        cap.pack(fill="x")
        self.cap_label = ttk.Label(cap, text="", font=("Segoe UI", 10, "bold"))
        self.cap_label.pack(anchor="w")
        self.canvas = tk.Canvas(cap, height=34, bg="#202020", highlightthickness=1,
                                highlightbackground="#808080")
        self.canvas.pack(fill="x", pady=(4, 0))
        self.canvas.bind("<Configure>", lambda e: self._draw_bar())
        self.canvas.bind("<Motion>", self._bar_hover)
        self.bar_tip = ttk.Label(cap, text=" ", foreground="#555555")
        self.bar_tip.pack(anchor="w")

        # Acciones
        act = ttk.Frame(self, padding=(10, 4, 10, 4))
        act.pack(fill="x")
        ttk.Button(act, text="Generar ROM...", command=self.generate).pack(side="left")
        ttk.Separator(act, orient="vertical").pack(side="left", fill="y", padx=12)
        ttk.Button(act, text="Probar en openMSX", command=self.test_openmsx).pack(side="left")
        ttk.Label(act, text="Máquina:").pack(side="left", padx=(8, 2))
        self.machine_cb = ttk.Combobox(act, textvariable=self.machine, width=22, values=self._machines())
        self.machine_cb.pack(side="left")
        ttk.Button(act, text="openMSX...", command=self.pick_openmsx).pack(side="left", padx=4)
        ttk.Checkbutton(act, text="Analizar en varias máquinas", variable=self.multi).pack(side="left", padx=8)

        # Informe
        logf = ttk.LabelFrame(self, text="Informe", padding=4)
        logf.pack(fill="both", padx=10, pady=(0, 10))
        self.log = tk.Text(logf, height=7, wrap="word", font=("Consolas", 9), state="disabled")
        self.log.pack(fill="both", expand=True)

    def about(self):
        """Ventana 'Acerca de': autor, version, web y creditos."""
        win = tk.Toplevel(self)
        win.title("Acerca de " + APP_NAME)
        win.resizable(False, False)
        win.transient(self)
        frm = ttk.Frame(win, padding=(20, 16))
        frm.pack(fill="both")
        head = ttk.Frame(frm)
        head.pack(fill="x")
        try:
            win.logo = tk.PhotoImage(file=ICON_PNG)
            ttk.Label(head, image=win.logo).pack(side="left", padx=(0, 14))
        except tk.TclError:
            pass
        names = ttk.Frame(head)
        names.pack(side="left")
        ttk.Label(names, text=APP_NAME, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(names, text="Versión " + APP_VERSION).pack(anchor="w")
        ttk.Label(frm, wraplength=420, justify="left", text=(
            "Generador de ROMs multijuego para MSX, con menú de selección, para los "
            "cartuchos RBSC Multimapper (512KB / 2MB) y Yamanooto SCC (8MB). Convierte "
            "juegos ASCII8, ASCII16, Konami4, Konami5 y ROMs sin mapper al mapper Konami5 (SCC).")
        ).pack(anchor="w", pady=(12, 8))
        ttk.Label(frm, text="Creado por " + APP_AUTHOR, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        link = ttk.Label(frm, text=APP_WEB.split("//")[1], foreground="#0060c0", cursor="hand2",
                         font=("Segoe UI", 10, "underline"))
        link.pack(anchor="w")
        link.bind("<Button-1>", lambda e: webbrowser.open(APP_WEB))
        ttk.Label(frm, text="© 2026 Germán Díaz. Todos los derechos reservados.").pack(anchor="w", pady=(2, 10))
        ttk.Label(frm, text="Créditos", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(frm, wraplength=420, justify="left", text=(
            "• openMSX: emulador usado para analizar y probar los juegos.\n"
            "• Base de datos de ROMs de openMSX (softwaredb, GPL) para detectar los mappers.\n"
            "• Pasmo: ensamblador del menú del MSX.\n"
            "• Python, Tkinter y PyInstaller.")).pack(anchor="w", pady=(2, 10))
        ttk.Label(frm, wraplength=420, justify="left", foreground="#606060", text=(
            "Usa solo ROMs de las que tengas una copia legal. Los juegos y marcas "
            "mencionados pertenecen a sus respectivos propietarios. Este programa se "
            "ofrece tal cual, sin garantía de ningún tipo.")).pack(anchor="w")
        ttk.Button(frm, text="Cerrar", command=win.destroy).pack(anchor="e", pady=(14, 0))
        win.bind("<Escape>", lambda e: win.destroy())
        win.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - win.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - win.winfo_height()) // 3
        win.geometry("+%d+%d" % (max(x, 0), max(y, 0)))
        win.grab_set()

    def _machines(self):
        if not self.openmsx:
            return ["C-BIOS_MSX1", "C-BIOS_MSX2", "C-BIOS_MSX2+"]
        names = set()
        dirs = [os.path.join(os.path.dirname(self.openmsx), "share", "machines"),
                os.path.join(os.path.expanduser("~"), "Documents", "openMSX", "share", "machines")]
        for d in dirs:
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.endswith(".xml"):
                        names.add(f[:-4])
        return sorted(names, key=lambda n: (not n.startswith("C-BIOS"), n.lower()))

    # -------------------------------------------------------------- estado
    def cart_key(self):
        return list(mr.CARTS)[self.cart_cb.current()]

    def size_kb(self):
        txt = self.size.get()
        return int(txt.split()[0]) * (1024 if "MB" in txt else 1)

    def _cart_changed(self, initial=False):
        keys = list(mr.CARTS)
        if initial:
            self.cart_cb.current(keys.index(self.cart.get()) if self.cart.get() in keys else 0)
        sizes = mr.CARTS[self.cart_key()]["sizes"]
        labels = ["%d KB" % s if s < 1024 else "%d MB" % (s // 1024) for s in sizes]
        self.size_cb["values"] = labels
        want = self.cfg.get("size") if initial else self.size.get()
        self.size.set(want if want in labels else labels[-1])
        self.refresh()

    def refresh(self):
        cart = self.cart_key()
        size = self.size_kb()
        valid = [g for g in self.games if not g.error]
        risky = set()
        bases = mr.allocate(valid, cart, size, risky) if valid else []
        base_of = {id(g): b for g, b in zip(valid, bases)}
        risky_ids = {id(valid[i]) for i in risky}
        self.tree.delete(*self.tree.get_children())
        for i, g in enumerate(self.games):
            b = base_of.get(id(g))
            notes = []
            tags = ()
            if g.error:
                notes.append(g.error)
                tags = ("error",)
            elif b is None:
                notes.append("No cabe")
                tags = ("nofit",)
            notes += g.prep_warnings + g.warnings
            if id(g) in risky_ids:
                notes.insert(0, "posible fallo: " + mr.RISKY_MSG)
                tags = tags or ("warn",)
            if cart == "k5" and g.mapper not in (None, mr.PLAIN) and not g.error:
                notes.append("se parchea el mapper")
            elif cart == "yama" and g.mapper in (mr.ASCII8, mr.ASCII16, mr.GENERIC16):
                notes.append("se parchea el mapper")
            if g.mapper_src == "deteccion" and g.mapper not in (None, mr.PLAIN):
                notes.insert(0, "mapper deducido (no está en la base de datos): compruébalo")
            if not tags and (g.prep_warnings or g.warnings or g.mapper_src == "deteccion"):
                tags = ("warn",)
            if g.error or not mr.needs_patch(g.mapper, cart, g.data):
                stubs = "-"
            elif g.stub_place == "rom":
                stubs = "ROM"
            elif g.ram_area:
                stubs = "RAM " + g.ram_area
            elif g.analysis and g.analysis.get("init"):
                stubs = "RAM auto"
            else:
                stubs = "RAM " + mr.DEFAULT_RAM_AREA
            an = "-"
            if g.analysis:
                runs = g.analysis.get("runs", 1)
                an = "sí" if runs == 1 else "sí (%d)" % runs
                if not g.analysis.get("init"):
                    an = "incompleto"
                    notes.append("el análisis no vio arrancar el juego")
            self.tree.insert("", "end", iid=str(i), tags=tags, values=(
                i + 1, g.title, g.describe() + ("" if g.mapper_src != "deteccion" else " ?"),
                "%d KB" % g.size_kb if g.data else "-",
                "" if b is None else b, stubs, an, "; ".join(notes) or "OK"))
        self.bases = [base_of.get(id(g)) for g in self.games]
        self._draw_bar()

    def _draw_bar(self):
        c = self.canvas
        c.delete("all")
        w = max(c.winfo_width() - 2, 10)
        h = 34
        total = self.size_kb() * 1024 // mr.BANK
        valid = [g for g in self.games if not g.error]
        menu = mr.menu_banks(valid, self.cart_key())
        scale = w / total
        self.segments = []
        c.create_rectangle(1, 1, 1 + menu * scale, h, fill="#909090", outline="")
        self.segments.append((0, menu, "Menú y tabla de juegos (%d KB)" % (menu * 8)))
        used = menu
        for i, g in enumerate(self.games):
            b = self.bases[i] if i < len(self.bases) else None
            if b is None:
                continue
            x0, x1 = 1 + b * scale, 1 + (b + g.nbanks) * scale
            col = PALETTE[i % len(PALETTE)]
            c.create_rectangle(x0, 1, x1, h, fill=col, outline="#202020" if x1 - x0 > 3 else "")
            if x1 - x0 > 40:
                c.create_text((x0 + x1) / 2, h / 2, text=g.title[:max(1, int((x1 - x0) / 7))],
                              fill="white", font=("Segoe UI", 8))
            self.segments.append((b, b + g.nbanks, "%s - %d KB (bancos %d-%d)" % (
                g.title, g.size_kb, b, b + g.nbanks - 1)))
            used += g.nbanks
        nofit = sum(1 for i, g in enumerate(self.games) if not g.error and self.bases[i] is None)
        free = total - used
        txt = "Ocupado: %d KB de %d KB   -   Libre: %d KB (%d%%)" % (
            used * 8, total * 8, free * 8, round(100 * free / total))
        if nofit:
            txt += "   -   %d juego(s) NO caben" % nofit
        self.cap_label.configure(text=txt, foreground="#c00000" if nofit else "")
        self._scale = scale

    def _bar_hover(self, ev):
        if not getattr(self, "_scale", None):
            return
        bank = (ev.x - 1) / self._scale
        for a, b, txt in self.segments:
            if a <= bank < b:
                self.bar_tip.configure(text=txt)
                return
        self.bar_tip.configure(text="Libre")

    def set_log(self, text):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("end", text)
        self.log.configure(state="disabled")

    # ------------------------------------------------------------- acciones
    def _add_paths(self, paths):
        errors = []
        for p in paths:
            try:
                self.games.append(mr.Game(p))
            except (OSError, mr.RomError) as e:
                errors.append("%s: %s" % (os.path.basename(p), e))
        self.refresh()
        if errors:
            self.set_log("No se pudieron añadir:\n" + "\n".join(errors))

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Añadir ROMs", initialdir=self.cfg.get("romdir"),
            filetypes=[("ROMs MSX", "*.rom *.mx1 *.mx2 *.bin *.zip"), ("Todos", "*.*")])
        if paths:
            self.cfg["romdir"] = os.path.dirname(paths[0])
            self._add_paths(paths)

    def add_folder(self):
        d = filedialog.askdirectory(title="Añadir todas las ROMs de una carpeta",
                                    initialdir=self.cfg.get("romdir"))
        if d:
            self.cfg["romdir"] = d
            paths = [os.path.join(d, f) for f in sorted(os.listdir(d))
                     if f.lower().endswith((".rom", ".mx1", ".mx2", ".zip"))]
            self._add_paths(paths)

    def selected(self):
        return sorted(int(i) for i in self.tree.selection())

    def remove(self):
        for i in reversed(self.selected()):
            del self.games[i]
        self.refresh()

    def move(self, d):
        sel = self.selected()
        if not sel:
            return
        if (d < 0 and sel[0] == 0) or (d > 0 and sel[-1] == len(self.games) - 1):
            return
        for i in (sel if d < 0 else reversed(sel)):
            self.games[i], self.games[i + d] = self.games[i + d], self.games[i]
        self.refresh()
        self.tree.selection_set([str(i + d) for i in sel])

    def sort(self):
        self.games.sort(key=lambda g: g.title.lower())
        self.refresh()

    def _on_double(self, ev):
        row = self.tree.identify_row(ev.y)
        col = self.tree.identify_column(ev.x)
        if not row:
            return
        i = int(row)
        x, y, w, h = self.tree.bbox(row, col)
        if col == "#2":
            var = tk.StringVar(value=self.games[i].title)
            ent = ttk.Entry(self.tree, textvariable=var)
            ent.place(x=x, y=y, width=w, height=h)
            ent.focus_set()
            ent.select_range(0, "end")

            def done(_=None):
                t = mr.ascii_name(var.get())[:mr.NAME_LEN]
                if t:
                    self.games[i].title = t
                ent.destroy()
                self.refresh()
            ent.bind("<Return>", done)
            ent.bind("<FocusOut>", done)
            ent.bind("<Escape>", lambda e: ent.destroy())
        elif col == "#3":
            names = [mr.MAPPER_NAMES[m] for m in MAPPER_CHOICES]
            cb = ttk.Combobox(self.tree, values=names, state="readonly")
            cb.place(x=x, y=y, width=max(w, 160), height=h)
            if self.games[i].mapper in MAPPER_CHOICES:
                cb.current(MAPPER_CHOICES.index(self.games[i].mapper))
            cb.focus_set()

            def chosen(_=None):
                if cb.current() >= 0:
                    self.games[i].set_mapper(MAPPER_CHOICES[cb.current()])
                cb.destroy()
                self.refresh()
            cb.bind("<<ComboboxSelected>>", chosen)
            cb.bind("<FocusOut>", lambda e: cb.destroy())
            cb.bind("<Escape>", lambda e: cb.destroy())
        elif col == "#6" and self.tree.set(row, "stubs") != "-":
            opts = ["RAM automática (%s si no hay análisis)" % mr.DEFAULT_RAM_AREA]
            opts += ["RAM %s (%04Xh, %d bytes)" % (k, a, n) for k, (a, n) in mr.RAM_AREAS.items()]
            opts.append("ROM (hueco libre del juego)")
            cb = ttk.Combobox(self.tree, values=opts, state="readonly")
            cb.place(x=x, y=y, width=max(w, 260), height=h)
            g = self.games[i]
            keys = [None] + list(mr.RAM_AREAS)
            cb.current(len(keys) if g.stub_place == "rom" else keys.index(g.ram_area))
            cb.focus_set()

            def chosen_stub(_=None):
                k = cb.current()
                if k == len(keys):
                    g.stub_place = "rom"
                elif k >= 0:
                    g.stub_place = "ram"
                    g.ram_area = keys[k]
                cb.destroy()
                self.refresh()
            cb.bind("<<ComboboxSelected>>", chosen_stub)
            cb.bind("<FocusOut>", lambda e: cb.destroy())
            cb.bind("<Escape>", lambda e: cb.destroy())

    def save_list(self):
        p = filedialog.asksaveasfilename(title="Guardar lista", defaultextension=".json",
                                         filetypes=[("Lista MultiROM", "*.json")])
        if not p:
            return
        data = {"cart": self.cart_key(), "size": self.size.get(), "title": self.menu_title.get(),
                "games": [{"path": g.path, "title": g.title, "mapper": g.mapper,
                           "mapper_src": g.mapper_src, "stub_place": g.stub_place,
                           "ram_area": g.ram_area} for g in self.games]}
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)

    def load_list(self):
        p = filedialog.askopenfilename(title="Abrir lista", filetypes=[("Lista MultiROM", "*.json")])
        if not p:
            return
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        games, errors = [], []
        for e in data.get("games", []):
            try:
                g = mr.Game(e["path"])
            except (OSError, mr.RomError) as ex:
                errors.append("%s: %s" % (e["path"], ex))
                continue
            g.title = e.get("title", g.title)
            if e.get("mapper_src") == "usuario":
                g.set_mapper(e["mapper"])
            g.stub_place = e.get("stub_place", g.stub_place)
            g.ram_area = e.get("ram_area")
            games.append(g)
        self.games = games
        self.menu_title.set(data.get("title", "MSX MULTIROM"))
        keys = list(mr.CARTS)
        if data.get("cart") in keys:
            self.cart_cb.current(keys.index(data["cart"]))
        self.cfg["size"] = data.get("size")
        self._cart_changed(initial=False)
        if data.get("size") in self.size_cb["values"]:
            self.size.set(data["size"])
        self.refresh()
        if errors:
            self.set_log("No se encontraron:\n" + "\n".join(errors))

    def _build_image(self):
        if not any(not g.error for g in self.games):
            messagebox.showwarning("MultiROM", "Añade al menos una ROM válida.")
            return None
        try:
            image, report = mr.build(self.games, self.cart_key(), self.size_kb(), self.menu_title.get())
        except (OSError, ValueError) as e:
            messagebox.showerror("MultiROM", "No se pudo generar la ROM:\n%s" % e)
            return None
        lines = []
        for g, b, rep in report:
            st = "NO CABE" if b is None else "banco %d" % b
            extra = ""
            if rep["sites"] or rep.get("dyn"):
                extra = "  %d cambios de banco parcheados (rutinas: %d en ROM, %d en RAM)" % (
                    rep["sites"] + rep.get("dyn", 0), rep["stubs"], rep["ram"])
                if rep.get("dyn"):
                    extra += ", %d gracias al análisis" % rep["dyn"]
            lines.append("%-30s %-10s%s" % (g.title, st, extra))
            for e in rep["errors"]:
                lines.append("    ERROR: " + e)
            for w in rep["warnings"][:5]:
                lines.append("    aviso: " + w)
        self.set_log("\n".join(lines))
        return image

    def generate(self):
        image = self._build_image()
        if image is None:
            return
        p = filedialog.asksaveasfilename(
            title="Guardar MultiROM", defaultextension=".rom", initialdir=self.cfg.get("outdir"),
            initialfile="multirom_%s_%s.rom" % (self.cart_key(), self.size.get().replace(" ", "")),
            filetypes=[("ROM MSX", "*.rom")])
        if not p:
            return
        self.cfg["outdir"] = os.path.dirname(p)
        with open(p, "wb") as f:
            f.write(image)
        messagebox.showinfo("MultiROM", "ROM generada:\n%s\n\nMapper: %s" % (
            p, mr.CARTS[self.cart_key()]["romtype"]))

    def pick_openmsx(self):
        p = filedialog.askopenfilename(title="Ejecutable de openMSX",
                                       filetypes=[("openmsx.exe", "openmsx.exe"), ("Todos", "*.*")])
        if p:
            self.openmsx = p
            self.machine_cb["values"] = self._machines()

    def test_openmsx(self):
        if not self.openmsx or not os.path.exists(self.openmsx):
            messagebox.showinfo("openMSX", "Indica dónde está openmsx.exe con el botón 'openMSX...'.")
            return
        image = self._build_image()
        if image is None:
            return
        path = os.path.join(tempfile.gettempdir(), "msx_multirom_test.rom")
        with open(path, "wb") as f:
            f.write(image)
        subprocess.Popen([self.openmsx, "-machine", self.machine.get(), "-cart", path,
                          "-romtype", mr.CARTS[self.cart_key()]["romtype"]],
                         cwd=os.path.dirname(self.openmsx))

    # ------------------------------------------------------------ analisis
    def _check_openmsx(self):
        if not self.openmsx or not os.path.exists(self.openmsx):
            messagebox.showinfo("openMSX", "Indica dónde está openmsx.exe con el botón 'openMSX...'.")
            return False
        if getattr(self, "_busy", False):
            messagebox.showinfo("Análisis", "Ya hay un análisis en marcha.")
            return False
        return True

    def _machine_ok(self, machine):
        """openMSX arranca la maquina (tiene sus ROMs de sistema)."""
        script = os.path.join(tempfile.gettempdir(), "msx_multirom_ok.tcl")
        with open(script, "w") as f:
            f.write("after time 0.1 exit\n")
        try:
            r = subprocess.run([self.openmsx, "-machine", machine, "-script", script],
                               capture_output=True, timeout=60,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return r.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _run_analysis(self, games, interactive):
        """Analiza los juegos en un hilo y va contando el progreso en el informe."""
        self._busy = True
        machines = [self.machine.get()]
        if self.multi.get() and not interactive:
            machines += [m for m in MULTI_MACHINES if m not in machines]
        lines = []

        def say(t):
            lines.append(t)
            self.after(0, self.set_log, "\n".join(lines[-40:]))

        def work():
            ok = [m for m in machines if len(machines) == 1 or self._machine_ok(m)]
            if len(machines) > 1:
                say("Máquinas: " + ", ".join(ok))
            for k, g in enumerate(games):
                say("[%d/%d] %s..." % (k + 1, len(games), g.title))
                try:
                    for m in ok:
                        g.analysis = analyze.run(g, self.openmsx, m, seconds=90, interactive=interactive)
                    lines[-1] += " " + analyze.summary(g.analysis)
                except Exception as e:  # noqa: BLE001 - se informa y se sigue con el siguiente
                    lines[-1] += " ERROR: %s" % e
                self.after(0, self.set_log, "\n".join(lines[-40:]))
            say("Análisis terminado. Las rutinas se colocarán según el análisis al generar la ROM.")
            self.after(0, self._analysis_done)

        threading.Thread(target=work, daemon=True).start()

    def _analysis_done(self):
        self._busy = False
        self.refresh()

    def analyze_auto(self):
        if not self._check_openmsx():
            return
        sel = self.selected() or range(len(self.games))
        games = [self.games[i] for i in sel
                 if not self.games[i].error and mr.needs_patch(self.games[i].mapper, "k5")]
        if not games:
            messagebox.showinfo("Análisis", "No hay juegos con mapper que analizar.")
            return
        msg = "Analizando %d juego(s) en openMSX (%s, 90 s de juego cada uno)..." % (
            len(games), self.machine.get())
        if self.machine.get().startswith("C-BIOS") and any(
                not m.startswith("C-BIOS") for m in self.machine_cb["values"]):
            msg += ("\nConsejo: es mejor analizar con una máquina con BIOS real "
                    "(por ejemplo Sony_HB-F1XD); C-BIOS no usa la RAM igual.")
        self.set_log(msg)
        self._run_analysis(games, False)

    def analyze_play(self):
        if not self._check_openmsx():
            return
        sel = self.selected()
        if len(sel) != 1 or self.games[sel[0]].error:
            messagebox.showinfo("Análisis", "Selecciona un juego.")
            return
        messagebox.showinfo(
            "Analizar jugando",
            "Se abrirá openMSX con el juego original. Juega un rato, pasando por "
            "el mayor número de pantallas, fases y menús que puedas (también "
            "cargar y grabar partida si tiene), y después cierra openMSX.\n\n"
            "Lo que se vea se suma a los análisis anteriores del juego.")
        self._run_analysis([self.games[sel[0]]], True)

    def forget_analysis(self):
        sel = self.selected()
        if not sel:
            messagebox.showinfo("Análisis", "Selecciona los juegos.")
            return
        for i in sel:
            analyze.forget(self.games[i].sha1)
            self.games[i].analysis = None
        self.refresh()

    def _quit(self):
        self.cfg.update(cart=self.cart_key(), size=self.size.get(), title=self.menu_title.get(),
                        openmsx=self.openmsx, machine=self.machine.get(), multi=self.multi.get())
        save_config(self.cfg)
        self.destroy()


if __name__ == "__main__":
    args = [os.path.abspath(a) for a in sys.argv[1:]]
    os.chdir(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else mr.APP_DIR)
    app = App()
    for a in args:
        app._add_paths([a])
    app.mainloop()
