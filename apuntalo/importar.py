"""Importa apuntes de otros programas y los convierte al Markdown de Apúntalo, sin librerías externas.

Formatos: Word (.docx), OpenDocument (.odt), página web (.html), Markdown (.md) y texto (.txt).

importar(ruta) devuelve un diccionario:
    titulo   -> título propuesto para el apunte
    cuerpo   -> el texto en Markdown; las imágenes aparecen como ![nombre](<{{imagen:N}}>)
    imagenes -> [(nombre_de_archivo, bytes)], en el mismo orden que N
"""
import base64
import html
import posixpath
import re
import urllib.parse
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

FORMATOS = {
    ".docx": "Word",
    ".odt": "OpenDocument (LibreOffice)",
    ".html": "Página web", ".htm": "Página web",
    ".md": "Markdown", ".markdown": "Markdown",
    ".txt": "Texto",
}
EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".gif"}


class Resultado:
    def __init__(self, titulo):
        self.titulo, self.lineas, self.imagenes = titulo, [], []

    def imagen(self, nombre, datos):
        """Añade una imagen y devuelve su enlace Markdown (o un aviso si el formato no se puede mostrar)."""
        ext = Path(nombre).suffix.lower()
        if ext not in EXT_IMAGEN:
            if datos[:8] == b"\x89PNG\r\n\x1a\n":
                ext = ".png"
            elif datos[:2] == b"\xff\xd8":
                ext = ".jpg"
            elif datos[:4] == b"GIF8":
                ext = ".gif"
            else:
                return f"*[Imagen no compatible: {Path(nombre).name}]*"
        nombre = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(nombre).stem)[:60] or "imagen"
        self.imagenes.append((nombre + ext, datos))
        return f"![{nombre}](<{{{{imagen:{len(self.imagenes) - 1}}}}}>)"

    def dict(self):
        texto = "\n".join(self.lineas)
        texto = re.sub(r"\n{3,}", "\n\n", texto).strip() + "\n"
        return {"titulo": self.titulo, "cuerpo": texto, "imagenes": self.imagenes}


MARCA = re.compile(r"^(?:([•◦▪·–-])|(☐)|(☑|☒)|(\d+[.)]))\s*")


def _item(texto, nivel=0):
    """Línea de lista en Markdown, quitando la viñeta que traiga el texto (•, 1., ☐...)."""
    sangria = "  " * nivel
    m = MARCA.match(texto)
    if not m:
        return f"{sangria}- {texto}"
    resto = texto[m.end():]
    if m[2]:
        return f"{sangria}- [ ] {resto}"
    if m[3]:
        return f"{sangria}- [x] {resto}"
    if m[4]:
        return f"{sangria}{m[4]} {resto}"
    return f"{sangria}- {resto}"


def _formato(texto, negrita, cursiva):
    if not texto.strip():
        return texto
    # las marcas van pegadas al texto, no a los espacios
    ini = texto[:len(texto) - len(texto.lstrip())]
    fin = texto[len(texto.rstrip()):]
    t = texto.strip()
    if cursiva:
        t = f"*{t}*"
    if negrita:
        t = f"**{t}**"
    return ini + t + fin


def _juntar(trozos):
    """Une trozos (texto, negrita, cursiva) juntando los consecutivos con el mismo formato."""
    unidos = []
    for t, b, i in trozos:
        if unidos and unidos[-1][1:] == (b, i):
            unidos[-1] = (unidos[-1][0] + t, b, i)
        else:
            unidos.append((t, b, i))
    return "".join(t if t.startswith("![") else _formato(t, b, i) for t, b, i in unidos)


# ---------- Word (.docx) ----------
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
VML = "{urn:schemas-microsoft-com:vml}"


def _activo(rpr, etiqueta):
    if rpr is None:
        return False
    e = rpr.find(W + etiqueta)
    return e is not None and e.get(W + "val", "true") not in ("0", "false", "none")


