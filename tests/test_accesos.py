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
        self.assertEqual(run_mock.call_count, 2)   # intenta el segundo aunque el primero falle...
        self.assertFalse(resultado)                # ...pero si uno falla, no cuenta como éxito completo

    @patch("apuntalo.accesos.subprocess.run")
    def test_exito_solo_si_todos_los_destinos_funcionan(self, run_mock):
        run_mock.return_value = None
        tmp = Path(tempfile.gettempdir())
        with patch.object(accesos.sys, "platform", "win32"):
            resultado = accesos.crear_accesos_directos(
                [tmp / "escritorio_prueba", tmp / "inicio_prueba"], Path(__file__))
        self.assertEqual(run_mock.call_count, 2)
        self.assertTrue(resultado)

    def test_quita_solo_los_accesos_que_apuntan_al_exe(self):
        with tempfile.TemporaryDirectory() as tmp:
            nuestro, ajeno, vacio = Path(tmp) / "a", Path(tmp) / "b", Path(tmp) / "c"
            for carpeta in (nuestro, ajeno, vacio):
                carpeta.mkdir()
            exe = Path(r"C:\Users\Prueba\Desktop\Apuntalo.exe")
            (nuestro / accesos.NOMBRE).write_bytes(b"\x4c\x00cabecera" + str(exe).upper().encode("utf-16-le"))
            (ajeno / accesos.NOMBRE).write_bytes(b"\x4c\x00" + r"C:\Otra\Apuntalo.exe".encode("utf-16-le"))
            quitados = accesos.quitar_accesos_rotos([nuestro, ajeno, vacio], exe)
            self.assertEqual(quitados, 1)
            self.assertFalse((nuestro / accesos.NOMBRE).exists())
            self.assertTrue((ajeno / accesos.NOMBRE).exists())

    @patch("apuntalo.accesos.subprocess.run", side_effect=OSError("powershell no disponible"))
    def test_si_powershell_no_esta_disponible_no_lanza_excepcion(self, run_mock):
        with patch.object(accesos.sys, "platform", "win32"):
            resultado = accesos.crear_accesos_directos(
                [Path(tempfile.gettempdir()) / "escritorio_prueba"], Path(__file__))
        self.assertFalse(resultado)
