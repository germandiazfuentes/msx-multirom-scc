# Copyright (C) 2026 Germán Díaz / MSX Calamar
# SPDX-License-Identifier: GPL-2.0-or-later
"""Genera docs/MANUAL.pdf a partir de docs/MANUAL.md.

    python docs/crear_pdf.py

Necesita: pip install markdown pypdf reportlab, y Microsoft Edge o Google Chrome
(se usa en modo sin ventana para imprimir el HTML a PDF).
"""
import io
import os
import re
import subprocess
import sys
import tempfile

import markdown
from markdown.extensions.toc import slugify_unicode
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "MANUAL.md")
OUT = os.path.join(HERE, "MANUAL.pdf")
ICON = os.path.join(HERE, "..", "app", "data", "calamar.png")
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"]

CSS = """
@page { size: A4; margin: 18mm 17mm 20mm 17mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1d1d1f; }
h1 { display: none; }
h2 { font-size: 17pt; color: #c2410c; border-bottom: 2px solid #f0a060; padding-bottom: 3px;
     margin-top: 30px; break-after: avoid; }
h2.salto { break-before: page; margin-top: 0; }
h3 { font-size: 12.5pt; color: #333; margin-top: 18px; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
a { color: #0060c0; text-decoration: none; }
code { font-family: Consolas, monospace; font-size: 9.5pt; background: #f2f2f2; padding: 0 3px; border-radius: 3px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 12px; font-size: 9.5pt; break-inside: auto; }
tr { break-inside: avoid; }
th { background: #f6e3d4; text-align: left; }
th, td { border: 1px solid #d8c8bc; padding: 4px 6px; vertical-align: top; }
img { max-width: 100%; display: block; margin: 8px auto; break-inside: avoid; }
td img { margin: 0 auto; }
img[src$="aviso_yamanooto.png"] { max-width: 55%; }
img[src$="acerca_de.png"] { max-width: 50%; }
blockquote { margin: 10px 0; padding: 6px 12px; background: #fff6ec; border-left: 4px solid #f0a060; }
blockquote p { margin: 2px 0; }
hr { display: none; }
.cover { height: 250mm; display: flex; flex-direction: column; align-items: center; justify-content: center;
         text-align: center; }
.cover img { width: 120px; image-rendering: pixelated; }
.cover .t { font-size: 34pt; font-weight: bold; margin-top: 18px; }
.cover .s { font-size: 15pt; color: #c2410c; margin-top: 4px; }
.cover .d { font-size: 11pt; color: #555; margin-top: 26px; max-width: 120mm; }
.cover .a { font-size: 12pt; margin-top: 60px; }
.toc { break-before: page; }
.toc h2 { break-before: avoid; }
.toc ol { font-size: 12pt; line-height: 1.9; }
"""


def main():
    with open(SRC, encoding="utf-8") as f:
        md = f.read()
    version = re.search(r"\*\*Versión ([\d.]+)\*\*", md).group(1)
    # El indice del .md se sustituye por uno propio en la portada; se quitan el
    # titulo, la linea de autor y la captura inicial (van en la portada)
    toc = re.search(r"## Índice\n(.*?)\n---", md, re.S).group(1)
    body = md[md.index("## 1."):]
    intro = md[md.index("\n", md.index("**Versión")) + 1:md.index("![")].strip()
    html_body = markdown.markdown(body, extensions=["tables", "toc"],
                                  extension_configs={"toc": {"slugify": slugify_unicode}})
    html_toc = markdown.markdown(toc)
    # Paginas nuevas solo en las secciones largas
    for sec in ("3-", "7-", "10-", "11-", "12-"):
        html_body = html_body.replace('<h2 id="%s' % sec, '<h2 class="salto" id="%s' % sec)
    html_intro = markdown.markdown(intro)
    # Las imagenes son relativas a docs/; el enlace a LICENSE se deja apuntando a GitHub
    html_body = html_body.replace('href="../LICENSE"',
                                  'href="https://github.com/germandiazfuentes/msx-multirom-scc/blob/main/LICENSE"')
    icon = "file:///" + os.path.abspath(ICON).replace("\\", "/")
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<base href="file:///{HERE.replace(os.sep, '/')}/"><title>Manual de MSX MultiROM</title><style>{CSS}</style></head><body>
<div class="cover"><img src="{icon}" alt="">
<div class="t">MSX MultiROM</div><div class="s">Manual de uso · versión {version}</div>
<div class="d">{html_intro}</div>
<div class="a"><b>Germán Díaz / MSX Calamar</b><br>msxcalamar.com</div></div>
<div class="toc"><h2>Índice</h2>{html_toc}</div>
<div class="toc"><h2>Ventana principal</h2><img src="img/ventana.png" alt=""></div>
{html_body}</body></html>"""
    tmp = tempfile.mkdtemp(prefix="manual_")
    page = os.path.join(tmp, "manual.html")
    raw = os.path.join(tmp, "manual.pdf")
    with open(page, "w", encoding="utf-8") as f:
        f.write(html)
    browser = next((b for b in BROWSERS if os.path.exists(b)), None)
    if not browser:
        sys.exit("No se encuentra Edge ni Chrome")
    subprocess.run([browser, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    "--allow-file-access-from-files", "--print-to-pdf=" + raw,
                    "file:///" + page.replace("\\", "/")], check=True, timeout=120,
                   capture_output=True)
    number_pages(raw, OUT, version)
    print(OUT)


def number_pages(src, dst, version):
    """Pie de pagina con el numero de pagina (salvo en la portada) y metadatos."""
    writer = PdfWriter(clone_from=src)     # conserva los destinos de los enlaces internos
    n = len(writer.pages)
    for i, pg in enumerate(writer.pages):
        if i:
            w, h = float(pg.mediabox.width), float(pg.mediabox.height)
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=(w, h))
            c.setFont("Helvetica", 8)
            c.setFillGray(0.45)
            c.drawString(48, 28, "MSX MultiROM %s - Manual de uso" % version)
            c.drawRightString(w - 48, 28, "%d / %d" % (i + 1, n))
            c.save()
            buf.seek(0)
            pg.merge_page(PdfReader(buf).pages[0])
    writer.add_metadata({"/Title": "MSX MultiROM - Manual de uso", "/Author": "Germán Díaz / MSX Calamar",
                         "/Subject": "Versión %s" % version})
    with open(dst, "wb") as f:
        writer.write(f)


if __name__ == "__main__":
    main()
