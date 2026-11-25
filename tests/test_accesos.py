"""Pruebas de accesos.py: no debe fallar el arranque si PowerShell falla, ni crear nada fuera de Windows."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from apuntalo import accesos  # noqa: E402


class TestAccesosDirectos(unittest.TestCase):
    def test_no_hace_nada_fuera_de_windows(self):
        with patch.object(accesos.sys, "platform", "linux"):
            resultado = accesos.crear_accesos_directos([Path(tempfile.gettempdir())], Path(__file__))
        self.assertFalse(resultado)

    @patch("apuntalo.accesos.subprocess.run")
    def test_intenta_cada_destino_aunque_el_primero_falle(self, run_mock):
        run_mock.side_effect = [subprocess.CalledProcessError(1, "powershell"), None]
        tmp = Path(tempfile.gettempdir())
        with patch.object(accesos.sys, "platform", "win32"):
            resultado = accesos.crear_accesos_directos(
                [tmp / "escritorio_prueba", tmp / "inicio_prueba"], Path(__file__))
        self.assertEqual(run_mock.call_count, 2)
        self.assertTrue(resultado)   # el segundo destino sí tuvo éxito

    @patch("apuntalo.accesos.subprocess.run", side_effect=OSError("powershell no disponible"))
    def test_si_powershell_no_esta_disponible_no_lanza_excepcion(self, run_mock):
        with patch.object(accesos.sys, "platform", "win32"):
            resultado = accesos.crear_accesos_directos(
                [Path(tempfile.gettempdir()) / "escritorio_prueba"], Path(__file__))
        self.assertFalse(resultado)