def _docx(ruta):
    res = Resultado(ruta.stem)
    with zipfile.ZipFile(ruta) as z:
        nombres = set(z.namelist())
        doc = ET.fromstring(z.read("word/document.xml"))
        rels = {}
        if "word/_rels/document.xml.rels" in nombres:
            for r in ET.fromstring(z.read("word/_rels/document.xml.rels")):
                rels[r.get("Id")] = r.get("Target", "")
        nombres_estilo = {}
        if "word/styles.xml" in nombres:
            for s in ET.fromstring(z.read("word/styles.xml")).iter(W + "style"):
                n = s.find(W + "name")
                nombres_estilo[s.get(W + "styleId")] = (n.get(W + "val") if n is not None else "").lower()

        def imagen_de(rid):
            destino = rels.get(rid, "")
            interna = posixpath.normpath(posixpath.join("word", destino)) if not destino.startswith("/") else destino[1:]
            if interna in nombres:
                return res.imagen(posixpath.basename(interna), z.read(interna))
            return ""

        def texto_parrafo(p):
            trozos = []
            for run in p.iter(W + "r"):
                rpr = run.find(W + "rPr")
                b, i = _activo(rpr, "b"), _activo(rpr, "i")
                for e in run:
                    if e.tag == W + "t":
                        trozos.append((e.text or "", b, i))
                    elif e.tag == W + "tab":
                        trozos.append(("\t", b, i))
                    elif e.tag in (W + "br", W + "cr"):
                        trozos.append((" ", b, i))
                    elif e.tag in (W + "drawing", W + "pict"):
                        for blip in e.iter(A + "blip"):
                            trozos.append(("\n" + imagen_de(blip.get(R + "embed")) + "\n", False, False))
                        for img in e.iter(VML + "imagedata"):
                            trozos.append(("\n" + imagen_de(img.get(R + "id")) + "\n", False, False))
            return _juntar(trozos)

        cuerpo = doc.find(W + "body")
        primer_titulo = True
        for bloque in (cuerpo if cuerpo is not None else []):
            if bloque.tag == W + "tbl":
                for fila in bloque.iter(W + "tr"):
                    celdas = [" ".join(texto_parrafo(p).strip() for p in c.iter(W + "p")).strip()
                              for c in fila.iter(W + "tc")]
                    res.lineas.append("| " + " | ".join(celdas) + " |")
                res.lineas.append("")
                continue
            if bloque.tag != W + "p":
                continue
            ppr = bloque.find(W + "pPr")
            estilo_id = ""
            lista = False
            if ppr is not None:
                ps = ppr.find(W + "pStyle")
                estilo_id = ps.get(W + "val", "") if ps is not None else ""
                lista = ppr.find(W + "numPr") is not None
            estilo = nombres_estilo.get(estilo_id, estilo_id.lower())
            texto = texto_parrafo(bloque).strip()
            if not texto:
                res.lineas.append("")
                continue
            plano = re.sub(r"[*]", "", texto)
            if estilo in ("title", "título", "titulo") and primer_titulo:
                res.titulo, primer_titulo = plano, False
                continue
            m = re.search(r"(?:heading|título|titulo)\s*(\d)", estilo)
            if m:
                res.lineas += ["", "#" * min(int(m[1]), 3) + " " + plano, ""]
            elif estilo in ("subtitle", "subtítulo") and not res.lineas:
                res.lineas.append(f"*{plano}*")
            elif lista or "list" in estilo or "lista" in estilo:
                nivel = 0
                if ppr is not None and (il := ppr.find(f"{W}numPr/{W}ilvl")) is not None:
                    nivel = int(il.get(W + "val", "0") or 0)
                res.lineas.append(_item(texto, nivel))
            elif "quote" in estilo or "cita" in estilo:
                res.lineas.append("> " + texto)
            else:
                res.lineas += [texto, ""]
    return res.dict()


# ---------- OpenDocument (.odt) ----------
O = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
}


def _q(nombre):
    pre, local = nombre.split(":")
    return "{" + O[pre] + "}" + local


