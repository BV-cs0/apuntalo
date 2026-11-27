"""Dónde se guardan los apuntes y la configuración, y cómo se leen y escriben."""
import ctypes
import json
import os
import re
import subprocess
import sys
from pathlib import Path


PAQUETE = Path(__file__).resolve().parent


def carpeta_windows(csidl, nombre):
    """Una carpeta especial de Windows tal como la tiene el usuario (puede estar en OneDrive)."""
    if sys.platform == "win32":
        try:
            buf = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0:
                return Path(buf.value)
        except Exception:
            pass
    ruta = Path.home() / nombre
    return ruta if ruta.is_dir() else Path.home()


def carpeta_documentos():
    """La carpeta Documentos real del usuario."""
    return carpeta_windows(5, "Documents")   # CSIDL_PERSONAL


def carpeta_datos():
    """Dónde se guardan los apuntes, según cómo se haya instalado la app."""
    for arg in sys.argv[1:]:
        if arg.startswith("--datos="):      # la pone _reabrir_como_admin al pedir permisos
            return Path(arg.split("=", 1)[1])
    if os.environ.get("APUNTALO_DATOS"):
        return Path(os.environ["APUNTALO_DATOS"])
    if getattr(sys, "frozen", False):           # Apuntalo.exe: portátil, junto al .exe
        return Path(sys.executable).resolve().parent
    if {"site-packages", "dist-packages"} & set(PAQUETE.parts):   # instalado con pip
        return carpeta_documentos() / "Apuntalo"
    return PAQUETE.parent                        # desde el código fuente: en la carpeta del proyecto


BASE = carpeta_datos()
NOTAS = BASE / "notas"
ADJUNTOS = NOTAS / "_adjuntos"
CONFIG = BASE / "config.json"


def cargar_config():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def guardar_config(cfg):
    try:
        CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        pass

PLANTILLAS = {
    "Nota rápida": "",
    "Clase / estudio": "## Tema\n\n## Ideas clave\n- \n\n## Definiciones\n- \n\n## Dudas\n- \n\n## Resumen\n",
    "Vídeo / reunión": "Enlace / asistentes: \n\n## Apuntes\n(Pulsa Ctrl+T para insertar la marca de tiempo)\n\n## Tareas\n- [ ] \n",
    "Captura / PDF": "Fuente: \n\n## Texto pasado a limpio\n\n## Comentarios\n",
}


def slug(texto):
    s = re.sub(r'[<>:"/\\|?*\n\r\t]', "", texto).strip().strip(".")
    return s[:80] or "sin titulo"


def leer_nota(ruta):
    texto = ruta.read_text(encoding="utf-8-sig").replace("\r\n", "\n")   # sin BOM ni saltos de Windows
    meta, cuerpo = {}, texto
    if texto.startswith("---\n"):
        fin = texto.find("\n---\n", 4)
        if fin != -1:
            for linea in texto[4:fin].splitlines():
                if ":" in linea:
                    k, v = linea.split(":", 1)
                    meta[k.strip()] = v.strip()
            cuerpo = texto[fin + 5:]
    meta.setdefault("titulo", ruta.stem)
    meta["etiquetas"] = [e.strip() for e in meta.get("etiquetas", "").split(",") if e.strip()]
    return meta, cuerpo


def escribir_nota(ruta, titulo, etiquetas, creado, cuerpo):
    cab = f"---\ntitulo: {titulo}\netiquetas: {', '.join(etiquetas)}\ncreado: {creado}\n---\n"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(cab + cuerpo, encoding="utf-8")


def abrir_en_sistema(ruta):
    if sys.platform == "win32":
        os.startfile(ruta)
    else:
        subprocess.Popen(["xdg-open", str(ruta)])
