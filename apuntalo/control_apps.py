"""Detecta si el Control inteligente de aplicaciones de Windows 11 está bloqueando programas.

Con ese control activo, Windows no deja abrir un acceso directo a un .exe que lleva la marca
de «descargado de Internet» (como Apuntalo.exe recién bajado de GitHub, que no está firmado),
aunque el .exe en sí sí se abra. Tampoco conviene que el programa se sustituya solo. Por eso,
con el control activo, Apúntalo no crea esos accesos ni se autoactualiza: solo avisa."""
import sys
from pathlib import Path

CLAVE = r"SYSTEM\CurrentControlSet\Control\CI\Policy"
VALOR = "VerifiedAndReputablePolicyState"
ACTIVO = 1   # 0 = desactivado, 1 = activado (bloquea), 2 = en evaluación (no bloquea)
ZONA_INTERNET = 3


def activo() -> bool:
    """True si el control está activado y bloqueando. Ante cualquier duda, False."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CLAVE) as clave:
            valor, _ = winreg.QueryValueEx(clave, VALOR)
        return valor == ACTIVO
    except (OSError, ImportError):
        return False


def marcado_de_internet(archivo: Path) -> bool:
    """True si Windows marcó el archivo como descargado de Internet (Zone.Identifier, zona 3 o 4)."""
    try:
        texto = Path(f"{archivo}:Zone.Identifier").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    for linea in texto.splitlines():
        clave, _, valor = linea.partition("=")
        if clave.strip().lower() == "zoneid":
            return valor.strip().isdigit() and int(valor.strip()) >= ZONA_INTERNET
    return False


def bloquea_accesos(exe: Path) -> bool:
    """True si un acceso directo a `exe` no se podría abrir en este PC."""
    return activo() and marcado_de_internet(exe)
