"""Exporta apuntes Markdown a PDF (vía Microsoft Edge), Word, OpenDocument, HTML, Markdown y texto,
sin librerías externas."""
import base64
import html
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path

from .editor import ESTILO_BLOQUE

# ---------- Markdown (subconjunto) ----------
INLINE = re.compile(r"(\*\*.+?\*\*|__.+?__|`[^`]+`|\*[^*\s][^*]*?\*|!?\[[^\]]*\]\(<?[^)>]*>?\))")


def trozos(texto):
    """Devuelve [(texto, negrita, cursiva, codigo)]."""
    out = []
    for parte in INLINE.split(texto):
        if not parte:
            continue
        if (parte.startswith("**") and parte.endswith("**") or parte.startswith("__") and parte.endswith("__")) and len(parte) > 4:
            out += [(t, True, i, c) for t, _, i, c in trozos(parte[2:-2])]
        elif parte.startswith("`") and parte.endswith("`") and len(parte) > 2:
            out.append((parte[1:-1], False, False, True))
        elif parte.startswith("*") and parte.endswith("*") and len(parte) > 2:
            out += [(t, b, True, c) for t, b, _, c in trozos(parte[1:-1])]
        elif re.fullmatch(r"\[[^\]]*\]\(<?[^)>]*>?\)", parte):
            out.append((parte[1:parte.index("](")], False, False, False))
        else:
            out.append((parte, False, False, False))
    return out


def bloques(md):
    res, en_codigo, codigo = [], False, []
    for linea in md.splitlines():
        if linea.strip().startswith("```"):
            if en_codigo:
                res.append({"tipo": "codigo", "texto": "\n".join(codigo)})
                codigo = []
            en_codigo = not en_codigo
            continue
        if en_codigo:
            codigo.append(linea)
            continue
        s = linea.strip()
        if not s:
            continue
        nivel = (len(linea) - len(linea.lstrip(" \t").replace("\t", "    "))) // 2
        if m := re.fullmatch(r"(#{1,3})\s+(.*)", s):
            res.append({"tipo": "h" + str(len(m[1])), "texto": m[2]})
        elif re.fullmatch(r"(-{3,}|\*{3,})", s):
            res.append({"tipo": "hr"})
        elif m := re.fullmatch(r"!\[([^\]]*)\]\(<?([^)>]*)>?\)", s):
            res.append({"tipo": "img", "texto": m[1], "src": m[2]})
        elif m := re.fullmatch(r"[-*+]\s+\[( |x|X)\]\s*(.*)", s):
            res.append({"tipo": "tarea", "hecha": m[1] != " ", "texto": m[2], "nivel": nivel})
        elif m := re.fullmatch(r"([-*+•→])\s+(.*)", s):
            res.append({"tipo": "ul", "texto": m[2], "nivel": nivel, "marca": "→" if m[1] == "→" else "•"})
        elif m := re.fullmatch(r"(\d+|(?=[ivx])x{0,3}(?:ix|iv|v?i{0,3})|[a-z])[.)]\s+(.*)", s):
            # 1. 2. 3. / a. b. c. / i. ii. iii. (las listas con letras y romanos del editor)
            res.append({"tipo": "ol", "num": m[1], "texto": m[2], "nivel": nivel})
        elif s.startswith(">"):
            res.append({"tipo": "cita", "texto": s.lstrip("> ")})
        else:
            res.append({"tipo": "p", "texto": s})
    if codigo:
        res.append({"tipo": "codigo", "texto": "\n".join(codigo)})
    return res


def subtitulo(nota):
    partes = []
    if nota.get("asignatura"):
        partes.append("Asignatura: " + nota["asignatura"])
    if nota.get("fecha"):
        partes.append("Fecha: " + nota["fecha"])
    if nota.get("etiquetas"):
        partes.append("Etiquetas: " + ", ".join(nota["etiquetas"]))
    return "  ·  ".join(partes)


# ---------- HTML / PDF ----------
def _inline_html(texto):
    out = ""
    for t, b, i, c in trozos(texto):
        t = html.escape(t)
        if c:
            t = f"<code>{t}</code>"
        if i:
            t = f"<em>{t}</em>"
        if b:
            t = f"<strong>{t}</strong>"
        out += t
    return out


TIPOS_IMAGEN = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif"}


