"""Apúntalo: programa sencillo para sacar apuntes de clase en Markdown (tkinter)."""
import ctypes
import queue
import re
import shutil
import subprocess
import sys
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from . import __version__, accesos, actualizar, control_apps, datos, editor
from .estilo import LETRA
from .ventana import VentanaMixin
from .escritura import EscrituraMixin
from .adjuntos import AdjuntosMixin
from .automatico import AutomaticoMixin
from .ia import IAMixin
from .exportacion import ExportacionMixin
from .ventana import iniciar_atajo_global


class App(VentanaMixin, EscrituraMixin, AdjuntosMixin, AutomaticoMixin, IAMixin, ExportacionMixin, tk.Tk):
    def __init__(self, aviso_acceso_creado=False):
        if sys.platform == "win32":
            try:  # coordenadas en píxeles reales (para elegir la zona de captura)
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass
        super().__init__()
        self.title(f"Apúntalo {__version__}")
        datos.NOTAS.mkdir(parents=True, exist_ok=True)
        try:
            self.iconbitmap(default=str(datos.PAQUETE / "apuntalo.ico"))
        except tk.TclError:
            pass
        self.actual = None          # Path de la nota abierta
        self.creado = ""
        self.cambiada = False
        self.crono_inicio = None
        self.cfg = datos.cargar_config()
        self.encima = tk.BooleanVar(value=self.cfg.get("encima", False))
        self.opacidad = tk.DoubleVar(value=self.cfg.get("opacidad", 1.0))
        self.compacto = False
        self.geo_normal = self.cfg.get("geo_normal")
        if not self._geo_normal_valida(self.geo_normal):
            self.geo_normal = "1250x720"
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
        self.cola_actualizacion = queue.Queue()
        actualizar.comprobar_en_segundo_plano(self.cola_actualizacion.put)
        self._mirar_actualizacion()
        # Reabrir el último apunte y autoguardar cada 15 s (por si se va la luz o se cierra mal).
        ultima = datos.NOTAS / self.cfg.get("ultima", "-")
        if self.cfg.get("ultima") and ultima.is_file() and ".." not in Path(self.cfg["ultima"]).parts:
            self.cargar(ultima)
            self.refrescar()
        self.after(15000, self._autoguardar)
        if aviso_acceso_creado:
            self.estado.configure(text="📌 Se creó un acceso directo en el Escritorio y en el menú Inicio")

    def _mirar_actualizacion(self, intentos=20):
        """Revisa cada 2 s si el hilo de actualizar.py encontró una versión más nueva (máx. 40 s)."""
        try:
            ultima = self.cola_actualizacion.get_nowait()
        except queue.Empty:
            if intentos > 0:
                self.after(2000, lambda: self._mirar_actualizacion(intentos - 1))
            return
        self.aviso_actualizacion.configure(text=f"🔔 Versión {ultima} disponible")
        self.aviso_actualizacion.pack(side="right", padx=(0, 4))

    def _autoguardar(self):
        if self.cambiada:
            self.guardar(silencioso=True)
        self.after(15000, self._autoguardar)

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
        ttk.Button(barra, text="🗺 Mapa mental", command=self.mapa_mental).pack(side="right", padx=(0, 4))
        ttk.Button(barra, text="▦ Tabla", command=self.insertar_tabla).pack(side="right", padx=(0, 4))
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
        ttk.Combobox(barra, textvariable=self.plantilla, values=list(datos.PLANTILLAS),
                     state="readonly", width=16).pack(side="left", padx=(2, 8))
        ttk.Button(barra, text="📁 Nueva carpeta", command=self.nueva_carpeta).pack(side="left")
        ttk.Button(barra, text="💾 Guardar", command=self.guardar).pack(side="left", padx=4)
        ttk.Button(barra, text="🗑 Borrar", command=self.borrar).pack(side="left")
        ttk.Button(barra, text="📂 Abrir carpeta", command=lambda: datos.abrir_en_sistema(datos.NOTAS)).pack(side="left", padx=4)
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
        t.bind("<Shift-Delete>", self._tecla_mayus_supr)
        t.bind("<Return>", self._tecla_enter)
        t.bind("<KP_Enter>", self._tecla_enter)
        t.bind("<Tab>", lambda e: self._tecla_tab(atras=False))
        t.bind("<Shift-Tab>", lambda e: self._tecla_tab(atras=True))
        try:
            t.bind("<ISO_Left_Tab>", lambda e: self._tecla_tab(atras=True))   # Mayús+Tab en Linux
        except tk.TclError:
            pass
        t.bind("<space>", self._tecla_espacio)
        t.bind("<KeyPress>", self._tecla_general)
        t.bind("<Control-b>", lambda e: self._envolver("**"))
        t.bind("<Control-k>", lambda e: self._envolver("*"))
        t.bind("<Control-Shift-X>", lambda e: self._envolver("~~"))
        fila_estado = ttk.Frame(der)
        fila_estado.pack(side="bottom", fill="x", before=marco)  # siempre visible, también en compacto
        self.estado = ttk.Label(fila_estado, text="", foreground="gray")
        self.estado.pack(side="left", anchor="w")
        # Oculto hasta que actualizar.py avise de una versión nueva (ver _mirar_actualizacion).
        self.aviso_actualizacion = ttk.Label(fila_estado, text="", foreground="#B45309", cursor="hand2")
        self.aviso_actualizacion.bind(
            "<Button-1>", lambda e: webbrowser.open("https://github.com/BV-cs0/apuntalo/releases/latest"))
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

    # ---------- lista ----------
    def notas(self):
        return sorted(p for p in datos.NOTAS.rglob("*.md") if datos.ADJUNTOS not in p.parents)

    def carpetas(self):
        return sorted(str(p.relative_to(datos.NOTAS)) for p in datos.NOTAS.rglob("*")
                      if p.is_dir() and p != datos.ADJUNTOS and datos.ADJUNTOS not in p.parents)

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
                meta, cuerpo = datos.leer_nota(ruta)
            except Exception:
                continue
            todas_etq.update(meta["etiquetas"])
            if etq != "(todas)" and etq not in meta["etiquetas"]:
                continue
            if q and q not in (meta["titulo"] + " " + cuerpo + " " + " ".join(meta["etiquetas"])).lower():
                continue
            rel = ruta.parent.relative_to(datos.NOTAS)
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
        meta, cuerpo = datos.leer_nota(ruta)
        self._cargando = True
        self.actual = ruta
        self.creado = meta.get("creado", "")
        self.titulo.set(meta["titulo"])
        rel = ruta.parent.relative_to(datos.NOTAS)
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
        self.estado.configure(text=f"{ruta.relative_to(datos.BASE)}  ·  creado {self.creado}")

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
            rel = self.actual.parent.relative_to(datos.NOTAS)
            carpeta = "" if str(rel) == "." else str(rel)
        ruta = self._ruta_libre(datos.NOTAS / carpeta, titulo)
        datos.escribir_nota(ruta, titulo, [], datetime.now().strftime("%Y-%m-%d %H:%M"),
                      datos.PLANTILLAS.get(self.plantilla.get(), ""))
        self.actual = None
        self.cargar(ruta)
        self.refrescar()
        self.texto.focus_set()
        self.texto.mark_set("insert", "end")

    def _ruta_libre(self, carpeta, titulo, excepto=None):
        ruta = carpeta / (datos.slug(titulo) + ".md")
        n = 2
        while ruta.exists() and ruta != excepto:
            ruta = carpeta / f"{datos.slug(titulo)} ({n}).md"
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
        destino_dir = datos.NOTAS / carpeta
        nueva_ruta = self.actual
        if destino_dir != self.actual.parent or datos.slug(titulo) != self.actual.stem.split(" (")[0]:
            nueva_ruta = self._ruta_libre(destino_dir, titulo, excepto=self.actual)
        datos.escribir_nota(nueva_ruta, titulo, etiquetas, self.creado, self.texto.get("1.0", "end-1c"))
        if nueva_ruta != self.actual and self.actual.exists():
            self.actual.unlink()
        if self.nota_auto == self.actual:
            self.nota_auto = nueva_ruta
        self.actual = nueva_ruta
        self.cambiada = False
        self.estado.configure(text=f"Guardado {datetime.now():%H:%M:%S}  ·  {nueva_ruta.relative_to(datos.BASE)}")
        self.refrescar()

    def borrar(self):
        if self.actual is None:
            return
        if not messagebox.askyesno("Borrar", f"¿Borrar «{self.titulo.get()}»?\nSe mueve a la carpeta _papelera."):
            return
        papelera = datos.BASE / "_papelera"
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
        partes = [datos.slug(p) for p in re.split(r"[/\\]", nombre) if p.strip() and p.strip() != ".."]
        if partes:
            (datos.NOTAS.joinpath(*partes)).mkdir(parents=True, exist_ok=True)
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

    def cerrar(self):
        self._mostrar_barras()
        self.parar_auto()
        self.guardar(silencioso=True)
        if self.compacto:
            if self.state() == "normal" and self._geo_compacta_valida(self.geometry()):
                self.geo_compacta = self.geometry()
        elif self.state() == "normal" and self._geo_normal_valida(self.geometry()):
            self.geo_normal = self.geometry()
        self.cfg.update({"encima": self.encima.get(), "opacidad": round(float(self.opacidad.get()), 2),
                         "compacto": self.compacto, "geo_normal": self.geo_normal,
                         "geo_compacta": self.geo_compacta, "tam_letra": self.tam_letra,
                         "ultima": self.actual.relative_to(datos.NOTAS).as_posix() if self.actual else ""})
        datos.guardar_config(self.cfg)
        self.destroy()


