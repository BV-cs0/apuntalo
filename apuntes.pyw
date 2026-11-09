"""Apuntes: programa sencillo para sacar apuntes en Markdown (tkinter)."""
import ctypes
import json
import os
import queue
import threading
import re
import shutil
import subprocess
import sys
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import exportar

# Como .exe (PyInstaller) los apuntes se guardan junto al .exe, no en la carpeta temporal.
BASE = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
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


def iniciar_atajo_global(cola):
    """Ctrl+Alt+A en cualquier programa muestra u oculta la ventana (solo Windows)."""
    if sys.platform != "win32":
        return

    def bucle():
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, 1, 0x0002 | 0x0001 | 0x4000, ord("A")):  # Ctrl+Alt, sin repetir
            return
        msg = ctypes.wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == 0x0312:  # WM_HOTKEY
                cola.put(1)

    import ctypes.wintypes  # noqa: F401
    threading.Thread(target=bucle, daemon=True).start()

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
    texto = ruta.read_text(encoding="utf-8")
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


def texto_util(ocr):
    """Quita las líneas basura del OCR (iconos, letras sueltas)."""
    buenas = []
    for linea in ocr.splitlines():
        l = linea.strip()
        letras = sum(c.isalnum() for c in l)
        if len(l) >= 4 and letras / len(l) >= 0.6 and sum(c.isalpha() for c in l) >= 3:
            buenas.append(l)
    return "\n".join(buenas)


def elegir_modelo_gemini(modelos):
    """Elige el modelo «flash» estable más reciente que admita generateContent."""
    import re as _re
    candidatos = []
    for m in modelos:
        nombre = m.get("name", "")
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        n = nombre.lower()
        if "flash" not in n or any(x in n for x in ("lite", "image", "tts", "live", "audio", "exp", "preview", "thinking")):
            continue
        version = tuple(int(x) for x in _re.findall(r"\d+", n.split("gemini-")[-1])[:2]) or (0,)
        candidatos.append((version, "latest" in n, nombre))
    if not candidatos:
        raise RuntimeError("No encuentro ningún modelo de Gemini disponible para tu clave.")
    return max(candidatos)[2]


