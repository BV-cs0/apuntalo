"""Exportar, importar y mapa mental desde la ventana."""
import os
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import datos, exportar, importar, mapa
from .estilo import LETRA


class ExportacionMixin:
    """Métodos de App: exportar, importar y mapa mental desde la ventana."""

    # ---------- exportar ----------
    def _datos_nota(self, ruta):
        meta, cuerpo = datos.leer_nota(ruta)
        rel = ruta.parent.relative_to(datos.NOTAS)
        return {"titulo": meta["titulo"], "cuerpo": cuerpo, "fecha": meta.get("creado", ""),
                "asignatura": "" if str(rel) == "." else " / ".join(rel.parts),
                "etiquetas": meta["etiquetas"], "carpeta": str(ruta.parent)}

    def _carpeta_elegida(self):
        sel = self.arbol.selection()
        if sel and sel[0].startswith("dir:"):
            return datos.NOTAS / sel[0][4:]
        if self.actual and self.actual.parent != datos.NOTAS:
            return self.actual.parent
        return None

    def _titulo_exportacion(self, que):
        if que == "nota":
            return self.titulo.get().strip() or "Apunte"
        if que == "carpeta" and self._carpeta_elegida():
            return self._carpeta_elegida().relative_to(datos.NOTAS).as_posix()
        return "Apuntes"

    def mapa_mental(self):
        """Dibuja el esquema del apunte abierto."""
        texto = self.texto.get("1.0", "end-1c") if self.actual is not None else ""
        raices = mapa.nodos(texto)
        if not raices:
            messagebox.showinfo("Mapa mental", "Abre un apunte con un tema y una lista sangrada de flechas, "
                                "por ejemplo:\n\nFotosíntesis\n   → Fase luminosa\n"
                                "      → produce ATP y NADPH", parent=self)
            return
        titulo = self.titulo.get().strip() or "sin titulo"
        c = self.colores
        v = tk.Toplevel(self)
        v.title(f"Mapa mental -- {titulo}")
        v.geometry("900x600")
        v.transient(self)
        v.configure(background=c["fondo"])
        marco = ttk.Frame(v, padding=8)
        marco.pack(fill="both", expand=True)
        marco.columnconfigure(0, weight=1)
        marco.rowconfigure(0, weight=1)
        lienzo = tk.Canvas(marco, highlightthickness=0, background=c["hoja"])
        vertical = ttk.Scrollbar(marco, orient="vertical", command=lienzo.yview)
        horizontal = ttk.Scrollbar(marco, orient="horizontal", command=lienzo.xview)
        lienzo.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        lienzo.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        v.bind("<MouseWheel>", lambda e: lienzo.yview_scroll(-e.delta // 120, "units"))
        v.bind("<Shift-MouseWheel>", lambda e: lienzo.xview_scroll(-e.delta // 120, "units"))
        v.bind("<Button-4>", lambda e: lienzo.yview_scroll(-1, "units"))
        v.bind("<Button-5>", lambda e: lienzo.yview_scroll(1, "units"))

        ancho_col, alto_fila = 220, 46
        cajas, ancho, alto = mapa.disponer(raices, ancho_col, alto_fila)
        rotulos = {}
        for caja in cajas:
            rotulo = lienzo.create_text(0, 0, text=caja.nodo.texto, width=ancho_col - 20,
                                        fill=c["texto"], font=(LETRA, 10), justify="center")
            rotulos[id(caja.nodo)] = rotulo
            limites = lienzo.bbox(rotulo)
            if limites:
                alto_fila = max(alto_fila, limites[3] - limites[1] + 16)
        if alto_fila != 46:
            cajas, ancho, alto = mapa.disponer(raices, ancho_col, alto_fila)
        lienzo.configure(scrollregion=(0, 0, ancho, alto))
        por_nodo = {id(caja.nodo): caja for caja in cajas}
        for caja in cajas:
            for hijo in caja.nodo.hijos:
                destino = por_nodo[id(hijo)]
                lienzo.create_line(caja.x + ancho_col - 8, caja.y + alto_fila // 2,
                                   destino.x + 8, destino.y + alto_fila // 2,
                                   fill=c["acento"], arrow=tk.LAST)
        for caja in cajas:
            lienzo.create_rectangle(caja.x + 8, caja.y + 4, caja.x + ancho_col - 8,
                                    caja.y + alto_fila - 4, fill=c["acento_suave"], outline=c["acento"])
            rotulo = rotulos[id(caja.nodo)]
            lienzo.coords(rotulo, caja.x + ancho_col // 2, caja.y + alto_fila // 2)
            lienzo.tag_raise(rotulo)

        def guardar_imagen():
            destino = filedialog.asksaveasfilename(parent=v, title="Guardar como imagen",
                                                    initialfile=titulo + ".svg", defaultextension=".svg",
                                                    filetypes=[("Imagen SVG", "*.svg"), ("Imagen PNG", "*.png")])
            if not destino:
                return
            try:
                if Path(destino).suffix.lower() == ".png":
                    from PIL import ImageGrab
                    v.lift()
                    v.update_idletasks()
                    x, y = lienzo.winfo_rootx(), lienzo.winfo_rooty()
                    ImageGrab.grab(bbox=(x, y, x + lienzo.winfo_width(), y + lienzo.winfo_height())).save(destino)
                else:
                    fuente = tkfont.Font(root=v, font=(LETRA, 10))

                    def partir(texto):
                        lineas = []
                        linea = ""
                        for palabra in texto.split():
                            candidata = f"{linea} {palabra}" if linea else palabra
                            if linea and fuente.measure(candidata) > ancho_col - 20:
                                lineas.append(linea)
                                linea = palabra
                            else:
                                linea = candidata
                        return lineas + [linea]

                    svg = mapa.a_svg(cajas, ancho, alto, ancho_col, alto_fila, c, partir, letra=LETRA)
                    Path(destino).write_text(svg, encoding="utf-8")
            except ImportError:
                messagebox.showerror("Mapa mental", "Falta el paquete 'Pillow'. Guarda el mapa como SVG, "
                                     "que no necesita instalar nada.", parent=v)
            except OSError as e:
                messagebox.showerror("Mapa mental", f"No se pudo guardar la imagen:\n{e}", parent=v)

        ttk.Button(marco, text="💾 Guardar como imagen", command=guardar_imagen).grid(
            row=2, column=0, sticky="e", pady=(8, 0))

    def menu_exportar(self):
        """Ventana «Exportar»: qué exportar, en qué formato (Guardar como) y en qué carpeta (Guardar en)."""
        self.guardar(silencioso=True)
        opciones = []
        if self.actual:
            opciones.append(("nota", f"Este apunte: «{self.titulo.get().strip()}»"))
        carpeta = self._carpeta_elegida()
        if carpeta:
            opciones.append(("carpeta", f"Toda la carpeta «{carpeta.relative_to(datos.NOTAS).as_posix()}»"))
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
        nombre = tk.StringVar(value=datos.slug(self._titulo_exportacion(que.get()).replace("/", " - ")))
        carpeta_dest = tk.StringVar(value=self.cfg.get("exportar_carpeta") or str(datos.BASE / "exportados"))
        abrir = tk.BooleanVar(value=self.cfg.get("exportar_abrir", True))
        ext = tk.StringVar()

        def al_cambiar_que():
            nombre.set(datos.slug(self._titulo_exportacion(que.get()).replace("/", " - ")))

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
                                              initialdir=carpeta_dest.get() if Path(carpeta_dest.get()).is_dir() else datos.BASE)
            if elegida:
                carpeta_dest.set(str(Path(elegida)))

        ttk.Button(caja, text="📁 Examinar...", command=examinar).pack(side="left", padx=(4, 0))
        fila += 1
        accesos = ttk.Frame(m)
        accesos.grid(row=fila, column=0, columnspan=3, sticky="w", padx=(12, 0), pady=(4, 0))
        for texto, ruta in (("Exportados", datos.BASE / "exportados"), ("Escritorio", datos.carpeta_windows(0x10, "Desktop")),
                            ("Documentos", datos.carpeta_documentos()), ("Descargas", Path.home() / "Downloads")):
            ttk.Button(accesos, text=texto, command=lambda r=ruta: carpeta_dest.set(str(r))).pack(side="left", padx=(0, 4))
        fila += 1
        ttk.Checkbutton(m, text="Abrir el archivo al terminar", variable=abrir).grid(
            row=fila, column=0, columnspan=3, sticky="w", pady=(12, 0))

        def aceptar(_e=None):
            nom = datos.slug(nombre.get().strip())
            if not nom:
                messagebox.showinfo("Exportar", "Escribe un nombre para el archivo.", parent=v)
                return
            carpeta_final = Path(carpeta_dest.get().strip() or datos.BASE / "exportados")
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
            datos.guardar_config(self.cfg)
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
            raiz = self._carpeta_elegida() if que == "carpeta" else datos.NOTAS
            rutas = [p for p in raiz.rglob("*.md") if datos.ADJUNTOS not in p.parents]
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
            datos.abrir_en_sistema(destino)
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
        carpeta = self._carpeta_elegida() or datos.NOTAS
        hechas, errores = [], []
        for ruta in rutas:
            try:
                importado = importar.importar(ruta)
            except Exception as e:  # noqa: BLE001 - un archivo roto no debe parar los demás
                errores.append(f"{ruta.name}: {e}")
                continue
            titulo = importado["titulo"].strip() or ruta.stem
            destino = self._ruta_libre(carpeta, titulo)
            cuerpo = importado["cuerpo"]
            for n, (nombre, contenido) in enumerate(importado["imagenes"]):
                archivo = self._ruta_adjunto(nombre)
                archivo.write_bytes(contenido)
                rel = os.path.relpath(archivo, destino.parent).replace("\\", "/")
                cuerpo = cuerpo.replace(f"{{{{imagen:{n}}}}}", rel)
            datos.escribir_nota(destino, titulo, ["importado"], datetime.now().strftime("%Y-%m-%d %H:%M"), cuerpo)
            hechas.append(destino)
        if hechas:
            self.actual = None
            self.cargar(hechas[-1])
            self.refrescar()
            self.estado.configure(text=f"Importados {len(hechas)} apunte(s) en «{carpeta.relative_to(datos.BASE)}»")
        if errores:
            messagebox.showwarning("Importar", "No se pudieron importar:\n\n" + "\n".join(errores))
        return hechas
