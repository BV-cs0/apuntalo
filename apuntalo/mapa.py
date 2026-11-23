"""Jerarquía y disposición del mapa mental, sin tkinter."""
from dataclasses import dataclass, field
from xml.sax.saxutils import escape, quoteattr

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


def a_svg(cajas, ancho, alto, ancho_col, alto_fila, colores, partir, letra=""):
    """Genera el SVG del mapa completo a partir de las cajas ya dispuestas."""
    acento = quoteattr(colores["acento"])
    relleno = quoteattr(colores["acento_suave"])
    tinta = quoteattr(colores["texto"])
    fondo = quoteattr(colores["hoja"])
    fuente = quoteattr(f"{letra}, sans-serif" if letra else "sans-serif")
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" '
        f'viewBox="0 0 {ancho} {alto}">',
        '<defs><marker id="flecha" viewBox="0 0 10 6" markerWidth="10" markerHeight="6" '
        'refX="10" refY="3" orient="auto">',
        f'<path d="M0 0 L10 3 L0 6 Z" fill={acento}/></marker></defs>',
        f'<path d="M0 0 H{ancho} V{alto} H0 Z" fill={fondo}/>',
    ]
    por_nodo = {id(caja.nodo): caja for caja in cajas}
    for caja in cajas:
        for hijo in caja.nodo.hijos:
            destino = por_nodo[id(hijo)]
            svg.append(f'<line x1="{caja.x + ancho_col - 8}" y1="{caja.y + alto_fila // 2}" '
                       f'x2="{destino.x + 8}" y2="{destino.y + alto_fila // 2}" '
                       f'stroke={acento} marker-end="url(#flecha)"/>')
    for caja in cajas:
        svg.append(f'<rect x="{caja.x + 8}" y="{caja.y + 4}" width="{ancho_col - 16}" '
                   f'height="{alto_fila - 8}" fill={relleno} stroke={acento}/>')
        x = caja.x + ancho_col // 2
        lineas = partir(caja.nodo.texto)
        paso = 16
        y = caja.y + alto_fila // 2 - (len(lineas) - 1) * paso // 2
        svg.append(f'<text text-anchor="middle" dominant-baseline="central" fill={tinta} '
                   f'font-family={fuente} font-size="10pt">')
        for i, linea in enumerate(lineas):
            svg.append(f'<tspan x="{x}" y="{y + i * paso}">{escape(linea)}</tspan>')
        svg.append("</text>")
    return "\n".join(svg + ["</svg>"])
