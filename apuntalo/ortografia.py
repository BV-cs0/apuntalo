"""Corrector ortográfico en español e inglés, sin instalar nada.

Usa el corrector que trae Windows (el mismo de Edge y Word, «Spell Checking API»). En otros sistemas, o si
falta el idioma, intenta `pyspellchecker` si está instalado; si no, el corrector queda apagado.

Una palabra solo cuenta como falta si está mal en TODOS los idiomas disponibles: así puedes mezclar
español e inglés («hacemos un deploy del exploit») sin que se marque todo.
"""
import ctypes
import re
import sys
import unicodedata
from difflib import SequenceMatcher

IDIOMAS = ("es-ES", "en-US")

# Palabras: letras (con tildes, ñ, ü) y apóstrofos internos (don't). Se saltan las que llevan números.
RE_PALABRA = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
# Trozos que no son texto normal: código, enlaces, rutas, correos, IPs, opciones de comandos, Markdown de imágenes
RE_SALTAR = re.compile(
    r"`[^`\n]*`"                          # `código`
    r"|!?\[[^\]\n]*\]\([^)\n]*\)"         # [texto](enlace) / ![imagen](ruta)
    r"|\b[a-z][a-z0-9+.-]*://\S+"         # http://...
    r"|\bwww\.\S+"
    r"|\S+@\S+\.\S+"                      # correos
    r"|\S*[/\\]\S*"                       # rutas y cosas con barras
    r"|\S+\.\w{1,4}\b"                    # archivo.py, exploit.sh
    r"|(?<!\S)--?\w[\w-]*"                # -p, --help
    r"|\S*[_=<>^$%{}|]\S*"                # variables, ^USER^, a=b
    , re.IGNORECASE)


def palabras(linea):
    """(inicio, fin, palabra) de las palabras de una línea que merece la pena revisar."""
    tapado = list(linea)
    for m in RE_SALTAR.finditer(linea):
        tapado[m.start():m.end()] = " " * (m.end() - m.start())
    texto = "".join(tapado)
    for m in RE_PALABRA.finditer(texto):
        p = m.group()
        if len(p) < 2 or (p.isupper() and len(p) <= 6):       # siglas: SQL, AWS, IAM
            continue
        if any(c.isupper() for c in p[1:]):                   # camelCase, BurpSuite, iPhone
            continue
        yield m.start(), m.end(), p


def faltas_en_texto(texto, corrector):
    """Lista de (fila, inicio, fin, palabra) mal escritas, fuera de bloques ``` ```. Fila desde 0."""
    if not corrector:
        return []
    faltas, en_codigo = [], False
    for fila, linea in enumerate(texto.split("\n")):
        if linea.strip().startswith("```"):
            en_codigo = not en_codigo
            continue
        if en_codigo:
            continue
        for ini, fin, p in palabras(linea):
            if not corrector.correcta(p):
                faltas.append((fila, ini, fin, p))
    return faltas


def _sin_tildes(p):
    return "".join(c for c in unicodedata.normalize("NFD", p.lower()) if unicodedata.category(c) != "Mn")


def parecida(palabra, sugerencia):
    """¿La sugerencia es casi la misma palabra? (las tildes no cuentan: aqui → aquí).
    Si no lo es, suele ser jerga que el diccionario no conoce («wordlist» → «mordiste»)."""
    return SequenceMatcher(None, _sin_tildes(palabra), _sin_tildes(sugerencia)).ratio() >= 0.8


def igualar_mayusculas(original, sugerencia):
    if original.isupper():
        return sugerencia.upper()
    if original[:1].isupper():
        return sugerencia[:1].upper() + sugerencia[1:]
    return sugerencia


# ---------- Windows: Spell Checking API por COM con ctypes ----------
class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]

    def __init__(self, texto):
        super().__init__()
        ctypes.oledll.ole32.CLSIDFromString(texto, ctypes.byref(self))


def _metodo(obj, indice, *tipos):
    """Función `indice` de la tabla virtual de un objeto COM."""
    tabla = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *tipos)(tabla[indice])


def _soltar(obj):
    if obj:
        tabla = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(tabla[2])(obj)


