"""Lógica de texto del editor: listas, flechas y palabras.

Son funciones puras (reciben texto y devuelven texto), sin tkinter, para poder probarlas.
La ventana (app.py) solo las llama y aplica el resultado.
"""
import re
from dataclasses import dataclass

SANGRIA = "  "   # un nivel de lista (el mismo que usan importar y exportar)

ROMANO = r"(?=[ivx])x{0,3}(?:ix|iv|v?i{0,3})"
RE_ITEM = re.compile(
    r"^(?P<sangria>[ \t]*)"
    r"(?:(?P<num>\d+|" + ROMANO + r"|[a-z])(?P<sep>[.)])|(?P<vineta>[-*+•→]))"
    r"(?P<tarea> \[[ xX]\])?"
    r"(?P<esp> |$)(?P<resto>.*)$")


@dataclass
class Item:
    sangria: str
    tipo: str          # "num", "alfa", "romano", "vineta" o "flecha"
    valor: int         # posición en la lista (1, 2, 3...); 0 en viñetas
    sep: str           # "." o ")" en listas ordenadas; el símbolo en las viñetas
    tarea: str         # " [ ]" / " [x]" o ""
    resto: str         # el texto del elemento
    ancho: int         # caracteres hasta donde empieza el texto

    @property
    def nivel(self):
        return len(self.sangria.replace("\t", SANGRIA)) // len(SANGRIA)

    @property
    def ordenada(self):
        return self.tipo in ("num", "alfa", "romano")

    def prefijo(self, valor=None, tarea=None):
        if self.ordenada:
            marca = marca_de(self.tipo, self.valor if valor is None else valor) + self.sep
        else:
            marca = self.sep
        return f"{self.sangria}{marca}{self.tarea if tarea is None else tarea} "


