"""Pruebas de control_apps.py: detectar el Control inteligente de aplicaciones y la marca de Internet."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from apuntalo import control_apps  # noqa: E402


class TestControlApps(unittest.TestCase):
    def test_fuera_de_windows_nunca_esta_activo(self):
        with patch.object(control_apps.sys, "platform", "linux"):
            self.assertFalse(control_apps.activo())

    @unittest.skipUnless(sys.platform == "win32", "solo en Windows")
    def test_lee_el_registro_sin_lanzar_excepciones(self):
        self.assertIn(control_apps.activo(), (True, False))
        with patch("winreg.OpenKey", side_effect=OSError("sin permiso")):
            self.assertFalse(control_apps.activo())

    @unittest.skipUnless(sys.platform == "win32", "Zone.Identifier es de NTFS")
    def test_reconoce_la_marca_de_descargado_de_internet(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "Apuntalo.exe"
            exe.write_bytes(b"MZ")
            self.assertFalse(control_apps.marcado_de_internet(exe))
            Path(f"{exe}:Zone.Identifier").write_text("[ZoneTransfer]\nZoneId=3\nHostUrl=https://github.com/\n")
            self.assertTrue(control_apps.marcado_de_internet(exe))
            Path(f"{exe}:Zone.Identifier").write_text("[ZoneTransfer]\nZoneId=1\n")
            self.assertFalse(control_apps.marcado_de_internet(exe))

    def test_solo_bloquea_accesos_con_el_control_activo_y_la_marca(self):
        exe = Path("Apuntalo.exe")
        for activo, marcado, esperado in ((True, True, True), (True, False, False), (False, True, False)):
            with patch.object(control_apps, "activo", return_value=activo), \
                 patch.object(control_apps, "marcado_de_internet", return_value=marcado):
                self.assertEqual(control_apps.bloquea_accesos(exe), esperado)


if __name__ == "__main__":
    unittest.main()
