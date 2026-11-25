"""Pruebas de Apúntalo. Ejecutar desde la carpeta del proyecto:  py -3 -m unittest -v"""
import sys
import tempfile
import unittest
import xml.dom.minidom
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from apuntalo import app as ap, editor, exportar, mapa  # noqa: E402


class TemporalMixin:
    """Redirige las carpetas de datos de la app a una carpeta temporal."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self._antes = (ap.BASE, ap.NOTAS, ap.ADJUNTOS, ap.CONFIG)
        ap.BASE, ap.NOTAS = base, base / "notas"
        ap.ADJUNTOS, ap.CONFIG = ap.NOTAS / "_adjuntos", base / "config.json"

    def tearDown(self):
        ap.BASE, ap.NOTAS, ap.ADJUNTOS, ap.CONFIG = self._antes
        self._tmp.cleanup()


class TestNotas(TemporalMixin, unittest.TestCase):
    def test_slug_quita_caracteres_prohibidos(self):
        self.assertEqual(ap.slug('Tema 1: ¿qué es "x"?'), "Tema 1 ¿qué es x")
        self.assertEqual(ap.slug("  ..  "), "sin titulo")

    def test_guardar_y_leer(self):
        ruta = ap.NOTAS / "Física" / "Clase 1.md"
        ap.escribir_nota(ruta, "Clase 1", ["examen", "tema 2"], "2026-11-09 10:00", "Texto con **negrita**\n")
        meta, cuerpo = ap.leer_nota(ruta)
        self.assertEqual(meta["titulo"], "Clase 1")
        self.assertEqual(meta["etiquetas"], ["examen", "tema 2"])
        self.assertEqual(meta["creado"], "2026-11-09 10:00")
        self.assertEqual(cuerpo, "Texto con **negrita**\n")

    def test_leer_markdown_sin_cabecera(self):
        ruta = ap.NOTAS / "suelta.md"
        ruta.parent.mkdir(parents=True)
        ruta.write_text("# Hola\n", encoding="utf-8")
        meta, cuerpo = ap.leer_nota(ruta)
        self.assertEqual(meta["titulo"], "suelta")
        self.assertEqual(cuerpo, "# Hola\n")


def dib_de_prueba(ancho=2, alto=2, bits=32):
    """DIB de abajo arriba: fila de abajo roja, el resto azul."""
    import struct
    bpp = bits // 8
    paso = ((ancho * bits + 31) // 32) * 4
    cab = struct.pack("<IiiHHIIiiII", 40, ancho, alto, 1, bits, 0, 0, 0, 0, 0, 0)
    rojo, azul = b"\x00\x00\xff\x00"[:bpp], b"\xff\x00\x00\x00"[:bpp]
    fila_abajo = (rojo * ancho).ljust(paso, b"\x00")
    fila_arriba = (azul * ancho).ljust(paso, b"\x00")
    return cab + fila_abajo + fila_arriba * (alto - 1)


class TestPortapapeles(unittest.TestCase):
    def test_dib_a_png(self):
        import zlib
        from apuntalo import portapapeles
        for bits in (24, 32):
            png = portapapeles.dib_a_png(dib_de_prueba(bits=bits))
            self.assertEqual(portapapeles.tamano_png(png), (2, 2))
            idat = png[png.index(b"IDAT") + 4:png.index(b"IEND") - 8]
            filas = zlib.decompress(idat)
            # PNG va de arriba abajo: primero azul, luego rojo (cada fila: filtro + 2 píxeles RGB)
            self.assertEqual(filas, b"\x00" + b"\x00\x00\xff" * 2 + b"\x00" + b"\xff\x00\x00" * 2)

    def test_dib_no_admitido(self):
        from apuntalo import portapapeles
        with self.assertRaises(ValueError):
            portapapeles.dib_a_png(dib_de_prueba(bits=32)[:50])

    def test_tamano_imagen_jpeg(self):
        import struct
        jpeg = b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 4) + b"\x00\x00" + \
               b"\xff\xc0" + struct.pack(">HBHH", 11, 8, 480, 640) + b"\x00" * 6
        self.assertEqual(exportar.tamano_imagen(jpeg), (640, 480))


class TestCarpetaDatos(unittest.TestCase):
    def test_variable_de_entorno_manda(self):
        from unittest import mock
        with mock.patch.dict("os.environ", {"APUNTALO_DATOS": "X:/mis apuntes"}):
            self.assertEqual(ap.carpeta_datos(), Path("X:/mis apuntes"))

    def test_instalado_con_pip_usa_documentos(self):
        from unittest import mock
        falso = Path("C:/Python/Lib/site-packages/apuntalo")
        with mock.patch.object(ap, "PAQUETE", falso), mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(ap.carpeta_datos(), ap.carpeta_documentos() / "Apuntalo")

    def test_desde_el_codigo_usa_la_carpeta_del_proyecto(self):
        from unittest import mock
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(ap.carpeta_datos(), RAIZ)


class TestUtilidades(unittest.TestCase):
    def test_texto_util_descarta_basura_del_ocr(self):
        ocr = "e\noo\n> x\nConceptos clave: (Cloud)\n0100\n1- Recursos (infraestructura)"
        self.assertEqual(ap.texto_util(ocr), "Conceptos clave: (Cloud)\n1- Recursos (infraestructura)")

    def test_elegir_modelo_gemini(self):
        def m(nombre, ok=True):
            return {"name": "models/" + nombre, "supportedGenerationMethods": ["generateContent"] if ok else []}
        modelos = [m("gemini-2.0-flash"), m("gemini-2.5-flash"), m("gemini-2.5-flash-lite"),
                   m("gemini-3.0-flash-preview"), m("gemini-2.5-pro"), m("gemini-9-flash", ok=False)]
        self.assertEqual(ap.elegir_modelo_gemini(modelos), "models/gemini-2.5-flash")
        with self.assertRaises(RuntimeError):
            ap.elegir_modelo_gemini([m("gemini-2.5-pro")])


class TestExportar(unittest.TestCase):
    ENLACE = '[texto & más](<https://example.com/?a=1&b="2">)'
    MD = ("# Título\nTexto con **negrita**, *cursiva*, ~~tachado~~ y `código`.\n- viñeta\n  - sub\n1. uno\n"
          "- [ ] tarea\n- [x] hecha\n> cita\n```\nprint(1)\n```\n![img](no-existe.png)\n")

    def nota(self):
        return {"titulo": "Clase & <1>", "cuerpo": self.MD, "fecha": "2026-11-09", "asignatura": "Física",
                "etiquetas": ["examen"], "carpeta": "."}

    def test_bloques(self):
        tipos = [b["tipo"] for b in exportar.bloques(self.MD)]
        self.assertEqual(tipos, ["h1", "p", "ul", "ul", "ol", "tarea", "tarea", "cita", "codigo", "img"])
        self.assertEqual(exportar.bloques(self.MD)[3]["nivel"], 1)

    def test_bloques_con_tablas(self):
        md = "| Nombre | Grupo |\n{}| Ana |\n| --- | --- |\n\nFuera\n```\n| dentro |\n```"
        for separador in ("", "| :--- | ---: |\n"):
            with self.subTest(separador=separador):
                tabla, parrafo, codigo = exportar.bloques(md.format(separador))
                self.assertEqual(tabla, {"tipo": "tabla", "filas": [["Nombre", "Grupo"], ["Ana"]],
                                         "encabezado": bool(separador)})
                self.assertEqual(parrafo, {"tipo": "p", "texto": "Fuera"})
                self.assertEqual(codigo, {"tipo": "codigo", "texto": "| dentro |"})

    def test_tabla_html(self):
        nota = dict(self.nota(), cuerpo="| Nombre | Grupo |\n| --- | --- |\n| *Ana* & Eva | A |")
        h = exportar.a_html([nota], "Tabla")
        self.assertIn("<table><tr><th>Nombre</th><th>Grupo</th></tr>"
                      "<tr><td><em>Ana</em> &amp; Eva</td><td>A</td></tr></table>", h)

    def test_tabla_docx_y_odt(self):
        nota = dict(self.nota(), cuerpo="| Nombre | Grupo |\n| --- | --- |\n| *Ana* & Eva |")
        for formato, archivo, etiqueta, fila, celda in (
            ("docx", "word/document.xml", "w:tbl", "w:tr", "w:tc"),
            ("odt", "content.xml", "table:table", "table:table-row", "table:table-cell"),
        ):
            with self.subTest(formato=formato), tempfile.TemporaryDirectory() as tmp:
                destino = exportar.exportar_como(formato, [nota], Path(tmp) / f"a.{formato}", "Tabla")
                with zipfile.ZipFile(destino) as z:
                    for nombre in z.namelist():
                        if nombre.endswith(".xml"):
                            xml.dom.minidom.parseString(z.read(nombre))
                    doc = z.read(archivo).decode("utf-8")
                self.assertIn(f"<{etiqueta}", doc)
                self.assertIn("Nombre", doc)
                self.assertIn("Ana", doc)
                self.assertIn("&amp; Eva", doc)
                tabla, = xml.dom.minidom.parseString(doc).getElementsByTagName(etiqueta)
                self.assertEqual([len(f.getElementsByTagName(celda)) for f in tabla.getElementsByTagName(fila)],
                                 [2, 1])

    def test_tabla_txt_y_md(self):
        nota = dict(self.nota(), cuerpo="| **Id** | Nombre |\n| --- | --- |\n| 123 | Ana |\n| 4 |")
        with tempfile.TemporaryDirectory() as tmp:
            txt = exportar.a_txt([nota], Path(tmp) / "a.txt", "Tabla")
            self.assertTrue(txt.read_text(encoding="utf-8").endswith(
                "Id  | Nombre\n--- | ------\n123 | Ana   \n4\n"))
            md = exportar.a_md([nota], Path(tmp) / "a.md", "Tabla")
            self.assertTrue(md.read_text(encoding="utf-8").endswith(nota["cuerpo"] + "\n"))

    def test_listas_con_letras_romanos_y_flechas(self):
        b = exportar.bloques("1. uno\n  a. letra\n    i. romano\n→ flecha\n> 💡 Idea clave: x")
        self.assertEqual([(x["tipo"], x.get("num"), x["nivel"]) for x in b[:3]],
                         [("ol", "1", 0), ("ol", "a", 1), ("ol", "i", 2)])
        self.assertEqual((b[3]["tipo"], b[3]["marca"]), ("ul", "→"))
        html = exportar.a_html([{"titulo": "T", "cuerpo": "a. letra\n→ flecha\n> 💡 Idea clave: x",
                                 "carpeta": "."}], "T")
        self.assertIn("<span class=m>a.</span>", html)
        self.assertIn("<span class=m>→</span>", html)
        self.assertIn("<blockquote class=idea>", html)

    def test_trozos(self):
        self.assertEqual(exportar.trozos("a **b** *c* `d` ~~tachado~~"),
                         [("a ", False, False, False, False, None), ("b", True, False, False, False, None),
                          (" ", False, False, False, False, None), ("c", False, True, False, False, None),
                          (" ", False, False, False, False, None), ("d", False, False, True, False, None),
                          (" ", False, False, False, False, None), ("tachado", False, False, False, True, None)])
        self.assertEqual(exportar.trozos("~~**a** *b* __*c*__ `d`~~"),
                         [("a", True, False, False, True, None), (" ", False, False, False, True, None),
                          ("b", False, True, False, True, None), (" ", False, False, False, True, None),
                          ("c", True, True, False, True, None), (" ", False, False, False, True, None),
                          ("d", False, False, True, True, None)])
        self.assertEqual(exportar.trozos("[texto](https://example.com)"),
                         [("texto", False, False, False, False, "https://example.com")])
        self.assertEqual(exportar.trozos("**[texto](url)**"),
                         [("texto", True, False, False, False, "url")])
        self.assertEqual(exportar.trozos("[**texto**](url)"),
                         [("**texto**", False, False, False, False, "url")])

    def test_html_escapa_y_da_formato(self):
        nota = dict(self.nota(), cuerpo=self.MD + f"~~**{self.ENLACE}**~~")
        h = exportar.a_html([nota], "Física")
        self.assertIn("Clase &amp; &lt;1&gt;", h)
        self.assertIn("<strong>negrita</strong>", h)
        self.assertIn("<em>cursiva</em>", h)
        self.assertIn("<s>tachado</s>", h)
        self.assertIn("[Adjunto: img]", h)
        self.assertIn('<a href="https://example.com/?a=1&amp;b=&quot;2&quot;">'
                      '<s><strong>texto &amp; más</strong></s></a>', h)

    def test_docx_valido(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "a.docx"
            nota = dict(self.nota(), cuerpo=self.MD + f"~~**  *{self.ENLACE}*  **~~")
            exportar.a_docx([nota, self.nota()], destino, "Física")
            with zipfile.ZipFile(destino) as z:
                for nombre in z.namelist():
                    xml.dom.minidom.parseString(z.read(nombre))  # XML bien formado
                doc = z.read("word/document.xml").decode("utf-8")
                rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
        self.assertIn("negrita", doc)
        self.assertIn('<w:rPr><w:strike/></w:rPr><w:t xml:space="preserve">tachado</w:t>', doc)
        self.assertIn('<w:hyperlink r:id="rIdLink1"><w:r><w:rPr><w:b/><w:i/><w:strike/>'
                      '<w:color w:val="2F5496"/><w:u w:val="single"/></w:rPr>'
                      '<w:t xml:space="preserve">texto &amp; más</w:t></w:r></w:hyperlink>', doc)
        self.assertIn('<Relationship Id="rIdLink1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                      'relationships/hyperlink" Target="https://example.com/?a=1&amp;b=&quot;2&quot;" '
                      'TargetMode="External"/>', rels)
        self.assertIn('w:type="page"', doc)  # salto de página entre apuntes
        self.assertIn("Clase &amp; &lt;1&gt;", doc)

    def test_docx_con_imagen(self):
        from apuntalo import portapapeles
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "foto.png").write_bytes(portapapeles.dib_a_png(dib_de_prueba(4000, 2)))
            nota = dict(self.nota(), cuerpo=f"Antes\n![foto](<foto.png>)\nDespués\n{self.ENLACE}\n", carpeta=tmp)
            destino = Path(tmp) / "b.docx"
            exportar.a_docx([nota], destino, "Física")
            with zipfile.ZipFile(destino) as z:
                for nombre in z.namelist():
                    if nombre.endswith(".xml") or nombre.endswith(".rels"):
                        xml.dom.minidom.parseString(z.read(nombre))
                self.assertIn("word/media/imagen1.png", z.namelist())
                doc = z.read("word/document.xml").decode("utf-8")
                rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
        self.assertIn('r:embed="rIdImg1"', doc)
        self.assertIn(f'cx="{exportar.ANCHO_UTIL_EMU}"', doc)  # imagen ancha: se ajusta a la página
        self.assertIn('Target="media/imagen1.png"', rels)
        relaciones = xml.dom.minidom.parseString(rels).getElementsByTagName("Relationship")
        ids = [r.getAttribute("Id") for r in relaciones]
        self.assertIn("rIdImg1", ids)
        self.assertIn("rIdLink1", ids)
        self.assertEqual(len(ids), len(set(ids)))

    def _nota_con_foto(self, tmp):
        from apuntalo import portapapeles
        Path(tmp, "foto.png").write_bytes(portapapeles.dib_a_png(dib_de_prueba(40, 20)))
        return dict(self.nota(), cuerpo=self.MD + "![foto](<foto.png>)\n", carpeta=tmp)

    def test_odt_valido(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "a.odt"
            nota = dict(self.nota(), cuerpo=f"**{self.ENLACE}**")
            exportar.a_odt([self._nota_con_foto(tmp), nota], destino, "Física")
            with zipfile.ZipFile(destino) as z:
                self.assertEqual(z.namelist()[0], "mimetype")
                self.assertEqual(z.getinfo("mimetype").compress_type, zipfile.ZIP_STORED)
                for nombre in z.namelist():
                    if nombre.endswith(".xml"):
                        xml.dom.minidom.parseString(z.read(nombre))
                self.assertIn("Pictures/imagen1.png", z.namelist())
                doc = z.read("content.xml").decode("utf-8")
        self.assertIn('text:style-name="Tb">negrita', doc)
        self.assertIn('text:style-name="Tt">tachado</text:span>', doc)
        self.assertIn('<style:style style:name="Tt" style:family="text"><style:text-properties '
                      'style:text-line-through-style="solid"/>', doc)
        self.assertIn('text:style-name="Salto"', doc)   # salto de página entre apuntes
        self.assertIn('<text:a xlink:href="https://example.com/?a=1&amp;b=&quot;2&quot;" xlink:type="simple">'
                      '<text:span text:style-name="Enlace">texto &amp; más</text:span></text:a>', doc)

    def test_html_md_y_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            nota = self._nota_con_foto(tmp)
            nota["cuerpo"] += self.ENLACE + "\n"
            h = exportar.a_html_archivo([nota], Path(tmp) / "a.html", "Física").read_text(encoding="utf-8")
            self.assertIn("data:image/png;base64,", h)       # imagen dentro del archivo
            Path(tmp, "sal").mkdir()
            md = exportar.a_md([nota], Path(tmp, "sal", "a.md"), "F")
            texto = md.read_text(encoding="utf-8")
            self.assertTrue(texto.startswith("# Clase & <1>\n"))
            self.assertIn("## Título", texto)                 # los títulos bajan un nivel
            self.assertIn("](<a_archivos/foto.png>)", texto)
            self.assertIn(self.ENLACE, texto)
            self.assertTrue(Path(tmp, "sal", "a_archivos", "foto.png").is_file())
            txt = exportar.a_txt([nota], Path(tmp) / "a.txt", "F").read_text(encoding="utf-8")
            self.assertIn("negrita", txt)
            self.assertIn("tachado", txt)
            self.assertNotIn("~~", txt)
            self.assertNotIn("**", txt)
            self.assertIn("[x] hecha", txt)

    def test_catalogo_de_formatos(self):
        self.assertEqual(set(exportar.FORMATOS), {"pdf", "docx", "odt", "html", "md", "txt"})


class TestImportar(unittest.TestCase):
    MD = "# Tema\nTexto con **negrita** y *cursiva*.\n- uno\n- dos\n> cita\n"

    def nota(self, tmp):
        from apuntalo import portapapeles
        Path(tmp, "foto.png").write_bytes(portapapeles.dib_a_png(dib_de_prueba(30, 10)))
        return {"titulo": "Mi clase", "cuerpo": self.MD + "![foto](<foto.png>)\n", "fecha": "", "asignatura": "",
                "etiquetas": [], "carpeta": tmp}

    def comprobar(self, datos):
        from apuntalo import importar
        self.assertEqual(datos["titulo"], "Mi clase")
        self.assertIn("**negrita**", datos["cuerpo"])
        self.assertIn("*cursiva*", datos["cuerpo"])
        self.assertIn("- uno", datos["cuerpo"])
        self.assertIn("Tema", datos["cuerpo"])
        self.assertEqual(len(datos["imagenes"]), 1)
        self.assertTrue(datos["imagenes"][0][1].startswith(b"\x89PNG"))
        self.assertIn("{{imagen:0}}", datos["cuerpo"])
        self.assertTrue(importar.FORMATOS)

    def test_de_ida_y_vuelta(self):
        from apuntalo import importar
        for formato in ("docx", "odt", "html", "md"):
            with self.subTest(formato=formato), tempfile.TemporaryDirectory() as tmp:
                destino = Path(tmp) / f"x.{formato}"
                exportar.exportar_como(formato, [self.nota(tmp)], destino, "Mi clase")
                Path(tmp, "foto.png").unlink()      # la imagen sale del archivo (en .md, de x_archivos)
                self.comprobar(importar.importar(destino))

    def test_txt_y_formato_desconocido(self):
        from apuntalo import importar
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "a.txt").write_bytes("Línea ñ\r\nOtra".encode("cp1252"))
            datos = importar.importar(Path(tmp, "a.txt"))
            self.assertEqual(datos["titulo"], "a")
            self.assertIn("Línea ñ\nOtra", datos["cuerpo"])
            with self.assertRaises(ValueError):
                importar.importar(Path(tmp, "a.xyz"))


def tk_error():
    return ap.tk.TclError


class TestTablas(unittest.TestCase):
    def test_alinear_tabla(self):
        lineas = ["Antes", "| Nombre| Nota |", "| ---|:---: |", "| Ana |", "Después"]
        alineadas = ["Antes", "| Nombre | Nota  |", "| ------ | :---: |", "| Ana    |       |", "Después"]
        self.assertEqual(editor.alinear_tabla(lineas, 1, 11), (alineadas, 1, 12))
        self.assertEqual(editor.alinear_tabla(alineadas, 1, 12), (alineadas, 1, 12))
        self.assertEqual(editor.alinear_tabla(alineadas, 1, 16), (alineadas, 1, 15))
        self.assertIsNone(editor.alinear_tabla(lineas, 0, 0))
        self.assertIsNone(editor.alinear_tabla(["```", *lineas, "```"], 2, 2))

    def test_tab_y_enter_alinean(self):
        lineas = ["| Nombre|Nota|", "| --- | --- |", "| Ana | |", "Después"]
        alineadas = ["| Nombre | Nota |", "| ------ | ---- |", "| Ana    |      |", "Después"]
        self.assertEqual(editor.tabla_tab(lineas, 0, 2), (alineadas, 0, 11))
        self.assertEqual(editor.tabla_tab(lineas, 2, 2), (alineadas, 2, 11))
        self.assertEqual(editor.tabla_tab(lineas, 2, 2, atras=True), (alineadas, 0, 11))
        self.assertEqual(editor.tabla_tab(lineas, 0, 2, atras=True), (alineadas, 0, 2))
        self.assertEqual(editor.tabla_enter(lineas, 0, 2), (alineadas, 2, 2))
        con_fila = alineadas[:3] + ["|        |      |", "Después"]
        self.assertEqual(editor.tabla_enter(lineas, 2, 2), (con_fila, 3, 2))
        self.assertEqual(editor.tabla_tab(lineas, 2, 9), (con_fila, 3, 2))
        self.assertEqual(editor.tabla_tab(lineas, 0, 2, alinear=False), (lineas, 0, 9))
        self.assertEqual(editor.tabla_enter(lineas, 2, 2, alinear=False),
                         (lineas[:3] + ["| | |", "Después"], 3, 2))

    def test_conserva_barra_escapada(self):
        lineas = [r"| a\|b|x|", "| --- | --- |"]
        self.assertEqual(editor.alinear_tabla(lineas, 0, 2),
                         ([r"| a\|b | x   |", "| ---- | --- |"], 0, 2))


class TestMapa(unittest.TestCase):
    def test_svg_del_mapa_completo(self):
        nodo = mapa.Nodo("A & B\n< C", [mapa.Nodo("Hijo"), mapa.Nodo("Otro hijo")])
        cajas, ancho, alto = mapa.disponer([nodo])
        colores = {"acento": "#123456", "acento_suave": "#abcdef", "texto": "#111111", "hoja": "#ffffff"}
        svg = mapa.a_svg(cajas, ancho, alto, 220, 46, colores, str.splitlines)
        raiz = ET.fromstring(svg)
        ns = {"svg": "http://www.w3.org/2000/svg"}
        self.assertEqual(raiz.get("viewBox"), f"0 0 {ancho} {alto}")
        self.assertEqual(len(raiz.findall("svg:rect", ns)), 3)
        flechas = raiz.findall("svg:line", ns)
        self.assertEqual(len(flechas), 2)
        self.assertTrue(all(flecha.get("marker-end") == "url(#flecha)" for flecha in flechas))
        self.assertIsNotNone(raiz.find("svg:defs/svg:marker", ns))
        self.assertEqual([t.text for t in raiz.findall("svg:text/svg:tspan", ns)][:2], ["A & B", "< C"])
        self.assertIn("A &amp; B", svg)
        self.assertIn("&lt; C", svg)


class TestGeometria(unittest.TestCase):
    def test_geo_normal_valida(self):
        for geo in ("1x1+-16+18", "1x1+0+0", "599x720", "600x399", "basura", None):
            self.assertFalse(ap.App._geo_normal_valida(geo), geo)
        for geo in ("1250x720+10+10", "1250x720", "600x400"):
            self.assertTrue(ap.App._geo_normal_valida(geo), geo)


class TestVentana(TemporalMixin, unittest.TestCase):
    """Prueba de humo de la interfaz (se salta si no hay pantalla)."""

    def setUp(self):
        super().setUp()
        try:
            self.app = ap.App()
        except Exception as e:  # noqa: BLE001
            self.skipTest(f"Sin pantalla: {e}")
        self.app.withdraw()

    def tearDown(self):
        self.app.cerrar()
        super().tearDown()

    def _otra_app(self):
        """Una ventana más; Tcl a veces no arranca en Windows y entonces se salta, como en setUp."""
        try:
            return ap.App()
        except Exception as e:  # noqa: BLE001
            self.skipTest(f"Sin pantalla: {e}")

    def test_descarta_geo_normal_diminuta_al_arrancar(self):
        for compacto in (False, True):
            with self.subTest(compacto=compacto):
                ap.guardar_config({"geo_normal": "1x1+-16+18", "compacto": compacto})
                app = self._otra_app()
                try:
                    self.assertEqual(app.geo_normal, "1250x720")
                    self.assertEqual(app.compacto, compacto)
                finally:
                    app.destroy()

    def test_alternar_compacto_antes_de_dibujar_conserva_geo_normal(self):
        app = self._otra_app()
        try:
            self.assertFalse(app.winfo_ismapped())
            app.alternar_compacto()
            app.alternar_compacto()
            self.assertTrue(ap.App._geo_normal_valida(app.geo_normal))
        finally:
            app.destroy()

    def test_crear_buscar_y_resaltar(self):
        from unittest import mock
        with mock.patch.object(ap.simpledialog, "askstring", return_value="Tema 1"):
            self.app.nueva_carpeta()
        self.app.arbol.selection_set("dir:Tema 1")
        with mock.patch.object(ap.simpledialog, "askstring", return_value="Derivadas"):
            self.app.nueva()
        self.app.texto.insert("end", "# Título\nLa **derivada** [00:01:12]\n")
        self.app.guardar()
        self.assertTrue((ap.NOTAS / "Tema 1" / "Derivadas.md").is_file())
        self.app.resaltar()
        self.assertTrue(self.app.texto.tag_ranges("h1"))
        self.assertTrue(self.app.texto.tag_ranges("negrita"))
        self.assertTrue(self.app.texto.tag_ranges("tiempo"))
        self.app.busqueda.set("derivada")
        self.app.refrescar()
        self.assertEqual(len(self.app.arbol.get_children("dir:Tema 1")), 1)
        self.app.busqueda.set("no-aparece")
        self.app.refrescar()
        self.assertEqual(len(self.app.arbol.get_children("dir:Tema 1")), 0)

    def test_pegar_imagen_con_ctrl_v(self):
        from unittest import mock
        from apuntalo import portapapeles
        with mock.patch.object(ap.simpledialog, "askstring", return_value="Con imagen"):
            self.app.nueva()
        self.app.texto.insert("end", "Texto antes")
        png = portapapeles.dib_a_png(dib_de_prueba(10, 10))
        with mock.patch.object(portapapeles, "hay_texto", return_value=False), \
                mock.patch.object(portapapeles, "imagen_png", return_value=png):
            self.assertEqual(self.app.pegar(), "break")
        texto = self.app.texto.get("1.0", "end-1c")
        self.assertRegex(texto, r"Texto antes\n!\[imagen [^\]]+\]\(<_adjuntos/imagen [^>]+\.png>\)\n")
        self.assertEqual(len(list(ap.ADJUNTOS.glob("*.png"))), 1)
        self.app.resaltar()
        t = self.app.texto
        self.assertEqual(len(t.dump("1.0", "end", image=True)), 1)   # vista previa
        # El enlace queda oculto: solo se ve la imagen
        ini, fin = t.tag_ranges("oculto")
        self.assertRegex(t.get(ini, fin), r"^!\[imagen [^\]]+\]\(<_adjuntos/[^>]+>\)$")
        self.app.guardar()
        guardado = (ap.NOTAS / "Con imagen.md").read_text(encoding="utf-8")
        self.assertNotIn("pyimage", guardado)
        self.assertIn("](<_adjuntos/imagen ", guardado)   # el enlace sí se guarda
        # Retroceso justo detrás de la imagen la borra entera (imagen + enlace)
        t.mark_set("insert", "2.end")
        self.assertEqual(self.app._borrar_imagen(adelante=False), "break")
        self.assertEqual(t.dump("1.0", "end", image=True), [])
        self.assertNotIn("_adjuntos", t.get("1.0", "end"))
        self.assertTrue(t.get("1.0", "end-1c").startswith("Texto antes"))
        # Con texto en el portapapeles, Ctrl+V pega texto normal
        with mock.patch.object(portapapeles, "hay_texto", return_value=True):
            self.assertIsNone(self.app.pegar())

    def test_ventana_exportar_e_importar(self):
        from unittest import mock
        with mock.patch.object(ap.simpledialog, "askstring", return_value="Clase 3"):
            self.app.nueva()
        self.app.texto.insert("end", "Hola **mundo**\n")
        self.app.guardar()
        v = self.app.menu_exportar()
        textos = []
        pendientes = [v]
        while pendientes:
            w = pendientes.pop()
            pendientes += w.winfo_children()
            try:
                textos.append(w.cget("text"))
            except tk_error():
                pass
        for esperado in ("Guardar como", "Guardar en", "PDF (.pdf)", "Word (.docx)", "Página web (.html)",
                         "Markdown (.md)", "Texto sin formato (.txt)", "OpenDocument (.odt)"):
            self.assertIn(esperado, textos)
        v.destroy()
        (ap.BASE / "fuera").mkdir()
        destino = self.app.exportar("nota", "docx", ap.BASE / "fuera" / "x.docx")
        self.assertTrue(destino.is_file())
        hechas = self.app.importar_archivos([destino])
        self.assertEqual(len(hechas), 1)
        self.assertIn("**mundo**", self.app.texto.get("1.0", "end"))
        self.assertEqual(self.app.titulo.get(), "Clase 3")

    def test_teclas_de_tabla(self):
        cuerpo = "| Nombre | Nota |\n| --- | --- |\n| Ana | 9 |"
        ruta = ap.NOTAS / "Tabla.md"
        ap.escribir_nota(ruta, "Tabla", [], "2026-11-09 10:00", cuerpo)
        self.app.cargar(ruta)
        t = self.app.texto
        t.mark_set("insert", "1.4")
        self.assertEqual(self.app._tecla_tab(atras=False), "break")
        self.assertEqual(t.index("insert"), "1.11")
        self.assertEqual(self.app._tecla_tab(atras=False), "break")
        self.assertEqual(t.index("insert"), "3.2")
        self.assertEqual(self.app._tecla_tab(atras=True), "break")
        self.assertEqual(t.index("insert"), "1.11")
        self.assertEqual(self.app._tecla_enter(), "break")
        self.assertEqual(t.index("insert"), "3.2")
        self.assertEqual(self.app._tecla_enter(), "break")
        self.assertEqual(t.index("insert"), "4.2")
        self.assertEqual(t.get("1.0", "end-1c"),
                         "| Nombre | Nota |\n| ------ | ---- |\n| Ana    | 9    |\n|        |      |")
        t.edit_undo()
        self.assertEqual(t.get("1.0", "end-1c"), "| Nombre | Nota |\n| ------ | ---- |\n| Ana    | 9    |")
        t.edit_undo()
        self.assertEqual(t.get("1.0", "end-1c"), cuerpo)

    def test_resaltar_tablas(self):
        cuerpo = "| **Nombre** |\n| --- |\n| ~~Ana~~ |\n```\n| código |\n```"
        ruta = ap.NOTAS / "Tabla.md"
        ap.escribir_nota(ruta, "Tabla", [], "2026-11-09 10:00", cuerpo)
        self.app.cargar(ruta)
        t = self.app.texto
        self.app.cfg["alinear_tablas"] = False
        self.app.resaltar()
        self.assertIn("tabla", t.tag_names("3.2"))
        self.assertIn("tabla_cabecera", t.tag_names("1.2"))
        self.assertNotIn("negrita", t.tag_names("1.2"))
        self.assertIn("tabla_raya", t.tag_names("2.2"))
        self.assertIn("simbolo", t.tag_names("2.0"))
        self.assertIn("tachado", t.tag_names("3.2"))
        self.assertNotIn("tabla", t.tag_names("5.2"))

    def test_insertar_tabla_se_deshace_en_un_paso(self):
        from unittest import mock
        cuerpo = "Antes\nDespués"
        ruta = ap.NOTAS / "Texto.md"
        ap.escribir_nota(ruta, "Texto", [], "2026-11-09 10:00", cuerpo)
        self.app.cargar(ruta)
        t = self.app.texto
        t.mark_set("insert", "1.2")
        with mock.patch.object(ap.simpledialog, "askinteger", side_effect=[2, 3]):
            self.app.insertar_tabla()
        self.assertEqual(t.get("1.0", "end-1c"),
                         "Antes\n\n|     |     |\n| --- | --- |\n|     |     |\n|     |     |\n\nDespués")
        self.assertEqual(t.index("insert"), "3.2")
        t.edit_undo()
        self.assertEqual(t.get("1.0", "end-1c"), cuerpo)
        with mock.patch.object(ap.simpledialog, "askinteger", side_effect=[1, 1]):
            t.mark_set("insert", "2.end")
            self.app.insertar_tabla()
        self.assertEqual(t.get("1.0", "end-1c"), cuerpo + "\n\n|     |\n")
        self.assertEqual(t.index("insert"), "4.2")

    def test_listas_flechas_y_palabras(self):
        from unittest import mock
        with mock.patch.object(ap.simpledialog, "askstring", return_value="Listas"):
            self.app.nueva()
        t = self.app.texto
        t.delete("1.0", "end")
        t.insert("1.0", "1. Hola")
        t.mark_set("insert", "1.end")
        self.assertEqual(self.app._tecla_enter(), "break")
        self.assertEqual(t.get("1.0", "end-1c"), "1. Hola\n2. ")
        self.assertEqual(t.index("insert"), "2.3")
        self.assertEqual(self.app._tecla_retroceso(), "break")          # 2. vacío -> a.
        self.assertEqual(t.get("1.0", "end-1c"), "1. Hola\n  a. ")
        self.app._tecla_retroceso()                                       # a. vacío -> vuelve a 2.
        self.assertEqual(t.get("1.0", "end-1c"), "1. Hola\n2. ")
        self.app._tecla_retroceso()                                       # y ahora quita la viñeta
        self.assertEqual(t.get("1.0", "end-1c"), "1. Hola\n")
        t.insert("insert", "2. ")
        self.app._tecla_retroceso()
        self.assertEqual(t.get("1.0", "end-1c"), "1. Hola\n  a. ")
        t.insert("insert", "x")
        self.app._tecla_enter()
        self.assertEqual(t.get("1.0", "end-1c"), "1. Hola\n  a. x\n  b. ")
        t.edit_reset()
        t.insert("insert", "va ->")
        self.assertEqual(self.app._tecla_espacio(), "break")
        self.assertTrue(t.get("1.0", "end-1c").endswith("  b. va → "))
        t.edit_undo()                                                     # Ctrl+Z devuelve el ->
        self.assertTrue(t.get("1.0", "end-1c").endswith("  b. va ->"))
        t.mark_set("insert", "end-1c")
        self.assertEqual(self.app._borrar_palabra(adelante=False), "break")
        self.assertTrue(t.get("1.0", "end-1c").endswith("  b. va "))
        self.app.resaltar()
        self.assertTrue([n for n in t.tag_names("2.0") if n.startswith("colgante_")])
        self.app.insertar_bloque("> 💡 Idea clave: ")
        self.app.resaltar()
        self.assertTrue(t.tag_ranges("bloque_idea"))
        self.app.alternar_tema()
        self.assertTrue(self.app.oscuro)
        self.app.alternar_tema()

    def test_mayusculas_auto(self):
        ruta = ap.NOTAS / "Mayúsculas.md"
        ap.escribir_nota(ruta, "Mayúsculas", [], "2026-11-09 10:00", "Hola. Mundo")
        self.app.cargar(ruta)
        t = self.app.texto
        t.mark_set("insert", "1.6")
        tecla = SimpleNamespace(char="h")
        self.assertEqual(self.app._tecla_general(tecla), "break")
        self.assertEqual(t.get("1.6", "1.7"), "H")
        t.edit_undo()
        t.mark_set("insert", "1.6")
        antes = t.get("1.0", "end-1c")
        self.assertEqual(t.get("1.0", "1.end"), "Hola. Mundo")
        self.app.cfg["mayusculas_auto"] = False
        self.assertIsNone(self.app._tecla_general(tecla))
        self.assertEqual(t.get("1.0", "end-1c"), antes)
        self.app.cfg["mayusculas_auto"] = True
        t.tag_add("sel", "1.6", "1.end")
        self.assertIsNone(self.app._tecla_general(tecla))
        self.assertEqual(t.get("1.0", "end-1c"), antes)

    def test_cierre_automatico(self):
        ruta = ap.NOTAS / "Pares.md"
        ap.escribir_nota(ruta, "Pares", [], "2026-11-09 10:00", "")
        self.app.cargar(ruta)
        t = self.app.texto
        abrir = SimpleNamespace(char="(")
        self.assertEqual(self.app._tecla_general(abrir), "break")
        self.assertEqual(t.get("1.0", "end-1c"), "()")
        self.assertEqual(t.index("insert"), "1.1")
        self.assertEqual(self.app._tecla_general(SimpleNamespace(char=")")), "break")
        self.assertEqual(t.get("1.0", "end-1c"), "()")
        self.assertEqual(t.index("insert"), "1.2")
        t.edit_undo()
        self.assertEqual(t.get("1.0", "end-1c"), "")

        self.assertEqual(self.app._tecla_general(abrir), "break")
        self.assertEqual(self.app._tecla_retroceso(), "break")
        self.assertEqual(t.get("1.0", "end-1c"), "")
        self.assertEqual(self.app._tecla_general(SimpleNamespace(char="¿")), "break")
        self.assertEqual(self.app._tecla_general(SimpleNamespace(char="q")), "break")
        self.assertEqual(t.get("1.0", "end-1c"), "¿Q?")

        t.delete("1.0", "end")
        t.insert("1.0", "texto")
        t.tag_add("sel", "1.0", "1.end")
        self.assertEqual(self.app._tecla_general(abrir), "break")
        self.assertEqual(t.get("1.0", "end-1c"), "(texto)")
        self.assertEqual(t.get("sel.first", "sel.last"), "texto")
        t.edit_undo()
        self.assertEqual(t.get("1.0", "end-1c"), "texto")
        t.tag_remove("sel", "1.0", "end")
        self.app.cfg["cierre_automatico"] = False
        self.assertIsNone(self.app._tecla_general(abrir))
        self.assertEqual(t.get("1.0", "end-1c"), "texto")

    def test_espacio_corrige_tilde_antes_de_puntuacion(self):
        from tests.test_ortografia import Falso

        ruta = ap.NOTAS / "Tildes.md"
        ap.escribir_nota(ruta, "Tildes", [], "2026-11-09 10:00", "aqui.")
        self.app.cargar(ruta)
        self.app._corr = Falso()
        t = self.app.texto
        t.mark_set("insert", "1.end")
        self.assertIsNone(self.app._tecla_espacio())
        self.assertEqual(t.get("1.0", "1.end"), "aquí.")
        self.assertEqual(t.index("insert"), "1.5")

    def test_tachado(self):
        ruta = ap.NOTAS / "Atajos.md"
        ap.escribir_nota(ruta, "Atajos", [], "2026-11-09 10:00", "texto")
        self.app.cargar(ruta)
        t = self.app.texto
        t.tag_add("sel", "1.0", "1.end")
        self.assertEqual(self.app._envolver("~~"), "break")
        self.app.resaltar()
        self.assertEqual(t.get("1.0", "end-1c").rstrip("\n"), "~~texto~~")
        self.assertEqual(tuple(map(str, t.tag_ranges("tachado"))), ("1.0", "1.9"))
        t.delete("1.0", "1.2")
        self.app.resaltar()
        self.assertFalse(t.tag_ranges("tachado"))

    def test_mayus_supr_borra_palabra(self):
        from unittest import mock
        with mock.patch.object(ap.simpledialog, "askstring", return_value="Atajos"):
            self.app.nueva()
        t = self.app.texto
        t.delete("1.0", "end")
        t.insert("1.0", "Hola mundo otra vez")
        t.mark_set("insert", "1.5")
        self.assertEqual(self.app._tecla_mayus_supr(), "break")
        self.assertEqual(t.get("1.0", "end-1c"), "Hola otra vez")

    def test_mayus_supr_corta_seleccion(self):
        from unittest import mock
        with mock.patch.object(ap.simpledialog, "askstring", return_value="Atajos"):
            self.app.nueva()
        self.app.cfg["mayus_supr_corta"] = True
        t = self.app.texto
        t.delete("1.0", "end")
        t.insert("1.0", "Hola mundo")
        t.tag_add("sel", "1.4", "1.end")
        self.app.clipboard_clear()
        self.assertEqual(self.app._tecla_mayus_supr(), "break")
        self.assertEqual(t.get("1.0", "end-1c"), "Hola")
        self.assertEqual(self.app.clipboard_get(), " mundo")

    def test_tamano_de_letra(self):
        self.app.cambiar_letra(+3)
        self.assertEqual(self.app.tam_letra, 15)
        self.app.cambiar_letra(0)
        self.assertEqual(self.app.tam_letra, 12)

    def test_opaca_con_el_raton_encima(self):
        from unittest import mock
        alpha = lambda: round(float(self.app.attributes("-alpha")), 2)  # noqa: E731
        dentro = {"si": True}
        with mock.patch.object(self.app, "winfo_viewable", return_value=True), \
                mock.patch.object(self.app, "_raton_dentro", side_effect=lambda: dentro["si"]):
            self.app.opacidad.set(0.4)
            self.app.aplicar_opacidad()          # moviendo la barra: se ve la opacidad elegida
            self.app._opaca_con_raton()
            self.assertEqual(alpha(), 0.4)
            dentro["si"] = False
            self.app._opaca_con_raton()
            self.assertEqual(alpha(), 0.4)
            dentro["si"] = True
            self.app._opaca_con_raton()
            self.assertEqual(alpha(), 1.0)
            dentro["si"] = False
            self.app._opaca_con_raton()
            self.assertEqual(alpha(), 0.4)


@unittest.skipUnless(sys.platform == "win32", "solo Windows")
class TestAdministrador(unittest.TestCase):
    def _reabrir(self, argv, admin=0, respuesta=42):
        from unittest import mock
        shell = mock.Mock()
        shell.IsUserAnAdmin.return_value = admin
        shell.ShellExecuteW.return_value = respuesta
        with mock.patch.object(ap.ctypes, "windll", SimpleNamespace(shell32=shell)), \
                mock.patch.object(ap.sys, "argv", argv):
            return ap._reabrir_como_admin(), shell.ShellExecuteW

    def test_pide_permisos_y_pasa_la_carpeta_de_datos(self):
        reabierta, ejecutar = self._reabrir(["apuntes.pyw"])
        self.assertTrue(reabierta)
        _, verbo, _, args, _, _ = ejecutar.call_args.args
        self.assertEqual(verbo, "runas")
        self.assertIn("-m apuntalo", args)
        self.assertIn("--datos=", args)
        self.assertTrue(args.endswith("--elevada"))

    def test_no_repite_si_ya_tiene_permisos_o_ya_se_pidieron(self):
        for argv, admin in ((["apuntes.pyw"], 1), (["apuntes.pyw", "--elevada"], 0)):
            reabierta, ejecutar = self._reabrir(argv, admin=admin)
            self.assertFalse(reabierta)
            ejecutar.assert_not_called()

    def test_exe_trabaja_en_su_carpeta_no_en_la_temporal(self):
        from unittest import mock
        with mock.patch.object(ap.sys, "frozen", True, create=True), \
                mock.patch.object(ap.sys, "executable", r"C:\Apps\Apuntalo.exe"):
            reabierta, ejecutar = self._reabrir([r"C:\Apps\Apuntalo.exe"])
        self.assertTrue(reabierta)
        _, _, programa, args, carpeta, _ = ejecutar.call_args.args
        self.assertEqual((programa, args, carpeta), (r"C:\Apps\Apuntalo.exe", "--elevada", r"C:\Apps"))

    def test_si_dicen_que_no_se_abre_sin_permisos(self):
        reabierta, _ = self._reabrir(["apuntes.pyw"], respuesta=5)    # SE_ERR_ACCESSDENIED
        self.assertFalse(reabierta)

    def test_carpeta_de_datos_por_argumento(self):
        from unittest import mock
        with mock.patch.object(ap.sys, "argv", ["x", r"--datos=C:\Mis apuntes"]):
            self.assertEqual(ap.carpeta_datos(), Path(r"C:\Mis apuntes"))


if __name__ == "__main__":
    unittest.main()
