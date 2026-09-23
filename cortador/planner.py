"""Calculo del plan de corte: donde van los planos y como se llama cada pieza."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .config import SliceConfig, axis_index


def column_letters(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA (como las columnas de una hoja de calculo)."""
    index = int(index)
    out = ""
    while True:
        out = chr(ord("A") + index % 26) + out
        index = index // 26 - 1
        if index < 0:
            return out


def _even_edges(lo: float, hi: float, count: int) -> np.ndarray:
    return np.linspace(float(lo), float(hi), int(count) + 1)


def _fixed_edges(lo: float, hi: float, step: float, fit: str = "exact") -> np.ndarray:
    span = float(hi) - float(lo)
    if step <= 0:
        raise ValueError("El espesor debe ser mayor que cero")
    count = max(1, int(math.ceil(span / step - 1e-9)))
    if fit == "even":
        return _even_edges(lo, hi, count)
    edges = [lo + i * step for i in range(count)]
    edges.append(hi)
    if len(edges) > 1 and edges[-1] - edges[-2] < step * 1e-6:
        edges.pop(-2)
    return np.asarray(edges, dtype=float)


@dataclass
class CutPlan:
    """Rejilla de corte resultante de aplicar la configuracion a un modelo."""

    bounds: np.ndarray
    edges: List[np.ndarray]
    layer_axis: int = 2
    mode: str = "chunks"
    kerf: float = 0.0
    warnings: List[str] = field(default_factory=list)

    @property
    def counts(self) -> Tuple[int, int, int]:
        return tuple(int(len(e) - 1) for e in self.edges)

    @property
    def total_cells(self) -> int:
        nx, ny, nz = self.counts
        return nx * ny * nz

    def cell_indices(self):
        nx, ny, nz = self.counts
        for k in range(nz):
            for j in range(ny):
                for i in range(nx):
                    yield (i, j, k)

    def cell_bounds(self, index: Sequence[int], apply_kerf: bool = True):
        """Caja de la celda. El kerf se descuenta solo en las caras interiores."""
        lo = np.empty(3)
        hi = np.empty(3)
        half = float(self.kerf) / 2.0 if apply_kerf else 0.0
        counts = self.counts
        for axis in range(3):
            i = int(index[axis])
            lo[axis] = self.edges[axis][i]
            hi[axis] = self.edges[axis][i + 1]
            if half > 0:
                if i > 0:
                    lo[axis] += half
                if i < counts[axis] - 1:
                    hi[axis] -= half
        return lo, hi

    def cell_size(self, index: Sequence[int]) -> np.ndarray:
        lo, hi = self.cell_bounds(index)
        return hi - lo

    def is_interior_face(self, index: Sequence[int], axis: int, sign: int) -> bool:
        """True si esa cara nace de un corte (y por tanto tiene pieza vecina)."""
        counts = self.counts
        i = int(index[axis])
        return (sign < 0 and i > 0) or (sign > 0 and i < counts[axis] - 1)

    def neighbor(self, index: Sequence[int], axis: int, sign: int) -> Optional[Tuple[int, int, int]]:
        if not self.is_interior_face(index, axis, sign):
            return None
        nb = list(int(v) for v in index)
        nb[axis] += 1 if sign > 0 else -1
        return tuple(nb)

    # -- nomenclatura ---------------------------------------------------
    def name_for(self, index: Sequence[int], naming: str = "grid") -> str:
        counts = self.counts
        if naming == "numeric":
            return "X{:02d}Y{:02d}Z{:02d}".format(index[0] + 1, index[1] + 1, index[2] + 1)
        layer = self.layer_axis
        others = [a for a in range(3) if a != layer]
        col, row = others[0], others[1]
        parts = []
        if counts[col] > 1:
            parts.append(column_letters(index[col]))
        if counts[row] > 1:
            parts.append(str(index[row] + 1))
        head = "".join(parts)
        tail = "L{:02d}".format(index[layer] + 1) if counts[layer] > 1 else ""
        if head and tail:
            return f"{head}-{tail}"
        return head or tail or "P01"

    def layer_of(self, index: Sequence[int]) -> int:
        return int(index[self.layer_axis]) + 1

    def to_dict(self) -> dict:
        return {
            "bounds": [[float(v) for v in self.bounds[0]],
                       [float(v) for v in self.bounds[1]]],
            "edges": [[float(v) for v in e] for e in self.edges],
            "counts": list(self.counts),
            "total_cells": self.total_cells,
            "layer_axis": int(self.layer_axis),
            "mode": self.mode,
            "kerf": float(self.kerf),
            "warnings": list(self.warnings),
        }