class _CorrectorWindows:
    def __init__(self, idioma):
        ole = ctypes.oledll.ole32
        try:
            ole.CoInitializeEx(None, 2)     # COINIT_APARTMENTTHREADED (Tk ya lo puede haber hecho)
        except OSError:
            pass
        fabrica = ctypes.c_void_p()
        ole.CoCreateInstance(ctypes.byref(_GUID("{7AB36653-1796-484B-BDFA-E74F1DB7C1DC}")), None, 1,
                             ctypes.byref(_GUID("{8E018A9D-2415-4677-BF08-794EA61F94BB}")), ctypes.byref(fabrica))
        try:
            si = ctypes.c_int()
            _metodo(fabrica, 4, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int))(fabrica, idioma, ctypes.byref(si))
            if not si.value:
                raise OSError("idioma no instalado: " + idioma)
            self._c = ctypes.c_void_p()
            _metodo(fabrica, 5, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p))(
                fabrica, idioma, ctypes.byref(self._c))
        finally:
            _soltar(fabrica)
        self.idioma = idioma

    def correcta(self, palabra):
        errores = ctypes.c_void_p()
        _metodo(self._c, 4, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p))(
            self._c, palabra, ctypes.byref(errores))
        try:
            error = ctypes.c_void_p()
            hr = _metodo(errores, 3, ctypes.POINTER(ctypes.c_void_p))(errores, ctypes.byref(error))
            _soltar(error)
            return hr == 1 or not error.value          # S_FALSE: no hay errores
        finally:
            _soltar(errores)

    def sugerencias(self, palabra, maximo=6):
        lista = ctypes.c_void_p()
        _metodo(self._c, 5, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p))(
            self._c, palabra, ctypes.byref(lista))
        salida = []
        try:
            siguiente = _metodo(lista, 3, ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p),
                                ctypes.POINTER(ctypes.c_ulong))
            while len(salida) < maximo:
                cadena, n = ctypes.c_void_p(), ctypes.c_ulong()
                if siguiente(lista, 1, ctypes.byref(cadena), ctypes.byref(n)) != 0 or not n.value:
                    break
                salida.append(ctypes.wstring_at(cadena.value))
                ctypes.windll.ole32.CoTaskMemFree(cadena)
        finally:
            _soltar(lista)
        return salida

    def ignorar(self, palabra):
        _metodo(self._c, 7, ctypes.c_wchar_p)(self._c, palabra)


class _CorrectorPython:
    """Respaldo con `pyspellchecker` (pip install pyspellchecker), si está instalado."""

    def __init__(self, idioma):
        from spellchecker import SpellChecker
        self._s = SpellChecker(language=idioma[:2])
        self.idioma = idioma

    def correcta(self, palabra):
        return not self._s.unknown([palabra.lower()])

    def sugerencias(self, palabra, maximo=6):
        mejor = self._s.correction(palabra.lower())
        resto = sorted(self._s.candidates(palabra.lower()) or [], key=lambda p: -self._s.word_usage_frequency(p))
        return [p for p in dict.fromkeys(([mejor] if mejor else []) + resto)][:maximo]

    def ignorar(self, palabra):
        self._s.word_frequency.add(palabra.lower())


class Corrector:
    """Junta los idiomas: correcta si lo es en alguno; sugerencias de todos, primero el español."""

    def __init__(self, idiomas=IDIOMAS):
        self.partes, self.ignoradas = [], set()
        for idioma in idiomas:
            for clase in ((_CorrectorWindows, _CorrectorPython) if sys.platform == "win32"
                          else (_CorrectorPython,)):
                try:
                    self.partes.append(clase(idioma))
                    break
                except Exception:
                    continue
        self._cache = {}

    def __bool__(self):
        return bool(self.partes)

    @property
    def idiomas(self):
        return [p.idioma for p in self.partes]

    def correcta(self, palabra):
        if palabra.lower() in self.ignoradas:
            return True
        if palabra not in self._cache:
            try:
                self._cache[palabra] = any(p.correcta(palabra) for p in self.partes)
            except Exception:
                self._cache[palabra] = True
        return self._cache[palabra]

    def sugerencias(self, palabra, maximo=6):
        salida = []
        for p in self.partes:
            try:
                salida += p.sugerencias(palabra, maximo)
            except Exception:
                pass
        salida = [igualar_mayusculas(palabra, s) for s in dict.fromkeys(salida) if s != palabra]
        return list(dict.fromkeys(salida))[:maximo]

    def ignorar(self, palabra):
        self.ignoradas.add(palabra.lower())
        self._cache.pop(palabra, None)