def a_html(notas, titulo_doc, incrustar=False):
    """HTML de los apuntes. Con incrustar=True las imágenes van dentro del archivo (página portable)."""
    cuerpo = []
    for n, nota in enumerate(notas):
        cuerpo.append(f'<section{" class=salto" if n else ""}><h1>{html.escape(nota["titulo"])}</h1>'
                      f'<p class=sub>{html.escape(subtitulo(nota))}</p>')
        for b in bloques(nota["cuerpo"]):
            t, sangria = b["tipo"], b.get("nivel", 0) * 18
            if t in ("h1", "h2", "h3"):
                nivel = int(t[1]) + 1
                cuerpo.append(f"<h{nivel}>{_inline_html(b['texto'])}</h{nivel}>")
            elif t == "hr":
                cuerpo.append("<hr>")
            elif t == "img":
                src = (Path(nota["carpeta"]) / b["src"]).resolve()
                if src.suffix.lower() == ".pdf" or not src.exists():
                    cuerpo.append(f"<p class=adj>[Adjunto: {html.escape(b['texto'])}]</p>")
                else:
                    url = src.as_uri()
                    if incrustar and src.suffix.lower() in TIPOS_IMAGEN:
                        url = f"data:{TIPOS_IMAGEN[src.suffix.lower()]};base64," + \
                              base64.b64encode(src.read_bytes()).decode("ascii")
                    cuerpo.append(f'<p><img src="{url}" alt="{html.escape(b["texto"])}"></p>')
            elif t in ("ul", "ol", "tarea"):
                marca = {"ul": b.get("marca", "•"), "ol": b.get("num", "") + ".", "tarea": "☑" if b.get("hecha") else "☐"}[t]
                cuerpo.append(f'<p class=li style="margin-left:{sangria}px"><span class=m>{marca}</span>'
                              f"{_inline_html(b['texto'])}</p>")
            elif t == "codigo":
                cuerpo.append(f"<pre>{html.escape(b['texto'])}</pre>")
            elif t == "cita":
                clase = next((f" class={n}" for e, n in ESTILO_BLOQUE.items() if b["texto"].startswith(e)), "")
                cuerpo.append(f"<blockquote{clase}>{_inline_html(b['texto'])}</blockquote>")
            else:
                cuerpo.append(f"<p>{_inline_html(b['texto'])}</p>")
        cuerpo.append("</section>")
    return f"""<!doctype html><html lang=es><head><meta charset=utf-8><title>{html.escape(titulo_doc)}</title>
<style>
@page {{ size: A4; margin: 2cm; }}
body {{ font-family: Calibri, "Segoe UI", Arial, sans-serif; font-size: 11.5pt; line-height: 1.45; color: #222; }}
h1 {{ font-size: 20pt; margin: 0 0 2pt; color: #1F3864; }}
h2 {{ font-size: 15pt; margin: 14pt 0 4pt; color: #2F5496; border-bottom: 1px solid #ccd; }}
h3 {{ font-size: 13pt; margin: 10pt 0 3pt; color: #2F5496; }}
h4 {{ font-size: 11.5pt; margin: 8pt 0 2pt; }}
p {{ margin: 3pt 0; }}
.sub {{ color: #666; font-size: 10pt; margin-bottom: 12pt; }}
.li {{ padding-left: 20px; text-indent: -20px; }} .m {{ display: inline-block; width: 20px; text-indent: 0; }}
.adj {{ color: #777; font-style: italic; }}
pre, code {{ font-family: Consolas, monospace; background: #f3f3f3; }}
pre {{ padding: 6pt; white-space: pre-wrap; }}
blockquote {{ border-left: 3px solid #bbb; margin: 4pt 0; padding-left: 8pt; color: #555; }}
blockquote[class] {{ color: #222; padding: 6pt 10pt; border-radius: 4pt; }}
.idea {{ background: #FFF6D6; border-color: #E8B800; }} .ojo {{ background: #FFE6E2; border-color: #E0533D; }}
.resumen {{ background: #E3F5E6; border-color: #3E9B52; }} .nota {{ background: #EEF0F4; border-color: #8A90A0; }}
.pregunta {{ background: #EFE8FB; border-color: #7B5CC4; }} .definicion {{ background: #E3EEFB; border-color: #2F5496; }}
img {{ max-width: 100%; }}
.salto {{ break-before: page; }}
</style></head><body>{"".join(cuerpo)}</body></html>"""


