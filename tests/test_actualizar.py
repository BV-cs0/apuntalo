"""Pruebas de actualizar.py: comparación de versiones y manejo de fallos de red (sin red real)."""
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from apuntalo import actualizar  # noqa: E402


class TestComparacionVersiones(unittest.TestCase):
    def test_version_a_tupla_ignora_sufijos_no_numericos(self):
        self.assertEqual(actualizar._version_a_tupla("1.4.1"), (1, 4, 1))
        self.assertEqual(actualizar._version_a_tupla("1.4.1rc1"), (1, 4, 1, 1))

    def test_hay_version_nueva_compara_numero_a_numero(self):
        self.assertTrue(actualizar.hay_version_nueva("1.4.0", "1.4.1"))
        self.assertTrue(actualizar.hay_version_nueva("1.4.0", "1.5.0"))
        self.assertTrue(actualizar.hay_version_nueva("1.9.0", "1.10.0"))   # no es comparación de texto
        self.assertFalse(actualizar.hay_version_nueva("1.4.0", "1.4.0"))
        self.assertFalse(actualizar.hay_version_nueva("1.4.1", "1.4.0"))


class TestComprobarEnSegundoPlano(unittest.TestCase):
    @patch("apuntalo.actualizar.urllib.request.urlopen")
    @patch("apuntalo.actualizar.__version__", "1.0.0")
    def test_avisa_cuando_pypi_tiene_una_version_mas_nueva(self, urlopen_mock):
        respuesta = urlopen_mock.return_value.__enter__.return_value
        respuesta.read.return_value = b'{"info": {"version": "9.9.9"}}'
        avisos, listo = [], threading.Event()

        def avisar(version):
            avisos.append(version)
            listo.set()

        actualizar.comprobar_en_segundo_plano(avisar)
        self.assertTrue(listo.wait(2), "no llamó a avisar() a tiempo")
        self.assertEqual(avisos, ["9.9.9"])

    @patch("apuntalo.actualizar.urllib.request.urlopen")
    @patch("apuntalo.actualizar.__version__", "9.9.9")
    def test_no_avisa_si_la_version_instalada_ya_es_la_ultima(self, urlopen_mock):
        respuesta = urlopen_mock.return_value.__enter__.return_value
        respuesta.read.return_value = b'{"info": {"version": "9.9.9"}}'
        avisos = []
        actualizar.comprobar_en_segundo_plano(avisos.append)
        threading.Event().wait(0.5)   # da tiempo al hilo a terminar; no debería avisar
        self.assertEqual(avisos, [])

    @patch("apuntalo.actualizar.urllib.request.urlopen", side_effect=OSError("sin red"))
    def test_no_avisa_ni_lanza_excepcion_si_falla_la_conexion(self, urlopen_mock):
        avisos = []
        actualizar.comprobar_en_segundo_plano(avisos.append)
        threading.Event().wait(0.5)   # da tiempo al hilo a terminar
        self.assertEqual(avisos, [])
