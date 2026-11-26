"""Pruebas de actualizar.py: comparación de versiones y manejo de fallos de red (sin red real)."""
import hashlib
import sys
import tempfile
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

    @patch("apuntalo.actualizar.puede_autoactualizarse", return_value=True)
    @patch("apuntalo.actualizar.preparar_actualizacion", side_effect=OSError("sin red"))
    @patch("apuntalo.actualizar.urllib.request.urlopen", side_effect=OSError("sin red"))
    def test_el_exe_sin_red_no_lanza_excepcion(self, *_):
        avisos = []
        actualizar.comprobar_en_segundo_plano(avisos.append)
        threading.Event().wait(0.5)
        self.assertEqual(avisos, [])

    @patch("apuntalo.actualizar.puede_autoactualizarse", return_value=True)
    @patch("apuntalo.actualizar.preparar_actualizacion", return_value="9.9.9")
    def test_el_exe_se_prepara_en_silencio_sin_avisar(self, preparar_mock, _):
        avisos = []
        actualizar.comprobar_en_segundo_plano(avisos.append)
        threading.Event().wait(0.5)
        preparar_mock.assert_called_once()
        self.assertEqual(avisos, [])


URL = "https://github.com/BV-cs0/apuntalo/releases/download/v1.5.0/"


def release_de_github(**cambios):
    datos = {"tag_name": "v1.5.0", "draft": False, "prerelease": False, "assets": [
        {"name": "Apuntalo.exe", "browser_download_url": URL + "Apuntalo.exe"},
        {"name": "Apuntalo.exe.sha256", "browser_download_url": URL + "Apuntalo.exe.sha256"}]}
    datos.update(cambios)
    return datos