def buscar_edge():
    for base in (r"C:\Program Files (x86)", r"C:\Program Files"):
        p = Path(base) / "Microsoft/Edge/Application/msedge.exe"
        if p.exists():
            return p
    for nombre in ("msedge", "chrome"):
        if r := shutil.which(nombre):
            return Path(r)
    return None


def a_pdf(notas, destino, titulo_doc):
    edge = buscar_edge()
    if not edge:
        raise RuntimeError("No encuentro Microsoft Edge para crear el PDF. Exporta a Word y guárdalo como PDF desde allí.")
    with tempfile.TemporaryDirectory() as tmp:
        pagina = Path(tmp) / "apuntes.html"
        pagina.write_text(a_html(notas, titulo_doc), encoding="utf-8")
        destino = Path(destino).resolve()
        if destino.exists():
            destino.unlink()
        subprocess.run([str(edge), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        f"--user-data-dir={Path(tmp) / 'perfil'}", "--allow-file-access-from-files",
                        f"--print-to-pdf={destino}", pagina.as_uri()],
                       timeout=90, capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if not destino.exists():
        raise RuntimeError("Edge no pudo generar el PDF.")
    return destino


# ---------- DOCX ----------
def _x(t):
    return html.escape(t, quote=False)


def _runs(texto, extra=""):
    out = ""
    for t, b, i, c in trozos(texto):
        # orden exigido por Word: rFonts, b, i, color, shd
        rpr = ('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>' if c else "") + ("<w:b/>" if b else "") +               ("<w:i/>" if i or "<w:i/>" in extra else "") + extra.replace("<w:i/>", "") +               ('<w:shd w:val="clear" w:fill="F0F0F0"/>' if c else "")
        out += f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{_x(t)}</w:t></w:r>'
    return out


def _p(contenido, estilo=None, ind=None, salto=False):
    ppr = (f'<w:pStyle w:val="{estilo}"/>' if estilo else "") + (
        f'<w:ind w:left="{ind}" w:hanging="300"/>' if ind else "")
    pre = '<w:r><w:br w:type="page"/></w:r>' if salto else ""
    return f"<w:p><w:pPr>{ppr}</w:pPr>{pre}{contenido}</w:p>"


ANCHO_UTIL_EMU = 9638 * 635        # ancho de texto de la página A4 con márgenes de 2 cm
EMU_POR_PIXEL = 9525               # a 96 ppp


def tamano_imagen(datos):
    """(ancho, alto) en píxeles de un PNG o JPEG, o None."""
    if datos[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", datos[16:24])
    if datos[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(datos):
            if datos[i] != 0xFF:
                i += 1
                continue
            marca = datos[i + 1]
            if marca in (0xD8, 0x01) or 0xD0 <= marca <= 0xD7:
                i += 2
                continue
            largo = struct.unpack(">H", datos[i + 2:i + 4])[0]
            if 0xC0 <= marca <= 0xCF and marca not in (0xC4, 0xC8, 0xCC):
                alto, ancho = struct.unpack(">HH", datos[i + 5:i + 9])
                return ancho, alto
            i += 2 + largo
    return None


def _imagen_docx(ruta, imagenes):
    """XML de una imagen incrustada (PNG/JPEG) y la registra en `imagenes`; None si no se puede."""
    try:
        datos = ruta.read_bytes()
    except OSError:
        return None
    tam = tamano_imagen(datos)
    if not tam or not all(tam):
        return None
    ext = "png" if datos[:4] == b"\x89PNG" else "jpeg"
    n = len(imagenes) + 1
    rid = f"rIdImg{n}"
    imagenes.append((rid, f"media/imagen{n}.{ext}", datos))
    cx, cy = tam[0] * EMU_POR_PIXEL, tam[1] * EMU_POR_PIXEL
    if cx > ANCHO_UTIL_EMU:
        cx, cy = ANCHO_UTIL_EMU, int(cy * ANCHO_UTIL_EMU / cx)
    return (f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{n}" name="Imagen {n}"/>'
            '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:nvPicPr><pic:cNvPr id="{n}" name="imagen{n}.{ext}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
            "</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>")


def a_docx(notas, destino, titulo_doc):
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    WP = ' xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"'
    imagenes = []
    cuerpo = []
    for n, nota in enumerate(notas):
        cuerpo.append(_p(_runs(nota["titulo"]), "Title", salto=bool(n)))
        cuerpo.append(_p(_runs(subtitulo(nota)), "Subtitle"))
        for b in bloques(nota["cuerpo"]):
            t = b["tipo"]
            if t in ("h1", "h2", "h3"):
                cuerpo.append(_p(_runs(b["texto"]), "Heading" + t[1]))
            elif t == "hr":
                cuerpo.append('<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="999999"/>'
                              "</w:pBdr></w:pPr></w:p>")
            elif t == "img":
                src = (Path(nota.get("carpeta", ".")) / b["src"]).resolve()
                dibujo = _imagen_docx(src, imagenes)
                if dibujo:
                    cuerpo.append(f'<w:p><w:pPr><w:spacing w:before="80" w:after="120"/></w:pPr>{dibujo}</w:p>')
                else:
                    cuerpo.append(_p(_runs(f"[Adjunto: {b['texto']}]", '<w:i/><w:color w:val="777777"/>')))
            elif t in ("ul", "ol", "tarea"):
                marca = {"ul": b.get("marca", "•"), "ol": b.get("num", "") + ".", "tarea": "☑" if b.get("hecha") else "☐"}[t]
                cuerpo.append(_p(f'<w:r><w:t xml:space="preserve">{_x(marca)}</w:t></w:r><w:r><w:tab/></w:r>'
                                 + _runs(b["texto"]), "Lista", ind=660 + 360 * b.get("nivel", 0)))
            elif t == "codigo":
                lineas = b["texto"].split("\n")
                runs = "".join(('<w:r><w:br/></w:r>' if k else "") +
                               f'<w:r><w:t xml:space="preserve">{_x(l)}</w:t></w:r>' for k, l in enumerate(lineas))
                cuerpo.append(_p(runs, "Codigo"))
            elif t == "cita":
                cuerpo.append(_p(_runs(b["texto"]), "Quote"))
            else:
                cuerpo.append(_p(_runs(b["texto"])))
    documento = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}{WP}><w:body>'
                 + "".join(cuerpo) +
                 '<w:sectPr><w:headerReference w:type="default" r:id="rIdH"/>'
                 '<w:footerReference w:type="default" r:id="rIdF"/>'
                 '<w:pgSz w:w="11906" w:h="16838"/>'
                 '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="567" w:footer="567" w:gutter="0"/>'
                 "</w:sectPr></w:body></w:document>")
    cabecera = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr {W}>'
                f'<w:p><w:pPr><w:jc w:val="right"/></w:pPr><w:r><w:rPr><w:color w:val="888888"/><w:sz w:val="18"/></w:rPr>'
                f'<w:t xml:space="preserve">{_x(titulo_doc)}</w:t></w:r></w:p></w:hdr>')
    pie = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {W}><w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
           '<w:r><w:rPr><w:color w:val="888888"/><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="begin"/></w:r>'
           '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>'
           "</w:p></w:ftr>")

    def estilo(id_, nombre, rpr="", ppr="", tipo="paragraph"):
        return (f'<w:style w:type="{tipo}" w:styleId="{id_}"><w:name w:val="{nombre}"/><w:basedOn w:val="Normal"/>'
                f'<w:qFormat/><w:pPr>{ppr}</w:pPr><w:rPr>{rpr}</w:rPr></w:style>')

    azul = '<w:color w:val="2F5496"/>'
    estilos = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W}>'
               '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri" w:eastAsia="Calibri"/>'
               '<w:sz w:val="23"/><w:lang w:val="es-ES"/></w:rPr></w:rPrDefault>'
               '<w:pPrDefault><w:pPr><w:spacing w:after="60" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
               '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
               + estilo("Title", "Title", '<w:b/><w:color w:val="1F3864"/><w:sz w:val="40"/>', '<w:spacing w:after="0"/>')
               + estilo("Subtitle", "Subtitle", '<w:color w:val="666666"/><w:sz w:val="20"/>', '<w:spacing w:after="240"/>')
               + estilo("Heading1", "heading 1", '<w:b/>' + azul + '<w:sz w:val="30"/>',
                        '<w:keepNext/><w:pBdr><w:bottom w:val="single" w:sz="4" w:space="1" w:color="CCCCDD"/></w:pBdr>'
                        '<w:spacing w:before="280" w:after="80"/><w:outlineLvl w:val="0"/>')
               + estilo("Heading2", "heading 2", '<w:b/>' + azul + '<w:sz w:val="26"/>',
                        '<w:keepNext/><w:spacing w:before="200" w:after="60"/><w:outlineLvl w:val="1"/>')
               + estilo("Heading3", "heading 3", '<w:b/><w:sz w:val="23"/>',
                        '<w:keepNext/><w:spacing w:before="160" w:after="40"/><w:outlineLvl w:val="2"/>')
               + estilo("Lista", "Lista", "", '<w:tabs><w:tab w:val="left" w:pos="0"/></w:tabs><w:spacing w:after="20"/>')
               + estilo("Codigo", "Codigo", '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="20"/>',
                        '<w:shd w:val="clear" w:fill="F3F3F3"/>')
               + estilo("Quote", "Quote", '<w:i/><w:color w:val="555555"/>',
                        '<w:pBdr><w:left w:val="single" w:sz="12" w:space="6" w:color="BBBBBB"/></w:pBdr><w:ind w:left="360"/>')
               + "</w:styles>")
    tipos = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Default Extension="png" ContentType="image/png"/>'
             '<Default Extension="jpeg" ContentType="image/jpeg"/>'
             '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
             '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
             '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
             '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
             '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
             "</Types>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            "</Relationships>")
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rIdS" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                '<Relationship Id="rIdH" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>'
                '<Relationship Id="rIdF" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
                + "".join(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                          f'relationships/image" Target="{ruta}"/>' for rid, ruta, _ in imagenes)
                + "</Relationships>")
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f"<dc:title>{_x(titulo_doc)}</dc:title><dc:creator>Apúntalo</dc:creator></cp:coreProperties>")
    destino = Path(destino)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", tipos)
        z.writestr("_rels/.rels", rels)
        z.writestr("docProps/core.xml", core)
        z.writestr("word/document.xml", documento)
        z.writestr("word/styles.xml", estilos)
        z.writestr("word/header1.xml", cabecera)
        z.writestr("word/footer1.xml", pie)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        for _, ruta, datos in imagenes:
            z.writestr("word/" + ruta, datos)
    return destino


