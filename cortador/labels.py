"""Marcado de piezas: graba o realza texto sobre una cara de la pieza."""

from __future__ import annotations

import math
from typing import Optional, Tuple

import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import Polygon, box as shapely_box
from shapely.ops import polylabel

from .config import LabelOptions
from .font import CAP_HEIGHT, text_polygons, text_size
from .geometry import (EPS, boolean_op, extrude_polygons, largest_polygon,
                       merge_polygons, plane_transform, section_polygons)

MIN_SIZE = 1.0  # altura minima de letra util (mm)


def label_region(mesh: trimesh.Trimesh,
                 axis: int,
                 sign: int,
                 value: float,
                 inset: float = 0.05) -> Optional[Polygon]:
    """Contorno de la cara donde queremos escribir, en coordenadas (u, v).

    Se secciona un poco por dentro de la cara para no caer en el plano exacto
    (que suele ser degenerado) y se queda con el contorno mas grande.
    """
    probe = float(value) - float(sign) * float(inset)
    polys = section_polygons(mesh, axis, probe)
    if not polys:
        polys = section_polygons(mesh, axis, float(value) - float(sign) * inset * 10)
    return largest_polygon(polys)


def _dentro(region, x: float, y: float) -> bool:
    from shapely.geometry import Point
    return region.contains(Point(x, y))


def _alcance(region, cx: float, cy: float, dx: float, dy: float,
             limite: float) -> float:
    """Cuanto se puede avanzar desde (cx, cy) en una direccion sin salirse."""
    lejos, cerca = limite, 0.0
    for _ in range(12):
        medio = (lejos + cerca) / 2.0
        if _dentro(region, cx + dx * medio, cy + dy * medio):
            cerca = medio
        else:
            lejos = medio
    return cerca


def _mejor_orientacion(region, cx: float, cy: float, pasos: int = 18):
    """Angulo en el que mas texto cabe, y el hueco perpendicular disponible.

    En una lamina hueca la pared es un anillo estrecho: el texto solo entra si
    se escribe siguiendo la pared, no cruzandola. Esto busca esa direccion.
    """
    minx, miny, maxx, maxy = region.bounds
    limite = max(maxx - minx, maxy - miny)
    mejor = (0.0, 0.0, 0.0)
    for i in range(pasos):
        ang = math.pi * i / pasos
        dx, dy = math.cos(ang), math.sin(ang)
        largo = (_alcance(region, cx, cy, dx, dy, limite)
                 + _alcance(region, cx, cy, -dx, -dy, limite))
        if largo > mejor[1]:
            ancho = (_alcance(region, cx, cy, -dy, dx, limite)
                     + _alcance(region, cx, cy, dy, -dx, limite))
            mejor = (ang, largo, ancho)
    return mejor


def fit_text(text: str,
             region: Polygon,
             opts: LabelOptions,
             mirror: bool = False):
    """Ajusta el texto dentro de la region disponible.

    Devuelve (geometria 2D centrada en su sitio, altura de letra usada) o None
    si la cara es demasiado pequena para escribir algo legible.
    """
    if region is None or region.is_empty:
        return None
    # margen minimo: en una lamina hueca la pared puede tener 3 mm y no hay
    # sitio que malgastar; que el texto quepa lo decide la comprobacion final
    margin = 0.2
    usable = region.buffer(-margin)
    if usable.is_empty:
        usable = region
    anchor = largest_polygon(list(usable.geoms)) if hasattr(usable, "geoms") else usable
    if anchor is None or anchor.is_empty:
        return None

    try:
        center_pt = polylabel(anchor, tolerance=max(anchor.length / 400.0, 0.05))
    except Exception:
        center_pt = anchor.representative_point()
    cx, cy = center_pt.x, center_pt.y

    # direccion en la que cabe mas texto (clave en las piezas huecas)
    angulo, largo, ancho = _mejor_orientacion(anchor, cx, cy)
    grados = math.degrees(angulo)

    size = float(opts.size)
    for _ in range(22):
        if size < MIN_SIZE:
            return None
        stroke = max(opts.stroke * size / max(opts.size, EPS), 0.15)
        width, height = text_size(text, size)
        if width + stroke <= largo and height + stroke <= ancho:
            geom = text_polygons(text, size=size, stroke=stroke)
            if geom is None:
                return None
            if mirror:
                geom = affinity.scale(geom, xfact=-1.0, yfact=1.0, origin=(0, 0))
            if abs(grados) > 1.0:
                geom = affinity.rotate(geom, grados, origin=(0, 0))
            geom = affinity.translate(geom, xoff=cx, yoff=cy)
            recortado = geom.intersection(anchor)
            if recortado.is_empty:
                return None
            if recortado.area < geom.area * 0.97:
                size *= 0.85          # se sale por los bordes: probar mas pequeno
                continue
            return recortado, size
        size *= 0.85
    return None


