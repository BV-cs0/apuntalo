"""Pruebas de la jerarquía y disposición del mapa mental. Sin ventanas."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from apuntalo import mapa  # noqa: E402


def test_fotosintesis_tiene_dos_fases_con_un_hijo_cada_una():
    md = ("Fotosintesis\n"
          "   → Fase luminosa\n"
          "      → produce ATP y NADPH\n"
          "   → Fase oscura (ciclo de Calvin)\n"
          "      → fija CO2 => glucosa")

    raices = mapa.nodos(md)

    assert raices == [mapa.Nodo("Fotosintesis", [
        mapa.Nodo("Fase luminosa", [mapa.Nodo("produce ATP y NADPH")]),
        mapa.Nodo("Fase oscura (ciclo de Calvin)", [mapa.Nodo("fija CO2 => glucosa")]),
    ])]


def test_las_listas_sangradas_cuelgan_del_encabezado():
    md = "# Tema\n  1. Concepto\n  - [x] Repaso"

    raices = mapa.nodos(md)

    assert raices == [mapa.Nodo("Tema", [mapa.Nodo("Concepto"), mapa.Nodo("Repaso")])]


def test_el_codigo_y_las_imagenes_cortan_la_jerarquia():
    md = "- Antes\n```\n  - Dentro\n```\n  - Después\n![Imagen](foto.png)\n    → Final"

    raices = mapa.nodos(md)

    assert raices == [mapa.Nodo("Antes"), mapa.Nodo("Después"), mapa.Nodo("Final")]


def test_los_elementos_del_mismo_nivel_son_raices_separadas():
    md = "- Uno\n- Dos\n→ Tres"

    raices = mapa.nodos(md)

    assert raices == [mapa.Nodo("Uno"), mapa.Nodo("Dos"), mapa.Nodo("Tres")]


def test_disponer_centra_los_padres_y_apila_las_raices():
    raices = mapa.nodos("Tema\n  - Rama\n    - Hoja\n  - Otra hoja\nSegundo tema")
    ancho_col, alto_fila = 220, 46

    cajas, ancho, alto = mapa.disponer(raices, ancho_col, alto_fila)

    por_texto = {caja.nodo.texto: caja for caja in cajas}
    tema, rama, hoja = (por_texto[texto] for texto in ("Tema", "Rama", "Hoja"))
    otra_hoja = por_texto["Otra hoja"]
    assert tema.x < rama.x < hoja.x
    assert len({(caja.x, caja.y) for caja in cajas}) == len(cajas) == 5
    assert rama.y == hoja.y
    assert otra_hoja.y == hoja.y + alto_fila
    assert tema.y == (rama.y + otra_hoja.y) // 2
    assert por_texto["Segundo tema"].y == otra_hoja.y + alto_fila
    assert ancho >= max(caja.x for caja in cajas) + ancho_col
    assert alto >= max(caja.y for caja in cajas) + alto_fila
