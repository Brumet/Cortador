"""Pasadores de alineacion (espigas y agujeros) en las caras de corte."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np
import trimesh
from shapely.geometry import MultiPolygon, Polygon, box as shapely_box
from shapely.ops import polylabel

from .config import JoineryOptions
from .geometry import EPS, boolean_op, largest_polygon, plane_transform


def pick_points(region,
                count: int,
                radius: float,
                margin: float) -> List[Tuple[float, float]]:
    """Elige puntos bien separados y con material alrededor dentro de la cara.

    `region` es el contorno comun a las dos piezas que comparten el corte,
    en coordenadas (u, v) del plano.
    """
    if region is None or region.is_empty or count <= 0:
        return []
    safe = region.buffer(-(float(radius) + float(margin)))
    if safe.is_empty:
        return []
    parts = list(safe.geoms) if isinstance(safe, MultiPolygon) else [safe]
    parts = [p for p in parts if isinstance(p, Polygon) and p.area > EPS]
    if not parts:
        return []

    points: List[Tuple[float, float]] = []
    # repartimos los pasadores entre las islas segun su area
    parts.sort(key=lambda p: p.area, reverse=True)
    total_area = sum(p.area for p in parts)
    quotas = []
    for part in parts:
        quotas.append(max(1, int(round(count * part.area / total_area))) if total_area > 0 else 1)
    while sum(quotas) > count and len(quotas) > 1:
        quotas[-1] -= 1
        if quotas[-1] <= 0:
            quotas.pop()
            parts.pop()

    for part, quota in zip(parts, quotas):
        points.extend(_points_in_polygon(part, quota))
    return points[:count]


def _points_in_polygon(poly: Polygon, count: int) -> List[Tuple[float, float]]:
    if count <= 0 or poly.is_empty:
        return []
    tol = max(poly.length / 400.0, 0.05)
    if count == 1:
        try:
            pt = polylabel(poly, tolerance=tol)
        except Exception:
            pt = poly.representative_point()
        return [(pt.x, pt.y)]

    minx, miny, maxx, maxy = poly.bounds
    horizontal = (maxx - minx) >= (maxy - miny)
    out: List[Tuple[float, float]] = []
    for i in range(count):
        t0, t1 = i / count, (i + 1) / count
        if horizontal:
            band = shapely_box(minx + (maxx - minx) * t0, miny,
                               minx + (maxx - minx) * t1, maxy)
        else:
            band = shapely_box(minx, miny + (maxy - miny) * t0,
                               maxx, miny + (maxy - miny) * t1)
        piece = poly.intersection(band)
        piece = largest_polygon(list(piece.geoms)) if hasattr(piece, "geoms") else piece
        if piece is None or piece.is_empty or piece.area <= EPS:
            continue
        try:
            pt = polylabel(piece, tolerance=tol)
        except Exception:
            pt = piece.representative_point()
        out.append((pt.x, pt.y))
    return out


def cylinder_at(axis: int,
                value: float,
                uv: Sequence[float],
                radius: float,
                z0: float,
                z1: float,
                sections: int = 24) -> trimesh.Trimesh:
    """Cilindro paralelo a `axis`, centrado en (u, v), entre value+z0 y value+z1."""
    height = float(z1) - float(z0)
    cyl = trimesh.creation.cylinder(radius=float(radius), height=abs(height),
                                    sections=sections)
    cyl.apply_translation([float(uv[0]), float(uv[1]), (z0 + z1) / 2.0])
    cyl.apply_transform(np.linalg.inv(plane_transform(axis, value)))
    return cyl


def hole_cylinder(axis: int, value: float, uv, sign: int,
                  opts: JoineryOptions, kerf: float = 0.0) -> trimesh.Trimesh:
    """Agujero ciego que entra en la pieza desde la cara (axis, sign)."""
    radius = opts.radius + opts.clearance
    over = 0.2 + kerf
    if sign > 0:
        z0, z1 = -opts.depth, over
    else:
        z0, z1 = -over, opts.depth
    return cylinder_at(axis, value, uv, radius, z0, z1)


def pin_cylinder(axis: int, value: float, uv, sign: int,
                 opts: JoineryOptions, kerf: float = 0.0) -> trimesh.Trimesh:
    """Espiga solidaria a la pieza que sobresale por la cara (axis, sign)."""
    radius = opts.radius
    anchor = max(opts.depth * 0.5, 1.0)  # parte que queda dentro de la pieza
    out = opts.depth + kerf
    if sign > 0:
        z0, z1 = -anchor, out
    else:
        z0, z1 = -out, anchor
    return cylinder_at(axis, value, uv, radius, z0, z1)


def dowel_mesh(opts: JoineryOptions, kerf: float = 0.0) -> trimesh.Trimesh:
    """Espiga suelta para imprimir aparte (modo 'holes')."""
    length = max(2 * opts.depth - 1.0 + kerf, 2.0)
    cyl = trimesh.creation.cylinder(radius=opts.radius, height=length, sections=32)
    cyl.apply_translation([0.0, 0.0, length / 2.0])
    return cyl


def apply_cutters(mesh: trimesh.Trimesh,
                  cutters: Sequence[trimesh.Trimesh],
                  op: str) -> Tuple[trimesh.Trimesh, Optional[str]]:
    """Aplica de una sola vez todos los cilindros de una pieza."""
    cutters = [c for c in cutters if c is not None and len(c.faces)]
    if not cutters:
        return mesh, None
    tool = trimesh.util.concatenate(cutters) if len(cutters) > 1 else cutters[0]
    result = boolean_op(op, mesh, tool)
    if result is None:
        if op == "union":
            return trimesh.util.concatenate([mesh, tool]), None
        return mesh, "no se pudieron perforar los alojamientos de las espigas"
    return result, None