def _odt(ruta):
    res = Resultado(ruta.stem)
    with zipfile.ZipFile(ruta) as z:
        nombres = set(z.namelist())
        raiz = ET.fromstring(z.read("content.xml"))
        estilos = {}       # nombre -> (negrita, cursiva, estilo padre)
        fuentes = [raiz]
        if "styles.xml" in nombres:
            fuentes.append(ET.fromstring(z.read("styles.xml")))
        for f in fuentes:
            for s in f.iter(_q("style:style")):
                tp = s.find(_q("style:text-properties"))
                b = tp is not None and tp.get(_q("fo:font-weight"), "") in ("bold", "600", "700", "800", "900")
                i = tp is not None and tp.get(_q("fo:font-style"), "") == "italic"
                estilos[s.get(_q("style:name"))] = (b, i, s.get(_q("style:parent-style-name"), ""),
                                                   s.get(_q("style:display-name"), "") or s.get(_q("style:name"), ""))

        def fmt(nombre):
            b, i, _, _ = estilos.get(nombre, (False, False, "", ""))
            return b, i

        def nombre_visible(nombre, saltos=5):
            while nombre and saltos:
                _, _, padre, visible = estilos.get(nombre, (False, False, "", nombre))
                if not nombre.startswith("P") or not padre:
                    return visible.lower()
                nombre, saltos = padre, saltos - 1
            return (nombre or "").lower()

        def recorrer(e, b, i, trozos):
            if e.text:
                trozos.append((e.text, b, i))
            for h in e:
                if h.tag == _q("text:span"):
                    hb, hi = fmt(h.get(_q("text:style-name")))
                    recorrer(h, b or hb, i or hi, trozos)
                elif h.tag == _q("text:s"):
                    trozos.append((" " * int(h.get(_q("text:c"), "1")), b, i))
                elif h.tag == _q("text:tab"):
                    trozos.append(("\t", b, i))
                elif h.tag == _q("text:line-break"):
                    trozos.append((" ", b, i))
                elif h.tag == _q("draw:frame"):
                    img = h.find(_q("draw:image"))
                    href = img.get(_q("xlink:href"), "") if img is not None else ""
                    if href in nombres:
                        trozos.append(("\n" + res.imagen(posixpath.basename(href), z.read(href)) + "\n", False, False))
                elif h.tag in (_q("text:a"), _q("text:bookmark-ref")):
                    recorrer(h, b, i, trozos)
                if h.tail:
                    trozos.append((h.tail, b, i))

        def parrafo(e):
            b, i = fmt(e.get(_q("text:style-name")))
            trozos = []
            recorrer(e, b, i, trozos)
            return _juntar(trozos).strip()

        def bloque(e, nivel_lista=-1):
            if e.tag == _q("text:h"):
                n = min(int(e.get(_q("text:outline-level"), "1")), 3)
                texto = re.sub(r"[*]", "", parrafo(e))
                if texto:
                    res.lineas += ["", "#" * n + " " + texto, ""]
            elif e.tag == _q("text:p"):
                texto = parrafo(e)
                visible = nombre_visible(e.get(_q("text:style-name"), ""))
                if nivel_lista >= 0:
                    res.lineas.append(_item(texto, nivel_lista))
                elif not texto:
                    res.lineas.append("")
                elif "lista" in visible or "list" in visible:
                    m = re.match(r"lista?\s*(\d)", visible)
                    res.lineas.append(_item(texto, int(m[1]) if m else 0))
                elif visible in ("title", "título", "titulo") and res.titulo == ruta.stem:
                    res.titulo = re.sub(r"[*]", "", texto)
                elif "quot" in visible or "cita" in visible:
                    res.lineas.append("> " + texto)
                else:
                    res.lineas += [texto, ""]
            elif e.tag == _q("text:list"):
                for item in e.findall(_q("text:list-item")):
                    for h in item:
                        bloque(h, nivel_lista + 1)
                if nivel_lista < 0:
                    res.lineas.append("")
            elif e.tag == _q("table:table"):
                for fila in e.iter(_q("table:table-row")):
                    celdas = [" ".join(parrafo(p) for p in c.iter(_q("text:p")))
                              for c in fila.findall(_q("table:table-cell"))]
                    res.lineas.append("| " + " | ".join(celdas) + " |")
                res.lineas.append("")
            elif e.tag == _q("text:section"):
                for h in e:
                    bloque(h, nivel_lista)

        texto = raiz.find(f"{_q('office:body')}/{_q('office:text')}")
        for e in (texto if texto is not None else []):
            bloque(e)
    return res.dict()