def _crear_accesos_si_hace_falta() -> bool:
    """La primera vez que se abre Apuntalo.exe, crea su acceso directo en el Escritorio y en el
    menú Inicio (apuntando a donde esté el .exe, sin moverlo). No hace nada en las demás formas
    de instalar la app. Si algún destino falla (por ejemplo, Windows todavía analizando el
    script la primera vez), no lo marca como hecho: lo reintenta en el próximo arranque."""
    if not getattr(sys, "frozen", False):
        return False
    destinos = [datos.carpeta_windows(0x10, "Desktop"), datos.carpeta_windows(0x02, "Start Menu\\Programs")]
    exe = Path(sys.executable).resolve()
    if control_apps.bloquea_accesos(exe):
        # Windows no dejaría abrirlos: quita los que creó una versión anterior y no crea más.
        accesos.quitar_accesos_rotos(destinos, exe)
        return False
    cfg = datos.cargar_config()
    if cfg.get("acceso_directo_creado"):
        return False
    creado = accesos.crear_accesos_directos(destinos, exe)
    if creado:
        cfg["acceso_directo_creado"] = True
        datos.guardar_config(cfg)
    return creado


def _reabrir_como_admin() -> bool:
    """Vuelve a abrir la app pidiendo permisos de administrador (el aviso de Windows).
    True si la copia con permisos se abrió y esta debe cerrarse; si dicen que no, sigue sin ellos."""
    if sys.platform != "win32" or "--elevada" in sys.argv:
        return False
    try:
        shell = ctypes.windll.shell32
        if shell.IsUserAnAdmin():
            return False
        if getattr(sys, "frozen", False):
            # No la carpeta temporal del .exe: si la copia con permisos trabaja ahí, no se puede borrar al salir.
            programa, args, carpeta = sys.executable, sys.argv[1:], Path(sys.executable).parent
        else:
            ventana = Path(sys.executable).with_name("pythonw.exe")
            programa = str(ventana if ventana.is_file() else sys.executable)
            # El proceso con permisos no hereda las variables de entorno: la carpeta de datos va en la orden.
            args, carpeta = ["-m", "apuntalo", f"--datos={datos.BASE}", *sys.argv[1:]], datos.PAQUETE.parent
        shell.ShellExecuteW.restype = ctypes.c_void_p
        r = shell.ShellExecuteW(None, "runas", programa, subprocess.list2cmdline([*args, "--elevada"]),
                                str(carpeta), 1)
        return (r or 0) > 32
    except Exception:
        return False


def main():
    """Punto de entrada: `apuntalo` (pip), `python -m apuntalo`, apuntes.pyw y Apuntalo.exe."""
    if _reabrir_como_admin():
        return
    if sys.platform == "win32":
        try:    # sin esto, abierta con Python, la barra de tareas la agrupa con pythonw y le pone su icono
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("BV-cs0.Apuntalo")
        except Exception:
            pass
    aviso_acceso = _crear_accesos_si_hace_falta()
    App(aviso_acceso_creado=aviso_acceso).mainloop()


if __name__ == "__main__":
    main()
