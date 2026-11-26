"""Actualizaciones de Apúntalo, siempre en segundo plano y sin bloquear nada.

- Apuntalo.exe: descarga la última Release de GitHub, comprueba su SHA-256 (publicado con la
  Release) y la deja preparada. Al cerrar la app sustituye el .exe, así que la versión nueva se
  usa la próxima vez que se abra. Si el Control inteligente de aplicaciones de Windows está
  activo, no se sustituye solo: solo avisa (ver control_apps.py).
- Instalada con pip o desde el código: solo avisa de que hay una versión nueva en PyPI.

Si algo falla (sin internet, GitHub caído, hash distinto...), la app sigue igual que antes."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from . import __version__, control_apps

URL_PYPI = "https://pypi.org/pypi/apuntalo/json"
URL_RELEASE = "https://api.github.com/repos/BV-cs0/apuntalo/releases/latest"
PREFIJO_DESCARGAS = "https://github.com/BV-cs0/apuntalo/releases/download/"
NOMBRE_EXE = "Apuntalo.exe"
TIEMPO_LIMITE = 4            # segundos para consultar la versión: si no hay respuesta, no se espera más
TIEMPO_DESCARGA = 120        # segundos sin datos antes de abandonar la descarga del .exe
TAMANO_MAXIMO = 150 * 1024 * 1024
ARGUMENTO_PRUEBA = "--comprobar"   # el .exe nuevo arranca y sale con 0 sin abrir ventanas
PENDIENTE = "pendiente.json"


def _version_a_tupla(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", version)) or (0,)


def hay_version_nueva(actual: str, ultima: str) -> bool:
    return _version_a_tupla(ultima) > _version_a_tupla(actual)


def carpeta_pendiente() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Apuntalo" / "actualizacion"


def puede_autoactualizarse() -> bool:
    """Solo Apuntalo.exe en Windows y sin el Control inteligente de aplicaciones activo."""
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False)) and not control_apps.activo()


def _leer_json(url: str, tiempo: float) -> dict:
    peticion = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Apuntalo"})
    with urllib.request.urlopen(peticion, timeout=tiempo) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ultima_release(tiempo: float = TIEMPO_LIMITE) -> Optional[dict]:
    """Versión y enlaces de la última Release estable, solo si sus archivos están en BV-cs0/apuntalo."""
    datos = _leer_json(URL_RELEASE, tiempo)
    etiqueta = str(datos.get("tag_name", ""))
    if datos.get("draft") or datos.get("prerelease") or not re.fullmatch(r"v?\d+(\.\d+){1,3}", etiqueta):
        return None
    enlaces = {}
    for nombre in (NOMBRE_EXE, NOMBRE_EXE + ".sha256"):
        activo = next((a for a in datos.get("assets", []) if a.get("name") == nombre), None)
        esperado = f"{PREFIJO_DESCARGAS}{etiqueta}/{nombre}"
        if not activo or activo.get("browser_download_url") != esperado:
            return None
        enlaces[nombre] = esperado
    return {"version": etiqueta.lstrip("v"), "exe": enlaces[NOMBRE_EXE], "sha": enlaces[NOMBRE_EXE + ".sha256"]}


def _descargar(url: str, destino: Path, limite: int = TAMANO_MAXIMO) -> None:
    if not url.startswith(PREFIJO_DESCARGAS):
        raise ValueError("Origen de descarga no permitido")
    peticion = urllib.request.Request(url, headers={"User-Agent": "Apuntalo"})
    with urllib.request.urlopen(peticion, timeout=TIEMPO_DESCARGA) as resp, open(destino, "wb") as salida:
        if not resp.geturl().startswith("https://"):
            raise ValueError("La descarga no llegó por HTTPS")
        total = 0
        while bloque := resp.read(1024 * 1024):
            total += len(bloque)
            if total > limite:
                raise ValueError("La descarga es demasiado grande")
            salida.write(bloque)


def sha256(archivo: Path) -> str:
    h = hashlib.sha256()
    with open(archivo, "rb") as f:
        while bloque := f.read(1024 * 1024):
            h.update(bloque)
    return h.hexdigest()


def _leer_estado(carpeta: Path) -> dict:
    try:
        datos = json.loads((carpeta / PENDIENTE).read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def _guardar_estado(carpeta: Path, datos: dict) -> None:
    (carpeta / PENDIENTE).write_text(json.dumps(datos), encoding="utf-8")


def _borrar(*archivos: Path) -> None:
    for archivo in archivos:
        try:
            archivo.unlink()
        except OSError:
            pass


def preparar_actualizacion(actual: str, carpeta: Path,
                           consultar: Callable[[], Optional[dict]] = ultima_release) -> Optional[str]:
    """Si hay una Release más nueva, descarga el .exe, comprueba su SHA-256 y lo deja en `carpeta`
    para aplicarlo al cerrar. Devuelve la versión preparada o None. Puede lanzar excepciones:
    quien la llama (el hilo de comprobar_en_segundo_plano) las recoge."""
    release = consultar()
    if not release or not hay_version_nueva(actual, release["version"]):
        return None
    version = release["version"]
    estado = _leer_estado(carpeta)
    if version in estado.get("descartadas", []):
        return None
    nombre = f"Apuntalo-{version}.exe"
    if estado.get("version") == version and (carpeta / nombre).is_file():
        return version   # ya estaba descargada y verificada
    carpeta.mkdir(parents=True, exist_ok=True)
    sha, parcial = carpeta / f"{nombre}.sha256", carpeta / f"{nombre}.part"
    try:
        _descargar(release["sha"], sha, limite=4096)
        esperado = sha.read_text(encoding="utf-8", errors="ignore").split()[0].lower() if sha.stat().st_size else ""
        if not re.fullmatch(r"[0-9a-f]{64}", esperado):
            raise ValueError("El SHA-256 publicado no es válido")
        _descargar(release["exe"], parcial)
        if sha256(parcial) != esperado:
            raise ValueError("El SHA-256 de la descarga no coincide con el publicado")
        os.replace(parcial, carpeta / nombre)
        anterior = Path(str(estado.get("archivo", ""))).name
        if anterior and anterior != nombre:
            _borrar(carpeta / anterior)   # una versión preparada antes y ya superada
        _guardar_estado(carpeta, {"version": version, "archivo": nombre, "sha256": esperado,
                                  "descartadas": estado.get("descartadas", [])})
        return version
    finally:
        _borrar(sha, parcial)


def _probar_exe(exe: Path) -> bool:
    """Arranca el .exe nuevo con --comprobar: si Windows no deja abrirlo o falla, no se instala."""
    try:
        r = subprocess.run([str(exe), ARGUMENTO_PRUEBA], timeout=60, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0
    except Exception:
        return False


def aplicar_pendiente(exe_actual: Path, actual: str, carpeta: Path,
                      probar: Callable[[Path], bool] = _probar_exe) -> Optional[str]:
    """Al cerrar: sustituye `exe_actual` por la versión ya descargada y verificada.
    Devuelve la versión aplicada o None. Si algo falla deja el .exe de antes."""
    estado = _leer_estado(carpeta)
    nombre = Path(str(estado.get("archivo", ""))).name
    if not nombre:
        return None
    nuevo = carpeta / nombre
    version = str(estado.get("version", ""))
    limpio = {"descartadas": estado.get("descartadas", [])}
    if not nuevo.is_file() or not hay_version_nueva(actual, version) or sha256(nuevo) != estado.get("sha256"):
        _borrar(nuevo)
        _guardar_estado(carpeta, limpio)
        return None
    if not probar(nuevo):
        # No volver a descargar esta versión una y otra vez si Windows no la deja abrir.
        _borrar(nuevo)
        _guardar_estado(carpeta, {"descartadas": [*limpio["descartadas"], version][-5:]})
        return None
    viejo = exe_actual.with_name(exe_actual.name + ".viejo")
    _borrar(viejo)
    os.replace(exe_actual, viejo)   # Windows deja renombrar un .exe en uso, no sobrescribirlo
    try:
        shutil.copyfile(nuevo, exe_actual)
    except OSError:
        _borrar(exe_actual)
        os.replace(viejo, exe_actual)
        raise
    _borrar(nuevo)
    _guardar_estado(carpeta, limpio)
    return version


def limpiar_restos(exe_actual: Path) -> None:
    """Al arrancar: borra el .exe anterior que quedó renombrado tras actualizar."""
    _borrar(exe_actual.with_name(exe_actual.name + ".viejo"))


def aplicar_al_cerrar() -> Optional[str]:
    """Lo llama main() al cerrar la ventana. Nunca lanza excepciones."""
    try:
        if puede_autoactualizarse():
            return aplicar_pendiente(Path(sys.executable).resolve(), __version__, carpeta_pendiente())
    except Exception:
        pass
    return None


def comprobar_en_segundo_plano(avisar: Callable[[str], None]) -> None:
    """Lanza la comprobación en un hilo aparte. Apuntalo.exe (sin el Control inteligente activo)
    prepara la actualización sin decir nada; en los demás casos, si PyPI tiene una versión más
    nueva que la instalada, llama a `avisar(version)`. Si falla, no hace nada."""

    def tarea():
        try:
            if puede_autoactualizarse():
                try:
                    preparar_actualizacion(__version__, carpeta_pendiente())
                    return
                except Exception:
                    pass   # si no se pudo preparar, al menos avisa
            datos = _leer_json(URL_PYPI, TIEMPO_LIMITE)
            ultima = datos["info"]["version"]
        except Exception:
            return
        if hay_version_nueva(__version__, ultima):
            avisar(ultima)

    threading.Thread(target=tarea, daemon=True).start()
