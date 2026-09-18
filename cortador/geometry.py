"""Operaciones geometricas de bajo nivel: recortes por caja y secciones."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np
import trimesh
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from .meshio import is_empty

EPS = 1e-7


def unit(axis: int) -> np.ndarray:
    v = np.zeros(3)
    v[axis] = 1.0
    return v


def plane_frame(axis: int) -> Tuple[int, int]:
    """Ejes (u, v) del plano perpendicular a `axis`, en orden dextrogiro."""
    return (axis + 1) % 3, (axis + 2) % 3


def plane_transform(axis: int, value: float) -> np.ndarray:
    """Matriz 4x4 que lleva el plano axis=value al plano XY (coordenadas u, v)."""
    u, v = plane_frame(axis)
    T = np.zeros((4, 4))
    T[0, u] = 1.0
    T[1, v] = 1.0
    T[2, axis] = 1.0
    T[2, 3] = -float(value)
    T[3, 3] = 1.0
    return T


def to_world(axis: int, points_uv: Sequence[Sequence[float]], value: float) -> np.ndarray:
    """Pasa puntos (u, v) del plano a coordenadas del mundo."""
    u, v = plane_frame(axis)
    pts = np.atleast_2d(np.asarray(points_uv, dtype=float))
    out = np.zeros((len(pts), 3))
    out[:, u] = pts[:, 0]
    out[:, v] = pts[:, 1]
    out[:, axis] = float(value)
    return out


def box_mesh(lo: Sequence[float], hi: Sequence[float]) -> trimesh.Trimesh:
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    extents = np.maximum(hi - lo, EPS)
    box = trimesh.creation.box(extents=extents)
    box.apply_translation((lo + hi) / 2.0)
    return box


def boxes_overlap(bounds: np.ndarray, lo: Sequence[float], hi: Sequence[float]) -> bool:
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    return bool(np.all(bounds[0] <= hi + EPS) and np.all(bounds[1] >= lo - EPS))


def clip_to_box(mesh: trimesh.Trimesh,
                lo: Sequence[float],
                hi: Sequence[float],
                engine: str = "auto") -> Optional[trimesh.Trimesh]:
    """Recorta la malla a la caja [lo, hi]. Devuelve None si no queda nada.

    'slice'   corta con seis planos y tapa las caras (rapido, tolerante con
              mallas imperfectas).
    'boolean' interseca con una caja usando CSG (mas lento, mas exacto en
              mallas complejas).
    'auto'    intenta el corte por planos y recurre al booleano si falla.
    """
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    if not boxes_overlap(mesh.bounds, lo, hi):
        return None

    if engine == "boolean":
        return _clip_boolean(mesh, lo, hi)

    result = _clip_slice(mesh, lo, hi)
    if engine == "slice":
        return result
    # el corte por planos es rapido pero puede dejar caras abiertas en mallas
    # con auto-intersecciones: en ese caso repetimos el recorte con CSG
    broken = result is not None and sin_bordes(mesh) and not sin_bordes(result)
    if result is None or is_empty(result) or broken:
        fallback = _clip_boolean(mesh, lo, hi)
        if fallback is not None:
            return fallback
    return result


def sin_bordes(mesh: trimesh.Trimesh) -> bool:
    """True si la malla no tiene agujeros, aunque no sea perfecta.

    `is_watertight` es mas estricto de lo que hace falta aqui: basta una
    membrana de espesor cero -dos caras que se tocan, cosa normal en una piel
    vaciada de un escaneo- para que diga que no. Cuando eso pasaba, el recorte
    rapido por planos se daba por bueno aunque hubiera dejado la pieza abierta,
    y de ahi salian los trozos rotos. Lo que hay que mirar para decidir si se
    repite el corte con CSG es solo si quedan bordes sueltos.
    """
    try:
        if mesh.is_watertight:
            return True
        aristas = mesh.edges_sorted
        if len(aristas) == 0:
            return False
        return len(trimesh.grouping.group_rows(aristas, require_count=1)) == 0
    except Exception:
        return False


def _clip_slice(mesh: trimesh.Trimesh,
                lo: np.ndarray,
                hi: np.ndarray) -> Optional[trimesh.Trimesh]:
    from trimesh.intersections import slice_mesh_plane

    current = mesh
    for axis in range(3):
        for sign, value in ((1.0, lo[axis]), (-1.0, hi[axis])):
            bounds = current.bounds
            if sign > 0 and bounds[0][axis] >= value - EPS:
                continue  # la malla ya esta entera del lado bueno
            if sign < 0 and bounds[1][axis] <= value + EPS:
                continue
            normal = unit(axis) * sign
            origin = np.zeros(3)
            origin[axis] = value
            try:
                current = slice_mesh_plane(current, normal, origin, cap=True)
            except Exception:
                return None
            if current is None or len(current.faces) == 0:
                return None
    if is_empty(current):
        return None
    out = current.copy()
    out.merge_vertices()
    out.remove_unreferenced_vertices()
    return out


def _clip_boolean(mesh: trimesh.Trimesh,
                  lo: np.ndarray,
                  hi: np.ndarray) -> Optional[trimesh.Trimesh]:
    try:
        result = trimesh.boolean.intersection([mesh, box_mesh(lo, hi)])
    except Exception:
        return None
    if isinstance(result, list):
        result = trimesh.util.concatenate(result) if result else None
    if result is None or is_empty(result):
        return None
    return result


def boolean_op(op: str, a: trimesh.Trimesh, b: trimesh.Trimesh) -> Optional[trimesh.Trimesh]:
    """Diferencia o union tolerante a fallos (devuelve None si el motor falla)."""
    fn = {"difference": trimesh.boolean.difference,
          "union": trimesh.boolean.union,
          "intersection": trimesh.boolean.intersection}[op]
    try:
        result = fn([a, b])
    except Exception:
        return None
    if isinstance(result, list):
        result = trimesh.util.concatenate(result) if result else None
    if result is None or is_empty(result):
        return None
    return result


def section_polygons(mesh: trimesh.Trimesh,
                     axis: int,
                     value: float) -> List[Polygon]:
    """Contorno cerrado de la malla en el plano axis=value, en coordenadas (u, v)."""
    origin = np.zeros(3)
    origin[axis] = float(value)
    try:
        section = mesh.section(plane_origin=origin, plane_normal=unit(axis))
    except Exception:
        section = None
    if section is None:
        return []
    try:
        planar, _ = section.to_2D(to_2D=plane_transform(axis, value))
    except Exception:
        return []
    try:
        polygons = list(planar.polygons_full)
    except Exception:
        # trimesh necesita rtree para anidar contornos; si falta, lo hacemos aqui
        polygons = polygons_from_loops(getattr(planar, "discrete", []))
    return [p for p in polygons if p is not None and not p.is_empty and p.area > EPS]


def polygons_from_loops(loops) -> List[Polygon]:
    """Reconstruye poligonos con agujeros a partir de contornos cerrados."""
    shells = []
    for loop in loops:
        pts = np.asarray(loop, dtype=float)
        if len(pts) < 3:
            continue
        try:
            poly = Polygon(pts[:, :2])
        except Exception:
            continue
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.area <= EPS:
            continue
        if isinstance(poly, Polygon):
            shells.append(poly)
        else:
            shells.extend(g for g in poly.geoms if isinstance(g, Polygon))

    shells.sort(key=lambda p: p.area, reverse=True)
    result: List[Polygon] = []
    consumed = set()
    for i, outer in enumerate(shells):
        if i in consumed:
            continue
        holes = []
        for j in range(i + 1, len(shells)):
            if j in consumed:
                continue
            inner = shells[j]
            if outer.contains(inner.representative_point()):
                holes.append(inner.exterior.coords)
                consumed.add(j)
        result.append(Polygon(outer.exterior.coords, holes) if holes else outer)
    return result


def section_area(mesh: trimesh.Trimesh, axis: int, value: float) -> float:
    return float(sum(p.area for p in section_polygons(mesh, axis, value)))


def merge_polygons(polygons: Sequence[Polygon]):
    polygons = [p for p in polygons if p is not None and not p.is_empty]
    if not polygons:
        return None
    merged = unary_union(polygons)
    if merged.is_empty:
        return None
    if isinstance(merged, Polygon):
        merged = MultiPolygon([merged])
    return merged


def largest_polygon(polygons: Sequence[Polygon]) -> Optional[Polygon]:
    polygons = [p for p in polygons if p is not None and not p.is_empty]
    if not polygons:
        return None
    return max(polygons, key=lambda p: p.area)


def extrude_polygons(geom, height: float) -> Optional[trimesh.Trimesh]:
    """Extruye un poligono/multipoligono shapely a lo largo de +Z."""
    if geom is None or height <= 0:
        return None
    polys = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    meshes = []
    for poly in polys:
        if poly.is_empty or poly.area <= EPS:
            continue
        try:
            meshes.append(trimesh.creation.extrude_polygon(poly, float(height)))
        except Exception:
            continue
    if not meshes:
        return None
    return trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]


def clip_slab(mesh: trimesh.Trimesh,
              axis: int,
              lo: float,
              hi: float,
              engine: str = "auto") -> Optional[trimesh.Trimesh]:
    """Recorta la malla entre dos planos perpendiculares a `axis`."""
    pad = float(np.max(mesh.extents)) + 10.0
    box_lo = mesh.bounds[0] - pad
    box_hi = mesh.bounds[1] + pad
    box_lo[axis] = float(lo)
    box_hi[axis] = float(hi)
    return clip_to_box(mesh, box_lo, box_hi, engine=engine)