# ---------- números, letras y romanos ----------
def a_romano(n):
    res = ""
    for v, s in ((40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
        while n >= v:
            res, n = res + s, n - v
    return res


def de_romano(s):
    vals = {"i": 1, "v": 5, "x": 10, "l": 50}
    total = 0
    for i, c in enumerate(s):
        v = vals[c]
        total += -v if i + 1 < len(s) and vals[s[i + 1]] > v else v
    return total


def a_letra(n):
    res = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        res = chr(97 + r) + res
    return res


def marca_de(tipo, n):
    return {"num": str, "alfa": a_letra, "romano": a_romano}[tipo](max(n, 1))


HIJO = {"num": "alfa", "alfa": "romano", "romano": "num", "vineta": "vineta", "flecha": "flecha"}
PADRE = {"alfa": "num", "romano": "alfa", "num": "num", "vineta": "vineta", "flecha": "flecha"}


def analizar(linea, anterior=None):
    """Un elemento de lista, o None si la línea no lo es.

    `anterior` (el elemento hermano de arriba) sirve para saber si «i.» es una letra o un romano."""
    m = RE_ITEM.match(linea)
    if not m:
        return None
    resto = m["resto"]
    if m["vineta"]:
        tipo = "flecha" if m["vineta"] == "→" else "vineta"
        return Item(m["sangria"], tipo, 0, m["vineta"], m["tarea"] or "", resto, m.start("resto"))
    if m["tarea"]:
        return None          # «1. [ ]» no es una tarea
    etiqueta = m["num"]
    if etiqueta.isdigit():
        tipo, valor = "num", int(etiqueta)
    elif re.fullmatch(ROMANO, etiqueta) and (len(etiqueta) > 1 or etiqueta == "i"
                                              or (anterior and anterior.tipo == "romano")):
        tipo, valor = "romano", de_romano(etiqueta)
        if anterior and anterior.tipo == "alfa" and len(etiqueta) == 1:
            tipo, valor = "alfa", ord(etiqueta) - 96
    else:
        tipo, valor = "alfa", ord(etiqueta) - 96
    return Item(m["sangria"], tipo, valor, m["sep"], "", resto, m.start("resto"))


def _ancho_sangria(linea):
    s = linea[:len(linea) - len(linea.lstrip(" \t"))]
    return len(s.replace("\t", SANGRIA))


def en_codigo(lineas, fila):
    """¿Está la línea dentro de un bloque ``` ... ```?"""
    return sum(1 for l in lineas[:fila] if l.strip().startswith("```")) % 2 == 1


# ---------- numeración ----------
def _hueco(lineas, i):
    """¿Es una línea en blanco entre dos elementos? (una lista puede llevar una línea vacía en medio)."""
    return (0 < i < len(lineas) - 1 and not lineas[i].strip()
            and bool(analizar(lineas[i - 1])) and bool(analizar(lineas[i + 1])))


def _en_lista(lineas, i):
    return bool(analizar(lineas[i])) or _hueco(lineas, i)


def _bloque(lineas, fila):
    """Primera y última línea de la lista que contiene `fila` (elementos seguidos, con huecos sueltos)."""
    ini = fin = fila
    while ini > 0 and _en_lista(lineas, ini - 1):
        ini -= 1
    while fin + 1 < len(lineas) and _en_lista(lineas, fin + 1):
        fin += 1
    return ini, fin


def renumerar(lineas, fila):
    """Vuelve a numerar la lista que contiene `fila`: 1, 2, 3… / a, b, c… según el nivel."""
    lineas = list(lineas)
    if not (0 <= fila < len(lineas)) or not analizar(lineas[fila]):
        return lineas
    ini, fin = _bloque(lineas, fila)
    grupos = {}   # ancho de sangría -> (tipo, siguiente valor, separador)
    for i in range(ini, fin + 1):
        if not lineas[i].strip():
            continue
        ancho = _ancho_sangria(lineas[i])
        for k in [k for k in grupos if k > ancho]:
            del grupos[k]
        previo = grupos.get(ancho)
        anterior = Item("", previo[0], 0, "", "", "", 0) if previo else None
        it = analizar(lineas[i], anterior)
        if not it.ordenada:
            grupos[ancho] = (it.tipo, 0, it.sep)
            continue
        if previo and previo[0] in ("num", "alfa", "romano"):
            tipo, valor, sep = previo
        else:
            tipo, valor, sep = it.tipo, it.valor, it.sep
        it.tipo, it.sep = tipo, sep
        nueva = it.prefijo(valor) + it.resto
        if nueva != lineas[i]:
            lineas[i] = nueva
        grupos[ancho] = (tipo, valor + 1, sep)
    return lineas


def _anterior(lineas, fila, ancho):
    """El elemento hermano (misma sangría) más cercano por encima, o None."""
    for i in range(fila - 1, -1, -1):
        if not lineas[i].strip() and i > 0 and analizar(lineas[i - 1]):
            continue                                    # hueco dentro de la lista
        it = analizar(lineas[i])
        if not it:
            return None
        a = _ancho_sangria(lineas[i])
        if a == ancho:
            return analizar(lineas[i], it)
        if a < ancho:
            return None
    return None


def _item(lineas, fila):
    return analizar(lineas[fila], _anterior(lineas, fila, _ancho_sangria(lineas[fila])))


# ---------- teclas ----------
def enter(lineas, fila, col):
    """Enter dentro de una lista: crea el siguiente elemento o termina la lista.

    Devuelve (líneas, fila, columna) del cursor, o None si Enter debe hacer lo normal."""
    if en_codigo(lineas, fila):
        return None
    it = _item(lineas, fila)
    if not it or col < it.ancho:
        return None
    if not it.resto.strip():
        if it.sangria:                                  # elemento vacío anidado: sube un nivel
            return tab(lineas, fila, col, atras=True)
        lineas = list(lineas)
        lineas[fila] = ""                               # elemento vacío: se acaba la lista
        return renumerar(lineas, fila + 1 if fila + 1 < len(lineas) else fila), fila, 0
    linea = lineas[fila]
    tarea = " [ ]" if it.tarea else ""
    prefijo = it.prefijo(it.valor + 1, tarea)
    lineas = lineas[:fila] + [linea[:col], prefijo + linea[col:].lstrip(" ")] + lineas[fila + 1:]
    return renumerar(lineas, fila + 1), fila + 1, len(prefijo)


def tab(lineas, fila, col, atras=False):
    """Tab / Mayús+Tab en un elemento: lo baja o lo sube un nivel (1. → a. → i.)."""
    if en_codigo(lineas, fila):
        return None
    it = _item(lineas, fila)
    if not it:
        return None
    if atras:
        if not it.sangria:
            return None
        sangria = it.sangria[:-1] if it.sangria.endswith("\t") else it.sangria[:-len(SANGRIA)]
        hermano = _anterior(lineas, fila, len(sangria.replace("\t", SANGRIA)))
        tipo = hermano.tipo if hermano else PADRE[it.tipo]
        sep = hermano.sep if hermano else it.sep
    else:
        sangria = it.sangria + SANGRIA
        hermano = _anterior(lineas, fila, len(sangria.replace("\t", SANGRIA)))
        tipo = hermano.tipo if hermano else HIJO[it.tipo]
        sep = hermano.sep if hermano else it.sep
    if tipo in ("vineta", "flecha") and it.ordenada:
        sep = "→" if tipo == "flecha" else "-"
    elif tipo in ("num", "alfa", "romano") and not it.ordenada:
        sep = "."
    nuevo = Item(sangria, tipo, (hermano.valor + 1) if hermano and hermano.ordenada else 1, sep,
                 it.tarea, it.resto, 0)
    prefijo = nuevo.prefijo()
    lineas = list(lineas)
    lineas[fila] = prefijo + it.resto
    lineas = renumerar(lineas, fila)
    return lineas, fila, max(len(prefijo), col + len(prefijo) - it.ancho)


def retroceso(lineas, fila, col, sangrar=True):
    """Retroceso justo detrás de la viñeta.

    Elemento con sangría → sube un nivel (a. → 2.).
    Elemento vacío sin sangría con un hermano encima → baja un nivel (2. → a.), salvo sangrar=False
    (la app lo pasa si acaba de subirlo con retroceso, para no dar vueltas: 2. → a. → 2. → texto).
    Si no, quita la viñeta."""
    if en_codigo(lineas, fila):
        return None
    it = _item(lineas, fila)
    if not it or col != it.ancho or col == 0:
        return None
    if it.sangria:
        return tab(lineas, fila, col, atras=True)
    if sangrar and not it.resto.strip() and _anterior(lineas, fila, 0):
        return tab(lineas, fila, col)
    lineas = list(lineas)
    lineas[fila] = it.sangria + it.resto
    lineas = renumerar(lineas, fila - 1) if fila > 0 and analizar(lineas[fila - 1]) else lineas
    if fila + 1 < len(lineas) and analizar(lineas[fila + 1]):
        lineas = renumerar(lineas, fila + 1)
    return lineas, fila, len(it.sangria)


# ---------- palabras ----------
def _clase(c):
    return "esp" if c.isspace() else ("pal" if c.isalnum() or c == "_" else "sim")


def palabra_izquierda(linea, col):
    """Columna donde empieza la palabra a la izquierda (Ctrl+Retroceso). None al principio de la línea."""
    if col <= 0:
        return None
    i = col
    while i > 0 and linea[i - 1].isspace():
        i -= 1
    if i > 0:
        clase = _clase(linea[i - 1])
        while i > 0 and _clase(linea[i - 1]) == clase:
            i -= 1
    return i


def palabra_derecha(linea, col):
    """Columna donde acaba la palabra a la derecha y sus espacios (Ctrl+Supr). None al final de la línea."""
    if col >= len(linea):
        return None
    i = col
    if not linea[i].isspace():
        clase = _clase(linea[i])
        while i < len(linea) and _clase(linea[i]) == clase:
            i += 1
    while i < len(linea) and linea[i].isspace():
        i += 1
    return i


# ---------- flechas, símbolos y bloques ----------
SIMBOLOS = {
    "<=>": "⇔", "<->": "↔", "-->": "⟶", "...": "…", "(c)": "©",
    "->": "→", "<-": "←", "=>": "⇒", "!=": "≠", "<=": "≤", ">=": "≥",
}

BLOQUES = {
    "/idea": "> 💡 Idea clave: ",
    "/ojo": "> ⚠ Ojo: ",
    "/resumen": "> ✅ Resumen: ",
    "/nota": "> 📝 ",
    "/pregunta": "> ❓ Pregunta: ",
    "/definicion": "> 📖 Definición: ",
}

# Emoji del principio de la cita -> nombre del estilo del bloque
ESTILO_BLOQUE = {"💡": "idea", "⚠": "ojo", "✅": "resumen", "📝": "nota", "❓": "pregunta", "📖": "definicion"}


def sustitucion(antes):
    """Al pulsar espacio: qué cambiar al final de `antes` (el texto de la línea hasta el cursor).

    Devuelve (cuántos caracteres quitar, qué poner) o None."""
    if antes.strip() in BLOQUES and not antes[:len(antes) - len(antes.lstrip())]:
        return len(antes), BLOQUES[antes.strip()]
    if antes.count("`") % 2 == 1:          # dentro de `código`
        return None
    for patron in sorted(SIMBOLOS, key=len, reverse=True):
        if antes.endswith(patron):
            return len(patron), SIMBOLOS[patron]
    return None


def tipo_bloque(linea):
    """«idea», «ojo»… si la línea es un bloque destacado; «cita» si es una cita normal; None si no."""
    if not linea.startswith(">"):
        return None
    texto = linea[1:].lstrip()
    for emoji, nombre in ESTILO_BLOQUE.items():
        if texto.startswith(emoji):
            return nombre
    return "cita"