class TestUltimaRelease(unittest.TestCase):
    def test_lee_version_y_enlaces_oficiales(self):
        with patch("apuntalo.actualizar._leer_json", return_value=release_de_github()):
            r = actualizar.ultima_release()
        self.assertEqual(r, {"version": "1.5.0", "exe": URL + "Apuntalo.exe", "sha": URL + "Apuntalo.exe.sha256"})

    def test_rechaza_enlaces_fuera_del_repositorio(self):
        datos = release_de_github()
        datos["assets"][0]["browser_download_url"] = "https://evil.example/Apuntalo.exe"
        with patch("apuntalo.actualizar._leer_json", return_value=datos):
            self.assertIsNone(actualizar.ultima_release())

    def test_ignora_versiones_previas_y_releases_sin_sha256(self):
        for datos in (release_de_github(prerelease=True), release_de_github(draft=True),
                      release_de_github(tag_name="nightly"), release_de_github(assets=release_de_github()["assets"][:1])):
            with patch("apuntalo.actualizar._leer_json", return_value=datos):
                self.assertIsNone(actualizar.ultima_release())

    def test_descargar_solo_desde_el_origen_oficial(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                actualizar._descargar("https://evil.example/x.exe", Path(tmp) / "x.exe")


class TestActualizarExe(unittest.TestCase):
    """Prepara (descarga + SHA-256) y aplica al cerrar, con descargas simuladas sin red."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.pendiente = self.tmp / "actualizacion"
        self.exe = self.tmp / "programa" / "Apuntalo.exe"
        self.exe.parent.mkdir()
        self.exe.write_bytes(b"version vieja")
        self.contenido = b"version nueva"
        self.publicado = hashlib.sha256(self.contenido).hexdigest()

    def tearDown(self):
        self._tmp.cleanup()

    def _descargar_falso(self, url, destino, limite=0):
        destino.write_bytes(f"{self.publicado}  Apuntalo.exe".encode() if url.endswith(".sha256") else self.contenido)

    def _preparar(self):
        release = {"version": "1.5.0", "exe": URL + "Apuntalo.exe", "sha": URL + "Apuntalo.exe.sha256"}
        with patch("apuntalo.actualizar._descargar", side_effect=self._descargar_falso):
            return actualizar.preparar_actualizacion("1.4.2", self.pendiente, consultar=lambda: release)

    def test_prepara_y_aplica_al_cerrar(self):
        self.assertEqual(self._preparar(), "1.5.0")
        self.assertEqual(self.exe.read_bytes(), b"version vieja")   # mientras está abierta no se toca
        self.assertEqual(actualizar.aplicar_pendiente(self.exe, "1.4.2", self.pendiente, probar=lambda e: True), "1.5.0")
        self.assertEqual(self.exe.read_bytes(), self.contenido)
        self.assertTrue(self.exe.with_name("Apuntalo.exe.viejo").is_file())
        actualizar.limpiar_restos(self.exe)
        self.assertFalse(self.exe.with_name("Apuntalo.exe.viejo").exists())
        self.assertEqual(list(self.pendiente.glob("*.exe")), [])

    def test_no_prepara_nada_si_el_sha256_no_coincide(self):
        self.publicado = "0" * 64
        with self.assertRaises(ValueError):
            self._preparar()
        self.assertEqual(list(self.pendiente.glob("*.exe*")), [])
        self.assertIsNone(actualizar.aplicar_pendiente(self.exe, "1.4.2", self.pendiente, probar=lambda e: True))
        self.assertEqual(self.exe.read_bytes(), b"version vieja")

    def test_no_aplica_si_el_exe_cambio_despues_de_verificarlo(self):
        self._preparar()
        (self.pendiente / "Apuntalo-1.5.0.exe").write_bytes(b"manipulado")
        self.assertIsNone(actualizar.aplicar_pendiente(self.exe, "1.4.2", self.pendiente, probar=lambda e: True))
        self.assertEqual(self.exe.read_bytes(), b"version vieja")

    def test_si_windows_no_deja_abrir_el_nuevo_se_queda_el_viejo_y_no_lo_reintenta(self):
        self._preparar()
        self.assertIsNone(actualizar.aplicar_pendiente(self.exe, "1.4.2", self.pendiente, probar=lambda e: False))
        self.assertEqual(self.exe.read_bytes(), b"version vieja")
        with patch("apuntalo.actualizar._descargar") as descargar_mock:
            self.assertIsNone(actualizar.preparar_actualizacion(
                "1.4.2", self.pendiente, consultar=lambda: {"version": "1.5.0", "exe": "", "sha": ""}))
        descargar_mock.assert_not_called()

    def test_no_descarga_si_ya_tiene_la_ultima(self):
        with patch("apuntalo.actualizar._descargar") as descargar_mock:
            resultado = actualizar.preparar_actualizacion(
                "1.5.0", self.pendiente, consultar=lambda: {"version": "1.5.0", "exe": "", "sha": ""})
        self.assertIsNone(resultado)
        descargar_mock.assert_not_called()

    def test_aplicar_al_cerrar_nunca_lanza_excepcion(self):
        with patch("apuntalo.actualizar.puede_autoactualizarse", return_value=True), \
             patch("apuntalo.actualizar.aplicar_pendiente", side_effect=PermissionError("en uso")):
            self.assertIsNone(actualizar.aplicar_al_cerrar())

    def test_estado_roto_no_rompe_nada(self):
        self.pendiente.mkdir()
        (self.pendiente / "pendiente.json").write_text("{roto", encoding="utf-8")
        self.assertIsNone(actualizar.aplicar_pendiente(self.exe, "1.4.2", self.pendiente, probar=lambda e: True))

    def test_con_el_control_inteligente_activo_solo_avisa(self):
        with patch.object(actualizar.sys, "platform", "win32"), patch.object(actualizar.sys, "frozen", True, create=True), \
             patch("apuntalo.actualizar.control_apps.activo", return_value=True):
            self.assertFalse(actualizar.puede_autoactualizarse())
        with patch.object(actualizar.sys, "platform", "win32"), patch.object(actualizar.sys, "frozen", True, create=True), \
             patch("apuntalo.actualizar.control_apps.activo", return_value=False):
            self.assertTrue(actualizar.puede_autoactualizarse())
