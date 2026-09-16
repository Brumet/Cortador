"""Motor de corte: convierte una malla en piezas listas para imprimir."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import trimesh
from shapely.geometry import box as shapely_box

from .config import SliceConfig, axis_index
from .geometry import (EPS, clip_slab, extrude_polygons, largest_polygon,
                       merge_polygons, plane_transform, section_polygons)
from . import joinery as jn
from .labels import apply_label
from .meshio import apply_units_and_scale, is_empty, mesh_stats, weld_bodies
from .planner import CutPlan, plan_cuts

Progress = Optional[Callable[[int, int, str], None]]

FACES = [(0, -1), (0, 1), (1, -1), (1, 1), (2, -1), (2, 1)]


@dataclass
class Piece:
    """Una pieza del despiece."""

    name: str
    index: Tuple[int, int, int]
    layer: int
    mesh: trimesh.Trimesh
    cell_lo: np.ndarray
    cell_hi: np.ndarray
    neighbors: Dict[str, str] = field(default_factory=dict)
    outline: object = None          # contorno 2D (modo lamina) para laser/CNC
    outline_axis: int = 2
    label_text: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def size(self) -> np.ndarray:
        return self.mesh.extents

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "index": [int(v) for v in self.index],
            "layer": int(self.layer),
            "label": self.label_text,
            "size": [round(float(v), 3) for v in self.size],
            "bounds": [[round(float(v), 3) for v in self.mesh.bounds[0]],
                       [round(float(v), 3) for v in self.mesh.bounds[1]]],
            "volume_cm3": round(float(self.mesh.volume) / 1000.0, 3) if self.mesh.is_volume else None,
            "triangles": int(len(self.mesh.faces)),
            "neighbors": dict(self.neighbors),
            "notes": list(self.notes),
        }


@dataclass
class SliceResult:
    pieces: List[Piece]
    plan: CutPlan
    config: SliceConfig
    source: dict
    warnings: List[str] = field(default_factory=list)
    dowels: int = 0

    @property
    def count(self) -> int:
        return len(self.pieces)

    def oversized(self) -> List[Piece]:
        return [p for p in self.pieces if not self.config.printer.fits(p.size)]

    def manifest(self) -> dict:
        return {
            "generador": "Cortador",
            "modelo": self.source,
            "configuracion": self.config.to_dict(),
            "plan": self.plan.to_dict(),
            "piezas": [p.to_dict() for p in self.pieces],
            "total_piezas": self.count,
            "espigas": self.dowels,
            "piezas_fuera_de_capacidad": [p.name for p in self.oversized()],
            "avisos": list(self.warnings),
        }


def slice_model(mesh: trimesh.Trimesh,
                cfg: SliceConfig,
                progress: Progress = None) -> SliceResult:
    """Corta el modelo segun la configuracion y devuelve todas las piezas."""
    cfg.validate()
    source_stats = mesh_stats(mesh)
    work = apply_units_and_scale(mesh, cfg.units, cfg.scale, cfg.target_size, cfg.target_axis)
    bodies = int(work.body_count)
    if cfg.weld and bodies > 1:
        welded = weld_bodies(work)
        if welded is not work:
            work = welded
    prepared_stats = mesh_stats(work)
    plan = plan_cuts(work.bounds, cfg)
    warnings = list(plan.warnings)
    if cfg.weld and bodies > 1:
        warnings.append(
            f"El modelo tenia {bodies} cuerpos sueltos o superpuestos: se han "
            "fundido en un solido antes de cortar."
        )
    if not work.is_watertight:
        warnings.append(
            "La malla de entrada no es estanca; los cortes pueden dejar caras "
            "abiertas. Repara el modelo si el resultado no imprime bien."
        )

    def report(done: int, total: int, msg: str) -> None:
        if progress:
            progress(done, total, msg)

    total_steps = plan.total_cells
    report(0, total_steps, "Cortando")

    if cfg.mode == "slabs" and cfg.slab_style == "prism":
        raw = _build_prisms(work, plan, cfg, report)
    else:
        raw = _build_chunks(work, plan, cfg, report)

    pieces: List[Piece] = []
    by_index: Dict[Tuple[int, int, int], Piece] = {}
    for index, piece_mesh, outline in raw:
        if piece_mesh is None or is_empty(piece_mesh):
            continue
        lo, hi = plan.cell_bounds(index)
        piece = Piece(
            name=plan.name_for(index, cfg.naming),
            index=index,
            layer=plan.layer_of(index),
            mesh=piece_mesh,
            cell_lo=lo,
            cell_hi=hi,
            outline=outline,
            outline_axis=plan.layer_axis,
        )
        pieces.append(piece)
        by_index[index] = piece

    _link_neighbors(pieces, by_index, plan)

    dowels = 0
    if cfg.joinery.mode != "none" and len(pieces) > 1:
        report(0, len(pieces), "Colocando pasadores")
        dowels = _apply_joinery(pieces, by_index, plan, cfg, report)

    if cfg.labels.enabled and len(pieces) >= 1:
        report(0, len(pieces), "Marcando piezas")
        _apply_labels(pieces, plan, cfg, report)

    result = SliceResult(pieces=pieces, plan=plan, config=cfg,
                         source={"original": source_stats, "escalado": prepared_stats},
                         warnings=warnings, dowels=dowels)
    over = result.oversized()
    if over:
        result.warnings.append(
            f"{len(over)} pieza(s) siguen sin caber en la maquina: "
            + ", ".join(p.name for p in over[:8]) + ("..." if len(over) > 8 else "")
        )
    if not pieces:
        result.warnings.append("El corte no ha producido ninguna pieza.")
    return result


# ---------------------------------------------------------------------------
# construccion de piezas
# ---------------------------------------------------------------------------

def _build_chunks(mesh: trimesh.Trimesh,
                  plan: CutPlan,
                  cfg: SliceConfig,
                  report) -> List[Tuple[Tuple[int, int, int], trimesh.Trimesh, object]]:
    """Corta en trozos reales, eje por eje, reutilizando el resto de cada corte.

    Cortar primero en bandas y luego subdividirlas es mucho mas rapido que
    recortar la malla completa contra cada celda.
    """
    out = []
    done = 0
    total = plan.total_cells
    bands_x = _split_axis(mesh, plan, 0, cfg)
    for i, band_x in bands_x:
        if band_x is None:
            done += plan.counts[1] * plan.counts[2]
            report(done, total, "Cortando")
            continue
        for j, band_y in _split_axis(band_x, plan, 1, cfg):
            if band_y is None:
                done += plan.counts[2]
                report(done, total, "Cortando")
                continue
            for k, cell in _split_axis(band_y, plan, 2, cfg):
                done += 1
                if cell is not None:
                    out.append(((i, j, k), cell, None))
                report(done, total, "Cortando")
    return out


def _split_axis(mesh: Optional[trimesh.Trimesh],
                plan: CutPlan,
                axis: int,
                cfg: SliceConfig):
    """Trocea una malla a lo largo de un eje devolviendo (indice, trozo)."""
    count = plan.counts[axis]
    if mesh is None:
        return [(i, None) for i in range(count)]
    if count == 1 and plan.kerf <= 0:
        return [(0, mesh)]

    edges = plan.edges[axis]
    half = plan.kerf / 2.0
    rest = mesh
    out = []
    for i in range(count):
        lo = edges[i] + (half if i > 0 else 0.0)
        hi = edges[i + 1] - (half if i < count - 1 else 0.0)
        if rest is None:
            out.append((i, None))
            continue
        if i == count - 1:
            # el resto ya esta cortado por abajo; solo hay que aplicar el kerf
            piece = clip_slab(rest, axis, lo, hi, cfg.engine) if half > 0 else rest
            out.append((i, piece))
            break
        piece = clip_slab(rest, axis, lo, hi, cfg.engine)
        out.append((i, piece))
        rest = clip_slab(rest, axis, edges[i + 1], float(plan.bounds[1][axis]) + 1.0, cfg.engine)
    while len(out) < count:
        out.append((len(out), None))
    return out


def _build_prisms(mesh: trimesh.Trimesh,
                  plan: CutPlan,
                  cfg: SliceConfig,
                  report) -> List[Tuple[Tuple[int, int, int], trimesh.Trimesh, object]]:
    """Modo lamina plana: seccion en el centro de la lamina y extrusion.

    Es la forma clasica de construir por capas con laser o CNC: cada lamina es
    una placa de espesor constante con el contorno del modelo.
    """
    axis = plan.layer_axis
    others = [a for a in range(3) if a != axis]
    out = []
    total = plan.total_cells
    done = 0
    half = plan.kerf / 2.0
    layers = plan.counts[axis]

    for k in range(layers):
        z_lo = plan.edges[axis][k] + (half if k > 0 else 0.0)
        z_hi = plan.edges[axis][k + 1] - (half if k < layers - 1 else 0.0)
        mid = (z_lo + z_hi) / 2.0
        height = max(z_hi - z_lo, EPS)
        merged = merge_polygons(section_polygons(mesh, axis, mid))
        if merged is None:
            done += plan.counts[others[0]] * plan.counts[others[1]]
            report(done, total, "Generando laminas")
            continue
        for a in range(plan.counts[others[0]]):
            for b in range(plan.counts[others[1]]):
                index = [0, 0, 0]
                index[axis] = k
                index[others[0]] = a
                index[others[1]] = b
                index = tuple(index)
                done += 1
                lo, hi = plan.cell_bounds(index)
                u, v = (axis + 1) % 3, (axis + 2) % 3
                rect = shapely_box(lo[u], lo[v], hi[u], hi[v])
                region = merged.intersection(rect)
                if region.is_empty or region.area <= EPS:
                    report(done, total, "Generando laminas")
                    continue
                solid = extrude_polygons(region, height)
                if solid is None:
                    report(done, total, "Generando laminas")
                    continue
                # extrude_polygon trabaja en XY: lo llevamos al plano real
                solid.apply_transform(np.linalg.inv(plane_transform(axis, z_lo)))
                out.append((index, solid, region))
                report(done, total, "Generando laminas")
    return out


# ---------------------------------------------------------------------------
# vecinos, pasadores y marcas
# ---------------------------------------------------------------------------

def _face_key(axis: int, sign: int) -> str:
    return ("+" if sign > 0 else "-") + "xyz"[axis]


def _link_neighbors(pieces: Sequence[Piece],
                    by_index: Dict[Tuple[int, int, int], Piece],
                    plan: CutPlan) -> None:
    for piece in pieces:
        for axis, sign in FACES:
            nb_index = plan.neighbor(piece.index, axis, sign)
            if nb_index is None:
                continue
            nb = by_index.get(nb_index)
            if nb is not None:
                piece.neighbors[_face_key(axis, sign)] = nb.name


def _face_value(piece: Piece, axis: int, sign: int) -> float:
    return float(piece.cell_hi[axis] if sign > 0 else piece.cell_lo[axis])


def _apply_joinery(pieces: Sequence[Piece],
                   by_index: Dict[Tuple[int, int, int], Piece],
                   plan: CutPlan,
                   cfg: SliceConfig,
                   report) -> int:
    opts = cfg.joinery
    cutters: Dict[str, Dict[str, List[trimesh.Trimesh]]] = {
        p.name: {"difference": [], "union": []} for p in pieces
    }
    dowels = 0

    for piece in pieces:
        for axis, sign in FACES:
            if sign < 0:
                continue  # tratamos cada corte una sola vez, desde la cara +
            nb_index = plan.neighbor(piece.index, axis, sign)
            if nb_index is None:
                continue
            nb = by_index.get(nb_index)
            if nb is None:
                continue
            value_a = _face_value(piece, axis, +1)
            value_b = _face_value(nb, axis, -1)
            region_a = largest_polygon(section_polygons(piece.mesh, axis, value_a - 0.1))
            region_b = largest_polygon(section_polygons(nb.mesh, axis, value_b + 0.1))
            if region_a is None or region_b is None:
                continue
            common = region_a.intersection(region_b)
            common = largest_polygon(list(common.geoms)) if hasattr(common, "geoms") else common
            if common is None or common.is_empty:
                continue
            points = jn.pick_points(common, opts.count, opts.radius + opts.clearance,
                                    opts.margin)
            if not points:
                piece.notes.append(
                    f"cara {_face_key(axis, sign)} demasiado estrecha para pasadores")
                continue
            for uv in points:
                if opts.mode == "holes":
                    cutters[piece.name]["difference"].append(
                        jn.hole_cylinder(axis, value_a, uv, +1, opts, plan.kerf))
                    cutters[nb.name]["difference"].append(
                        jn.hole_cylinder(axis, value_b, uv, -1, opts, plan.kerf))
                    dowels += 1
                else:  # pins
                    cutters[piece.name]["union"].append(
                        jn.pin_cylinder(axis, value_a, uv, +1, opts, plan.kerf))
                    cutters[nb.name]["difference"].append(
                        jn.hole_cylinder(axis, value_b, uv, -1, opts, plan.kerf))

    done = 0
    for piece in pieces:
        done += 1
        sets = cutters[piece.name]
        if sets["union"]:
            piece.mesh, note = jn.apply_cutters(piece.mesh, sets["union"], "union")
            if note:
                piece.notes.append(note)
        if sets["difference"]:
            piece.mesh, note = jn.apply_cutters(piece.mesh, sets["difference"], "difference")
            if note:
                piece.notes.append(note)
        report(done, len(pieces), "Colocando pasadores")
    return dowels


def _apply_labels(pieces: Sequence[Piece],
                  plan: CutPlan,
                  cfg: SliceConfig,
                  report) -> None:
    opts = cfg.labels
    prefix = (opts.prefix or "").strip()
    done = 0
    for piece in pieces:
        done += 1
        base = f"{prefix}{piece.name}" if prefix else piece.name
        piece.label_text = base
        targets = _label_targets(piece, plan, cfg)
        for axis, sign, value in targets:
            text = base
            if opts.placement == "cuts" and opts.with_neighbor:
                nb = piece.neighbors.get(_face_key(axis, sign))
                if nb:
                    text = f"{base}>{nb}"
            piece.mesh, note = apply_label(piece.mesh, text, axis, sign, value, opts)
            if note:
                piece.notes.append(note)
        report(done, len(pieces), "Marcando piezas")


def _label_targets(piece: Piece,
                   plan: CutPlan,
                   cfg: SliceConfig) -> List[Tuple[int, int, float]]:
    """Caras donde escribir: preferimos las de corte (quedan ocultas al armar)."""
    opts = cfg.labels
    interior = [(axis, sign) for axis, sign in FACES
                if plan.is_interior_face(piece.index, axis, sign)]

    if opts.placement == "cuts" and interior:
        scored = [(axis, sign, _face_value(piece, axis, sign)) for axis, sign in interior]
        return scored[: max(1, opts.max_faces)]

    if opts.placement == "bottom":
        return [(2, -1, float(piece.mesh.bounds[0][2]))]

    best = None
    best_area = 0.0
    candidates = interior if interior else FACES
    for axis, sign in candidates:
        if interior:
            value = _face_value(piece, axis, sign)
        else:
            value = float(piece.mesh.bounds[1][axis] if sign > 0 else piece.mesh.bounds[0][axis])
        polys = section_polygons(piece.mesh, axis, value - sign * 0.1)
        area = float(sum(p.area for p in polys))
        if area > best_area:
            best_area = area
            best = (axis, sign, value)
    if best is None:
        return [(2, -1, float(piece.mesh.bounds[0][2]))]
    return [best]
