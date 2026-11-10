"""Pruebas de la lógica del editor (listas, flechas, palabras). Sin ventanas."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from apuntalo import editor as ed  # noqa: E402


class TestMarcas(unittest.TestCase):
    def test_romanos_y_letras(self):
        self.assertEqual([ed.a_romano(n) for n in (1, 4, 9, 14, 39)], ["i", "iv", "ix", "xiv", "xxxix"])
        self.assertEqual([ed.de_romano(s) for s in ("i", "iv", "ix", "xiv")], [1, 4, 9, 14])
        self.assertEqual([ed.a_letra(n) for n in (1, 2, 26, 27)], ["a", "b", "z", "aa"])

    def test_analizar(self):
        it = ed.analizar("  2. Hola")
        self.assertEqual((it.tipo, it.valor, it.sangria, it.resto, it.ancho), ("num", 2, "  ", "Hola", 5))
        self.assertEqual(ed.analizar("b) algo").tipo, "alfa")
        self.assertEqual(ed.analizar("iv. algo").tipo, "romano")
        self.assertEqual(ed.analizar("i. algo").tipo, "romano")
        self.assertEqual(ed.analizar("i. algo", ed.analizar("h. x")).tipo, "alfa")
        self.assertEqual(ed.analizar("→ idea").tipo, "flecha")
        self.assertEqual(ed.analizar("- [ ] tarea").tarea, " [ ]")
        self.assertEqual(ed.analizar("3.").resto, "")
        for no in ("Hola", "1.5 kg", ". punto", "---", "# Título", "a.b"):
            self.assertIsNone(ed.analizar(no), no)


class TestListas(unittest.TestCase):
    def test_enter_crea_el_siguiente(self):
        lineas, fila, col = ed.enter(["1. Hola"], 0, 7)
        self.assertEqual(lineas, ["1. Hola", "2. "])
        self.assertEqual((fila, col), (1, 3))

    def test_enter_en_medio_parte_la_linea(self):
        lineas, fila, col = ed.enter(["- uno dos"], 0, 5)
        self.assertEqual(lineas, ["- uno", "- dos"])
        self.assertEqual((fila, col), (1, 2))

    def test_enter_renumera_los_de_abajo(self):
        lineas, *_ = ed.enter(["1. a", "2. b"], 0, 4)
        self.assertEqual(lineas, ["1. a", "2. ", "3. b"])

    def test_enter_en_vacio_termina_la_lista(self):
        lineas, fila, col = ed.enter(["1. Hola", "2. "], 1, 3)
        self.assertEqual(lineas, ["1. Hola", ""])
        self.assertEqual((fila, col), (1, 0))

    def test_enter_en_vacio_anidado_sube_de_nivel(self):
        lineas, fila, col = ed.enter(["1. Hola", "  a. x", "  b. "], 2, 5)
        self.assertEqual(lineas, ["1. Hola", "  a. x", "2. "])

    def test_tareas(self):
        lineas, *_ = ed.enter(["- [x] hecho"], 0, 11)
        self.assertEqual(lineas, ["- [x] hecho", "- [ ] "])

    def test_retroceso_en_vacio_pasa_a_letras(self):
        lineas, fila, col = ed.retroceso(["1. Hola", "2. "], 1, 3)
        self.assertEqual(lineas, ["1. Hola", "  a. "])
        self.assertEqual(col, 5)
        lineas, *_ = ed.enter(lineas[:1] + ["  a. x"], 1, 6)
        self.assertEqual(lineas, ["1. Hola", "  a. x", "  b. "])

    def test_retroceso_quita_la_vineta(self):
        self.assertEqual(ed.retroceso(["1. texto"], 0, 3)[0], ["texto"])
        self.assertEqual(ed.retroceso(["1. a", "2. "], 1, 3, sangrar=False)[0], ["1. a", ""])

    def test_lista_con_lineas_en_blanco(self):
        lineas = ["1. test", "2. test", "", "  a. test", "  b. test", "", "  c. ", "", "4. x"]
        r, fila, col = ed.retroceso(lineas, 6, 5)
        self.assertEqual(r[6], "3. ")
        self.assertEqual(r[8], "4. x")
        self.assertEqual(ed.enter(["1. a", "", "2. b"], 2, 4)[0][-1], "3. ")
        self.assertEqual(ed.renumerar(["1. a", "", "", "1. b"], 0)[-1], "1. b")   # dos huecos: otra lista

    def test_retroceso_en_letra_vuelve_al_numero(self):
        lineas, fila, col = ed.retroceso(["1. a", "  a. "], 1, 5)
        self.assertEqual(lineas, ["1. a", "2. "])
        self.assertEqual(col, 3)
        lineas, *_ = ed.retroceso(["1. a", "  a. x", "  b. y", "2. z"], 2, 5)
        self.assertEqual(lineas, ["1. a", "  a. x", "2. y", "3. z"])
        self.assertIsNone(ed.retroceso(["1. texto"], 0, 5))   # en medio: Retroceso normal

    def test_tab_y_mayus_tab(self):
        lineas, fila, col = ed.tab(["1. a", "2. b", "3. c"], 1, 4)
        self.assertEqual(lineas, ["1. a", "  a. b", "2. c"])
        self.assertEqual(col, 6)
        lineas, *_ = ed.tab(lineas, 1, 6, atras=True)
        self.assertEqual(lineas, ["1. a", "2. b", "3. c"])
        self.assertEqual(ed.tab(["  a. x"], 0, 6)[0], ["    i. x"])
        self.assertIsNone(ed.tab(["Hola"], 0, 0))
        self.assertIsNone(ed.tab(["1. a"], 0, 3, atras=True))

    def test_renumerar_anidadas(self):
        lineas = ["1. a", "  a. x", "  c. y", "5. b", "- suelto"]
        self.assertEqual(ed.renumerar(lineas, 0), ["1. a", "  a. x", "  b. y", "2. b", "- suelto"])

    def test_respeta_el_numero_inicial(self):
        self.assertEqual(ed.renumerar(["3. a", "9. b"], 0), ["3. a", "4. b"])

    def test_nada_dentro_de_codigo(self):
        self.assertIsNone(ed.enter(["```", "1. a"], 1, 4))


class TestPalabras(unittest.TestCase):
    def test_izquierda(self):
        self.assertEqual(ed.palabra_izquierda("hola canción", 12), 5)
        self.assertEqual(ed.palabra_izquierda("año 2026  ", 10), 4)
        self.assertEqual(ed.palabra_izquierda("fin.", 4), 3)
        self.assertIsNone(ed.palabra_izquierda("x", 0))

    def test_derecha(self):
        self.assertEqual(ed.palabra_derecha("hola canción", 0), 5)
        self.assertEqual(ed.palabra_derecha("hola", 2), 4)
        self.assertIsNone(ed.palabra_derecha("hola", 4))


class TestSimbolos(unittest.TestCase):
    def test_flechas(self):
        self.assertEqual(ed.sustitucion("a ->"), (2, "→"))
        self.assertEqual(ed.sustitucion("x <=>"), (3, "⇔"))
        self.assertEqual(ed.sustitucion("x -->"), (3, "⟶"))
        self.assertEqual(ed.sustitucion("x =>"), (2, "⇒"))
        self.assertIsNone(ed.sustitucion("hola"))
        self.assertIsNone(ed.sustitucion("`a ->"))   # dentro de código

    def test_bloques(self):
        self.assertEqual(ed.sustitucion("/idea"), (5, "> 💡 Idea clave: "))
        self.assertIsNone(ed.sustitucion("texto /idea"))
        self.assertEqual(ed.tipo_bloque("> 💡 Idea clave: x"), "idea")
        self.assertEqual(ed.tipo_bloque("> cita"), "cita")
        self.assertIsNone(ed.tipo_bloque("nada"))


if __name__ == "__main__":
    unittest.main()
