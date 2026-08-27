#!/usr/bin/env python3
"""Convierte docs/guion-video-flujo-telegram.md en HTML y PDF.

El PDF se produce con LibreOffice en modo headless, que es lo único
disponible en esta máquina. Dos rarezas de su importador de HTML obligan a
trabajar así:

- se come el primer elemento de bloque del documento, de ahí el espaciador;
- ignora ``colgroup``, ``nowrap`` y el ancho por CSS, así que los anchos van
  como atributo ``width`` en cada celda.

Uso: python3 scripts/guion-a-pdf.py
"""

import html
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MD = RAIZ / "docs" / "guion-video-flujo-telegram.md"
HTML = MD.with_suffix(".html")
PDF = MD.with_suffix(".pdf")

CSS = """
body{font-family:'Liberation Sans',Arial,sans-serif;font-size:10pt;color:#1a1a1a;}
p{margin:4pt 0;line-height:1.35;}
p.t1{font-size:19pt;font-weight:bold;margin:0 0 8pt 0;}
p.t2{font-size:13pt;font-weight:bold;margin:16pt 0 4pt 0;border-bottom:1px solid #888;padding-bottom:2pt;}
p.t3{font-size:11pt;font-weight:bold;margin:10pt 0 2pt 0;}
li{font-size:10pt;line-height:1.35;margin:2pt 0;}
table{border-collapse:collapse;margin:6pt 0 10pt 0;}
th{background:#e8e8e8;border:1px solid #888;padding:3pt 5pt;text-align:left;font-size:9pt;font-weight:bold;}
td{border:1px solid #bbb;padding:3pt 5pt;font-size:9pt;vertical-align:top;line-height:1.3;}
.c{font-family:'Liberation Mono',monospace;font-size:8.5pt;}
"""

# Anchos por número de columnas: las de tiempo estrechas, la de texto ancha.
ANCHOS = {3: ["13", "17", "70"], 4: ["9", "13", "13", "65"]}


def inline(texto: str) -> str:
    texto = html.escape(texto)
    texto = re.sub(r"`([^`]+)`", r'<span class="c">\1</span>', texto)
    texto = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", texto)
    return texto


def tabla(filas: list[list[str]]) -> str:
    cabecera, cuerpo = filas[0], filas[2:]
    n = len(cabecera)
    ancho = ANCHOS.get(n, [str(100 // n)] * n)
    partes = ['<table width="100%">', "<tr>"]
    partes += [f'<th width="{ancho[i]}%">{inline(c)}</th>' for i, c in enumerate(cabecera)]
    partes.append("</tr>")
    for fila in cuerpo:
        partes.append("<tr>")
        partes += [f'<td width="{ancho[i]}%">{inline(c)}</td>' for i, c in enumerate(fila)]
        partes.append("</tr>")
    partes.append("</table>")
    return "".join(partes)


def a_html(md: str) -> str:
    lineas = md.split("\n")
    salida, i = [], 0
    while i < len(lineas):
        linea = lineas[i]
        if linea.startswith("### "):
            salida.append(f'<p class="t3">{inline(linea[4:])}</p>')
        elif linea.startswith("## "):
            salida.append(f'<p class="t2">{inline(linea[3:])}</p>')
        elif linea.startswith("# "):
            salida.append(f'<p class="t1">{inline(linea[2:])}</p>')
        elif linea.startswith("|"):
            filas = []
            while i < len(lineas) and lineas[i].startswith("|"):
                filas.append([c.strip() for c in lineas[i].strip().strip("|").split("|")])
                i += 1
            salida.append(tabla(filas))
            continue
        elif linea.startswith("- "):
            puntos = []
            while i < len(lineas) and (lineas[i].startswith("- ") or lineas[i].startswith("  ")):
                if lineas[i].startswith("- "):
                    puntos.append(lineas[i][2:])
                else:
                    puntos[-1] += " " + lineas[i].strip()
                i += 1
            salida.append("<ul>" + "".join(f"<li>{inline(p)}</li>" for p in puntos) + "</ul>")
            continue
        elif not linea.strip():
            salida.append("")
        else:
            parrafo = [linea]
            while (
                i + 1 < len(lineas)
                and lineas[i + 1].strip()
                and not lineas[i + 1].startswith(("|", "#", "- "))
            ):
                i += 1
                parrafo.append(lineas[i])
            salida.append("<p>" + inline(" ".join(parrafo)) + "</p>")
        i += 1
    # El espaciador absorbe el primer bloque que LibreOffice descarta.
    return (
        '<html><head><meta charset="utf-8"><style>'
        + CSS
        + '</style></head><body><p style="font-size:1pt;margin:0">&nbsp;</p>'
        + "\n".join(salida)
        + "</body></html>"
    )


def main() -> int:
    if shutil.which("libreoffice") is None:
        print("Falta libreoffice para producir el PDF", file=sys.stderr)
        return 1
    HTML.write_text(a_html(MD.read_text()), encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", tmp, str(HTML)],
            check=True,
            capture_output=True,
        )
        generado = Path(tmp) / (HTML.stem + ".pdf")
        PDF.write_bytes(generado.read_bytes())
    print(f"{HTML.relative_to(RAIZ)} y {PDF.relative_to(RAIZ)} regenerados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