# ---------- Página web (un solo archivo) ----------
def a_html_archivo(notas, destino, titulo_doc):
    destino = Path(destino)
    destino.write_text(a_html(notas, titulo_doc, incrustar=True), encoding="utf-8")
    return destino


# ---------- Markdown ----------
ENLACE = re.compile(r"(!?)\[([^\]]*)\]\(<?([^)>]*)>?\)")


def a_md(notas, destino, titulo_doc):
    """Un .md con todos los apuntes. Las imágenes y adjuntos se copian a «<nombre>_archivos»."""
    destino = Path(destino)
    carpeta_arch = destino.with_name(destino.stem + "_archivos")
    copiados = {}

    def cambiar(m, nota):
        objetivo = m[3]
        if re.match(r"[a-z]+:", objetivo, re.I):        # enlace web: se deja igual
            return m[0]
        src = (Path(nota.get("carpeta", ".")) / objetivo).resolve()
        if not src.is_file():
            return m[0]
        if src not in copiados:
            carpeta_arch.mkdir(exist_ok=True)
            nombre, n = src.name, 1
            while (carpeta_arch / nombre).exists():
                n += 1
                nombre = f"{src.stem} ({n}){src.suffix}"
            shutil.copy2(src, carpeta_arch / nombre)
            copiados[src] = nombre
        return f"{m[1]}[{m[2]}](<{carpeta_arch.name}/{copiados[src]}>)"

    partes = []
    for nota in notas:
        lineas, en_codigo = [], False
        for linea in nota["cuerpo"].splitlines():
            if linea.strip().startswith("```"):
                en_codigo = not en_codigo
            elif not en_codigo:
                if re.match(r"#{1,5}\s", linea):
                    linea = "#" + linea                   # el título del apunte es el «#»
                linea = ENLACE.sub(lambda m: cambiar(m, nota), linea)
            lineas.append(linea)
        sub = subtitulo(nota)
        partes.append(f"# {nota['titulo']}\n\n" + (f"*{sub}*\n\n" if sub else "") + "\n".join(lineas).strip() + "\n")
    destino.write_text("\n---\n\n".join(partes), encoding="utf-8")
    return destino


