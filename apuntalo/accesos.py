"""Crea los accesos directos de Apúntalo (Escritorio y menú Inicio) la primera vez que se
abre Apuntalo.exe, para que quede accesible como un programa instalado. No mueve ni copia
el .exe: el acceso directo apunta a donde esté, así que la carpeta sigue siendo portátil."""
import os
import subprocess
import sys
from pathlib import Path

PAQUETE = Path(__file__).resolve().parent
NOMBRE = "Apúntalo.lnk"


def _crear_uno(destino: Path, objetivo: Path) -> bool:
    origen = PAQUETE / "crear_acceso.ps1"
    script = Path(os.environ.get("TEMP", str(objetivo.parent))) / "apuntalo_acceso.ps1"
    try:
        # PowerShell 5.1 necesita BOM para leer bien las tildes (igual que captura.ps1).
        script.write_text(origen.read_text(encoding="utf-8"), encoding="utf-8-sig")
        args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                "-Destino", str(destino), "-Objetivo", str(objetivo),
                "-Carpeta", str(objetivo.parent), "-Icono", f"{objetivo},0"]
        subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                       timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=True)
        return True
    except Exception:
        return False


def crear_accesos_directos(destinos: list[Path], objetivo: Path) -> bool:
    """Crea un acceso directo a `objetivo` (el .exe) en cada carpeta de `destinos`.
    Solo hace algo en Windows. Si una carpeta falla no deja de intentar las demás.
    Devuelve True solo si TODAS tuvieron éxito: un fallo suele ser puntual (por ejemplo,
    Windows analizando el .ps1 recién creado la primera vez), así que quien llame a esto
    debe poder reintentar en el próximo arranque los destinos que fallaron."""
    if sys.platform != "win32":
        return False
    resultados = [_crear_uno(destino / NOMBRE, objetivo) for destino in destinos]
    return all(resultados)


def quitar_accesos_rotos(destinos: list[Path], objetivo: Path) -> int:
    """Con el Control inteligente de aplicaciones activo, Windows no deja abrir los accesos
    directos al .exe: quita los que creó Apúntalo (los que apuntan a `objetivo`) para que no
    quede en el Escritorio un icono que no abre. Nunca toca otros accesos. Devuelve cuántos quitó."""
    # El acceso guarda la ruta del .exe en UTF-16 (icono y destino); así se reconoce sin abrir PowerShell.
    huella = str(objetivo).encode("utf-16-le").lower()
    quitados = 0
    for destino in destinos:
        acceso = destino / NOMBRE
        try:
            if acceso.is_file() and huella in acceso.read_bytes().lower():
                acceso.unlink()
                quitados += 1
        except OSError:
            pass
    return quitados
