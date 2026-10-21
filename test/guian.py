"""Prueba del boton Analizar: analiza 2 juegos desde la GUI y captura la ventana."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import guishot_lib as GS
import multirom_gui as G, analyze
app = G.App()
app._add_paths(sys.argv[2:])
for g in app.games:
    analyze.forget(g.sha1); g.analysis = None
app.refresh()
app.tree.selection_set([str(i) for i in range(len(app.games))])
app.analyze_auto()
def wait():
    if getattr(app, "_busy", False):
        app.after(300, wait)
    else:
        app._build_image()
        app.after(500, lambda: GS.shot(app, sys.argv[1]))
app.after(500, wait)
app.mainloop()