# ---------- Texto sin formato ----------
def _plano(texto):
    return "".join(t for t, *_ in trozos(texto))


def a_txt(notas, destino, titulo_doc):
    salida = []
    for n, nota in enumerate(notas):
        if n:
            salida += ["", "=" * 60, ""]
        salida += [nota["titulo"].upper(), "=" * len(nota["titulo"])]
        if sub := subtitulo(nota):
            salida.append(sub)
        salida.append("")
        for b in bloques(nota["cuerpo"]):
            t, sangria = b["tipo"], "  " * b.get("nivel", 0)
            if t in ("h1", "h2", "h3"):
                texto = _plano(b["texto"])
                salida += ["", texto, ("=" if t == "h1" else "-") * len(texto)]
            elif t == "hr":
                salida.append("-" * 40)
            elif t == "img":
                salida.append(f"[Imagen: {b['texto']}]")
            elif t == "ul":
                salida.append(f"{sangria}{b.get('marca', '•')} {_plano(b['texto'])}")
            elif t == "ol":
                salida.append(f"{sangria}{b['num']}. {_plano(b['texto'])}")
            elif t == "tarea":
                salida.append(f"{sangria}[{'x' if b['hecha'] else ' '}] {_plano(b['texto'])}")
            elif t == "codigo":
                salida += ["    " + l for l in b["texto"].split("\n")]
            elif t == "cita":
                salida.append("  | " + _plano(b["texto"]))
            else:
                salida.append(_plano(b["texto"]))
    destino = Path(destino)
    destino.write_text("\n".join(salida).rstrip() + "\n", encoding="utf-8")
    return destino


