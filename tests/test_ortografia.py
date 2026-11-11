import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from apuntalo import ortografia as o  # noqa: E402


class Falso:
    """Corrector de mentira: conoce unas pocas palabras."""
    BUENAS = {"una", "vez", "encontrado", "el", "exploit", "generalmente", "hay", "que", "editarlo", "y", "ok",
              "usuario", "podemos", "ver"}

    def correcta(self, p):
        return p.lower() in self.BUENAS

    def __bool__(self):
        return True


class TestPalabras(unittest.TestCase):
    def test_salta_codigo_enlaces_rutas_y_siglas(self):
        linea = "Usamos `nano exploit.py` en http://192.168.0.1/drupal con /etc/passwd, -p y AWS BurpSuite hola"
        self.assertEqual([p for *_x, p in o.palabras(linea)], ["Usamos", "en", "con", "hola"])   # «y»: muy corta

    def test_faltas_con_posiciones_y_bloques_de_codigo(self):
        texto = "Una vez encontrado el exploit, generalemnte hay que editarlo.\n```\nesto nuncca\n```\npoodemos"
        self.assertEqual(o.faltas_en_texto(texto, Falso()), [(0, 31, 43, "generalemnte"), (4, 0, 8, "poodemos")])

    def test_sugerencia_parecida(self):
        self.assertTrue(o.parecida("Aqui", "Aquí"))
        self.assertTrue(o.parecida("intrucion", "intrusión"))
        self.assertFalse(o.parecida("wordlist", "mordiste"))
        self.assertFalse(o.parecida("rockyou", "lockout"))

    def test_sin_espanol_el_corrector_se_apaga(self):
        c = o.Corrector(idiomas=())
        self.assertFalse(c)
        self.assertEqual(o.faltas_en_texto("holaa", c), [])

    def test_mayusculas_de_la_sugerencia(self):
        self.assertEqual(o.igualar_mayusculas("Poodemos", "podemos"), "Podemos")
        self.assertEqual(o.igualar_mayusculas("HOLAA", "hola"), "HOLA")

    def test_corrector_real_si_lo_hay(self):
        c = o.Corrector()
        if not c:
            self.skipTest("sin diccionario de español en este equipo")
        self.assertTrue(c.correcta("hola"))
        self.assertFalse(c.correcta("generalemnte"))
        self.assertIn("generalmente", c.sugerencias("generalemnte"))
        c.ignorar("generalemnte")
        self.assertTrue(c.correcta("generalemnte"))


class TestVentanaOrtografia(unittest.TestCase):
    def test_dialogo_corrige_las_marcadas(self):
        d = tempfile.mkdtemp()
        (Path(d) / "notas").mkdir()
        (Path(d) / "notas" / "P.md").write_text("---\ntitulo: P\netiquetas: \ncreado: x\n---\n"
                                                "poodemos ver el exploit\n", encoding="utf-8")
        from apuntalo import app as ap
        antes = (ap.BASE, ap.NOTAS, ap.ADJUNTOS, ap.CONFIG)
        ap.BASE, ap.NOTAS = Path(d), Path(d) / "notas"
        ap.ADJUNTOS, ap.CONFIG = ap.NOTAS / "_adjuntos", Path(d) / "config.json"
        self.addCleanup(lambda: setattr(ap, "BASE", antes[0]) or setattr(ap, "NOTAS", antes[1])
                        or setattr(ap, "ADJUNTOS", antes[2]) or setattr(ap, "CONFIG", antes[3]))
        a = ap.App()
        try:
            a.update()
            a.cargar(ap.NOTAS / "P.md")
            a._corr = Falso()
            a._corr.sugerencias = lambda p, maximo=6: ["podemos"]
            a._corr.ignorar = lambda p: None
            a._corr.idiomas = ["es-ES"]
            a.subrayar_faltas()
            self.assertEqual(a.texto.tag_ranges("falta")[0].string, "1.0")
            a.dialogo_ortografia()
            a.ventana_ortografia.corregir()
            self.assertEqual(a.texto.get("1.0", "1.end"), "podemos ver el exploit")
            a.texto.edit_undo()
            self.assertEqual(a.texto.get("1.0", "1.end"), "poodemos ver el exploit")
        finally:
            a.destroy()


if __name__ == "__main__":
    unittest.main()