class App(tk.Tk):
    def __init__(self):
        if sys.platform == "win32":
            try:  # coordenadas en píxeles reales (para elegir la zona de captura)
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass
        super().__init__()
        self.title("Apúntalo")
        NOTAS.mkdir(exist_ok=True)
        self.actual = None          # Path de la nota abierta
        self.creado = ""
        self.cambiada = False
        self.crono_inicio = None
        self.cfg = cargar_config()
        self.encima = tk.BooleanVar(value=self.cfg.get("encima", False))
        self.opacidad = tk.DoubleVar(value=self.cfg.get("opacidad", 1.0))
        self.compacto = False
        self.geo_normal = self.cfg.get("geo_normal", "1250x720")
        self.geo_compacta = self.cfg.get("geo_compacta", "440x520")
        self.tam_letra = int(self.cfg.get("tam_letra", 12))
        self._construir()
        self.geometry(self.geo_normal)
        self.aplicar_encima()
        self.aplicar_opacidad()
        if self.cfg.get("compacto"):
            self.alternar_compacto()
        self.refrescar()
        self.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.proc_auto = None
        self.nota_auto = None
        self.cola_auto = queue.Queue()
        self.cola_ia = queue.Queue()
        self.cola_atajo = queue.Queue()
        iniciar_atajo_global(self.cola_atajo)
        self._mirar_atajo()
        # Reabrir el último apunte y autoguardar cada 15 s (por si se va la luz o se cierra mal).
        ultima = NOTAS / self.cfg.get("ultima", "-")
        if self.cfg.get("ultima") and ultima.is_file() and ".." not in Path(self.cfg["ultima"]).parts:
            self.cargar(ultima)
            self.refrescar()
        self.after(15000, self._autoguardar)

    def _autoguardar(self):
        if self.cambiada:
            self.guardar(silencioso=True)
        self.after(15000, self._autoguardar)

    # ---------- ventana siempre encima / compacta ----------
    def aplicar_encima(self):
        self.attributes("-topmost", self.encima.get())
        txt = "📌 Fijada" if self.encima.get() else "📌 Fijar"
        for b in (self.btn_fijar, self.btn_fijar2):
            b.configure(text=txt)

    def alternar_encima(self):
        self.encima.set(not self.encima.get())
        self.aplicar_encima()

    def aplicar_opacidad(self, *_):
        self.attributes("-alpha", max(0.3, min(1.0, float(self.opacidad.get()))))

    def alternar_compacto(self):
        if not self.compacto:
            self.geo_normal = self.geometry()
            self.barra.pack_forget()
            self.fila_meta.pack_forget()
            self.panel.forget(self.izq)
            self.mini.pack(fill="x", before=self.panel)
            self.geometry(self.geo_compacta)
            if not self.encima.get():
                self.alternar_encima()
        else:
            self.geo_compacta = self.geometry()
            self.mini.pack_forget()
            self.barra.pack(fill="x", before=self.panel)
            self.panel.insert(0, self.izq, weight=1)
            self.fila_meta.pack(fill="x", before=self.marco)
            self.geometry(self.geo_normal)
        self.compacto = not self.compacto

    def mostrar_ocultar(self):
        if self.state() == "normal" and self.winfo_viewable():
            self.withdraw()
        else:
            self.deiconify()
            self.lift()
            self.focus_force()
            self.texto.focus_set()

    def _mirar_atajo(self):
        try:
            while True:
                self.cola_atajo.get_nowait()
                self.mostrar_ocultar()
        except queue.Empty:
            pass
        self._procesar_auto()
        try:
            while True:
                self._resumen_listo(*self.cola_ia.get_nowait())
        except queue.Empty:
            pass
        self.after(150, self._mirar_atajo)

    # ---------- interfaz ----------
    def _construir(self):
        # Barra en dos filas: arriba organizar, abajo tomar apuntes en clase.
        self.barra = ttk.Frame(self, padding=(4, 4, 4, 0))
        self.barra.pack(fill="x")
        barra = ttk.Frame(self.barra)
        barra.pack(fill="x")
        clase = ttk.Frame(self.barra)
        clase.pack(fill="x", pady=(3, 0))
        self.btn_fijar = ttk.Button(barra, text="📌 Fijar", command=self.alternar_encima)
        self.btn_fijar.pack(side="right")
        ttk.Button(barra, text="🗗 Compacto", command=self.alternar_compacto).pack(side="right", padx=4)
        ttk.Button(barra, text="📤 Exportar", command=self.menu_exportar).pack(side="right")
        ttk.Button(clase, text="✨ Resumir con IA", command=self.resumir_ia).pack(side="right")
        self.btn_auto = ttk.Button(clase, text="🤖 Apuntes automáticos", command=self.alternar_auto)
        self.btn_auto.pack(side="right", padx=4)

        mini = self.mini = ttk.Frame(self, padding=2)
        self.btn_fijar2 = ttk.Button(mini, text="📌", width=9, command=self.alternar_encima)
        self.btn_fijar2.pack(side="left")
        ttk.Button(mini, text="⏱", width=3, command=self.marca_tiempo).pack(side="left")
        self.btn_crono2 = ttk.Button(mini, text="▶", width=9, command=self.crono)
        self.btn_crono2.pack(side="left")
        self.btn_auto2 = ttk.Button(mini, text="🤖", width=4, command=self.alternar_auto)
        self.btn_auto2.pack(side="left")
        ttk.Button(mini, text="💾", width=3, command=self.guardar).pack(side="left")
        ttk.Button(mini, text="⤢", width=3, command=self.alternar_compacto).pack(side="left")
        ttk.Scale(mini, from_=0.3, to=1.0, variable=self.opacidad,
                  command=self.aplicar_opacidad).pack(side="left", fill="x", expand=True, padx=4)

        self.plantilla = tk.StringVar(value="Nota rápida")
        ttk.Button(barra, text="➕ Nueva", command=self.nueva).pack(side="left")
        ttk.Combobox(barra, textvariable=self.plantilla, values=list(PLANTILLAS),
                     state="readonly", width=16).pack(side="left", padx=(2, 8))
        ttk.Button(barra, text="📁 Nueva carpeta", command=self.nueva_carpeta).pack(side="left")
        ttk.Button(barra, text="💾 Guardar", command=self.guardar).pack(side="left", padx=4)
        ttk.Button(barra, text="🗑 Borrar", command=self.borrar).pack(side="left")
        ttk.Button(barra, text="📂 Abrir carpeta", command=lambda: abrir_en_sistema(NOTAS)).pack(side="left", padx=4)
        ttk.Button(clase, text="⏱ Hora", command=self.marca_tiempo).pack(side="left")
        self.btn_crono = ttk.Button(clase, text="▶ Cronómetro", command=self.crono)
        self.btn_crono.pack(side="left", padx=4)
        ttk.Button(clase, text="📎 Adjuntar captura o PDF", command=self.adjuntar).pack(side="left")

        panel = self.panel = ttk.PanedWindow(self, orient="horizontal")
        panel.pack(fill="both", expand=True)

        izq = self.izq = ttk.Frame(panel, padding=4)
        ttk.Label(izq, text="Buscar:").pack(anchor="w")
        self.busqueda = tk.StringVar()
        self.busqueda.trace_add("write", lambda *a: self._despues("buscar", 250, self.refrescar))
        self.caja_buscar = ttk.Entry(izq, textvariable=self.busqueda)
        self.caja_buscar.pack(fill="x")
        ttk.Label(izq, text="Etiqueta:").pack(anchor="w", pady=(4, 0))
        self.filtro_etq = tk.StringVar(value="(todas)")
        self.combo_etq = ttk.Combobox(izq, textvariable=self.filtro_etq, state="readonly")
        self.combo_etq.pack(fill="x")
        self.combo_etq.bind("<<ComboboxSelected>>", lambda e: self.refrescar())
        self.arbol = ttk.Treeview(izq, show="tree", selectmode="browse")
        self.arbol.pack(fill="both", expand=True, pady=(6, 0))
        self.arbol.bind("<<TreeviewSelect>>", self.al_seleccionar)
        panel.add(izq, weight=1)

        der = ttk.Frame(panel, padding=4)
        fila = self.fila_meta = ttk.Frame(der)
        fila.pack(fill="x")
        ttk.Label(fila, text="Título:").grid(row=0, column=0, sticky="w")
        self.titulo = tk.StringVar()
        ttk.Entry(fila, textvariable=self.titulo, font=("Segoe UI", 12, "bold")).grid(row=0, column=1, sticky="ew")
        ttk.Label(fila, text="Carpeta:").grid(row=1, column=0, sticky="w")
        self.carpeta = tk.StringVar()
        self.combo_carpeta = ttk.Combobox(fila, textvariable=self.carpeta)
        self.combo_carpeta.grid(row=1, column=1, sticky="ew", pady=2)
        ttk.Label(fila, text="Etiquetas:").grid(row=2, column=0, sticky="w")
        self.etiquetas = tk.StringVar()
        ttk.Entry(fila, textvariable=self.etiquetas).grid(row=2, column=1, sticky="ew")
        ttk.Label(fila, text="(separadas por comas)", foreground="gray").grid(row=2, column=2, padx=4)
        fila.columnconfigure(1, weight=1)
        for v in (self.titulo, self.carpeta, self.etiquetas):
            v.trace_add("write", lambda *a: self.marcar_cambio())

        marco = self.marco = ttk.Frame(der)
        marco.pack(fill="both", expand=True, pady=(6, 0))
        self.texto = tk.Text(marco, wrap="word", undo=True, font=("Consolas", self.tam_letra), padx=10, pady=8,
                             spacing1=2, spacing3=2)
        self._configurar_resaltado()
        scroll = ttk.Scrollbar(marco, command=self.texto.yview)
        self.texto.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.texto.pack(fill="both", expand=True)
        self.texto.bind("<<Modified>>", self._modificado)
        self.estado = ttk.Label(der, text="", foreground="gray")
        self.estado.pack(side="bottom", anchor="w", before=marco)  # siempre visible abajo
        panel.add(der, weight=3)

        self.bind_all("<Control-s>", lambda e: self.guardar())
        self.bind_all("<Control-n>", lambda e: self.nueva())
        self.bind_all("<Control-t>", lambda e: (self.marca_tiempo(), "break")[1])
        self.bind_all("<Control-f>", lambda e: self.caja_buscar.focus_set())
        self.bind_all("<F9>", lambda e: self.alternar_encima())
        self.bind_all("<F10>", lambda e: self.alternar_compacto())
        self.bind_all("<F8>", lambda e: self.alternar_auto())
        # Tamaño de letra (accesibilidad): Ctrl + / Ctrl - / Ctrl 0 y Ctrl + rueda del ratón
        for tecla in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"):
            self.bind_all(tecla, lambda e: self.cambiar_letra(+1))
        for tecla in ("<Control-minus>", "<Control-KP_Subtract>"):
            self.bind_all(tecla, lambda e: self.cambiar_letra(-1))
        self.bind_all("<Control-0>", lambda e: self.cambiar_letra(0))
        self.texto.bind("<Control-MouseWheel>", lambda e: (self.cambiar_letra(1 if e.delta > 0 else -1), "break")[1])
        self.bind_all("<Control-e>", lambda e: self.menu_exportar())
        self._habilitar_editor(False)

    def _habilitar_editor(self, si):
        self.texto.configure(state="normal" if si else "disabled")

    # ---------- utilidades de la interfaz ----------
    def _despues(self, nombre, ms, funcion):
        """Ejecuta `funcion` cuando pasen `ms` sin volver a pedirlo (para no repetir trabajo al teclear)."""
        if not hasattr(self, "_pendientes"):
            self._pendientes = {}
        if nombre in self._pendientes:
            self.after_cancel(self._pendientes[nombre])
        self._pendientes[nombre] = self.after(ms, lambda: (self._pendientes.pop(nombre, None), funcion()))

    def cambiar_letra(self, paso):
        self.tam_letra = 12 if paso == 0 else max(8, min(32, self.tam_letra + paso))
        self.texto.configure(font=("Consolas", self.tam_letra))
        self._configurar_resaltado()
        self.estado.configure(text=f"Tamaño de letra: {self.tam_letra}  (Ctrl + / Ctrl - / Ctrl 0)")

    def _configurar_resaltado(self):
        t, n = self.texto, self.tam_letra
        t.tag_configure("h1", font=("Segoe UI", n + 7, "bold"), foreground="#1F3864")
        t.tag_configure("h2", font=("Segoe UI", n + 4, "bold"), foreground="#2F5496")
        t.tag_configure("h3", font=("Segoe UI", n + 2, "bold"), foreground="#2F5496")
        t.tag_configure("negrita", font=("Consolas", n, "bold"))
        t.tag_configure("cursiva", font=("Consolas", n, "italic"))
        t.tag_configure("codigo", background="#EEEEEE")
        t.tag_configure("cita", foreground="#666666")
        t.tag_configure("tiempo", foreground="#2F5496")
        t.tag_configure("hecha", foreground="#888888", overstrike=True)
        t.tag_configure("vineta", foreground="#2F5496")

    PATRONES = [
        ("negrita", re.compile(r"\*\*[^*\n]+\*\*")),
        ("cursiva", re.compile(r"(?<![*\w])\*[^*\s][^*\n]*\*(?!\*)")),
        ("codigo", re.compile(r"`[^`\n]+`")),
        ("tiempo", re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?\]")),
    ]

    def resaltar(self):
        """Colorea el Markdown del editor: títulos, negritas, citas, listas, marcas de tiempo."""
        t = self.texto
        for tag in ("h1", "h2", "h3", "negrita", "cursiva", "codigo", "cita", "tiempo", "hecha", "vineta"):
            t.tag_remove(tag, "1.0", "end")
        for n, linea in enumerate(t.get("1.0", "end-1c").split("\n"), start=1):
            if not linea:
                continue
            m = re.match(r"(#{1,3})\s", linea)
            if m:
                t.tag_add("h" + str(len(m.group(1))), f"{n}.0", f"{n}.end")
                continue
            if linea.startswith(">"):
                t.tag_add("cita", f"{n}.0", f"{n}.end")
            elif re.match(r"\s*[-*+]\s+\[[xX]\]", linea):
                t.tag_add("hecha", f"{n}.0", f"{n}.end")
            m = re.match(r"\s*([-*+]|\d+[.)])\s", linea)
            if m:
                t.tag_add("vineta", f"{n}.{m.start(1)}", f"{n}.{m.end(1)}")
            for tag, patron in self.PATRONES:
                for m in patron.finditer(linea):
                    t.tag_add(tag, f"{n}.{m.start()}", f"{n}.{m.end()}")

    def _modificado(self, _e):
        if self.texto.edit_modified():
            self.marcar_cambio()
            self._despues("resaltar", 300, self.resaltar)
            self.texto.edit_modified(False)

    def marcar_cambio(self):
        if self.actual is not None and not getattr(self, "_cargando", False):
            self.cambiada = True
            if getattr(self, "proc_auto", None):
                return  # no tapar el estado del modo automático
            self.estado.configure(text="Cambios sin guardar (se guardan solos al cambiar de nota)")

    # ---------- lista ----------
    def notas(self):
        return sorted(p for p in NOTAS.rglob("*.md") if ADJUNTOS not in p.parents)

    def carpetas(self):
        return sorted(str(p.relative_to(NOTAS)) for p in NOTAS.rglob("*")
                      if p.is_dir() and p != ADJUNTOS and ADJUNTOS not in p.parents)

    def refrescar(self):
        q = self.busqueda.get().lower().strip()
        etq = self.filtro_etq.get()
        self.arbol.delete(*self.arbol.get_children())
        todas_etq = set()
        nodos = {}
        for c in self.carpetas():
            padre = nodos.get(str(Path(c).parent), "")
            nodos[c] = self.arbol.insert(padre, "end", iid="dir:" + c, text="📁 " + Path(c).name, open=True)
        for ruta in self.notas():
            try:
                meta, cuerpo = leer_nota(ruta)
            except Exception:
                continue
            todas_etq.update(meta["etiquetas"])
            if etq != "(todas)" and etq not in meta["etiquetas"]:
                continue
            if q and q not in (meta["titulo"] + " " + cuerpo + " " + " ".join(meta["etiquetas"])).lower():
                continue
            rel = ruta.parent.relative_to(NOTAS)
            padre = "" if str(rel) == "." else nodos.get(str(rel), "")
            self.arbol.insert(padre, "end", iid="nota:" + str(ruta), text="📝 " + meta["titulo"])
        self.combo_etq.configure(values=["(todas)"] + sorted(todas_etq))
        self.combo_carpeta.configure(values=[""] + self.carpetas())
        if self.actual and self.arbol.exists("nota:" + str(self.actual)):
            self.arbol.selection_set("nota:" + str(self.actual))
            self.arbol.see("nota:" + str(self.actual))

    def al_seleccionar(self, _e):
        sel = self.arbol.selection()
        if not sel or not sel[0].startswith("nota:"):
            return
        ruta = Path(sel[0][5:])
        if ruta == self.actual:
            return
        self.guardar(silencioso=True)
        self.cargar(ruta)

    def cargar(self, ruta):
        meta, cuerpo = leer_nota(ruta)
        self._cargando = True
        self.actual = ruta
        self.creado = meta.get("creado", "")
        self.titulo.set(meta["titulo"])
        rel = ruta.parent.relative_to(NOTAS)
        self.carpeta.set("" if str(rel) == "." else str(rel))
        self.etiquetas.set(", ".join(meta["etiquetas"]))
        self._habilitar_editor(True)
        self.texto.delete("1.0", "end")
        self.texto.insert("1.0", cuerpo)
        self.resaltar()
        self.texto.edit_reset()
        self.texto.edit_modified(False)
        self._cargando = False
        self.cambiada = False
        self.estado.configure(text=f"{ruta.relative_to(BASE)}  ·  creado {self.creado}")

    # ---------- acciones ----------
    def nueva(self):
        self.guardar(silencioso=True)
        titulo = simpledialog.askstring("Nueva nota", "Título:", parent=self)
        if not titulo:
            return
        sel = self.arbol.selection()
        carpeta = ""
        if sel and sel[0].startswith("dir:"):
            carpeta = sel[0][4:]
        elif self.actual:
            rel = self.actual.parent.relative_to(NOTAS)
            carpeta = "" if str(rel) == "." else str(rel)
        ruta = self._ruta_libre(NOTAS / carpeta, titulo)
        escribir_nota(ruta, titulo, [], datetime.now().strftime("%Y-%m-%d %H:%M"),
                      PLANTILLAS.get(self.plantilla.get(), ""))
        self.actual = None
        self.cargar(ruta)
        self.refrescar()
        self.texto.focus_set()
        self.texto.mark_set("insert", "end")

    def _ruta_libre(self, carpeta, titulo, excepto=None):
        ruta = carpeta / (slug(titulo) + ".md")
        n = 2
        while ruta.exists() and ruta != excepto:
            ruta = carpeta / f"{slug(titulo)} ({n}).md"
            n += 1
        return ruta

    def guardar(self, silencioso=False):
        if self.actual is None:
            return
        if silencioso and not self.cambiada:
            return
        titulo = self.titulo.get().strip() or "sin titulo"
        carpeta = self.carpeta.get().strip().strip("/\\")
        if ".." in Path(carpeta).parts:
            carpeta = ""
        etiquetas = [e.strip() for e in self.etiquetas.get().split(",") if e.strip()]
        destino_dir = NOTAS / carpeta
        nueva_ruta = self.actual
        if destino_dir != self.actual.parent or slug(titulo) != self.actual.stem.split(" (")[0]:
            nueva_ruta = self._ruta_libre(destino_dir, titulo, excepto=self.actual)
        escribir_nota(nueva_ruta, titulo, etiquetas, self.creado, self.texto.get("1.0", "end-1c"))
        if nueva_ruta != self.actual and self.actual.exists():
            self.actual.unlink()
        if self.nota_auto == self.actual:
            self.nota_auto = nueva_ruta
        self.actual = nueva_ruta
        self.cambiada = False
        self.estado.configure(text=f"Guardado {datetime.now():%H:%M:%S}  ·  {nueva_ruta.relative_to(BASE)}")
        self.refrescar()

    def borrar(self):
        if self.actual is None:
            return
        if not messagebox.askyesno("Borrar", f"¿Borrar «{self.titulo.get()}»?\nSe mueve a la carpeta _papelera."):
            return
        papelera = BASE / "_papelera"
        papelera.mkdir(exist_ok=True)
        shutil.move(str(self.actual), str(papelera / f"{datetime.now():%Y%m%d-%H%M%S} {self.actual.name}"))
        self.actual = None
        self.cambiada = False
        self._cargando = True
        self.titulo.set(""); self.carpeta.set(""); self.etiquetas.set("")
        self._cargando = False
        self.texto.delete("1.0", "end")
        self._habilitar_editor(False)
        self.estado.configure(text="Nota movida a _papelera")
        self.refrescar()

    def nueva_carpeta(self):
        nombre = simpledialog.askstring("Nueva carpeta", "Nombre (puedes usar Asignatura/Tema):", parent=self)
        if not nombre:
            return
        partes = [slug(p) for p in re.split(r"[/\\]", nombre) if p.strip() and p.strip() != ".."]
        if partes:
            (NOTAS.joinpath(*partes)).mkdir(parents=True, exist_ok=True)
            self.refrescar()

    def marca_tiempo(self):
        if self.actual is None:
            return
        if self.crono_inicio is not None:
            s = int(time.time() - self.crono_inicio)
            marca = f"[{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}] "
        else:
            marca = f"[{datetime.now():%H:%M}] "
        self.texto.insert("insert", marca)
        self.texto.focus_set()

    def crono(self):
        if self.crono_inicio is None:
            self.crono_inicio = time.time()
            self._tic()
        else:
            self.crono_inicio = None
            self.btn_crono.configure(text="▶ Cronómetro")
            self.btn_crono2.configure(text="▶")

    def _tic(self):
        if self.crono_inicio is None:
            return
        s = int(time.time() - self.crono_inicio)
        t = f"⏹ {s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"
        self.btn_crono.configure(text=t)
        self.btn_crono2.configure(text=t)
        self.after(1000, self._tic)

    def adjuntar(self):
        if self.actual is None:
            messagebox.showinfo("Adjuntar", "Abre o crea una nota primero.")
            return
        archivo = filedialog.askopenfilename(title="Elige captura o PDF", filetypes=[
            ("Imágenes y PDF", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.pdf"), ("Todos", "*.*")])
        if not archivo:
            return
        ADJUNTOS.mkdir(parents=True, exist_ok=True)
        origen = Path(archivo)
        destino = ADJUNTOS / origen.name
        n = 2
        while destino.exists():
            destino = ADJUNTOS / f"{origen.stem} ({n}){origen.suffix}"
            n += 1
        shutil.copy2(origen, destino)
        rel = os.path.relpath(destino, self.actual.parent).replace("\\", "/")
        signo = "!" if origen.suffix.lower() != ".pdf" else ""
        self.texto.insert("insert", f"\n{signo}[{origen.name}](<{rel}>)\n")
        abrir_en_sistema(destino)  # se abre al lado para pasarlo a limpio

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
            ruta = self._ruta_libre(NOTAS / carpeta, titulo)
            escribir_nota(ruta, titulo, ["automático"], datetime.now().strftime("%Y-%m-%d %H:%M"), "")
            self.cargar(ruta)
            self.refrescar()
        self.guardar(silencioso=True)
        ADJUNTOS.mkdir(parents=True, exist_ok=True)
        origen = Path(getattr(sys, "_MEIPASS", BASE)) / "captura.ps1"
        script = Path(os.environ.get("TEMP", BASE)) / "apuntes_captura.ps1"
        # PowerShell 5.1 necesita BOM para leer bien las tildes.
        script.write_text(origen.read_text(encoding="utf-8"), encoding="utf-8-sig")
        args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                "-Carpeta", str(ADJUNTOS)]
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
                    base = self.nota_auto.parent if self.nota_auto else NOTAS
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

    # ---------- resumen con IA (opcional) ----------
    PROMPT_IA = (
        "Conviertes material de una clase en apuntes de estudio claros, en español. El material puede "
        "incluir notas del alumno, transcripción automática del audio (con errores de reconocimiento y "
        "marcas de tiempo [hh:mm:ss]) y texto leído de las diapositivas (líneas que empiezan por '>'). "
        "Escribe en Markdown con estas secciones cuando haya contenido para ellas: '## Resumen' (un párrafo), "
        "'## Ideas clave' (viñetas, con **negrita** en los conceptos), '## Definiciones', '## Ejemplos y "
        "fórmulas', '## Tareas y fechas' y '## Dudas para repasar'. Corrige los errores evidentes de la "
        "transcripción, ordena el contenido por temas y no inventes nada que no esté en el material. "
        "Devuelve solo los apuntes, sin introducción."
    )

    def resumir_ia(self):
        if self.actual is None:
            messagebox.showinfo("Resumir con IA", "Abre primero el apunte que quieres resumir.")
            return
        self.guardar(silencioso=True)
        v = tk.Toplevel(self)
        v.title("Resumir con IA")
        v.attributes("-topmost", True)
        v.resizable(False, False)
        v.transient(self)
        marco = ttk.Frame(v, padding=12)
        marco.pack()
        ttk.Label(marco, text="¿Con qué IA quieres ordenar este apunte?",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        prov = tk.StringVar(value=self.cfg.get("ia_proveedor", "chatgpt"))
        opciones = [
            ("chatgpt", "ChatGPT (gratis, copiar y pegar)",
             "Copia el apunte con las instrucciones y abre chatgpt.com. Pegas (Ctrl+V), copias la respuesta "
             "y la app crea el apunte ordenado. Sin claves."),
            ("gemini", "Google Gemini (clave gratuita)",
             "Automático. Necesita una clave gratis de aistudio.google.com. Ojo: en el plan gratuito "
             "Google puede usar los textos para mejorar sus productos."),
            ("claude", "Claude de Anthropic (clave de pago)",
             "Automático y de mejor calidad. Necesita una clave de console.anthropic.com; "
             "una clase cuesta unos céntimos."),
        ]
        for valor, titulo, ayuda in opciones:
            ttk.Radiobutton(marco, text=titulo, value=valor, variable=prov).pack(anchor="w", pady=(8, 0))
            ttk.Label(marco, text=ayuda, foreground="gray", wraplength=400,
                      justify="left").pack(anchor="w", padx=(22, 0))

        def seguir():
            self.cfg["ia_proveedor"] = prov.get()
            v.destroy()
            {"chatgpt": self._ia_chatgpt, "gemini": self._ia_gemini, "claude": self._ia_claude}[prov.get()]()

        fila = ttk.Frame(marco)
        fila.pack(fill="x", pady=(12, 0))
        ttk.Button(fila, text="Continuar", command=seguir).pack(side="right")
        ttk.Button(fila, text="Cancelar", command=v.destroy).pack(side="right", padx=4)
        v.bind("<Return>", lambda e: seguir())

    # --- ChatGPT: copiar y pegar, gratis ---
    def _ia_chatgpt(self):
        meta, cuerpo = leer_nota(self.actual)
        origen = self.actual
        texto = (self.PROMPT_IA + "\n\nAquí está el material de la clase:\n\n---\nTítulo: "
                 + meta["titulo"] + "\n\n" + cuerpo)
        self.clipboard_clear()
        self.clipboard_append(texto)
        self.update()
        import webbrowser
        webbrowser.open("https://chatgpt.com/")
        v = tk.Toplevel(self)
        v.title("Resumir con ChatGPT")
        v.attributes("-topmost", True)
        v.resizable(False, False)
        marco = ttk.Frame(v, padding=12)
        marco.pack()
        aviso = ("1. Ya está copiado. En ChatGPT pulsa Ctrl+V y Enviar.\n"
                 "2. Cuando responda, pulsa el botón de copiar que hay debajo de su respuesta.\n"
                 "3. Vuelve aquí y pulsa «Crear apunte con la respuesta».")
        if len(texto) > 40000:
            aviso += ("\n\nEl apunte es muy largo y puede que ChatGPT gratis no lo acepte entero. "
                      "Si falla, divide la clase en dos apuntes.")
        ttk.Label(marco, text=aviso, justify="left", wraplength=420).pack(anchor="w")

        def crear():
            try:
                respuesta = self.clipboard_get().strip()
            except tk.TclError:
                respuesta = ""
            if not respuesta or respuesta == texto.strip():
                messagebox.showinfo("Resumir con ChatGPT",
                                    "Todavía no has copiado la respuesta de ChatGPT.", parent=v)
                return
            v.destroy()
            self._resumen_listo(origen, meta, respuesta, None)

        fila = ttk.Frame(marco)
        fila.pack(fill="x", pady=(12, 0))
        ttk.Button(fila, text="📋 Crear apunte con la respuesta", command=crear).pack(side="right")
        ttk.Button(fila, text="Copiar otra vez", command=lambda: (self.clipboard_clear(),
                                                                  self.clipboard_append(texto))).pack(side="right", padx=4)
        ttk.Button(fila, text="Cerrar", command=v.destroy).pack(side="left")

    # --- Gemini y Claude: automáticos con clave ---
    def _pedir_clave(self, nombre_cfg, variable_entorno, mensaje):
        clave = os.environ.get(variable_entorno) or self.cfg.get(nombre_cfg)
        if clave:
            return clave
        clave = simpledialog.askstring("Resumir con IA", mensaje, parent=self, show="*")
        if clave and clave.strip():
            self.cfg[nombre_cfg] = clave.strip()
            return self.cfg[nombre_cfg]
        return None

    def _lanzar_ia(self, nombre, funcion):
        meta, cuerpo = leer_nota(self.actual)
        origen = self.actual
        self.estado.configure(text=f"✨ Resumiendo con {nombre}… (puede tardar un minuto)")
        self.config(cursor="watch")

        def trabajo():  # en otro hilo: no toca Tk, deja el resultado en la cola
            try:
                self.cola_ia.put((origen, meta, funcion(meta["titulo"], cuerpo), None))
            except Exception as e:  # noqa: BLE001
                self.cola_ia.put((origen, meta, None, str(e)))

        threading.Thread(target=trabajo, daemon=True).start()

    def _ia_gemini(self):
        clave = self._pedir_clave(
            "gemini_key", "GEMINI_API_KEY",
            "Pega tu clave gratuita de Google Gemini.\n"
            "Créala en aistudio.google.com/apikey (con tu cuenta de Google).\n"
            "Se guarda solo en este PC, en config.json.")
        if not clave:
            return

        def llamar(titulo, cuerpo):
            import urllib.error
            import urllib.request
            base = "https://generativelanguage.googleapis.com/v1beta/"
            cab = {"x-goog-api-key": clave, "Content-Type": "application/json"}

            def pedir(url, datos=None):
                req = urllib.request.Request(url, headers=cab,
                                             data=json.dumps(datos).encode() if datos else None)
                try:
                    with urllib.request.urlopen(req, timeout=180) as r:
                        return json.loads(r.read().decode("utf-8"))
                except urllib.error.HTTPError as e:
                    detalle = e.read().decode("utf-8", "replace")
                    if e.code in (400, 401, 403) and ("API_KEY" in detalle or "API key" in detalle):
                        self.cfg.pop("gemini_key", None)
                        raise RuntimeError("La clave de Gemini no es válida.") from None
                    if e.code == 429:
                        raise RuntimeError("Has llegado al límite gratuito de Gemini. Prueba más tarde.") from None
                    raise RuntimeError(f"Gemini respondió con error {e.code}.") from None
                except urllib.error.URLError:
                    raise RuntimeError("No hay conexión a internet.") from None

            modelo = elegir_modelo_gemini(pedir(base + "models?pageSize=200").get("models", []))
            r = pedir(base + modelo + ":generateContent", {
                "systemInstruction": {"parts": [{"text": self.PROMPT_IA}]},
                "contents": [{"role": "user", "parts": [{"text": f"Título: {titulo}\n\n{cuerpo}"}]}],
            })
            partes = (r.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            texto = "".join(p.get("text", "") for p in partes).strip()
            if not texto:
                raise RuntimeError("Gemini no devolvió ningún texto.")
            return texto

        self._lanzar_ia("Gemini", llamar)

    def _ia_claude(self):
        try:
            import anthropic  # noqa: F401
        except ImportError:
            messagebox.showerror("Resumir con IA", "Falta el paquete 'anthropic' (py -3 -m pip install anthropic).")
            return
        clave = self._pedir_clave(
            "api_key", "ANTHROPIC_API_KEY",
            "Pega tu clave de API de Anthropic (console.anthropic.com).\n"
            "Se guarda solo en este PC, en config.json. Cada resumen cuesta unos céntimos.")
        if not clave:
            return

        def llamar(titulo, cuerpo):
            import anthropic
            try:
                r = anthropic.Anthropic(api_key=clave).beta.messages.create(
                    model="claude-opus-5-5",
                    max_tokens=16000,
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                    output_config={"effort": "medium"},
                    system=self.PROMPT_IA,
                    messages=[{"role": "user", "content": f"Título: {titulo}\n\n{cuerpo}"}],
                )
            except anthropic.AuthenticationError:
                self.cfg.pop("api_key", None)
                raise RuntimeError("La clave de API de Anthropic no es válida.") from None
            except anthropic.APIConnectionError:
                raise RuntimeError("No hay conexión a internet.") from None
            if r.stop_reason == "refusal":
                raise RuntimeError("La IA no ha querido procesar este texto.")
            return "".join(b.text for b in r.content if b.type == "text").strip()

        self._lanzar_ia("Claude", llamar)

    def _resumen_listo(self, origen, meta, texto, error):
        self.config(cursor="")
        if error or not texto:
            self.estado.configure(text="")
            messagebox.showerror("Resumir con IA", f"No se pudo resumir:\n{error or 'respuesta vacía'}")
            return
        titulo = meta["titulo"] + " (resumen)"
        ruta = self._ruta_libre(origen.parent, titulo)
        etiquetas = [e for e in meta["etiquetas"] if e != "automático"] + ["resumen"]
        escribir_nota(ruta, titulo, etiquetas, datetime.now().strftime("%Y-%m-%d %H:%M"), texto + "\n")
        self.guardar(silencioso=True)
        self.cargar(ruta)
        self.refrescar()

    # ---------- exportar ----------
    def _datos_nota(self, ruta):
        meta, cuerpo = leer_nota(ruta)
        rel = ruta.parent.relative_to(NOTAS)
        return {"titulo": meta["titulo"], "cuerpo": cuerpo, "fecha": meta.get("creado", ""),
                "asignatura": "" if str(rel) == "." else " / ".join(rel.parts),
                "etiquetas": meta["etiquetas"], "carpeta": str(ruta.parent)}

    def _carpeta_elegida(self):
        sel = self.arbol.selection()
        if sel and sel[0].startswith("dir:"):
            return NOTAS / sel[0][4:]
        if self.actual and self.actual.parent != NOTAS:
            return self.actual.parent
        return None

    def menu_exportar(self):
        self.guardar(silencioso=True)
        m = tk.Menu(self, tearoff=0)
        if self.actual:
            m.add_command(label="Este apunte → PDF", command=lambda: self.exportar("nota", "pdf"))
            m.add_command(label="Este apunte → Word (.docx)", command=lambda: self.exportar("nota", "docx"))
            m.add_separator()
        carpeta = self._carpeta_elegida()
        if carpeta:
            nombre = carpeta.relative_to(NOTAS).as_posix()
            m.add_command(label=f"Carpeta «{nombre}» → PDF", command=lambda: self.exportar("carpeta", "pdf"))
            m.add_command(label=f"Carpeta «{nombre}» → Word (.docx)", command=lambda: self.exportar("carpeta", "docx"))
            m.add_separator()
        m.add_command(label="Todos los apuntes → PDF", command=lambda: self.exportar("todo", "pdf"))
        m.add_command(label="Todos los apuntes → Word (.docx)", command=lambda: self.exportar("todo", "docx"))
        m.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def exportar(self, que, formato):
        if que == "nota":
            rutas, titulo = [self.actual], self.titulo.get()
        else:
            raiz = self._carpeta_elegida() if que == "carpeta" else NOTAS
            rutas = [p for p in raiz.rglob("*.md") if ADJUNTOS not in p.parents]
            titulo = raiz.relative_to(NOTAS).as_posix() if que == "carpeta" else "Apuntes"
        notas = sorted((self._datos_nota(r) for r in rutas), key=lambda n: (n["asignatura"], n["fecha"], n["titulo"]))
        if not notas:
            messagebox.showinfo("Exportar", "No hay apuntes que exportar.")
            return
        if que == "nota" and notas[0]["asignatura"]:
            cab = f"{notas[0]['asignatura']}  ·  {notas[0]['fecha']}"
        else:
            cab = titulo
        salida = BASE / "exportados"
        salida.mkdir(exist_ok=True)
        destino = filedialog.asksaveasfilename(
            parent=self, initialdir=salida, initialfile=slug(titulo.replace("/", " - ")) + "." + formato,
            defaultextension="." + formato,
            filetypes=[("PDF", "*.pdf")] if formato == "pdf" else [("Documento de Word", "*.docx")])
        if not destino:
            return
        self.config(cursor="watch")
        self.update()
        try:
            (exportar.a_pdf if formato == "pdf" else exportar.a_docx)(notas, destino, cab)
        except Exception as e:
            messagebox.showerror("Exportar", f"No se pudo exportar:\n{e}")
            return
        finally:
            self.config(cursor="")
        self.estado.configure(text=f"Exportado: {destino}")
        if messagebox.askyesno("Exportar", "Exportado. ¿Abrirlo ahora?"):
            abrir_en_sistema(destino)

    def cerrar(self):
        self.parar_auto()
        self.guardar(silencioso=True)
        if self.compacto:
            self.geo_compacta = self.geometry()
        else:
            self.geo_normal = self.geometry()
        self.cfg.update({"encima": self.encima.get(), "opacidad": round(float(self.opacidad.get()), 2),
                         "compacto": self.compacto, "geo_normal": self.geo_normal,
                         "geo_compacta": self.geo_compacta, "tam_letra": self.tam_letra,
                         "ultima": self.actual.relative_to(NOTAS).as_posix() if self.actual else ""})
        guardar_config(self.cfg)
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
