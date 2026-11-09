"""Pruebas de Apúntalo. Ejecutar desde la carpeta del proyecto:  py -3 -m unittest -v"""
import sys
import tempfile
import unittest
import xml.dom.minidom
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from apuntalo import app as ap, exportar  # noqa: E402


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
    MD = ("# Título\nTexto con **negrita**, *cursiva* y `código`.\n- viñeta\n  - sub\n1. uno\n"
          "- [ ] tarea\n- [x] hecha\n> cita\n```\nprint(1)\n```\n![img](no-existe.png)\n")

    def nota(self):
        return {"titulo": "Clase & <1>", "cuerpo": self.MD, "fecha": "2026-11-09", "asignatura": "Física",
                "etiquetas": ["examen"], "carpeta": "."}

    def test_bloques(self):
        tipos = [b["tipo"] for b in exportar.bloques(self.MD)]
        self.assertEqual(tipos, ["h1", "p", "ul", "ul", "ol", "tarea", "tarea", "cita", "codigo", "img"])
        self.assertEqual(exportar.bloques(self.MD)[3]["nivel"], 1)

    def test_trozos(self):
        self.assertEqual(exportar.trozos("a **b** *c* `d`"),
                         [("a ", False, False, False), ("b", True, False, False), (" ", False, False, False),
                          ("c", False, True, False), (" ", False, False, False), ("d", False, False, True)])

    def test_html_escapa_y_da_formato(self):
        h = exportar.a_html([self.nota()], "Física")
        self.assertIn("Clase &amp; &lt;1&gt;", h)
        self.assertIn("<strong>negrita</strong>", h)
        self.assertIn("<em>cursiva</em>", h)
        self.assertIn("[Adjunto: img]", h)

    def test_docx_valido(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "a.docx"
            exportar.a_docx([self.nota(), self.nota()], destino, "Física")
            with zipfile.ZipFile(destino) as z:
                for nombre in z.namelist():
                    xml.dom.minidom.parseString(z.read(nombre))  # XML bien formado
                doc = z.read("word/document.xml").decode("utf-8")
        self.assertIn("negrita", doc)
        self.assertIn('w:type="page"', doc)  # salto de página entre apuntes
        self.assertIn("Clase &amp; &lt;1&gt;", doc)

    def test_docx_con_imagen(self):
        from apuntalo import portapapeles
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "foto.png").write_bytes(portapapeles.dib_a_png(dib_de_prueba(4000, 2)))
            nota = dict(self.nota(), cuerpo="Antes\n![foto](<foto.png>)\nDespués\n", carpeta=tmp)
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

    def _nota_con_foto(self, tmp):
        from apuntalo import portapapeles
        Path(tmp, "foto.png").write_bytes(portapapeles.dib_a_png(dib_de_prueba(40, 20)))
        return dict(self.nota(), cuerpo=self.MD + "![foto](<foto.png>)\n", carpeta=tmp)

    def test_odt_valido(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "a.odt"
            exportar.a_odt([self._nota_con_foto(tmp), self.nota()], destino, "Física")
            with zipfile.ZipFile(destino) as z:
                self.assertEqual(z.namelist()[0], "mimetype")
                self.assertEqual(z.getinfo("mimetype").compress_type, zipfile.ZIP_STORED)
                for nombre in z.namelist():
                    if nombre.endswith(".xml"):
                        xml.dom.minidom.parseString(z.read(nombre))
                self.assertIn("Pictures/imagen1.png", z.namelist())
                doc = z.read("content.xml").decode("utf-8")
        self.assertIn('text:style-name="Tb">negrita', doc)
        self.assertIn('text:style-name="Salto"', doc)   # salto de página entre apuntes

    def test_html_md_y_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            nota = self._nota_con_foto(tmp)
            h = exportar.a_html_archivo([nota], Path(tmp) / "a.html", "Física").read_text(encoding="utf-8")
            self.assertIn("data:image/png;base64,", h)       # imagen dentro del archivo
            Path(tmp, "sal").mkdir()
            md = exportar.a_md([nota], Path(tmp, "sal", "a.md"), "F")
            texto = md.read_text(encoding="utf-8")
            self.assertTrue(texto.startswith("# Clase & <1>\n"))
            self.assertIn("## Título", texto)                 # los títulos bajan un nivel
            self.assertIn("](<a_archivos/foto.png>)", texto)
            self.assertTrue(Path(tmp, "sal", "a_archivos", "foto.png").is_file())
            txt = exportar.a_txt([nota], Path(tmp) / "a.txt", "F").read_text(encoding="utf-8")
            self.assertIn("negrita", txt)
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

    def test_tamano_de_letra(self):
        self.app.cambiar_letra(+3)
        self.assertEqual(self.app.tam_letra, 15)
        self.app.cambiar_letra(0)
        self.assertEqual(self.app.tam_letra, 12)


if __name__ == "__main__":
    unittest.main()
