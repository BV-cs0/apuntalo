"""Exporta apuntes Markdown a PDF (vía Microsoft Edge) y a DOCX (Word), sin librerías externas."""
import html
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

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
        elif m := re.fullmatch(r"[-*+]\s+(.*)", s):
            res.append({"tipo": "ul", "texto": m[1], "nivel": nivel})
        elif m := re.fullmatch(r"(\d+)[.)]\s+(.*)", s):
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


def a_html(notas, titulo_doc):
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
                    cuerpo.append(f'<p><img src="{src.as_uri()}" alt="{html.escape(b["texto"])}"></p>')
            elif t in ("ul", "ol", "tarea"):
                marca = {"ul": "•", "ol": b.get("num", "") + ".", "tarea": "☑" if b.get("hecha") else "☐"}[t]
                cuerpo.append(f'<p class=li style="margin-left:{sangria}px"><span class=m>{marca}</span>'
                              f"{_inline_html(b['texto'])}</p>")
            elif t == "codigo":
                cuerpo.append(f"<pre>{html.escape(b['texto'])}</pre>")
            elif t == "cita":
                cuerpo.append(f"<blockquote>{_inline_html(b['texto'])}</blockquote>")
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


def a_docx(notas, destino, titulo_doc):
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
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
                cuerpo.append(_p(_runs(f"[Adjunto: {b['texto']}]", '<w:i/><w:color w:val="777777"/>')))
            elif t in ("ul", "ol", "tarea"):
                marca = {"ul": "•", "ol": b.get("num", "") + ".", "tarea": "☑" if b.get("hecha") else "☐"}[t]
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
    documento = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>'
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
                "</Relationships>")
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f"<dc:title>{_x(titulo_doc)}</dc:title><dc:creator>Apuntes</dc:creator></cp:coreProperties>")
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
    return destino