def plan_cuts(bounds: np.ndarray, cfg: SliceConfig, mesh=None) -> CutPlan:
    """Decide los planos de corte a partir del tamano del modelo y la maquina.

    Si se pasa la malla y `cfg.snap_cuts` esta puesto, los planos interiores se
    mueven al estrechamiento mas cercano -un tobillo, una muneca, un cuello-
    siempre que las piezas sigan cabiendo. Ver `estrechamientos.py`.
    """
    bounds = np.asarray(bounds, dtype=float)
    lo, hi = bounds[0], bounds[1]
    size = hi - lo
    usable = cfg.printer.usable()
    warnings: List[str] = []
    forced = list(cfg.divisions) + [None] * (3 - len(cfg.divisions)) if cfg.divisions else [None, None, None]

    layer_axis = axis_index(cfg.slab_axis) if cfg.mode == "slabs" else 2
    edges: List[np.ndarray] = []

    for axis in range(3):
        if cfg.mode == "slabs" and axis == layer_axis:
            thickness = float(cfg.slab_thickness)
            if thickness > usable[axis]:
                warnings.append(
                    f"El espesor de lamina ({thickness:g} mm) supera la capacidad "
                    f"del eje {'xyz'[axis]} ({usable[axis]:g} mm)."
                )
            edges.append(_fixed_edges(lo[axis], hi[axis], thickness, cfg.slab_fit))
            continue

        if forced[axis]:
            count = max(1, int(forced[axis]))
        elif cfg.mode == "slabs" and not cfg.split_slabs_to_fit:
            count = 1
        else:
            # kerf: cada corte interior come material, hay que tenerlo en cuenta
            count = _divisions_needed(size[axis], usable[axis], cfg.kerf)
        edges.append(_even_edges(lo[axis], hi[axis], count))

    if mesh is not None and getattr(cfg, "snap_cuts", False):
        edges, movidos = _afinar_por_estrechamientos(mesh, edges, cfg, layer_axis, usable)
        if movidos:
            warnings.append(
                f"{movidos} plano(s) de corte se han movido al estrechamiento mas "
                "cercano (un tobillo, una muneca, un cuello): la cara de corte es "
                "mas pequena, la junta se disimula y las piezas encajan mejor."
            )

    plan = CutPlan(bounds=bounds, edges=edges, layer_axis=layer_axis,
                   mode=cfg.mode, kerf=float(cfg.kerf), warnings=warnings)

    for axis in range(3):
        cell = float(np.max(np.diff(plan.edges[axis]))) if len(plan.edges[axis]) > 1 else 0.0
        if cell > usable[axis] + 1e-6:
            warnings.append(
                f"Las piezas miden {cell:.1f} mm en {'xyz'[axis]} y la maquina "
                f"admite {usable[axis]:.1f} mm: no van a caber."
            )
    if plan.total_cells > 4000:
        warnings.append(
            f"El plan genera {plan.total_cells} piezas; considera subir el espesor "
            "o usar una maquina mas grande."
        )
    return plan


def _afinar_por_estrechamientos(mesh, edges, cfg: SliceConfig, layer_axis: int,
                                usable) -> Tuple[List[np.ndarray], int]:
    """Lleva cada plano de corte al estrechamiento util mas cercano.

    En el modo laminas no se toca el eje de apilado: ahi el espesor lo pone el
    usuario y tiene que salir constante. Los otros dos ejes si, que son los que
    parten brazos y piernas por la mitad.
    """
    from .estrechamientos import ajustar_cortes, estrechamientos

    nuevos, movidos = list(edges), 0
    for axis in range(3):
        if cfg.mode == "slabs" and axis == layer_axis:
            continue
        if len(nuevos[axis]) < 3:
            continue                             # sin cortes interiores no hay nada que mover
        try:
            candidatos = estrechamientos(mesh, axis)
        except Exception:
            continue
        if not candidatos:
            continue
        bordes, cuantos = ajustar_cortes(nuevos[axis], candidatos, usable[axis])
        nuevos[axis] = bordes
        movidos += cuantos
    return nuevos, movidos


def _divisions_needed(size: float, capacity: float, kerf: float = 0.0) -> int:
    if capacity <= 0:
        return 1
    count = max(1, int(math.ceil(size / capacity - 1e-9)))
    # al cortar perdemos kerf/2 en cada cara interior, lo que reduce la pieza,
    # asi que basta con comprobar que la celda resultante sigue cabiendo
    while count < 10000 and (size / count) > capacity + 1e-9:
        count += 1
    return count


def estimate_plan(bounds: np.ndarray, cfg: SliceConfig) -> dict:
    """Resumen rapido del plan (para el panel de la interfaz, sin cortar nada)."""
    plan = plan_cuts(bounds, cfg)
    sizes = [np.diff(e) for e in plan.edges]
    return {
        "counts": list(plan.counts),
        "total_cells": plan.total_cells,
        "piece_size": [float(np.max(s)) if len(s) else 0.0 for s in sizes],
        "layer_axis": plan.layer_axis,
        "layers": int(plan.counts[plan.layer_axis]),
        "edges": [[float(v) for v in e] for e in plan.edges],
        "warnings": plan.warnings,
    }
