"""Apúntalo: programa sencillo para sacar apuntes de clase en Markdown (tkinter)."""
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
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import editor, exportar, importar, ortografia, portapapeles

PAQUETE = Path(__file__).resolve().parent

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
        NOTAS.mkdir(parents=True, exist_ok=True)
        try:
            self.iconbitmap(default=str(PAQUETE / "apuntalo.ico"))
        except tk.TclError:
            pass
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
        self.oscuro = bool(self.cfg.get("oscuro", False))
        self.ocultar_barra = tk.BooleanVar(value=self.cfg.get("ocultar_barra", False))
        if self.ocultar_barra.get():
            self._mostrar_barras()      # por si la última vez se cerró de golpe con la barra escondida
            import atexit
            atexit.register(self._mostrar_barras)
        self._construir()
        self.geometry(self.geo_normal)
        self.aplicar_encima()
        self.aplicar_opacidad()
        if self.cfg.get("compacto"):
            self.alternar_compacto()
        self.refrescar()
        self.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.bind("<FocusIn>", self._al_enfocar, add="+")
        self.bind("<FocusOut>", self._al_desenfocar, add="+")
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
        if not self.encima.get() and getattr(self, "_barras_ocultas", False):
            self._mostrar_barras()
        txt = "📌 Fijada" if self.encima.get() else "📌 Fijar"
        for b in (self.btn_fijar, self.btn_fijar2):
            b.configure(text=txt)

    def alternar_encima(self):
        self.encima.set(not self.encima.get())
        self.aplicar_encima()

    def _al_enfocar(self, e=None):
        """Fijada encima de un vídeo a pantalla completa: Windows saca la barra de tareas al dar el foco
        a Apúntalo. La mandamos detrás del vídeo (vuelve sola al salir de pantalla completa) o, con la
        opción «Ocultar la barra de tareas», la escondemos mientras escribes."""
        if sys.platform == "win32" and self.encima.get() and not getattr(self, "_barra_pendiente", False):
            self._barra_pendiente = True
            self.after(450, lambda: setattr(self, "_barra_pendiente", False))
            for ms in (60, 400):
                self.after(ms, self._esconder_barra_tareas)

    def _al_desenfocar(self, e=None):
        # FocusOut también salta al moverse entre campos de la propia ventana: miramos un poco después
        if getattr(self, "_barras_ocultas", False):
            self.after(150, self._comprobar_foco)

    def _comprobar_foco(self):
        try:
            fuera = self.focus_get() is None
        except (KeyError, tk.TclError):
            fuera = True
        if fuera:
            self._mostrar_barras()

    def _barras_tareas(self, monitor=None):
        """Ventanas de la barra de tareas (principal y de otros monitores), opcionalmente de un monitor."""
        from ctypes import wintypes
        u = ctypes.windll.user32
        u.FindWindowExW.restype = wintypes.HWND
        u.MonitorFromWindow.restype = wintypes.HMONITOR
        barras = []
        for clase in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            h = u.FindWindowExW(None, None, clase, None)
            while h:
                if monitor is None or u.MonitorFromWindow(h, 2) == monitor:
                    barras.append(h)
                h = u.FindWindowExW(None, h, clase, None)
        return barras

    def _mostrar_barras(self):
        """Vuelve a mostrar las barras de tareas que escondimos nosotros."""
        if sys.platform != "win32":
            return
        try:
            for h in self._barras_tareas():
                if not ctypes.windll.user32.IsWindowVisible(h):
                    ctypes.windll.user32.ShowWindow(h, 8)        # SW_SHOWNA: sin quitarle el foco a nadie
        except Exception:
            pass
        self._barras_ocultas = False

    def alternar_ocultar_barra(self):
        self.cfg["ocultar_barra"] = bool(self.ocultar_barra.get())
        guardar_config(self.cfg)
        if not self.ocultar_barra.get():
            self._mostrar_barras()

    def _menu_fijar(self, e):
        m = tk.Menu(self, tearoff=False)
        m.add_checkbutton(label="Fijar encima de todo (F9)", variable=self.encima, command=self.aplicar_encima)
        m.add_checkbutton(label="Ocultar la barra de tareas sobre un vídeo a pantalla completa",
                          variable=self.ocultar_barra, command=self.alternar_ocultar_barra)
        m.tk_popup(e.x_root, e.y_root)

    def _esconder_barra_tareas(self):
        try:
            from ctypes import wintypes
            u = ctypes.windll.user32
            u.GetParent.restype = u.GetWindow.restype = u.FindWindowW.restype = wintypes.HWND
            u.MonitorFromWindow.restype = wintypes.HMONITOR

            class INFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                            ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

            yo = u.GetParent(self.winfo_id()) or self.winfo_id()
            monitor = u.MonitorFromWindow(yo, 2)
            info = INFO()
            info.cbSize = ctypes.sizeof(INFO)
            u.GetMonitorInfoW(monitor, ctypes.byref(info))
            m = info.rcMonitor
            barras = self._barras_tareas()
            h = u.GetWindow(yo, 2)                      # GW_HWNDNEXT: ventanas debajo de la nuestra
            r = wintypes.RECT()
            oculta = wintypes.DWORD()
            while h:
                oculta.value = 0
                ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 14, ctypes.byref(oculta), 4)  # DWMWA_CLOAKED
                fija = u.GetWindowLongW(h, -20) & 0x8                                      # WS_EX_TOPMOST
                if h not in barras and u.IsWindowVisible(h) and not u.IsIconic(h) and not oculta.value                         and not fija:
                    u.GetWindowRect(h, ctypes.byref(r))
                    if (r.left, r.top, r.right, r.bottom) == (m.left, m.top, m.right, m.bottom):
                        if self.ocultar_barra.get():
                            for b in self._barras_tareas(monitor):
                                u.ShowWindow(b, 0)              # SW_HIDE: vuelve al soltar o cerrar
                            self._barras_ocultas = True
                        else:   # detrás de la ventana a pantalla completa, sin activarla
                            for b in self._barras_tareas(monitor):
                                u.SetWindowPos(b, h, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
                        return
                    if r.right - r.left > 0 and r.bottom - r.top > 0:
                        return      # la primera ventana normal debajo no es pantalla completa
                h = u.GetWindow(h, 2)
        except Exception:
            pass

    def aplicar_opacidad(self, *_):
        self.attributes("-alpha", max(0.3, min(1.0, float(self.opacidad.get()))))

    @staticmethod
    def _geo_compacta_valida(geo):
        """Un tamaño compacto que ocupa media pantalla no es compacto: se descarta."""
        try:
            ancho, alto = (int(n) for n in geo.split("+")[0].split("x"))
        except (ValueError, AttributeError):
            return False
        return 200 <= ancho <= 900 and 200 <= alto <= 1000

    def alternar_compacto(self):
        if not self.compacto:
            if self.state() == "zoomed":
                self.state("normal")          # una ventana maximizada no se deja encoger
            else:
                self.geo_normal = self.geometry()
            self.barra.pack_forget()
            self.fila_meta.pack_forget()
            self.panel.forget(self.izq)
            self.mini.pack(fill="x", before=self.panel)
            if not self._geo_compacta_valida(self.geo_compacta):
                self.geo_compacta = f"440x520+{self.winfo_screenwidth() - 480}+80"
            self.geometry(self.geo_compacta)
            if not self.encima.get():
                self.alternar_encima()
        else:
            if self.state() == "zoomed":
                self.state("normal")
            elif self._geo_compacta_valida(self.geometry()):
                self.geo_compacta = self.geometry()
            self.mini.pack_forget()
            self.barra.pack(fill="x", before=self.panel)
            self.panel.insert(0, self.izq, weight=1)
            self.fila_meta.pack(fill="x", before=self.marco)
            self.geometry(self.geo_normal)
            self.state("zoomed")              # al salir del modo compacto, pantalla completa
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
        self.btn_fijar.bind("<Button-3>", self._menu_fijar)
        ttk.Button(barra, text="🗗 Compacto", command=self.alternar_compacto).pack(side="right", padx=4)
        ttk.Button(barra, text="📤 Exportar", command=self.menu_exportar).pack(side="right")
        ttk.Button(barra, text="📥 Importar", command=self.importar).pack(side="right", padx=(0, 4))
        ttk.Button(clase, text="✨ Resumir con IA", command=self.resumir_ia).pack(side="right")
        self.btn_auto = ttk.Button(clase, text="🤖 Apuntes automáticos", command=self.alternar_auto)
        self.btn_auto.pack(side="right", padx=4)

        mini = self.mini = ttk.Frame(self, padding=2)
        self.btn_fijar2 = ttk.Button(mini, text="📌", width=9, command=self.alternar_encima)
        self.btn_fijar2.pack(side="left")
        self.btn_fijar2.bind("<Button-3>", self._menu_fijar)
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
        bloque = ttk.Menubutton(clase, text="➕ Bloque")
        menu = tk.Menu(bloque, tearoff=False)
        for comando, texto in editor.BLOQUES.items():
            menu.add_command(label=f"{texto[2:].strip()}   ({comando})",
                             command=lambda tx=texto: self.insertar_bloque(tx))
        bloque.configure(menu=menu)
        bloque.pack(side="left", padx=4)
        self.menu_bloque = menu
        ttk.Button(clase, text="✓ Ortografía", command=self.dialogo_ortografia).pack(side="left")
        self.btn_tema = ttk.Button(barra, text="☾ Oscuro", command=self.alternar_tema)
        self.btn_tema.pack(side="right", padx=(0, 4))

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
        self.texto = tk.Text(marco, wrap="word", undo=True, font=(LETRA, self.tam_letra), padx=28, pady=18,
                             spacing1=3, spacing2=2, spacing3=3, relief="flat", borderwidth=0,
                             highlightthickness=1)
        scroll = ttk.Scrollbar(marco, command=self.texto.yview)
        self.texto.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.texto.pack(fill="both", expand=True)
        t = self.texto
        t.bind("<<Modified>>", self._modificado)
        t.bind("<Button-3>", self._menu_texto)
        t.bind("<<Paste>>", self.pegar)  # Ctrl+V / Mayús+Insert: imágenes y archivos
        t.bind("<Control-i>", lambda e: self.importar() or "break")   # si no, Tk mete un tabulador
        t.bind("<BackSpace>", self._tecla_retroceso)
        t.bind("<Delete>", lambda e: self._borrar_imagen(adelante=True))
        # Escribir como en Word: borrar palabras, listas que siguen solas, flechas automáticas
        t.bind("<Control-BackSpace>", lambda e: self._borrar_palabra(adelante=False))
        t.bind("<Control-Delete>", lambda e: self._borrar_palabra(adelante=True))
        t.bind("<Return>", self._tecla_enter)
        t.bind("<KP_Enter>", self._tecla_enter)
        t.bind("<Tab>", lambda e: self._tecla_tab(atras=False))
        t.bind("<Shift-Tab>", lambda e: self._tecla_tab(atras=True))
        try:
            t.bind("<ISO_Left_Tab>", lambda e: self._tecla_tab(atras=True))   # Mayús+Tab en Linux
        except tk.TclError:
            pass
        t.bind("<space>", self._tecla_espacio)
        t.bind("<Control-b>", lambda e: self._envolver("**"))
        t.bind("<Control-k>", lambda e: self._envolver("*"))
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
        self.bind_all("<F7>", lambda e: self.dialogo_ortografia())
        self.bind_all("<Control-i>", lambda e: self.importar() or "break")
        self.aplicar_tema()
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
        self.texto.configure(font=(LETRA, self.tam_letra))
        self._configurar_resaltado()
        self.resaltar()
        self.estado.configure(text=f"Tamaño de letra: {self.tam_letra}  (Ctrl + / Ctrl - / Ctrl 0)")

    # ---------- aspecto: colores, modo oscuro ----------
    def aplicar_tema(self):
        c = self.colores = TEMAS["oscuro" if self.oscuro else "claro"]
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=c["fondo"], foreground=c["texto"], fieldbackground=c["hoja"],
                    bordercolor=c["borde"], lightcolor=c["fondo"], darkcolor=c["fondo"],
                    troughcolor=c["fondo"], selectbackground=c["sel"], selectforeground=c["texto"],
                    insertcolor=c["texto"], arrowcolor=c["suave"], font=(LETRA, 10))
        s.configure("TButton", background=c["boton"], padding=(10, 4), borderwidth=1, focusthickness=0)
        s.map("TButton", background=[("pressed", c["acento_suave"]), ("active", c["boton_hover"])],
              bordercolor=[("active", c["acento"])])
        s.configure("TMenubutton", background=c["boton"], padding=(10, 4), borderwidth=1)
        s.map("TMenubutton", background=[("active", c["boton_hover"])])
        s.configure("TEntry", padding=5)
        s.configure("TCombobox", padding=4)
        s.map("TCombobox", fieldbackground=[("readonly", c["hoja"])], foreground=[("readonly", c["texto"])],
              selectbackground=[("readonly", c["hoja"])], selectforeground=[("readonly", c["texto"])])
        s.configure("Treeview", background=c["hoja"], fieldbackground=c["hoja"], foreground=c["texto"],
                    rowheight=int(tkfont.Font(family=LETRA, size=10).metrics("linespace") * 1.7), borderwidth=0)
        s.map("Treeview", background=[("selected", c["acento_suave"])], foreground=[("selected", c["texto"])])
        s.configure("TScrollbar", background=c["fondo"], gripcount=0, borderwidth=0)
        s.map("TScrollbar", background=[("active", c["borde"])])
        s.configure("TCheckbutton", background=c["fondo"])
        s.configure("TRadiobutton", background=c["fondo"])
        self.configure(background=c["fondo"])
        for clave, valor in (("*Toplevel.background", c["fondo"]), ("*Menu.background", c["hoja"]),
                             ("*Menu.foreground", c["texto"]), ("*Menu.activeBackground", c["acento_suave"]),
                             ("*Menu.activeForeground", c["texto"]), ("*TCombobox*Listbox.background", c["hoja"]),
                             ("*TCombobox*Listbox.foreground", c["texto"])):
            self.option_add(clave, valor)
        self.menu_bloque.configure(background=c["hoja"], foreground=c["texto"],
                                   activebackground=c["acento_suave"], activeforeground=c["texto"])
        self.texto.configure(background=c["hoja"], foreground=c["texto"], insertbackground=c["acento"],
                             selectbackground=c["sel"], selectforeground=c["texto"], inactiveselectbackground=c["sel"],
                             highlightbackground=c["borde"], highlightcolor=c["borde"])
        self.btn_tema.configure(text="☀ Claro" if self.oscuro else "☾ Oscuro")
        self._configurar_resaltado()

    def alternar_tema(self):
        self.oscuro = not self.oscuro
        self.cfg["oscuro"] = self.oscuro
        guardar_config(self.cfg)
        self.aplicar_tema()
        self.resaltar()

    def _configurar_resaltado(self):
        t, n, c = self.texto, self.tam_letra, self.colores
        self._fuente = tkfont.Font(family=LETRA, size=n)
        # Como en Canva: título grande y centrado con una raya debajo, secciones marcadas
        t.tag_configure("h1", font=(LETRA, n + 12, "bold"), foreground=c["titulo"], justify="center",
                        spacing1=18, spacing3=10)
        t.tag_configure("h2", font=(LETRA, n + 5, "bold"), foreground=c["titulo"], spacing1=18, spacing3=6)
        # Raya: una línea vacía (o «---») cuyo salto de línea pinta el fondo hasta el borde derecho
        t.tag_configure("regla", font=(LETRA, 1), background=c["borde"], foreground=c["borde"], spacing1=0, spacing3=0,
                        lmargin1=0, rmargin=0)
        t.tag_configure("h3", font=(LETRA, n + 2, "bold"), foreground=c["acento"], spacing1=8, spacing3=2)
        t.tag_configure("simbolo", foreground=c["suave"])      # los «#» de los títulos, más discretos
        t.tag_configure("negrita", font=(LETRA, n, "bold"))
        t.tag_configure("cursiva", font=(LETRA, n, "italic"))
        t.tag_configure("codigo", font=(MONO, n - 1), background=c["acento_suave"], foreground=c["titulo"])
        t.tag_configure("bloque_codigo", font=(MONO, n - 1), background=c["codigo"], lmargin1=12, lmargin2=12)
        t.tag_configure("tiempo", foreground=c["acento"])
        t.tag_configure("hecha", foreground=c["suave"], overstrike=True)
        t.tag_configure("vineta", foreground=c["acento"], font=(LETRA, n, "bold"))
        for nombre, fondo in c["bloques"].items():
            t.tag_configure("cita" if nombre == "cita" else "bloque_" + nombre, background=fondo,
                            lmargin1=12, lmargin2=12, rmargin=12, spacing1=6, spacing3=6,
                            foreground=c["suave"] if nombre == "cita" else c["texto"])
        t.tag_configure("falta", underline=True)
        try:
            t.tag_configure("falta", underlinefg="#e5484d")     # subrayado rojo (Tk 8.6.6 o más nuevo)
        except tk.TclError:
            t.tag_configure("falta", foreground="#e5484d")
        t.tag_configure("oculto", elide=True)   # enlaces de imágenes: se ve la imagen, no el texto
        t.tag_raise("simbolo")
        t.tag_raise("vineta")
        t.tag_raise("sel")

    PATRONES = [
        ("negrita", re.compile(r"\*\*[^*\n]+\*\*")),
        ("cursiva", re.compile(r"(?<![*\w])\*[^*\s][^*\n]*\*(?!\*)")),
        ("codigo", re.compile(r"`[^`\n]+`")),
        ("tiempo", re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?\]")),
    ]

    def resaltar(self):
        """Colorea el Markdown del editor: títulos, negritas, citas, listas, marcas de tiempo."""
        t = self.texto
        quitar = ["h1", "h2", "h3", "simbolo", "negrita", "cursiva", "codigo", "cita", "tiempo", "hecha", "vineta",
                  "regla", "bloque_codigo"]
        quitar += ["bloque_" + b for b in self.colores["bloques"]]
        quitar += [tag for tag in t.tag_names() if tag.startswith("colgante_")]
        for tag in quitar:
            t.tag_remove(tag, "1.0", "end")
        lineas = t.get("1.0", "end-1c").split("\n")
        self.mostrar_imagenes(lineas)
        en_codigo = False
        for n, linea in enumerate(lineas, start=1):
            if linea.strip().startswith("```"):
                en_codigo = not en_codigo
                t.tag_add("bloque_codigo", f"{n}.0", f"{n}.end+1c")
                continue
            if en_codigo:
                t.tag_add("bloque_codigo", f"{n}.0", f"{n}.end+1c")
                continue
            if not linea.strip() and n > 1 and re.match(r"#\s", lineas[n - 2]):
                t.tag_add("regla", f"{n}.end", f"{n}.end+1c")       # raya bajo el título
                continue
            if re.fullmatch(r"\s*(-{3,}|\*{3,}|_{3,})\s*", linea):
                t.tag_add("regla", f"{n}.0", f"{n}.end+1c")      # «---» casi invisible: queda la raya
                continue
            if not linea:
                continue
            m = re.match(r"(#{1,3})\s", linea)
            if m:
                t.tag_add("h" + str(len(m.group(1))), f"{n}.0", f"{n}.end")
                t.tag_add("simbolo", f"{n}.0", f"{n}.{m.end()}")
                continue
            bloque = editor.tipo_bloque(linea)
            if bloque:
                t.tag_add("cita" if bloque == "cita" else "bloque_" + bloque, f"{n}.0", f"{n}.end+1c")
                t.tag_add("simbolo", f"{n}.0", f"{n}.1")
            elif re.match(r"\s*[-*+]\s+\[[xX]\]", linea):
                t.tag_add("hecha", f"{n}.0", f"{n}.end")
            item = editor.analizar(linea)
            if item:
                self._sangria_colgante(n, linea, item)
            for tag, patron in self.PATRONES:
                for m in patron.finditer(linea):
                    t.tag_add(tag, f"{n}.{m.start()}", f"{n}.{m.end()}")
                    if tag == "codigo":     # las comillas `…` más discretas, que destaque el comando
                        t.tag_add("simbolo", f"{n}.{m.start()}", f"{n}.{m.start() + 1}")
                        t.tag_add("simbolo", f"{n}.{m.end() - 1}", f"{n}.{m.end()}")
        self._despues("ortografia", 700, self.subrayar_faltas)

    # ---------- ortografía: español e inglés ----------
    def _corrector(self):
        if getattr(self, "_corr", None) is None:
            self._corr = ortografia.Corrector()
            for p in self.cfg.get("palabras_propias", []):
                self._corr.ignorar(p)
        return self._corr

    def subrayar_faltas(self):
        """Subraya en rojo las palabras mal escritas (si el corrector está encendido)."""
        t = self.texto
        t.tag_remove("falta", "1.0", "end")
        if not self.cfg.get("ortografia", True) or not self.actual:
            return
        texto = t.get("1.0", "end-1c")
        if len(texto) > 200_000:
            return
        for ini, fin, _p in self._faltas(texto):
            t.tag_add("falta", ini, fin)

    def _faltas(self, texto=None):
        """Faltas del texto actual como (inicio, fin, palabra) en índices del editor."""
        if texto is None:
            texto = self.texto.get("1.0", "end-1c")
        return [(f"{fila + 1}.{ini}", f"{fila + 1}.{fin}", p) for fila, ini, fin, p in
                ortografia.faltas_en_texto(texto, self._corrector())]

    def _cambiar_palabra(self, ini, fin, nueva):
        t = self.texto
        t.configure(autoseparators=False)        # un solo Ctrl+Z deshace el cambio
        try:
            t.edit_separator()
            t.delete(ini, fin)
            t.insert(ini, nueva)
            t.edit_separator()
        finally:
            t.configure(autoseparators=True)
        self.resaltar()

    def _menu_texto(self, e):
        t = self.texto
        if not self._editable():
            return None
        m = tk.Menu(self, tearoff=False)
        pos = t.index(f"@{e.x},{e.y}")
        rango = t.tag_prevrange("falta", pos + "+1c")
        if rango and t.compare(rango[0], "<=", pos) and t.compare(pos, "<", rango[1]):
            ini, fin = rango
            palabra = t.get(ini, fin)
            sugerencias = self._corrector().sugerencias(palabra)
            for sug in sugerencias:
                m.add_command(label=sug, font=(LETRA, 10, "bold"),
                              command=lambda sug=sug: self._cambiar_palabra(ini, fin, sug))
            if not sugerencias:
                m.add_command(label="(sin sugerencias)", state="disabled")
            m.add_separator()
            m.add_command(label=f"Añadir «{palabra}» a mi diccionario", command=lambda: self.palabra_propia(palabra))
            m.add_separator()
        m.add_command(label="Cortar", command=lambda: t.event_generate("<<Cut>>"))
        m.add_command(label="Copiar", command=lambda: t.event_generate("<<Copy>>"))
        m.add_command(label="Pegar", command=lambda: t.event_generate("<<Paste>>"))
        m.add_separator()
        m.add_command(label="Revisar ortografía…  (F7)", command=self.dialogo_ortografia)
        m.add_checkbutton(label="Subrayar faltas mientras escribo", variable=self._var_ortografia(),
                          command=self._alternar_ortografia)
        m.tk_popup(e.x_root, e.y_root)
        return "break"

    def _var_ortografia(self):
        if not hasattr(self, "_v_ort"):
            self._v_ort = tk.BooleanVar(value=self.cfg.get("ortografia", True))
        return self._v_ort

    def _alternar_ortografia(self):
        self.cfg["ortografia"] = bool(self._var_ortografia().get())
        guardar_config(self.cfg)
        self.subrayar_faltas()

    def palabra_propia(self, palabra):
        """La palabra deja de marcarse (se guarda en la configuración: nombres, términos técnicos…)."""
        propias = self.cfg.setdefault("palabras_propias", [])
        if palabra.lower() not in propias:
            propias.append(palabra.lower())
            guardar_config(self.cfg)
        self._corrector().ignorar(palabra)
        self.subrayar_faltas()

    def dialogo_ortografia(self):
        """«¿Quieres corregir estas palabras?»: lista de faltas con su sugerencia, y se corrigen de una vez."""
        if not self._editable():
            return
        corr = self._corrector()
        if not corr:
            messagebox.showinfo("Ortografía", "Falta el diccionario de español en este equipo.\n\n"
                                "En Windows: Configuración → Hora e idioma → Idioma → añade Español.\n"
                                "O instala el de respaldo: py -3 -m pip install pyspellchecker", parent=self)
            return
        faltas = self._faltas()
        if not faltas:
            messagebox.showinfo("Ortografía", "✓ No he encontrado faltas.", parent=self)
            return
        palabras = list(dict.fromkeys(p for _i, _f, p in faltas))
        c = self.colores
        v = self.ventana_ortografia = tk.Toplevel(self)
        v.title("Ortografía")
        v.transient(self)
        v.configure(background=c["fondo"])
        marco = ttk.Frame(v, padding=14)
        marco.pack(fill="both", expand=True)
        ttk.Label(marco, text="¿Quieres corregir estas palabras?", font=(LETRA, 13, "bold")).pack(anchor="w")
        ttk.Label(marco, text="Marca las que quieras cambiar y elige cómo se escriben.   Idiomas: "
                  + ", ".join(corr.idiomas), foreground=c["suave"]).pack(anchor="w", pady=(2, 10))
        lienzo = tk.Canvas(marco, highlightthickness=0, background=c["fondo"])
        filas = ttk.Frame(lienzo)
        lienzo.create_window(0, 0, window=filas, anchor="nw")
        elegidas = []
        for i, p in enumerate(palabras):
            sugerencias = corr.sugerencias(p)
            # Marcada solo si la sugerencia se parece de verdad (si no, suele ser jerga: «wordlist», «rockyou»)
            marcada = tk.BooleanVar(value=bool(sugerencias) and ortografia.parecida(p, sugerencias[0]))
            cambio = tk.StringVar(value=sugerencias[0] if sugerencias else p)
            veces = sum(1 for *_x, q in faltas if q == p)
            ttk.Checkbutton(filas, variable=marcada, text=p + (f"  ×{veces}" if veces > 1 else "")).grid(
                row=i, column=0, sticky="w", padx=(0, 10), pady=3)
            ttk.Label(filas, text="→").grid(row=i, column=1)
            ttk.Combobox(filas, textvariable=cambio, values=sugerencias, width=22).grid(row=i, column=2, padx=6, pady=3)
            ttk.Button(filas, text="Es correcta",
                       command=lambda p=p, m=marcada: (self.palabra_propia(p), m.set(False))).grid(row=i, column=3)
            elegidas.append((p, marcada, cambio))
        filas.update_idletasks()
        alto = filas.winfo_reqheight()
        lienzo.configure(width=filas.winfo_reqwidth(), height=min(alto, 400), scrollregion=(0, 0, 0, alto))
        if alto > 400:
            barra = ttk.Scrollbar(marco, command=lienzo.yview)
            lienzo.configure(yscrollcommand=barra.set)
            barra.pack(side="right", fill="y")
            v.bind("<MouseWheel>", lambda e: lienzo.yview_scroll(-e.delta // 120, "units"))
        lienzo.pack(side="top", fill="both", expand=True)

        def corregir():
            cambios = {p: c_.get().strip() for p, m, c_ in elegidas
                       if m.get() and c_.get().strip() and c_.get().strip() != p}
            t = self.texto
            t.configure(autoseparators=False)    # todas las correcciones se deshacen con un solo Ctrl+Z
            try:
                t.edit_separator()
                for ini, fin, p in reversed(self._faltas()):     # de atrás adelante: no se mueven las posiciones
                    if p in cambios:
                        t.delete(ini, fin)
                        t.insert(ini, cambios[p])
                t.edit_separator()
            finally:
                t.configure(autoseparators=True)
            v.destroy()
            self.resaltar()
            self.estado.configure(text=f"✓ {len(cambios)} palabra(s) corregida(s). Ctrl+Z para deshacer.")

        v.corregir = corregir
        botones = ttk.Frame(marco)
        botones.pack(fill="x", pady=(12, 0))
        ttk.Button(botones, text="Corregir las marcadas", command=corregir).pack(side="right")
        ttk.Button(botones, text="Ahora no", command=v.destroy).pack(side="right", padx=6)
        v.bind("<Escape>", lambda e: v.destroy())
        v.bind("<Return>", lambda e: corregir())
        v.grab_set()
        v.focus_set()

    def _sangria_colgante(self, n, linea, item):
        """Lista con sangría francesa: si el texto salta de línea, sigue alineado tras el número."""
        t = self.texto
        t.tag_add("vineta", f"{n}.{len(item.sangria)}", f"{n}.{item.ancho}")
        izquierda = 18 + 14 * item.nivel
        colgante = izquierda + self._fuente.measure(linea[:item.ancho])
        nombre = f"colgante_{izquierda}_{colgante}"
        t.tag_configure(nombre, lmargin1=izquierda, lmargin2=colgante)
        t.tag_lower(nombre)
        t.tag_add(nombre, f"{n}.0", f"{n}.end+1c")

    # ---------- teclas del editor: listas, flechas, palabras ----------
    def _posicion(self):
        fila, col = map(int, self.texto.index("insert").split("."))
        return fila, col

    def _lineas(self):
        return self.texto.get("1.0", "end-1c").split("\n")

    def _aplicar(self, resultado):
        """Pone en el editor las líneas que han cambiado (un solo paso de Ctrl+Z) y coloca el cursor."""
        if not resultado:
            return None
        nuevas, fila, col = resultado
        t, viejas = self.texto, self._lineas()
        a = 0
        while a < len(viejas) and a < len(nuevas) and viejas[a] == nuevas[a]:
            a += 1
        bv, bn = len(viejas) - 1, len(nuevas) - 1
        while bv >= a and bn >= a and viejas[bv] == nuevas[bn]:
            bv, bn = bv - 1, bn - 1
        t.configure(autoseparators=False)
        t.edit_separator()
        try:
            if bv < a:                                   # solo se añaden líneas
                if bn >= a:
                    if a < len(viejas):
                        t.insert(f"{a + 1}.0", "\n".join(nuevas[a:bn + 1]) + "\n")
                    else:
                        t.insert("end-1c", "\n" + "\n".join(nuevas[a:bn + 1]))
            elif bn < a:                                 # solo se quitan líneas
                if bv + 1 < len(viejas):
                    t.delete(f"{a + 1}.0", f"{bv + 2}.0")
                else:
                    t.delete(f"{a}.end" if a else "1.0", f"{bv + 1}.end")
            else:
                t.delete(f"{a + 1}.0", f"{bv + 1}.end")
                t.insert(f"{a + 1}.0", "\n".join(nuevas[a:bn + 1]))
        finally:
            t.edit_separator()
            t.configure(autoseparators=True)
        t.mark_set("insert", f"{fila + 1}.{col}")
        t.see("insert")
        self._despues("resaltar", 30, self.resaltar)
        return "break"

    def _editable(self):
        return self.actual is not None and str(self.texto.cget("state")) == "normal"

    def _tecla_enter(self, _e=None):
        if not self._editable() or self.texto.tag_ranges("sel"):
            return None
        fila, col = self._posicion()
        return self._aplicar(editor.enter(self._lineas(), fila - 1, col))

    def _tecla_tab(self, atras):
        if not self._editable():
            return "break"
        fila, col = self._posicion()
        r = self._aplicar(editor.tab(self._lineas(), fila - 1, col, atras=atras))
        if r or atras:
            return "break"   # Mayús+Tab fuera de una lista no salta a otro control
        return None

    def _tecla_retroceso(self, _e=None):
        r = self._borrar_imagen(adelante=False)
        if r or not self._editable() or self.texto.tag_ranges("sel"):
            return r
        fila, col = self._posicion()
        lineas = self._lineas()
        # Si este elemento acaba de subir de nivel con Retroceso (a. → 2.), el siguiente quita la viñeta
        # en vez de volver a bajarlo: así no se queda dando vueltas.
        sangrar = getattr(self, "_subido", None) != (fila, lineas[fila - 1])
        res = editor.retroceso(lineas, fila - 1, col, sangrar=sangrar)
        subio = res and len(res[0][fila - 1]) - len(res[0][fila - 1].lstrip()) < \
            len(lineas[fila - 1]) - len(lineas[fila - 1].lstrip())
        self._subido = (fila, res[0][fila - 1]) if subio else None
        return self._aplicar(res)

    def _tecla_espacio(self, _e=None):
        """Flechas y símbolos al escribir (-> da →) y comandos de bloque (/idea)."""
        t = self.texto
        if not self._editable() or t.tag_ranges("sel") or not self.cfg.get("simbolos", True):
            return None
        fila, _ = self._posicion()
        if editor.en_codigo(self._lineas(), fila - 1):
            return None
        cambio = editor.sustitucion(t.get(f"{fila}.0", "insert"))
        if not cambio:
            return None
        quitar, poner = cambio
        t.configure(autoseparators=False)
        t.edit_separator()
        t.delete(f"insert-{quitar}c", "insert")
        t.insert("insert", poner if poner.endswith(" ") else poner + " ")
        t.edit_separator()            # Ctrl+Z justo después devuelve lo que se escribió (->)
        t.configure(autoseparators=True)
        t.see("insert")
        return "break"

    def _borrar_palabra(self, adelante):
        """Ctrl+Retroceso / Ctrl+Supr: borra la palabra entera, como en cualquier programa."""
        t = self.texto
        if not self._editable():
            return "break"
        if t.tag_ranges("sel"):
            t.delete("sel.first", "sel.last")
            return "break"
        if self._borrar_imagen(adelante=adelante):
            return "break"
        fila, col = self._posicion()
        linea = t.get(f"{fila}.0", f"{fila}.end")
        if t.dump(f"{fila}.0", f"{fila}.end", image=True):     # línea con imagen: lo que haga Tk
            desde, hasta = ("insert", "insert wordend") if adelante else ("insert-1c wordstart", "insert")
        elif adelante:
            fin = editor.palabra_derecha(linea, col)
            desde, hasta = "insert", ("insert+1c" if fin is None else f"{fila}.{fin}")
        else:
            ini = editor.palabra_izquierda(linea, col)
            desde, hasta = ("insert-1c" if ini is None else f"{fila}.{ini}"), "insert"
        t.edit_separator()
        t.delete(desde, hasta)
        t.edit_separator()
        return "break"

    def _envolver(self, marca):
        """Ctrl+B negrita / Ctrl+K cursiva: rodea la selección (o deja el cursor en medio)."""
        t = self.texto
        if not self._editable():
            return "break"
        if t.tag_ranges("sel"):
            ini, fin = t.index("sel.first"), t.index("sel.last")
            t.insert(fin, marca)
            t.insert(ini, marca)
        else:
            t.insert("insert", marca * 2)
            t.mark_set("insert", f"insert-{len(marca)}c")
        return "break"

    def insertar_bloque(self, texto):
        """Inserta un bloque destacado (💡 idea, ⚠ ojo…) en la línea del cursor o debajo."""
        if not self._editable():
            messagebox.showinfo("Bloque", "Abre o crea una nota primero.")
            return
        t = self.texto
        if t.get("insert linestart", "insert lineend").strip():
            t.mark_set("insert", "insert lineend")
            t.insert("insert", "\n")
        t.insert("insert", texto)
        t.focus_set()
        self.resaltar()

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
        origen = Path(archivo)
        destino = self._ruta_adjunto(origen.name)
        shutil.copy2(origen, destino)
        self._insertar_adjunto(destino)
        abrir_en_sistema(destino)  # se abre al lado para pasarlo a limpio

    def _ruta_adjunto(self, nombre):
        """Ruta libre en _adjuntos para un archivo nuevo."""
        ADJUNTOS.mkdir(parents=True, exist_ok=True)
        base = Path(nombre)
        destino, n = ADJUNTOS / base.name, 2
        while destino.exists():
            destino = ADJUNTOS / f"{base.stem} ({n}){base.suffix}"
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
        origen = PAQUETE / "captura.ps1"
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

    def _titulo_exportacion(self, que):
        if que == "nota":
            return self.titulo.get().strip() or "Apunte"
        if que == "carpeta" and self._carpeta_elegida():
            return self._carpeta_elegida().relative_to(NOTAS).as_posix()
        return "Apuntes"

    def menu_exportar(self):
        """Ventana «Exportar»: qué exportar, en qué formato (Guardar como) y en qué carpeta (Guardar en)."""
        self.guardar(silencioso=True)
        opciones = []
        if self.actual:
            opciones.append(("nota", f"Este apunte: «{self.titulo.get().strip()}»"))
        carpeta = self._carpeta_elegida()
        if carpeta:
            opciones.append(("carpeta", f"Toda la carpeta «{carpeta.relative_to(NOTAS).as_posix()}»"))
        opciones.append(("todo", "Todos los apuntes"))

        v = self._ventana_exportar = tk.Toplevel(self)
        v.title("Exportar apuntes")
        v.transient(self)
        v.resizable(False, False)
        if self.encima.get():
            v.attributes("-topmost", True)
        m = ttk.Frame(v, padding=14)
        m.pack(fill="both", expand=True)
        negrita = ("Segoe UI", 10, "bold")

        que = tk.StringVar(value=opciones[0][0])
        guardado = self.cfg.get("exportar_formato", "pdf")
        formato = tk.StringVar(value=guardado if guardado in exportar.FORMATOS else "pdf")
        nombre = tk.StringVar(value=slug(self._titulo_exportacion(que.get()).replace("/", " - ")))
        carpeta_dest = tk.StringVar(value=self.cfg.get("exportar_carpeta") or str(BASE / "exportados"))
        abrir = tk.BooleanVar(value=self.cfg.get("exportar_abrir", True))
        ext = tk.StringVar()

        def al_cambiar_que():
            nombre.set(slug(self._titulo_exportacion(que.get()).replace("/", " - ")))

        def al_cambiar_formato():
            ext.set(exportar.FORMATOS[formato.get()][1])

        al_cambiar_formato()
        fila = 0
        ttk.Label(m, text="Qué exportar", font=negrita).grid(row=fila, column=0, columnspan=3, sticky="w")
        for clave, texto in opciones:
            fila += 1
            ttk.Radiobutton(m, text=texto, variable=que, value=clave, command=al_cambiar_que).grid(
                row=fila, column=0, columnspan=3, sticky="w", padx=(12, 0))
        fila += 1
        ttk.Label(m, text="Guardar como", font=negrita).grid(row=fila, column=0, columnspan=3, sticky="w", pady=(12, 0))
        for clave, (nom, extension, para_que, _) in exportar.FORMATOS.items():
            fila += 1
            ttk.Radiobutton(m, text=f"{nom} ({extension})", variable=formato, value=clave,
                            command=al_cambiar_formato).grid(row=fila, column=0, sticky="w", padx=(12, 8))
            ttk.Label(m, text=para_que, foreground="#666666").grid(row=fila, column=1, columnspan=2, sticky="w")
        fila += 1
        ttk.Label(m, text="Nombre del archivo", font=negrita).grid(row=fila, column=0, sticky="w", pady=(12, 0))
        fila += 1
        caja = ttk.Frame(m)
        caja.grid(row=fila, column=0, columnspan=3, sticky="we", padx=(12, 0))
        ttk.Entry(caja, textvariable=nombre, width=50).pack(side="left", fill="x", expand=True)
        ttk.Label(caja, textvariable=ext, width=6).pack(side="left", padx=(2, 0))
        fila += 1
        ttk.Label(m, text="Guardar en", font=negrita).grid(row=fila, column=0, sticky="w", pady=(12, 0))
        fila += 1
        caja = ttk.Frame(m)
        caja.grid(row=fila, column=0, columnspan=3, sticky="we", padx=(12, 0))
        ttk.Entry(caja, textvariable=carpeta_dest, width=50).pack(side="left", fill="x", expand=True)

        def examinar():
            elegida = filedialog.askdirectory(parent=v, title="Guardar en...",
                                              initialdir=carpeta_dest.get() if Path(carpeta_dest.get()).is_dir() else BASE)
            if elegida:
                carpeta_dest.set(str(Path(elegida)))

        ttk.Button(caja, text="📁 Examinar...", command=examinar).pack(side="left", padx=(4, 0))
        fila += 1
        accesos = ttk.Frame(m)
        accesos.grid(row=fila, column=0, columnspan=3, sticky="w", padx=(12, 0), pady=(4, 0))
        for texto, ruta in (("Exportados", BASE / "exportados"), ("Escritorio", carpeta_windows(0x10, "Desktop")),
                            ("Documentos", carpeta_documentos()), ("Descargas", Path.home() / "Downloads")):
            ttk.Button(accesos, text=texto, command=lambda r=ruta: carpeta_dest.set(str(r))).pack(side="left", padx=(0, 4))
        fila += 1
        ttk.Checkbutton(m, text="Abrir el archivo al terminar", variable=abrir).grid(
            row=fila, column=0, columnspan=3, sticky="w", pady=(12, 0))

        def aceptar(_e=None):
            nom = slug(nombre.get().strip())
            if not nom:
                messagebox.showinfo("Exportar", "Escribe un nombre para el archivo.", parent=v)
                return
            carpeta_final = Path(carpeta_dest.get().strip() or BASE / "exportados")
            try:
                carpeta_final.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                messagebox.showerror("Exportar", f"No se puede usar esa carpeta:\n{e}", parent=v)
                return
            destino = carpeta_final / (nom + ext.get())
            if destino.exists() and not messagebox.askyesno(
                    "Exportar", f"Ya existe «{destino.name}» en esa carpeta.\n¿Quieres reemplazarlo?", parent=v):
                return
            self.cfg.update({"exportar_formato": formato.get(), "exportar_abrir": abrir.get(),
                             "exportar_carpeta": str(carpeta_final)})
            guardar_config(self.cfg)
            v.destroy()
            self.exportar(que.get(), formato.get(), destino, abrir=abrir.get())

        fila += 1
        botones = ttk.Frame(m)
        botones.grid(row=fila, column=0, columnspan=3, sticky="e", pady=(14, 0))
        ttk.Button(botones, text="Cancelar", command=v.destroy).pack(side="right")
        ttk.Button(botones, text="📤 Exportar", command=aceptar).pack(side="right", padx=(0, 6))
        v.bind("<Return>", aceptar)
        v.bind("<Escape>", lambda e: v.destroy())
        v.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - v.winfo_reqwidth()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - v.winfo_reqheight()) // 3)
        v.geometry(f"+{x}+{y}")
        v.grab_set()
        v.focus_set()
        return v

    def exportar(self, que, formato, destino, abrir=False):
        if que == "nota":
            rutas = [self.actual]
        else:
            raiz = self._carpeta_elegida() if que == "carpeta" else NOTAS
            rutas = [p for p in raiz.rglob("*.md") if ADJUNTOS not in p.parents]
        titulo = self._titulo_exportacion(que)
        notas = sorted((self._datos_nota(r) for r in rutas), key=lambda n: (n["asignatura"], n["fecha"], n["titulo"]))
        if not notas:
            messagebox.showinfo("Exportar", "No hay apuntes que exportar.")
            return None
        if que == "nota" and notas[0]["asignatura"]:
            cab = f"{notas[0]['asignatura']}  ·  {notas[0]['fecha']}"
        else:
            cab = titulo
        self.config(cursor="watch")
        self.update()
        try:
            exportar.exportar_como(formato, notas, destino, cab)
        except Exception as e:
            messagebox.showerror("Exportar", f"No se pudo exportar:\n{e}")
            return None
        finally:
            self.config(cursor="")
        self.estado.configure(text=f"Exportado: {destino}")
        if abrir:
            abrir_en_sistema(destino)
        return destino

    # ---------- importar ----------
    def importar(self):
        """Trae apuntes de Word, LibreOffice, páginas web, Markdown o texto para seguir editándolos aquí."""
        archivos = filedialog.askopenfilenames(parent=self, title="Importar apuntes", filetypes=[
            ("Apuntes (Word, LibreOffice, web, Markdown, texto)", "*.docx *.odt *.html *.htm *.md *.markdown *.txt"),
            ("Word", "*.docx"), ("LibreOffice / OpenDocument", "*.odt"), ("Página web", "*.html *.htm"),
            ("Markdown", "*.md *.markdown"), ("Texto", "*.txt")])
        if archivos:
            self.importar_archivos([Path(a) for a in archivos])

    def importar_archivos(self, rutas):
        self.guardar(silencioso=True)
        carpeta = self._carpeta_elegida() or NOTAS
        hechas, errores = [], []
        for ruta in rutas:
            try:
                datos = importar.importar(ruta)
            except Exception as e:  # noqa: BLE001 - un archivo roto no debe parar los demás
                errores.append(f"{ruta.name}: {e}")
                continue
            titulo = datos["titulo"].strip() or ruta.stem
            destino = self._ruta_libre(carpeta, titulo)
            cuerpo = datos["cuerpo"]
            for n, (nombre, contenido) in enumerate(datos["imagenes"]):
                archivo = self._ruta_adjunto(nombre)
                archivo.write_bytes(contenido)
                rel = os.path.relpath(archivo, destino.parent).replace("\\", "/")
                cuerpo = cuerpo.replace(f"{{{{imagen:{n}}}}}", rel)
            escribir_nota(destino, titulo, ["importado"], datetime.now().strftime("%Y-%m-%d %H:%M"), cuerpo)
            hechas.append(destino)
        if hechas:
            self.actual = None
            self.cargar(hechas[-1])
            self.refrescar()
            self.estado.configure(text=f"Importados {len(hechas)} apunte(s) en «{carpeta.relative_to(BASE)}»")
        if errores:
            messagebox.showwarning("Importar", "No se pudieron importar:\n\n" + "\n".join(errores))
        return hechas

    def cerrar(self):
        self._mostrar_barras()
        self.parar_auto()
        self.guardar(silencioso=True)
        if self.compacto:
            if self.state() == "normal" and self._geo_compacta_valida(self.geometry()):
                self.geo_compacta = self.geometry()
        elif self.state() == "normal":
            self.geo_normal = self.geometry()
        self.cfg.update({"encima": self.encima.get(), "opacidad": round(float(self.opacidad.get()), 2),
                         "compacto": self.compacto, "geo_normal": self.geo_normal,
                         "geo_compacta": self.geo_compacta, "tam_letra": self.tam_letra,
                         "ultima": self.actual.relative_to(NOTAS).as_posix() if self.actual else ""})
        guardar_config(self.cfg)
        self.destroy()


def main():
    """Punto de entrada: `apuntalo` (pip), `python -m apuntalo`, apuntes.pyw y Apuntalo.exe."""
    App().mainloop()


if __name__ == "__main__":
    main()
