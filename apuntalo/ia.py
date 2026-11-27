"""Resumir con IA: ChatGPT, Gemini y Claude."""
import json
import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, simpledialog, ttk

from . import datos


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


class IAMixin:
    """Métodos de App: resumir con IA (ChatGPT, Gemini y Claude)."""

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
        meta, cuerpo = datos.leer_nota(self.actual)
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
        meta, cuerpo = datos.leer_nota(self.actual)
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
        datos.escribir_nota(ruta, titulo, etiquetas, datetime.now().strftime("%Y-%m-%d %H:%M"), texto + "\n")
        self.guardar(silencioso=True)
        self.cargar(ruta)
        self.refrescar()
