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

    def test_tamano_de_letra(self):
        self.app.cambiar_letra(+3)
        self.assertEqual(self.app.tam_letra, 15)
        self.app.cambiar_letra(0)
        self.assertEqual(self.app.tam_letra, 12)


if __name__ == "__main__":
    unittest.main()
