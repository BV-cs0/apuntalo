"""Adjuntos: archivos adjuntos, pegar con Ctrl+V e imágenes dentro del texto."""
import os
import re
import shutil
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

from . import datos, portapapeles


class AdjuntosMixin:
    """Métodos de App: archivos adjuntos, pegar con Ctrl+V e imágenes dentro del texto."""

    def adjuntar(self):
        if self.actual is None:
            messagebox.showinfo("Adjuntar", "Abre o crea una nota primero.")
            return
        archivo = filedialog.askopenfilename(title="Elige captura o PDF", filetypes=[
            ("Imágenes y PDF", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.pdf"), ("Todos", "*.*")])
        if not archivo:
            return
        origen = Path(archivo)
        destino = self._ruta_adjunto(origen.name)
        shutil.copy2(origen, destino)
        self._insertar_adjunto(destino)
        datos.abrir_en_sistema(destino)  # se abre al lado para pasarlo a limpio

    def _ruta_adjunto(self, nombre):
        """Ruta libre en _adjuntos para un archivo nuevo."""
        datos.ADJUNTOS.mkdir(parents=True, exist_ok=True)
        base = Path(nombre)
        destino, n = datos.ADJUNTOS / base.name, 2
        while destino.exists():
            destino = datos.ADJUNTOS / f"{base.stem} ({n}){base.suffix}"
            n += 1
        return destino

    def _insertar_adjunto(self, destino):
        """Pone el enlace Markdown al adjunto en una línea propia, donde está el cursor."""
        rel = os.path.relpath(destino, self.actual.parent).replace("\\", "/")
        signo = "" if destino.suffix.lower() == ".pdf" else "!"
        antes = "" if self.texto.compare("insert", "==", "insert linestart") else "\n"
        self.texto.insert("insert", f"{antes}{signo}[{destino.stem}](<{rel}>)\n")
        self.texto.see("insert")

    def pegar(self, _e=None):
        """Ctrl+V: si hay una imagen o archivos copiados, se guardan como adjuntos; si no, pega texto."""
        if self.actual is None or str(self.texto.cget("state")) == "disabled":
            return None
        if portapapeles.hay_texto():
            return None  # pegado normal de texto
        png = portapapeles.imagen_png()
        if png:
            destino = self._ruta_adjunto(f"imagen {datetime.now():%Y-%m-%d %H.%M.%S}.png")
            destino.write_bytes(png)
            self._insertar_adjunto(destino)
            self.estado.configure(text=f"🖼 Imagen pegada: {destino.name}")
            return "break"
        rutas = [Path(r) for r in portapapeles.archivos() if Path(r).is_file()]
        if rutas:
            for origen in rutas:
                destino = self._ruta_adjunto(origen.name)
                shutil.copy2(origen, destino)
                self._insertar_adjunto(destino)
            self.estado.configure(text=f"📎 {len(rutas)} archivo(s) pegado(s) como adjuntos")
            return "break"
        return None

    # ---------- vista previa de imágenes dentro del editor ----------
    RE_IMAGEN = re.compile(r"!\[[^\]]*\]\(<?([^)>]+)>?\)")

    def _miniatura(self, ruta):
        """La imagen reducida (si hace falta) al ancho del editor."""
        if not hasattr(self, "_miniaturas"):
            self._miniaturas = {}
        ancho_editor = self.texto.winfo_width()
        maximo = ancho_editor - 60 if ancho_editor > 300 else 800
        clave = (str(ruta), ruta.stat().st_mtime, maximo)
        if clave not in self._miniaturas:
            img = tk.PhotoImage(file=str(ruta))
            factor = max(1, -(-img.width() // maximo))
            self._miniaturas[clave] = img.subsample(factor) if factor > 1 else img
        return self._miniaturas[clave]

    def mostrar_imagenes(self, lineas=None):
        """En el editor, cambia cada enlace ![..](..) a un PNG/GIF por la propia imagen.

        El enlace sigue en el texto (se guarda en el .md y sirve para exportar), pero queda oculto."""
        t = self.texto
        if self.actual is None:
            return
        if lineas is None:
            lineas = t.get("1.0", "end-1c").split("\n")
        deseadas = []
        for n, linea in enumerate(lineas, start=1):
            m = self.RE_IMAGEN.search(linea)
            if not m:
                continue
            ruta = (self.actual.parent / m.group(1)).resolve()
            if ruta.suffix.lower() in (".png", ".gif") and ruta.is_file():
                deseadas.append((n, str(ruta), m.start(), m.end()))
        nombres = getattr(self, "_img_ruta", {})
        actuales = [(int(idx.split(".")[0]), nombres.get(nombre)) for _, nombre, idx in t.dump("1.0", "end", image=True)]
        if actuales == [(n, r) for n, r, _, _ in deseadas]:
            return
        self._img_ruta = {}
        t.tag_remove("oculto", "1.0", "end")
        for _, nombre, _ in t.dump("1.0", "end", image=True):
            t.delete(nombre)
        for n, ruta, ini, fin in deseadas:
            try:
                img = self._miniatura(Path(ruta))
            except (tk.TclError, OSError):
                continue
            nombre = t.image_create(f"{n}.{ini}", image=img, padx=4, pady=6)
            self._img_ruta[nombre] = ruta
            t.tag_add("oculto", f"{n}.{ini + 1}", f"{n}.{fin + 1}")   # el enlace va justo detrás de la imagen
        t.edit_modified(False)  # mostrar imágenes no es un cambio del apunte

    def _borrar_imagen(self, adelante):
        """Retroceso/Supr junto a una imagen: borra la imagen y su enlace oculto de una vez."""
        t = self.texto
        if t.tag_ranges("sel"):
            return None
        idx = t.index("insert" if adelante else "insert-1c")
        es_imagen = bool(t.dump(idx, f"{idx}+1c", image=True))
        if not es_imagen and "oculto" not in t.tag_names(idx):
            return None
        linea = idx.split(".")[0]
        for _, nombre, inicio in t.dump(f"{linea}.0", f"{linea}.end", image=True):
            rango = t.tag_nextrange("oculto", inicio)
            fin = rango[1] if rango else f"{inicio}+1c"
            if t.compare(inicio, "<=", idx) and t.compare(idx, "<", fin):
                t.delete(inicio, fin)
                if not t.get(f"{linea}.0", f"{linea}.end").strip():
                    t.delete(f"{linea}.0", f"{linea}.0+1c")   # no dejar una línea vacía
                self.marcar_cambio()
                return "break"
        return None
