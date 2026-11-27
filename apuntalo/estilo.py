"""Letras y colores de la app (tema claro y oscuro)."""
import sys


LETRA = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"
MONO = "Consolas" if sys.platform == "win32" else "DejaVu Sans Mono"

# Colores de la app en un solo sitio (claro y oscuro)
TEMAS = {
    "claro": {
        "fondo": "#F3F4F7", "hoja": "#FFFFFF", "texto": "#1F2430", "suave": "#8A90A0", "borde": "#DADDE5",
        "acento": "#2F5496", "acento_suave": "#E6ECF8", "titulo": "#1F3864", "codigo": "#F1F2F5",
        "sel": "#CFE0FF", "boton": "#FFFFFF", "boton_hover": "#EAEFF8",
        "bloques": {"idea": "#FFF6D6", "ojo": "#FFE6E2", "resumen": "#E3F5E6", "nota": "#EEF0F4",
                    "pregunta": "#EFE8FB", "definicion": "#E3EEFB", "cita": "#F4F5F8"},
    },
    "oscuro": {
        "fondo": "#16181D", "hoja": "#1E2128", "texto": "#E4E6EB", "suave": "#8B92A3", "borde": "#30343D",
        "acento": "#7AA2F7", "acento_suave": "#26314A", "titulo": "#A9C1FF", "codigo": "#2A2E37",
        "sel": "#33415E", "boton": "#262A33", "boton_hover": "#30364A",
        "bloques": {"idea": "#3A3420", "ojo": "#3F2726", "resumen": "#203827", "nota": "#2A2E37",
                    "pregunta": "#30284A", "definicion": "#22324A", "cita": "#262A33"},
    },
}