# ---------- Página web (.html) ----------
class _LectorHTML(HTMLParser):
    BLOQUES = {"p", "div", "section", "article", "header", "footer", "main", "tr", "table", "blockquote",
               "h1", "h2", "h3", "h4", "h5", "h6", "li", "pre", "ul", "ol", "hr", "br"}

    def __init__(self, res, carpeta):
        super().__init__(convert_charrefs=True)
        self.res, self.carpeta = res, carpeta
        self.actual, self.prefijo = [], ""
        self.negrita = self.cursiva = 0
        self.listas, self.ignorar, self.en_pre, self.en_title = [], 0, False, False
        self.titulo_pagina = ""

    def _cerrar(self):
        texto = _juntar(self.actual)
        self.actual = []
        if self.en_pre:
            self.res.lineas += ["```", texto.strip("\n"), "```", ""]
            return
        texto = re.sub(r"[ \t\r\n]+", " ", texto).strip()
        if texto and not self.prefijo and re.match(r"[•◦▪☐☑☒]", texto):   # viñeta escrita a mano
            self.prefijo, texto = "", _item(texto)
            self.res.lineas.append(texto)
            return
        if texto:
            self.res.lineas.append(self.prefijo + texto)
            if not self.prefijo.lstrip().startswith(("-", "1.")):
                self.res.lineas.append("")
        self.prefijo = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript", "nav"):
            self.ignorar += 1
        elif tag == "title":
            self.en_title = True
        if self.ignorar:
            return
        if tag in self.BLOQUES:
            self._cerrar()
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.prefijo = "#" * min(int(tag[1]), 3) + " "
        elif tag in ("ul", "ol"):
            self.listas.append(tag)
        elif tag == "li":
            nivel = max(len(self.listas) - 1, 0)
            self.prefijo = "  " * nivel + ("1. " if self.listas and self.listas[-1] == "ol" else "- ")
        elif tag == "blockquote":
            self.prefijo = "> "
        elif tag == "pre":
            self.en_pre = True
        elif tag == "hr":
            self.res.lineas += ["---", ""]
        elif tag in ("b", "strong"):
            self.negrita += 1
        elif tag in ("i", "em"):
            self.cursiva += 1
        elif tag == "img":
            enlace = self._imagen(a.get("src", ""), a.get("alt", ""))
            if enlace:
                self._cerrar()
                self.res.lineas += [enlace, ""]

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "nav"):
            self.ignorar = max(self.ignorar - 1, 0)
            return
        if tag == "title":
            self.en_title = False
        if self.ignorar:
            return
        if tag in ("b", "strong"):
            self.negrita = max(self.negrita - 1, 0)
        elif tag in ("i", "em"):
            self.cursiva = max(self.cursiva - 1, 0)
        elif tag in self.BLOQUES:
            self._cerrar()
            if tag == "pre":
                self.en_pre = False
            elif tag in ("ul", "ol") and self.listas:
                self.listas.pop()
                if not self.listas:
                    self.res.lineas.append("")

    def handle_data(self, data):
        if self.en_title:
            self.titulo_pagina += data
        elif not self.ignorar:
            self.actual.append((data, self.negrita > 0, self.cursiva > 0))

    def _imagen(self, src, alt):
        if src.startswith("data:"):
            m = re.match(r"data:image/(\w+);base64,(.*)", src, re.S)
            if m:
                return self.res.imagen(f"{alt or 'imagen'}.{m[1].replace('jpeg', 'jpg')}", base64.b64decode(m[2]))
            return ""
        if re.match(r"[a-z]+:", src, re.I) and not src.lower().startswith("file:"):
            return f"![{alt}]({src})"     # imagen de internet: se deja el enlace
        ruta = Path(urllib.parse.unquote(urllib.parse.urlparse(src).path.lstrip("/") if src.lower().startswith("file:")
                                         else urllib.parse.unquote(src)))
        if not ruta.is_absolute():
            ruta = self.carpeta / ruta
        if ruta.is_file():
            return self.res.imagen(ruta.name, ruta.read_bytes())
        return ""


def _leer_texto(ruta):
    datos = ruta.read_bytes()
    for codif in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return datos.decode(codif)
        except UnicodeDecodeError:
            continue
    return datos.decode("utf-8", "replace")


def _html(ruta):
    res = Resultado(ruta.stem)
    lector = _LectorHTML(res, ruta.parent)
    lector.feed(_leer_texto(ruta))
    lector._cerrar()
    lector.close()
    if lector.titulo_pagina.strip():
        res.titulo = html.unescape(lector.titulo_pagina.strip())
    return res.dict()


# ---------- Markdown y texto ----------
def _md(ruta):
    texto = _leer_texto(ruta).replace("\r\n", "\n")
    res = Resultado(ruta.stem)
    m = re.match(r"---\n(.*?)\n---\n", texto, re.S)          # cabecera YAML (Obsidian, Apúntalo...)
    if m:
        t = re.search(r"^(?:titulo|title):\s*(.+)$", m[1], re.M)
        if t:
            res.titulo = t[1].strip().strip("\"'")
        texto = texto[m.end():]
    else:
        m = re.match(r"\s*#\s+(.+)\n", texto)                 # el primer «# Título» pasa a ser el título
        if m:
            res.titulo = m[1].strip()
            texto = texto[m.end():]

    def cambiar(m):
        objetivo = urllib.parse.unquote(m[3])
        if re.match(r"[a-z]+:", objetivo, re.I):
            return m[0]
        archivo = (ruta.parent / objetivo).resolve()
        if archivo.is_file() and archivo.suffix.lower() in EXT_IMAGEN:
            return res.imagen(archivo.name, archivo.read_bytes())
        return m[0]

    res.lineas = [re.sub(r"(!)\[([^\]]*)\]\(<?([^)>]+)>?\)", cambiar, texto)]
    return res.dict()


def _txt(ruta):
    res = Resultado(ruta.stem)
    res.lineas = [_leer_texto(ruta).replace("\r\n", "\n")]
    return res.dict()


def importar(ruta):
    ruta = Path(ruta)
    ext = ruta.suffix.lower()
    if ext == ".docx":
        return _docx(ruta)
    if ext == ".odt":
        return _odt(ruta)
    if ext in (".html", ".htm"):
        return _html(ruta)
    if ext in (".md", ".markdown"):
        return _md(ruta)
    if ext == ".txt":
        return _txt(ruta)
    raise ValueError(f"No sé importar archivos {ext or 'sin extensión'}. "
                     "Usa Word (.docx), LibreOffice (.odt), página web (.html), Markdown (.md) o texto (.txt).")
