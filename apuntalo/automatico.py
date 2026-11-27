"""Apuntes automáticos: subtítulos en directo y capturas con OCR."""
import ctypes
import json
import os
import queue
import threading
import subprocess
import sys
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from . import datos


def texto_util(ocr):
    """Quita las líneas basura del OCR (iconos, letras sueltas)."""
    buenas = []
    for linea in ocr.splitlines():
        l = linea.strip()
        letras = sum(c.isalnum() for c in l)
        if len(l) >= 4 and letras / len(l) >= 0.6 and sum(c.isalpha() for c in l) >= 3:
            buenas.append(l)
    return "\n".join(buenas)


class AutomaticoMixin:
    """Métodos de App: apuntes automáticos con los subtítulos en directo y capturas con OCR."""

    # ---------- apuntes automáticos (audio + pantalla) ----------
    def alternar_auto(self):
        if self.proc_auto:
            self.parar_auto()
            return
        v = tk.Toplevel(self)
        v.title("Apuntes automáticos")
        v.attributes("-topmost", True)
        v.resizable(False, False)
        v.transient(self)
        audio = tk.BooleanVar(value=self.cfg.get("auto_audio", True))
        pantalla = tk.BooleanVar(value=self.cfg.get("auto_pantalla", True))
        marco = ttk.Frame(v, padding=12)
        marco.pack()
        ttk.Label(marco, text="¿Qué quieres que apunte solo?", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Checkbutton(marco, text="🎧 Lo que se escucha (Subtítulos en directo de Windows)",
                        variable=audio).pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(marco, text="🖥 Lo que se ve (captura y texto de cada pantalla nueva)",
                        variable=pantalla).pack(anchor="w")
        zona = tk.StringVar(value=self.cfg.get("auto_zona", ""))
        fz = ttk.Frame(marco)
        fz.pack(fill="x", padx=(20, 0))
        lz = ttk.Label(fz, foreground="gray")
        lz.pack(side="left")

        def pintar_zona():
            z = zona.get()
            lz.configure(text=("Zona: " + "×".join(z.split(",")[2:]) + " px") if z else "Zona: toda la pantalla")

        def elegir():
            v.withdraw()

            def hecho(z):
                if z:
                    zona.set(z)
                pintar_zona()
                v.deiconify()
            self.elegir_zona(hecho)

        ttk.Button(fz, text="✂ Elegir zona del vídeo", command=elegir).pack(side="left", padx=6)
        ttk.Button(fz, text="Toda", width=5, command=lambda: (zona.set(""), pintar_zona())).pack(side="left")
        pintar_zona()
        ttk.Label(marco, foreground="gray", wraplength=380, justify="left",
                  text="Se añade al apunte abierto (o a uno nuevo). La ventana de Apúntalo no sale en "
                       "las capturas. Pide permiso antes de grabar una clase.").pack(anchor="w", pady=6)

        def empezar():
            if not (audio.get() or pantalla.get()):
                return
            self.cfg["auto_audio"], self.cfg["auto_pantalla"] = audio.get(), pantalla.get()
            self.cfg["auto_zona"] = zona.get()
            v.destroy()
            self.empezar_auto(audio.get(), pantalla.get(), zona.get())

        fila = ttk.Frame(marco)
        fila.pack(fill="x")
        ttk.Button(fila, text="▶ Empezar", command=empezar).pack(side="right")
        ttk.Button(fila, text="Cancelar", command=v.destroy).pack(side="right", padx=4)
        v.bind("<Return>", lambda e: empezar())

    def empezar_auto(self, audio, pantalla, zona=""):
        if self.actual is None:
            carpeta = ""
            sel = self.arbol.selection()
            if sel and sel[0].startswith("dir:"):
                carpeta = sel[0][4:]
            titulo = f"Clase {datetime.now():%d-%m-%Y %H.%M}"
            ruta = self._ruta_libre(datos.NOTAS / carpeta, titulo)
            datos.escribir_nota(ruta, titulo, ["automático"], datetime.now().strftime("%Y-%m-%d %H:%M"), "")
            self.cargar(ruta)
            self.refrescar()
        self.guardar(silencioso=True)
        datos.ADJUNTOS.mkdir(parents=True, exist_ok=True)
        origen = datos.PAQUETE / "captura.ps1"
        script = Path(os.environ.get("TEMP", datos.BASE)) / "apuntes_captura.ps1"
        # PowerShell 5.1 necesita BOM para leer bien las tildes.
        script.write_text(origen.read_text(encoding="utf-8"), encoding="utf-8-sig")
        args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                "-Carpeta", str(datos.ADJUNTOS)]
        if audio:
            args.append("-Audio")
        if pantalla:
            args.append("-Pantalla")
            if zona:
                args += ["-Zona", zona]
        try:
            self.proc_auto = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                              stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace",
                                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as e:
            messagebox.showerror("Apuntes automáticos", f"No se pudo empezar:\n{e}")
            return
        proc, cola = self.proc_auto, self.cola_auto

        def leer():
            for linea in proc.stdout:
                try:
                    cola.put((proc, json.loads(linea)))
                except ValueError:
                    pass
            cola.put((proc, {"tipo": "fin"}))

        threading.Thread(target=leer, daemon=True).start()
        self.nota_auto = self.actual
        self.inicio_auto = time.time()
        self.ultima_voz = 0
        self._excluir_de_capturas(True)
        fuentes = " + ".join(x for x, s in (("audio", audio), ("pantalla", pantalla)) if s)
        self._anadir_auto(f"\n\n## 🤖 Apuntes automáticos ({datetime.now():%H:%M}, {fuentes})\n")
        for b in (self.btn_auto, self.btn_auto2):
            b.configure(text="⏹ Parar automáticos" if b is self.btn_auto else "⏹")
        self.estado.configure(text="🤖 Tomando apuntes automáticos… (F8 para parar)"
                              + ("  ·  Abriendo Subtítulos en directo…" if audio else ""))

    def elegir_zona(self, al_terminar):
        """Pantalla semitransparente: arrastra un recuadro sobre el vídeo."""
        self.withdraw()
        capa = tk.Toplevel(self)
        capa.overrideredirect(True)
        capa.attributes("-topmost", True)
        capa.attributes("-alpha", 0.35)
        ancho, alto = self.winfo_screenwidth(), self.winfo_screenheight()
        capa.geometry(f"{ancho}x{alto}+0+0")
        lienzo = tk.Canvas(capa, bg="black", cursor="crosshair", highlightthickness=0)
        lienzo.pack(fill="both", expand=True)
        lienzo.create_text(ancho // 2, 60, fill="white", font=("Segoe UI", 20, "bold"),
                           text="Arrastra un recuadro sobre el vídeo o las diapositivas  ·  Esc para cancelar")
        ini = {}

        def bajar(e):
            ini["x"], ini["y"] = e.x_root, e.y_root
            ini["r"] = lienzo.create_rectangle(e.x, e.y, e.x, e.y, outline="#4da3ff", width=3, fill="white")

        def mover(e):
            if "r" in ini:
                lienzo.coords(ini["r"], ini["x"] - capa.winfo_rootx(), ini["y"] - capa.winfo_rooty(), e.x, e.y)

        def terminar(z):
            capa.destroy()
            self.deiconify()
            al_terminar(z)

        def soltar(e):
            if "x" not in ini:
                return
            x0, y0 = min(ini["x"], e.x_root), min(ini["y"], e.y_root)
            w, h = abs(e.x_root - ini["x"]), abs(e.y_root - ini["y"])
            terminar(f"{x0},{y0},{w},{h}" if w > 40 and h > 40 else None)

        lienzo.bind("<ButtonPress-1>", bajar)
        lienzo.bind("<B1-Motion>", mover)
        lienzo.bind("<ButtonRelease-1>", soltar)
        capa.bind("<Escape>", lambda e: terminar(None))
        capa.focus_force()

    def parar_auto(self):
        if not self.proc_auto:
            return
        try:
            self.proc_auto.kill()
        except OSError:
            pass
        self.proc_auto = None
        self._excluir_de_capturas(False)
        self.btn_auto.configure(text="🤖 Apuntes automáticos")
        self.btn_auto2.configure(text="🤖")
        self.estado.configure(text="Apuntes automáticos parados")
        self.guardar(silencioso=True)

    def _excluir_de_capturas(self, si):
        if sys.platform != "win32":
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11 if si else 0)  # WDA_EXCLUDEFROMCAPTURE
        except Exception:
            pass

    def _tiempo_auto(self):
        s = int(time.time() - self.inicio_auto)
        return f"[{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}]"

    def _anadir_auto(self, texto):
        """Añade texto al final de la nota automática (esté abierta o no)."""
        if self.actual == self.nota_auto:
            abajo = self.texto.yview()[1] > 0.95
            self.texto.insert("end-1c", texto)
            if abajo:
                self.texto.see("end")
        elif self.nota_auto and self.nota_auto.exists():
            with open(self.nota_auto, "a", encoding="utf-8") as f:
                f.write(texto)

    def _procesar_auto(self):
        try:
            while True:
                proc, ev = self.cola_auto.get_nowait()
                if proc is not self.proc_auto:
                    continue
                tipo = ev.get("tipo")
                if tipo == "voz":
                    ahora = time.time()
                    if ahora - self.ultima_voz > 20:
                        self._anadir_auto(f"\n\n{self._tiempo_auto()} {ev['texto']}")
                    else:
                        self._anadir_auto(" " + ev["texto"])
                    self.ultima_voz = ahora
                elif tipo == "diapo":
                    png = Path(ev["png"])
                    base = self.nota_auto.parent if self.nota_auto else datos.NOTAS
                    rel = os.path.relpath(png, base).replace("\\", "/")
                    texto = "\n".join("> " + l for l in texto_util(ev.get("texto", "")).splitlines())
                    self._anadir_auto(f"\n\n### 🖥 Pantalla {self._tiempo_auto()}\n![pantalla](<{rel}>)\n"
                                      + (texto + "\n" if texto else ""))
                    self.ultima_voz = 0
                elif tipo == "aviso":
                    self.estado.configure(text="🤖 " + ev["texto"])
                elif tipo == "fin":
                    self.proc_auto = None
                    self._excluir_de_capturas(False)
                    self.btn_auto.configure(text="🤖 Apuntes automáticos")
                    self.btn_auto2.configure(text="🤖")
                    self.estado.configure(text="⚠ La captura automática se detuvo sola")
        except queue.Empty:
            pass
