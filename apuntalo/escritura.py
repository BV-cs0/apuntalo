"""Editor: letra, tema, resaltado, corrector y teclas que dan formato al escribir."""
import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, simpledialog, ttk

from . import datos, editor, ortografia
from .estilo import LETRA, MONO, TEMAS


class EscrituraMixin:
    """Métodos de App: letra, tema, resaltado, corrector y teclas que dan formato al escribir."""

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
        datos.guardar_config(self.cfg)
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
        t.tag_configure("tachado", overstrike=True)
        t.tag_configure("codigo", font=(MONO, n - 1), background=c["acento_suave"], foreground=c["titulo"])
        t.tag_configure("bloque_codigo", font=(MONO, n - 1), background=c["codigo"], lmargin1=12, lmargin2=12)
        t.tag_configure("tabla", font=(MONO, n - 1), background=c["codigo"], lmargin1=12, lmargin2=12)
        t.tag_configure("tabla_cabecera", font=(MONO, n - 1, "bold"))
        t.tag_configure("tabla_raya", foreground=c["suave"])
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
        ("tachado", re.compile(r"~~[^~\n]+~~")),
        ("codigo", re.compile(r"`[^`\n]+`")),
        ("tiempo", re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?\]")),
    ]

    def resaltar(self):
        """Colorea el Markdown del editor: títulos, negritas, citas, listas, marcas de tiempo."""
        t = self.texto
        quitar = ["h1", "h2", "h3", "simbolo", "negrita", "cursiva", "tachado", "codigo", "cita", "tiempo", "hecha",
                  "vineta", "regla", "bloque_codigo", "tabla", "tabla_cabecera", "tabla_raya"]
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
            if editor.RE_FILA_TABLA.match(linea):
                t.tag_add("tabla", f"{n}.0", f"{n}.end+1c")
                if editor.es_separador_tabla(linea):
                    t.tag_add("tabla_raya", f"{n}.0", f"{n}.end+1c")
                elif n < len(lineas) and editor.es_separador_tabla(lineas[n]):
                    t.tag_add("tabla_cabecera", f"{n}.0", f"{n}.end+1c")
                for barra in re.finditer(r"\|", linea):
                    t.tag_add("simbolo", f"{n}.{barra.start()}", f"{n}.{barra.end()}")
                for tag, patron in self.PATRONES:
                    if tag in {"tachado", "tiempo"}:
                        for m in patron.finditer(linea):
                            t.tag_add(tag, f"{n}.{m.start()}", f"{n}.{m.end()}")
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
        m.add_checkbutton(label="Mayús+Supr corta en vez de borrar la palabra",
                          variable=self._var_mayus_supr_corta(), command=self._alternar_mayus_supr_corta)
        m.add_separator()
        m.add_command(label="Revisar ortografía…  (F7)", command=self.dialogo_ortografia)
        m.add_checkbutton(label="Subrayar faltas mientras escribo", variable=self._var_ortografia(),
                          command=self._alternar_ortografia)
        m.add_checkbutton(label="Corregir tildes automáticamente", variable=self._var_tildes(),
                          command=self._alternar_tildes)
        m.add_checkbutton(label="Mayúscula automática al empezar frase",
                          variable=self._var_mayusculas_auto(), command=self._alternar_mayusculas_auto)
        m.add_checkbutton(label="Cerrar paréntesis y comillas automáticamente",
                          variable=self._var_cierre_automatico(), command=self._alternar_cierre_automatico)
        m.add_checkbutton(label="Alinear tablas automáticamente",
                          variable=self._var_alinear_tablas(), command=self._alternar_alinear_tablas)
        m.tk_popup(e.x_root, e.y_root)
        return "break"

    def _var_ortografia(self):
        if not hasattr(self, "_v_ort"):
            self._v_ort = tk.BooleanVar(value=self.cfg.get("ortografia", True))
        return self._v_ort

    def _alternar_ortografia(self):
        self.cfg["ortografia"] = bool(self._var_ortografia().get())
        datos.guardar_config(self.cfg)
        self.subrayar_faltas()

    def _var_tildes(self):
        if not hasattr(self, "_v_tildes"):
            self._v_tildes = tk.BooleanVar(value=self.cfg.get("tildes", True))
        return self._v_tildes

    def _alternar_tildes(self):
        self.cfg["tildes"] = bool(self._var_tildes().get())
        datos.guardar_config(self.cfg)

    def _var_mayusculas_auto(self):
        if not hasattr(self, "_v_mayusculas_auto"):
            self._v_mayusculas_auto = tk.BooleanVar(value=self.cfg.get("mayusculas_auto", True))
        return self._v_mayusculas_auto

    def _alternar_mayusculas_auto(self):
        self.cfg["mayusculas_auto"] = bool(self._var_mayusculas_auto().get())
        datos.guardar_config(self.cfg)

    def _var_cierre_automatico(self):
        if not hasattr(self, "_v_cierre_automatico"):
            self._v_cierre_automatico = tk.BooleanVar(value=self.cfg.get("cierre_automatico", True))
        return self._v_cierre_automatico

    def _alternar_cierre_automatico(self):
        self.cfg["cierre_automatico"] = bool(self._var_cierre_automatico().get())
        datos.guardar_config(self.cfg)

    def _var_alinear_tablas(self):
        if not hasattr(self, "_v_alinear_tablas"):
            self._v_alinear_tablas = tk.BooleanVar(value=self.cfg.get("alinear_tablas", True))
        return self._v_alinear_tablas

    def _alternar_alinear_tablas(self):
        self.cfg["alinear_tablas"] = self._var_alinear_tablas().get()
        datos.guardar_config(self.cfg)

    def _var_mayus_supr_corta(self):
        if not hasattr(self, "_v_mayus_supr_corta"):
            self._v_mayus_supr_corta = tk.BooleanVar(value=self.cfg.get("mayus_supr_corta", False))
        return self._v_mayus_supr_corta

    def _alternar_mayus_supr_corta(self):
        self.cfg["mayus_supr_corta"] = bool(self._var_mayus_supr_corta().get())
        datos.guardar_config(self.cfg)

    def palabra_propia(self, palabra):
        """La palabra deja de marcarse (se guarda en la configuración: nombres, términos técnicos…)."""
        propias = self.cfg.setdefault("palabras_propias", [])
        if palabra.lower() not in propias:
            propias.append(palabra.lower())
            datos.guardar_config(self.cfg)
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
        lineas = self._lineas()
        resultado = editor.enter(lineas, fila - 1, col)
        if resultado is None:
            resultado = editor.tabla_enter(lineas, fila - 1, col, alinear=self.cfg.get("alinear_tablas", True))
        return self._aplicar(resultado)

    def _tecla_tab(self, atras):
        if not self._editable():
            return "break"
        fila, col = self._posicion()
        lineas = self._lineas()
        resultado = editor.tab(lineas, fila - 1, col, atras=atras)
        if resultado is None:
            resultado = editor.tabla_tab(lineas, fila - 1, col, atras=atras,
                                         alinear=self.cfg.get("alinear_tablas", True))
        r = self._aplicar(resultado)
        if r or atras:
            return "break"   # Mayús+Tab fuera de una lista no salta a otro control
        return None

    def _tecla_retroceso(self, _e=None):
        r = self._borrar_imagen(adelante=False)
        if r or not self._editable() or self.texto.tag_ranges("sel"):
            return r
        fila, col = self._posicion()
        lineas = self._lineas()
        if self.cfg.get("cierre_automatico", True) and editor.borra_par(lineas[fila - 1], col):
            t = self.texto
            t.configure(autoseparators=False)
            t.edit_separator()
            t.delete("insert-1c", "insert+1c")
            t.edit_separator()
            t.configure(autoseparators=True)
            t.see("insert")
            return "break"
        # Si este elemento acaba de subir de nivel con Retroceso (a. → 2.), el siguiente quita la viñeta
        # en vez de volver a bajarlo: así no se queda dando vueltas.
        sangrar = getattr(self, "_subido", None) != (fila, lineas[fila - 1])
        res = editor.retroceso(lineas, fila - 1, col, sangrar=sangrar)
        subio = res and len(res[0][fila - 1]) - len(res[0][fila - 1].lstrip()) < \
            len(lineas[fila - 1]) - len(lineas[fila - 1].lstrip())
        self._subido = (fila, res[0][fila - 1]) if subio else None
        return self._aplicar(res)

    def _tecla_general(self, e):
        """Cierra pares y pone en mayúscula la letra al empezar frase."""
        t = self.texto
        caracter = e.char
        if (self.cfg.get("cierre_automatico", True)
                and (caracter in editor.PARES or caracter in editor.CIERRES) and self._editable()):
            seleccion = t.tag_ranges("sel")
            if seleccion:
                if caracter not in editor.PARES:
                    return None
                ini, fin = t.index("sel.first"), t.index("sel.last")
                accion = "envolver"
            else:
                _, col = self._posicion()
                linea = t.get("insert linestart", "insert lineend")
                accion = editor.accion_par(linea, col, caracter)
            if accion == "saltar":
                t.mark_set("insert", "insert+1c")
                t.see("insert")
                return "break"
            if accion:
                t.configure(autoseparators=False)
                t.edit_separator()
                if seleccion:
                    # Sin etiquetas en los signos para conservar seleccionada solo la parte interior.
                    t.insert(fin, editor.PARES[caracter], ())
                    t.insert(ini, caracter, ())
                else:
                    t.insert("insert", caracter + editor.PARES[caracter])
                    t.mark_set("insert", "insert-1c")
                t.edit_separator()
                t.configure(autoseparators=True)
                t.see("insert")
                return "break"
        if not e.char or not e.char.isalpha() or not e.char.islower():
            return None
        if not self._editable() or t.tag_ranges("sel") or not self.cfg.get("mayusculas_auto", True):
            return None
        fila, col = self._posicion()
        if not editor.necesita_mayuscula(self._lineas(), fila - 1, col):
            return None
        t.configure(autoseparators=False)
        t.edit_separator()
        t.insert("insert", e.char.upper())
        t.edit_separator()
        t.configure(autoseparators=True)
        return "break"

    def _tecla_espacio(self, _e=None):
        """Flechas, símbolos, comandos de bloque y tildes al escribir."""
        t = self.texto
        if not self._editable() or t.tag_ranges("sel"):
            return None
        simbolos = self.cfg.get("simbolos", True)
        tildes = self.cfg.get("ortografia", True) and self.cfg.get("tildes", True)
        if not (simbolos or tildes):
            return None
        fila, _ = self._posicion()
        if editor.en_codigo(self._lineas(), fila - 1):
            return None
        linea = t.get(f"{fila}.0", "insert")
        cambio = editor.sustitucion(linea) if simbolos else None
        if not cambio:
            if tildes and (corrector := self._corrector()):
                sin_cierres = linea.rstrip(')]}"?!».,;:')
                for ini, fin, palabra in ortografia.palabras(sin_cierres):
                    if fin == len(sin_cierres):
                        correccion = ortografia.correccion_tilde(corrector, palabra)
                        if correccion:
                            t.configure(autoseparators=False)
                            t.edit_separator()
                            inicio = t.index(f"insert-{len(linea) - ini}c")
                            t.delete(inicio, f"insert-{len(linea) - fin}c")
                            t.insert(inicio, correccion)
                            t.configure(autoseparators=True)
                            # El espacio de Tk se deshace junto con la corrección.
                            t.after_idle(t.edit_separator)
                        break
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

    def _tecla_mayus_supr(self, _e=None):
        """Mayús+Supr: borra la palabra o la selección como Ctrl+Supr, salvo que se haya configurado para cortar."""
        if not self._editable():
            return "break"
        if self.cfg.get("mayus_supr_corta", False):
            self.texto.event_generate("<<Cut>>")
            return "break"
        return self._borrar_palabra(adelante=True)

    def _borrar_palabra(self, adelante):
        """Ctrl+Retroceso / Ctrl+Supr / Mayús+Supr: borra la palabra entera, como en cualquier programa."""
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
        """Rodea la selección con la marca (o deja el cursor en medio)."""
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

    def insertar_tabla(self):
        """Inserta una tabla en la línea del cursor o debajo y deja el cursor en la primera celda."""
        if not self._editable():
            messagebox.showinfo("Tabla", "Abre o crea una nota primero.")
            return
        columnas = simpledialog.askinteger("Tabla", "Columnas:", parent=self, initialvalue=2, minvalue=1)
        if columnas is None:
            return
        filas = simpledialog.askinteger("Tabla", "Filas (incluye el encabezado):",
                                       parent=self, initialvalue=3, minvalue=1)
        if filas is None:
            return
        vacia = "| " + " | ".join([" " * 3] * columnas) + " |"
        tabla = [vacia]
        if filas > 1:
            tabla += ["| " + " | ".join(["---"] * columnas) + " |"] + [vacia] * (filas - 1)

        t = self.texto
        fila, _ = self._posicion()
        lineas = self._lineas()
        if t.compare(f"{fila}.0", "!=", f"{fila}.end"):
            punto = f"{fila}.end"
            antes = "\n\n"
            despues = "\n" if fila == len(lineas) or lineas[fila].strip() else ""
        else:
            punto = f"{fila}.0"
            antes = "\n" if fila > 1 and lineas[fila - 2].strip() else ""
            despues = "\n"
        t.configure(autoseparators=False)
        t.edit_separator()
        try:
            t.insert(punto, antes + "\n".join(tabla) + despues)
        finally:
            t.edit_separator()
            t.configure(autoseparators=True)
        t.mark_set("insert", f"{fila + len(antes)}.2")
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
