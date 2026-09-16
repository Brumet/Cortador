"""Tipografia de trazo incluida en el paquete.

No dependemos de ninguna fuente del sistema ni de freetype: cada caracter es
una lista de polilineas dibujadas sobre una caja de 4 x 7 unidades (altura de
mayuscula = 7, linea base = 0). Los trazos se engordan con shapely para
convertirlos en poligonos que luego se extruyen y se graban en las piezas.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union

Polyline = List[Tuple[float, float]]

CAP_HEIGHT = 7.0
ADVANCE = 4.0
LETTER_GAP = 1.6
LINE_GAP = 3.0

GLYPHS: Dict[str, List[Polyline]] = {
    " ": [],
    "0": [[(0, 1), (0, 6), (4, 6), (4, 1), (0, 1)], [(0, 1), (4, 6)]],
    "1": [[(0.8, 5.4), (2, 7), (2, 0)], [(0.5, 0), (3.5, 0)]],
    "2": [[(0, 6), (1, 7), (3, 7), (4, 6), (4, 4.5), (0, 0), (4, 0)]],
    "3": [[(0, 7), (4, 7), (2, 4)], [(2, 4), (4, 3), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "4": [[(3, 0), (3, 7), (0, 2.5), (4, 2.5)]],
    "5": [[(4, 7), (0, 7), (0, 4), (3, 4), (4, 3), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "6": [[(4, 6), (3, 7), (1, 7), (0, 6), (0, 1), (1, 0), (3, 0), (4, 1), (4, 3),
           (3, 4), (1, 4), (0, 3)]],
    "7": [[(0, 7), (4, 7), (1.5, 0)]],
    "8": [[(1, 4), (0, 5), (0, 6), (1, 7), (3, 7), (4, 6), (4, 5), (3, 4), (1, 4)],
          [(3, 4), (4, 3), (4, 1), (3, 0), (1, 0), (0, 1), (0, 3), (1, 4)]],
    "9": [[(0, 1), (1, 0), (3, 0), (4, 1), (4, 6), (3, 7), (1, 7), (0, 6), (0, 4),
           (1, 3), (3, 3), (4, 4)]],
    "A": [[(0, 0), (2, 7), (4, 0)], [(0.75, 2.6), (3.25, 2.6)]],
    "B": [[(0, 0), (0, 7), (3, 7), (4, 6), (4, 4.5), (3, 3.6), (0, 3.6)],
          [(3, 3.6), (4, 2.6), (4, 1), (3, 0), (0, 0)]],
    "C": [[(4, 6), (3, 7), (1, 7), (0, 6), (0, 1), (1, 0), (3, 0), (4, 1)]],
    "D": [[(0, 0), (0, 7), (3, 7), (4, 6), (4, 1), (3, 0), (0, 0)]],
    "E": [[(4, 7), (0, 7), (0, 0), (4, 0)], [(0, 3.6), (3, 3.6)]],
    "F": [[(4, 7), (0, 7), (0, 0)], [(0, 3.6), (3, 3.6)]],
    "G": [[(4, 6), (3, 7), (1, 7), (0, 6), (0, 1), (1, 0), (3, 0), (4, 1), (4, 3),
           (2, 3)]],
    "H": [[(0, 7), (0, 0)], [(4, 7), (4, 0)], [(0, 3.6), (4, 3.6)]],
    "I": [[(2, 7), (2, 0)], [(0.6, 7), (3.4, 7)], [(0.6, 0), (3.4, 0)]],
    "J": [[(4, 7), (4, 1), (3, 0), (1, 0), (0, 1), (0, 2)]],
    "K": [[(0, 7), (0, 0)], [(4, 7), (0, 3)], [(1.3, 4.3), (4, 0)]],
    "L": [[(0, 7), (0, 0), (4, 0)]],
    "M": [[(0, 0), (0, 7), (2, 3.2), (4, 7), (4, 0)]],
    "N": [[(0, 0), (0, 7), (4, 0), (4, 7)]],
    "O": [[(1, 7), (3, 7), (4, 6), (4, 1), (3, 0), (1, 0), (0, 1), (0, 6), (1, 7)]],
    "P": [[(0, 0), (0, 7), (3, 7), (4, 6), (4, 4.6), (3, 3.6), (0, 3.6)]],
    "Q": [[(1, 7), (3, 7), (4, 6), (4, 1), (3, 0), (1, 0), (0, 1), (0, 6), (1, 7)],
          [(2.4, 1.6), (4.2, -0.4)]],
    "R": [[(0, 0), (0, 7), (3, 7), (4, 6), (4, 4.6), (3, 3.6), (0, 3.6)],
          [(2, 3.6), (4, 0)]],
    "S": [[(4, 6), (3, 7), (1, 7), (0, 6), (0, 4.6), (1, 3.6), (3, 3.6), (4, 2.6),
           (4, 1), (3, 0), (1, 0), (0, 1)]],
    "T": [[(0, 7), (4, 7)], [(2, 7), (2, 0)]],
    "U": [[(0, 7), (0, 1), (1, 0), (3, 0), (4, 1), (4, 7)]],
    "V": [[(0, 7), (2, 0), (4, 7)]],
    "W": [[(0, 7), (1, 0), (2, 3.8), (3, 0), (4, 7)]],
    "X": [[(0, 7), (4, 0)], [(0, 0), (4, 7)]],
    "Y": [[(0, 7), (2, 3.4), (4, 7)], [(2, 3.4), (2, 0)]],
    "Z": [[(0, 7), (4, 7), (0, 0), (4, 0)]],
    "-": [[(0.5, 3.5), (3.5, 3.5)]],
    "_": [[(0, -0.6), (4, -0.6)]],
    ".": [[(1.8, 0), (2.2, 0)]],
    ",": [[(2.2, 0.4), (1.6, -0.8)]],
    ":": [[(2, 1.4), (2, 1.8)], [(2, 4.6), (2, 5.0)]],
    "/": [[(0, 0), (4, 7)]],
    "\\": [[(0, 7), (4, 0)]],
    "+": [[(0.5, 3.5), (3.5, 3.5)], [(2, 1.7), (2, 5.3)]],
    "=": [[(0.5, 2.6), (3.5, 2.6)], [(0.5, 4.6), (3.5, 4.6)]],
    "#": [[(1, 0), (1.6, 7)], [(2.6, 0), (3.2, 7)], [(0.2, 2.2), (3.9, 2.2)],
          [(0.4, 4.8), (4.1, 4.8)]],
    "(": [[(3, 7), (1.5, 5), (1.5, 2), (3, 0)]],
    ")": [[(1, 7), (2.5, 5), (2.5, 2), (1, 0)]],
    "<": [[(3.5, 7), (0.5, 3.5), (3.5, 0)]],
    ">": [[(0.5, 7), (3.5, 3.5), (0.5, 0)]],
    "*": [[(2, 2), (2, 6)], [(0.4, 2.8), (3.6, 5.2)], [(0.4, 5.2), (3.6, 2.8)]],
    "?": [[(0, 6), (1, 7), (3, 7), (4, 6), (4, 4.6), (2, 3.4), (2, 1.6)],
          [(2, 0.4), (2, 0)]],
    "!": [[(2, 7), (2, 1.6)], [(2, 0.4), (2, 0)]],
    "%": [[(0, 0), (4, 7)], [(0.9, 6.9), (0.9, 5.1)], [(3.1, 1.9), (3.1, 0.1)]],
    "@": [[(3.4, 2), (2, 2), (2, 3.6), (3.4, 3.6), (3.4, 1), (1, 1), (0, 2.4),
           (0.6, 6), (3, 7), (4, 6.2)]],
}

#: caracteres que no conocemos se sustituyen por este
FALLBACK = "?"


def normalize_text(text: str) -> str:
    """Pasa a mayusculas y quita acentos para que todo tenga glifo."""
    replacements = {
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ü": "U", "Ñ": "N",
        "º": "O", "ª": "A",
    }
    out = []
    for ch in str(text).upper():
        ch = replacements.get(ch, ch)
        out.append(ch if ch in GLYPHS else FALLBACK)
    return "".join(out)


def line_width(line: str, size: float = CAP_HEIGHT) -> float:
    """Ancho de una linea de texto para una altura de mayuscula dada."""
    line = normalize_text(line)
    if not line:
        return 0.0
    scale = size / CAP_HEIGHT
    return (len(line) * ADVANCE + max(len(line) - 1, 0) * LETTER_GAP) * scale


def text_width(text: str, size: float = CAP_HEIGHT) -> float:
    """Ancho del texto completo (la linea mas larga si hay varias)."""
    return max((line_width(l, size) for l in str(text).split("\n")), default=0.0)


def text_height(text: str, size: float = CAP_HEIGHT) -> float:
    """Alto total del texto contando los saltos de linea."""
    lines = max(len(str(text).split("\n")), 1)
    return size * lines + LINE_GAP * (size / CAP_HEIGHT) * (lines - 1)


def text_size(text: str, size: float = CAP_HEIGHT):
    return text_width(text, size), text_height(text, size)


def text_polylines(text: str, size: float = CAP_HEIGHT) -> List[Polyline]:
    """Polilineas del texto, centradas en (0, 0). Soporta saltos de linea."""
    scale = size / CAP_HEIGHT
    lines = str(text).split("\n")
    step_y = (CAP_HEIGHT + LINE_GAP) * scale
    total_h = step_y * len(lines) - LINE_GAP * scale
    out: List[Polyline] = []
    for row, raw in enumerate(lines):
        line = normalize_text(raw)
        width = line_width(line, size)
        x0 = -width / 2.0
        y0 = total_h / 2.0 - step_y * row - CAP_HEIGHT * scale
        for i, ch in enumerate(line):
            ox = x0 + i * (ADVANCE + LETTER_GAP) * scale
            for poly in GLYPHS.get(ch, GLYPHS[FALLBACK]):
                out.append([(ox + px * scale, y0 + py * scale) for px, py in poly])
    return out


def text_polygons(text: str, size: float = CAP_HEIGHT, stroke: float = 1.0):
    """Devuelve el texto como poligono(s) 2D listos para extruir.

    El resultado esta centrado en el origen. `stroke` es el grosor del trazo.
    """
    stroke = max(float(stroke), 1e-3)
    parts = []
    for line in text_polylines(text, size):
        if len(line) < 2:
            continue
        geom = LineString(line).buffer(stroke / 2.0, cap_style=1, join_style=1,
                                       quad_segs=4)
        if not geom.is_empty:
            parts.append(geom)
        if len(line) == 2 and line[0] == line[1]:
            parts.append(Point(line[0]).buffer(stroke / 2.0, quad_segs=4))
    if not parts:
        return None
    merged = unary_union(parts)
    if isinstance(merged, Polygon):
        merged = MultiPolygon([merged])
    return merged


def available_characters() -> Sequence[str]:
    return tuple(sorted(GLYPHS))