# ---------- OpenDocument (.odt, LibreOffice) ----------
NS_ODF = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
          'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
          'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
          'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
          'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" '
          'xmlns:xlink="http://www.w3.org/1999/xlink" '
          'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" '
          'xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0" '
          'xmlns:dc="http://purl.org/dc/elements/1.1/" office:version="1.3"')
ANCHO_UTIL_CM = 17.0


def _odt_texto(t):
    t = _x(t).replace("\t", "<text:tab/>")
    return re.sub(r"  +", lambda m: f' <text:s text:c="{len(m[0]) - 1}"/>', t)


def _odt_runs(texto):
    out = ""
    for t, b, i, c in trozos(texto):
        estilo = "Tc" if c else {(True, True): "Tbi", (True, False): "Tb", (False, True): "Ti"}.get((b, i))
        out += f'<text:span text:style-name="{estilo}">{_odt_texto(t)}</text:span>' if estilo else _odt_texto(t)
    return out


def a_odt(notas, destino, titulo_doc):
    imagenes, cuerpo = [], []

    def p(contenido, estilo="Standard"):
        cuerpo.append(f'<text:p text:style-name="{estilo}">{contenido}</text:p>')

    for n, nota in enumerate(notas):
        p(_odt_runs(nota["titulo"]), "Salto" if n else "Titulo")
        p(_odt_runs(subtitulo(nota)), "Subtitulo")
        for b in bloques(nota["cuerpo"]):
            t = b["tipo"]
            if t in ("h1", "h2", "h3"):
                cuerpo.append(f'<text:h text:style-name="Heading_20_{t[1]}" text:outline-level="{t[1]}">'
                              f'{_odt_runs(b["texto"])}</text:h>')
            elif t == "hr":
                p("", "Raya")
            elif t == "img":
                src = (Path(nota.get("carpeta", ".")) / b["src"]).resolve()
                datos = src.read_bytes() if src.is_file() else b""
                tam = tamano_imagen(datos) if datos else None
                if tam and all(tam):
                    ext = "png" if datos[:4] == b"\x89PNG" else "jpg"
                    ruta = f"Pictures/imagen{len(imagenes) + 1}.{ext}"
                    imagenes.append((ruta, datos, "image/png" if ext == "png" else "image/jpeg"))
                    ancho, alto = tam[0] * 2.54 / 96, tam[1] * 2.54 / 96
                    if ancho > ANCHO_UTIL_CM:
                        ancho, alto = ANCHO_UTIL_CM, alto * ANCHO_UTIL_CM / ancho
                    p(f'<draw:frame draw:style-name="fr1" draw:name="Imagen {len(imagenes)}" text:anchor-type="as-char" '
                      f'svg:width="{ancho:.3f}cm" svg:height="{alto:.3f}cm"><draw:image xlink:href="{ruta}" '
                      'xlink:type="simple" xlink:show="embed" xlink:actuate="onLoad"/></draw:frame>')
                else:
                    p(f'<text:span text:style-name="Ti">{_odt_texto("[Adjunto: " + b["texto"] + "]")}</text:span>')
            elif t in ("ul", "ol", "tarea"):
                marca = {"ul": b.get("marca", "•"), "ol": b.get("num", "") + ".", "tarea": "☑" if b.get("hecha") else "☐"}[t]
                p(f"{_x(marca)}<text:tab/>{_odt_runs(b['texto'])}", f"Lista{min(b.get('nivel', 0), 5)}")
            elif t == "codigo":
                p("<text:line-break/>".join(_odt_texto(l) for l in b["texto"].split("\n")), "Codigo")
            elif t == "cita":
                p(_odt_runs(b["texto"]), "Cita")
            else:
                p(_odt_runs(b["texto"]))

    listas = "".join(
        f'<style:style style:name="Lista{k}" style:family="paragraph" style:parent-style-name="Standard">'
        f'<style:paragraph-properties fo:margin-left="{0.6 + 0.6 * k:.1f}cm" fo:text-indent="-0.5cm" fo:margin-bottom="0.05cm">'
        f'<style:tab-stops><style:tab-stop style:position="0cm"/></style:tab-stops></style:paragraph-properties></style:style>'
        for k in range(6))
    contenido = (f'<?xml version="1.0" encoding="UTF-8"?><office:document-content {NS_ODF}><office:automatic-styles>'
                 '<style:style style:name="Salto" style:family="paragraph" style:parent-style-name="Titulo">'
                 '<style:paragraph-properties fo:break-before="page"/></style:style>'
                 '<style:style style:name="Tb" style:family="text"><style:text-properties fo:font-weight="bold"/></style:style>'
                 '<style:style style:name="Ti" style:family="text"><style:text-properties fo:font-style="italic"/></style:style>'
                 '<style:style style:name="Tbi" style:family="text"><style:text-properties fo:font-weight="bold" fo:font-style="italic"/></style:style>'
                 '<style:style style:name="Tc" style:family="text"><style:text-properties '
                 'fo:font-family="Consolas" fo:background-color="#F0F0F0"/></style:style>'
                 '<style:style style:name="fr1" style:family="graphic"><style:graphic-properties '
                 'style:vertical-pos="top" style:vertical-rel="baseline"/></style:style>'
                 + listas + '</office:automatic-styles><office:body><office:text>'
                 + "".join(cuerpo) + "</office:text></office:body></office:document-content>")

    def estilo(nombre, visible, texto="", parrafo="", extra=""):
        return (f'<style:style style:name="{nombre}" style:display-name="{visible}" style:family="paragraph" '
                f'style:parent-style-name="Standard"{extra}><style:paragraph-properties {parrafo}/>'
                f'<style:text-properties {texto}/></style:style>')

    estilos = (f'<?xml version="1.0" encoding="UTF-8"?><office:document-styles {NS_ODF}><office:styles>'
               '<style:default-style style:family="paragraph"><style:paragraph-properties fo:margin-bottom="0.1cm" '
               'fo:line-height="115%"/><style:text-properties fo:font-family="Calibri" '
               'fo:font-size="11.5pt" fo:language="es" fo:country="ES"/></style:default-style>'
               '<style:style style:name="Standard" style:family="paragraph" style:class="text"/>'
               + estilo("Titulo", "Título", 'fo:font-size="20pt" fo:font-weight="bold" fo:color="#1F3864"', 'fo:margin-bottom="0cm"')
               + estilo("Subtitulo", "Subtítulo", 'fo:font-size="10pt" fo:color="#666666"', 'fo:margin-bottom="0.4cm"')
               + estilo("Heading_20_1", "Heading 1", 'fo:font-size="15pt" fo:font-weight="bold" fo:color="#2F5496"',
                        'fo:margin-top="0.45cm" fo:margin-bottom="0.15cm" fo:keep-with-next="always" '
                        'fo:border-bottom="0.5pt solid #CCCCDD" fo:padding-bottom="0.05cm"',
                        ' style:default-outline-level="1"')
               + estilo("Heading_20_2", "Heading 2", 'fo:font-size="13pt" fo:font-weight="bold" fo:color="#2F5496"',
                        'fo:margin-top="0.35cm" fo:margin-bottom="0.1cm" fo:keep-with-next="always"',
                        ' style:default-outline-level="2"')
               + estilo("Heading_20_3", "Heading 3", 'fo:font-size="11.5pt" fo:font-weight="bold"',
                        'fo:margin-top="0.3cm" fo:margin-bottom="0.05cm" fo:keep-with-next="always"',
                        ' style:default-outline-level="3"')
               + estilo("Cita", "Cita", 'fo:font-style="italic" fo:color="#555555"',
                        'fo:margin-left="0.6cm" fo:border-left="1.5pt solid #BBBBBB" fo:padding-left="0.2cm"')
               + estilo("Codigo", "Código", 'fo:font-family="Consolas" fo:font-size="10pt"',
                        'fo:background-color="#F3F3F3" fo:padding="0.1cm"')
               + estilo("Raya", "Raya", "", 'fo:border-bottom="0.5pt solid #999999"')
               + '</office:styles><office:automatic-styles><style:page-layout style:name="pm1">'
               '<style:page-layout-properties fo:page-width="21cm" fo:page-height="29.7cm" fo:margin-top="2cm" '
               'fo:margin-bottom="2cm" fo:margin-left="2cm" fo:margin-right="2cm"/></style:page-layout>'
               '</office:automatic-styles><office:master-styles><style:master-page style:name="Standard" '
               'style:page-layout-name="pm1"/></office:master-styles></office:document-styles>')
    meta = (f'<?xml version="1.0" encoding="UTF-8"?><office:document-meta {NS_ODF}><office:meta>'
            f"<dc:title>{_x(titulo_doc)}</dc:title><meta:generator>Apúntalo</meta:generator>"
            "</office:meta></office:document-meta>")
    manifiesto = ('<?xml version="1.0" encoding="UTF-8"?>'
                  '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3">'
                  '<manifest:file-entry manifest:full-path="/" manifest:version="1.3" '
                  'manifest:media-type="application/vnd.oasis.opendocument.text"/>'
                  + "".join(f'<manifest:file-entry manifest:full-path="{n}" manifest:media-type="text/xml"/>'
                            for n in ("content.xml", "styles.xml", "meta.xml"))
                  + "".join(f'<manifest:file-entry manifest:full-path="{r}" manifest:media-type="{m}"/>'
                            for r, _, m in imagenes)
                  + "</manifest:manifest>")
    destino = Path(destino)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.text",
                   compress_type=zipfile.ZIP_STORED)          # debe ir primero y sin comprimir
        z.writestr("META-INF/manifest.xml", manifiesto)
        z.writestr("content.xml", contenido)
        z.writestr("styles.xml", estilos)
        z.writestr("meta.xml", meta)
        for ruta, datos, _ in imagenes:
            z.writestr(ruta, datos)
    return destino


# ---------- Catálogo para la ventana «Exportar» ----------
# clave: (nombre, extensión, para qué sirve, función)
FORMATOS = {
    "pdf": ("PDF", ".pdf", "Para imprimir, enviar o subir a la plataforma de clase.", a_pdf),
    "docx": ("Word", ".docx", "Para seguir editando en Word, Google Docs o LibreOffice.", a_docx),
    "odt": ("OpenDocument", ".odt", "Para LibreOffice u OpenOffice (formato libre).", a_odt),
    "html": ("Página web", ".html", "Se abre en cualquier navegador o móvil, con las imágenes dentro.", a_html_archivo),
    "md": ("Markdown", ".md", "Para Obsidian, Notion o GitHub. Las imágenes van en una carpeta aparte.", a_md),
    "txt": ("Texto sin formato", ".txt", "Solo el texto, para cualquier programa.", a_txt),
}


def exportar_como(formato, notas, destino, titulo_doc):
    return FORMATOS[formato][3](notas, destino, titulo_doc)
