"""El logo de Brumet para las pantallas propias de la aplicacion.

El archivo del logo es el oficial de la marca y no se toca: solo cambia el
color de relleno segun el fondo, como dice el propio archivo. Aqui se lee y
se devuelve en linea para poder meterlo en las pantallas de espera, que se
muestran antes de que haya servidor que sirva archivos.
"""

from __future__ import annotations

import os
import re

ESTATICOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "static")
NEGRO = os.path.join(ESTATICOS, "brumet.svg")
BLANCO = os.path.join(ESTATICOS, "brumet-blanco.svg")

# por si el archivo no viaja con la app: el nombre, en texto, antes que nada
RESPALDO = '<span class="marca-texto">BRUMET</span>'


def logo(blanco: bool = True) -> str:
    """Devuelve el logo en linea, listo para incrustar en un HTML."""
    ruta = BLANCO if blanco else NEGRO
    try:
        with open(ruta, encoding="utf-8") as fh:
            svg = fh.read()
    except OSError:
        return RESPALDO
    svg = re.sub(r"<\?xml[^>]*\?>", "", svg).strip()
    if not svg.startswith("<svg"):
        return RESPALDO
    return svg
