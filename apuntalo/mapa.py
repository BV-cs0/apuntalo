"""Jerarquía y disposición del mapa mental, sin tkinter."""
from dataclasses import dataclass, field

from .exportar import bloques


@dataclass
class Nodo:
    texto: str
    hijos: list["Nodo"] = field(default_factory=list)


def nodos(md: str) -> list[Nodo]:
    """Agrupa los bloques de texto según la sangría de las listas."""
    raices = []
    ancestros = []
    for b in bloques(md):
        tipo = b["tipo"]
        if tipo in {"ul", "ol", "tarea"}:
            nivel = b["nivel"]
        elif tipo in {"p", "h1", "h2", "h3"}:
            nivel = 0
        else:
            ancestros.clear()
            continue
        while ancestros and ancestros[-1][0] >= nivel:
            ancestros.pop()
        nodo = Nodo(b["texto"])
        if ancestros:
            ancestros[-1][1].hijos.append(nodo)
        else:
            raices.append(nodo)
        ancestros.append((nivel, nodo))
    return raices


@dataclass
class Caja:
    nodo: Nodo
    x: int
    y: int


def disponer(raiz: list[Nodo], ancho_col: int = 220, alto_fila: int = 46) -> tuple[list[Caja], int, int]:
    """Reserva una fila por hoja y centra cada padre entre sus hijos."""
    cajas = []
    fila = 0

    def situar(nodo, profundidad):
        nonlocal fila
        caja = Caja(nodo, profundidad * ancho_col, 0)
        cajas.append(caja)
        if nodo.hijos:
            caja.y = sum(situar(hijo, profundidad + 1) for hijo in nodo.hijos) // len(nodo.hijos)
        else:
            caja.y = fila * alto_fila
            fila += 1
        return caja.y

    for nodo in raiz:
        situar(nodo, 0)
    ancho = max((caja.x + ancho_col for caja in cajas), default=0)
    return cajas, ancho + 8, fila * alto_fila + 8