def build_text_prism(geom2d,
                     axis: int,
                     sign: int,
                     value: float,
                     depth: float,
                     style: str = "engrave") -> Optional[trimesh.Trimesh]:
    """Convierte el texto 2D en un solido colocado sobre la cara indicada."""
    depth = max(float(depth), 0.05)
    over = max(depth * 0.25, 0.2)      # sobresale para garantizar el corte
    embed = max(depth * 0.25, 0.2)     # se hunde para que suelde bien el relieve
    if style == "engrave":
        height = depth + over
        z0 = -depth if sign > 0 else -over
    else:
        height = depth + embed
        z0 = -embed if sign > 0 else -depth

    prism = extrude_polygons(geom2d, height)
    if prism is None:
        return None
    prism.apply_translation([0.0, 0.0, z0])
    prism.apply_transform(np.linalg.inv(plane_transform(axis, value)))
    return prism


def apply_label(mesh: trimesh.Trimesh,
                text: str,
                axis: int,
                sign: int,
                value: float,
                opts: LabelOptions) -> Tuple[trimesh.Trimesh, Optional[str]]:
    """Marca `text` sobre la cara (axis, sign) de la pieza.

    Devuelve la malla marcada y un aviso cuando no se ha podido marcar.
    """
    text = (text or "").strip()
    if not text:
        return mesh, None
    region = label_region(mesh, axis, sign, value)
    if region is None:
        return mesh, f"sin contorno para marcar en {'xyz'[axis]}{'+' if sign > 0 else '-'}"
    fitted = None
    for candidato in _variantes(text):
        fitted = fit_text(candidato, region, opts, mirror=(sign < 0))
        if fitted is not None:
            break
    if fitted is None:
        return mesh, f"la cara es demasiado pequena para la marca '{text}'"
    geom2d, _used = fitted
    prism = build_text_prism(geom2d, axis, sign, value, opts.depth, opts.style)
    if prism is None:
        return mesh, f"no se pudo construir la marca '{text}'"

    op = "difference" if opts.style == "engrave" else "union"
    result = boolean_op(op, mesh, prism)
    if result is None:
        if opts.style == "emboss":
            # ultimo recurso: dejar el relieve como geometria pegada
            return trimesh.util.concatenate([mesh, prism]), None
        return mesh, f"el motor booleano fallo al grabar '{text}'"
    return result, None


def _variantes(text: str):
    """El texto tal cual y, si es largo, partido en dos lineas.

    Una marca como 'B1-L03>C1-L03' no entra en una cara estrecha en una sola
    linea, pero si en dos.
    """
    yield text
    if "\n" in text or len(text) < 6:
        return
    for sep in (">", "-"):
        corte = text.rfind(sep, 1, len(text) - 1)
        if corte > 0:
            yield text[:corte] + "\n" + text[corte:]
            return


def text_preview_svg(text: str, size: float = 10.0, stroke: float = 1.5) -> str:
    """SVG del texto (util para comprobar la tipografia o para el corte laser)."""
    geom = text_polygons(text, size=size, stroke=stroke)
    if geom is None:
        return "<svg xmlns='http://www.w3.org/2000/svg'/>"
    minx, miny, maxx, maxy = geom.bounds
    paths = []
    for poly in (geom.geoms if hasattr(geom, "geoms") else [geom]):
        rings = [poly.exterior] + list(poly.interiors)
        d = " ".join(
            "M " + " L ".join(f"{x:.3f},{(maxy + miny - y):.3f}" for x, y in ring.coords) + " Z"
            for ring in rings
        )
        paths.append(f"<path d='{d}' fill='black' fill-rule='evenodd'/>")
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='{minx:.3f} {miny:.3f} "
        f"{maxx - minx:.3f} {maxy - miny:.3f}'>" + "".join(paths) + "</svg>"
    )
