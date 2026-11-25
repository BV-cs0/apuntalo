"""Comprueba en segundo plano si hay una versión de Apúntalo más nueva que la instalada."""
import json
import re
import threading
import urllib.request
from typing import Callable

from . import __version__

URL_PYPI = "https://pypi.org/pypi/apuntalo/json"
TIEMPO_LIMITE = 4   # segundos: si no hay respuesta, no se espera más ni se bloquea nada


def _version_a_tupla(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", version)) or (0,)


def hay_version_nueva(actual: str, ultima: str) -> bool:
    return _version_a_tupla(ultima) > _version_a_tupla(actual)


def comprobar_en_segundo_plano(avisar: Callable[[str], None]) -> None:
    """Lanza la comprobación en un hilo aparte. Si PyPI tiene una versión más nueva que la
    instalada, llama a `avisar(version)`. Si falla (sin internet, PyPI caído...), no hace nada."""

    def tarea():
        try:
            with urllib.request.urlopen(URL_PYPI, timeout=TIEMPO_LIMITE) as resp:
                datos = json.loads(resp.read().decode("utf-8"))
            ultima = datos["info"]["version"]
        except Exception:
            return
        if hay_version_nueva(__version__, ultima):
            avisar(ultima)

    threading.Thread(target=tarea, daemon=True).start()
