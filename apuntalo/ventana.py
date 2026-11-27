"""Ventana: fijar encima, barra de tareas, opacidad, modo compacto y atajo global."""
import ctypes
import queue
import threading
import sys
import tkinter as tk

from . import datos


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


class VentanaMixin:
    """Métodos de App: fijar encima, barra de tareas, opacidad, modo compacto y atajo global."""

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
        datos.guardar_config(self.cfg)
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
        self._alpha = max(0.3, min(1.0, float(self.opacidad.get())))
        self.attributes("-alpha", self._alpha)
        # Al mover la barra el ratón está encima: se ve la opacidad elegida hasta que salga y vuelva.
        self._raton_encima = self._raton_dentro()

    def _raton_dentro(self):
        x, y = self.winfo_pointerxy()
        x0, y0 = self.winfo_rootx(), self.winfo_rooty()
        return x0 <= x < x0 + self.winfo_width() and y0 <= y < y0 + self.winfo_height()

    def _opaca_con_raton(self):
        """Semitransparente sobre el vídeo, pero entera mientras el ratón está encima."""
        if self._alpha >= 1.0 or not self.winfo_viewable():
            return
        dentro = self._raton_dentro()
        if dentro != self._raton_encima:
            self._raton_encima = dentro
            self.attributes("-alpha", 1.0 if dentro else self._alpha)

    @staticmethod
    def _geo_compacta_valida(geo):
        """Un tamaño compacto que ocupa media pantalla no es compacto: se descarta."""
        try:
            ancho, alto = (int(n) for n in geo.split("+")[0].split("x"))
        except (ValueError, AttributeError):
            return False
        return 200 <= ancho <= 900 and 200 <= alto <= 1000

    @staticmethod
    def _geo_normal_valida(geo):
        """Un tamaño normal diminuto (1x1 de una ventana aún sin dibujar) no sirve: se descarta."""
        try:
            ancho, alto = (int(n) for n in geo.split("+")[0].split("x"))
        except (ValueError, AttributeError):
            return False
        return ancho >= 600 and alto >= 400

    def alternar_compacto(self):
        if not self.compacto:
            if self.state() == "zoomed":
                self.state("normal")          # una ventana maximizada no se deja encoger
            elif self._geo_normal_valida(self.geometry()):
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
        self._opaca_con_raton()
        self.after(150, self._mirar_atajo)
