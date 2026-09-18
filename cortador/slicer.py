"""Motor de corte: convierte una malla en piezas listas para imprimir."""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import trimesh
from shapely.geometry import box as shapely_box

from .config import SliceConfig, axis_index
from .geometry import (EPS, clip_slab, extrude_polygons, hilos, largest_polygon,
                       merge_polygons, plane_transform, section_polygons)
from . import joinery as jn
from .hollow import (espesor_recomendado, hollow_mesh, hollow_region,
                     hollow_slab, limpiar, medir_pared, savings)
from .font import text_size
from .labels import apply_label
from .meshio import apply_units_and_scale, is_empty, mesh_stats
from .repair import auto_repair
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
    #: volumen macizo y volumen real, para saber cuanto material se ahorra
    solid_volume: float = 0.0
    hollow_volume: float = 0.0

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
            "volumen_cm3": round(self.hollow_volume / 1000.0, 1),
            "volumen_macizo_cm3": round(self.solid_volume / 1000.0, 1),
            "piezas_fuera_de_capacidad": [p.name for p in self.oversized()],
            "avisos": list(self.warnings),
        }


def orientar(mesh: trimesh.Trimesh, cfg: SliceConfig) -> trimesh.Trimesh:
    """Gira el modelo antes de cortarlo.

    Girar cambia como se reparten los cortes: una figura tumbada se corta en
    otras piezas que la misma figura de pie. Se aplica en el orden X, Y, Z y,
    al terminar, el modelo se vuelve a apoyar en el origen para que el plan de
    corte siempre empiece en cero.
    """
    angulos = [float(a) for a in (cfg.rotation or (0.0, 0.0, 0.0))]
    girado = mesh
    if cfg.auto_base:
        girado = apoyar_base(girado)
    if any(abs(a) > 1e-9 for a in angulos):
        girado = girado.copy() if girado is mesh else girado
        for eje, angulo in enumerate(angulos):
            if abs(angulo) < 1e-9:
                continue
            direccion = [0.0, 0.0, 0.0]
            direccion[eje] = 1.0
            girado.apply_transform(
                trimesh.transformations.rotation_matrix(np.radians(angulo), direccion))
    if girado is not mesh:
        girado.apply_translation(-girado.bounds[0])
    return girado


def apoyar_base(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Deja hacia abajo la cara plana mas grande del modelo.

    Es lo que uno hace a mano en el laminador antes de imprimir: buscar el
    apoyo mas ancho. Si la malla no tiene caras planas claras, se queda como
    esta en vez de inventarse un giro raro.
    """
    try:
        copia = mesh.copy()
        transform, _ = trimesh.bounds.oriented_bounds(copia)
        copia.apply_transform(transform)
        # oriented_bounds alinea la caja minima; dejamos el lado mas corto en Z
        extents = copia.extents
        eje_corto = int(np.argmin(extents))
        if eje_corto != 2:
            direccion = [0.0, 0.0, 0.0]
            direccion[1 - eje_corto if eje_corto < 2 else 0] = 1.0
            copia.apply_transform(
                trimesh.transformations.rotation_matrix(np.pi / 2, direccion))
        copia.apply_translation(-copia.bounds[0])
        return copia
    except Exception:
        return mesh


def slice_model(mesh: trimesh.Trimesh,
                cfg: SliceConfig,
                progress: Progress = None) -> SliceResult:
    """Corta el modelo segun la configuracion y devuelve todas las piezas."""
    cfg.validate()
    source_stats = mesh_stats(mesh)
    work = apply_units_and_scale(mesh, cfg.units, cfg.scale, cfg.target_size, cfg.target_axis)
    work = orientar(work, cfg)
    # sellar la malla aqui dentro, pase lo que pase: de esto dependen el
    # solidificado y el corte booleano de respaldo
    work, informe = auto_repair(work, weld=cfg.weld)
    bodies = int(informe.cuerpos_antes)
    prepared_stats = mesh_stats(work)
    plan = plan_cuts(work.bounds, cfg)
    warnings = list(plan.warnings)
    if informe.cambiada:
        warnings.append(informe.resumen())
    if not work.is_watertight:
        warnings.append(
            "La malla de entrada no es estanca; los cortes pueden dejar caras "
            "abiertas. Repara el modelo si el resultado no imprime bien."
        )

    def report(done: int, total: int, msg: str) -> None:
        if progress:
            progress(done, total, msg)

    report(0, 1, "Preparando el modelo")

    volumen_macizo = float(work.volume) if work.is_volume else 0.0

    total_steps = plan.total_cells
    report(0, total_steps, "Cortando")

    # En modo trozos se vacia PRIMERO el modelo entero y luego se corta la piel.
    # Al reves (cortar y vaciar cada trozo) cada trozo acaba siendo una cajita
    # cerrada: aparecen paredes en las caras de corte, los trozos del centro
    # salen como cubos huecos que no aportan nada, y se gasta material de mas.
    # Vaciando antes, cada pieza es un trozo de piel y el centro no existe.
    piel = False
    if cfg.hollow and cfg.mode == "chunks":
        report(0, 1, "Solidificando la piel")
        macizo = work
        hueca, aviso = hollow_mesh(work, cfg.wall,
                                   report=lambda texto: report(0, 1, texto))
        if aviso is None and hueca is not work and not is_empty(hueca):
            work = hueca
            piel = True
            # el espesor no se da por supuesto: se mide sobre la piel que ha
            # salido y se dice. Una pared mas fina de la cuenta no se pega bien
            # y complica el ensamble, asi que es un numero que hay que ver.
            medida = medir_pared(macizo, work)
            if medida is not None:
                # se da el percentil 1 y no el minimo absoluto: el minimo de un
                # muestreo lo marca siempre alguna esquirla del borde donde la
                # camara se cierra, y no dice nada util de la pieza
                _minimo, p1, mediana = medida
                aviso_pared = (f"Pared medida sobre la piel: el 1 % mas fino "
                               f"queda en {p1:.1f} mm y la mediana en "
                               f"{mediana:.1f} mm (pedidos {cfg.wall:g} mm).")
                pedir = espesor_recomendado(cfg.wall, medida)
                if pedir is not None:
                    aviso_pared += (
                        " En un escaneo la cara de fuera tiene relieve y la de"
                        " dentro es lisa, asi que por los valles la pared se"
                        f" queda corta. Si necesitas {cfg.wall:g} mm de minimo,"
                        f" pide {pedir:g}."
                    )
                warnings.append(aviso_pared)
        else:
            # vaciar despues, trozo a trozo, no es una alternativa: cada trozo
            # sale como una cajita cerrada con paredes en las caras de corte,
            # que es justo lo que no se quiere. Antes de entregar eso se deja
            # el modelo macizo y se dice claramente por que.
            warnings.append(
                (aviso or "No se ha podido vaciar este modelo.") +
                " Las piezas salen macizas. Prueba a bajar el espesor de piel, "
                "a reparar la malla antes de cortarla o a usar el modo laminas, "
                "que vacia por secciones y nunca falla."
            )

    if cfg.mode == "slabs" and cfg.slab_style == "prism":
        raw = _build_prisms(work, plan, cfg, report)
    else:
        # una piel no se puede cortar con el recorte rapido por planos: al tapar
        # la cara de corte hay que coser un anillo, y en una cascara de escaneo
        # ese tapado deja agujeros. Un trozo con agujeros ya no es un solido: no
        # se puede medir, el laminador lo rechaza y en la vista previa se ve
        # roto. Con CSG cuesta un poco mas y sale cerrado siempre.
        raw = _build_chunks(work, plan, cfg, report,
                            engine="boolean" if piel else None)

    if cfg.hollow and cfg.mode == "slabs" and cfg.slab_style == "solid":
        raw = _hollow_slabs(raw, plan, cfg, report)

    pieces: List[Piece] = []
    descartadas: List[float] = []
    by_index: Dict[Tuple[int, int, int], List[Piece]] = {}
    for index, piece_mesh, outline in raw:
        if piece_mesh is None or is_empty(piece_mesh):
            continue
        lo, hi = plan.cell_bounds(index)
        base = plan.name_for(index, cfg.naming)
        for nombre, trozo, contorno in _separar_islas(base, piece_mesh, outline, cfg,
                                                      descartadas):
            piece = Piece(
                name=nombre,
                index=index,
                layer=plan.layer_of(index),
                mesh=trozo,
                cell_lo=lo,
                cell_hi=hi,
                outline=contorno,
                outline_axis=plan.layer_axis,
            )
            pieces.append(piece)
            by_index.setdefault(index, []).append(piece)

    if descartadas:
        perdido = sum(descartadas) / 1000.0            # cm3
        del_total = (perdido * 1000.0 / volumen_macizo * 100.0
                     if volumen_macizo > 0 else 0.0)
        warnings.append(
            f"Se han descartado {len(descartadas)} trozos sueltos de menos de "
            f"{cfg.min_piece:g} mm: son esquirlas que no se pueden fabricar. "
            f"Entre todas suman {perdido:.1f} cm3, el {del_total:.2f} % del "
            f"modelo, asi que no falta nada que se note."
            if del_total < 1.0 else
            f"Se han descartado {len(descartadas)} trozos sueltos de menos de "
            f"{cfg.min_piece:g} mm ({perdido:.0f} cm3, el {del_total:.1f} % del "
            f"modelo). Si es mucho, baja el tamano minimo de pieza."
        )

    _link_neighbors(pieces, by_index, plan)

    dowels = 0
    if cfg.joinery.mode != "none" and len(pieces) > 1:
        report(0, len(pieces), "Colocando pasadores")
        dowels = _apply_joinery(pieces, by_index, plan, cfg, report)

    if cfg.labels.enabled and len(pieces) >= 1:
        report(0, len(pieces), "Marcando piezas")
        _apply_labels(pieces, plan, cfg, report)

    volumen_real = float(sum(_volumen_pieza(p.mesh, cfg) for p in pieces))
    result = SliceResult(pieces=pieces, plan=plan, config=cfg,
                         source={"original": source_stats, "escalado": prepared_stats},
                         warnings=warnings, dowels=dowels,
                         solid_volume=volumen_macizo, hollow_volume=volumen_real)
    if cfg.hollow and volumen_macizo > 0 and volumen_real < volumen_macizo * 0.99:
        result.warnings.append("Modelo vaciado: " + savings(volumen_macizo, volumen_real) + ".")
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

def hilos_de_corte() -> int:
    """Cuantos hilos se reparten el corte (ver `geometry.hilos`)."""
    return hilos()


def _build_chunks(mesh: trimesh.Trimesh,
                  plan: CutPlan,
                  cfg: SliceConfig,
                  report,
                  engine: Optional[str] = None
                  ) -> List[Tuple[Tuple[int, int, int], trimesh.Trimesh, object]]:
    """Corta en trozos reales, eje por eje, reutilizando el resto de cada corte.

    Cortar primero en bandas y luego subdividirlas es mucho mas rapido que
    recortar la malla completa contra cada celda. Las bandas del primer eje son
    independientes entre si, asi que cada una se trocea en su propio hilo.
    """
    total = plan.total_cells
    engine = engine or cfg.engine
    bandas = _split_axis(mesh, plan, 0, cfg, engine)

    hechas = [0]
    candado = threading.Lock()

    def avisar(cuantas: int) -> None:
        with candado:
            hechas[0] += cuantas
            report(hechas[0], total, "Cortando")

    def trocear(par):
        i, band_x = par
        celdas = []
        if band_x is None:
            avisar(plan.counts[1] * plan.counts[2])
            return i, celdas
        for j, band_y in _split_axis(band_x, plan, 1, cfg, engine):
            if band_y is None:
                avisar(plan.counts[2])
                continue
            for k, cell in _split_axis(band_y, plan, 2, cfg, engine):
                if cell is not None:
                    celdas.append(((i, j, k), cell, None))
                avisar(1)
        return i, celdas

    obreros = min(hilos_de_corte(), len(bandas))
    if obreros > 1:
        with ThreadPoolExecutor(max_workers=obreros) as equipo:
            resultados = list(equipo.map(trocear, bandas))
    else:
        resultados = [trocear(par) for par in bandas]

    out = []
    for _i, celdas in sorted(resultados, key=lambda r: r[0]):
        out.extend(celdas)
    return out


def _reunir_cavidades(trozos: Sequence[trimesh.Trimesh]) -> List[trimesh.Trimesh]:
    """Devuelve las piezas reales, con sus huecos interiores dentro.

    Al partir una pieza vaciada en componentes salen dos superficies: la piel
    de fuera y la del hueco. No son dos piezas: son una pieza con una camara
    dentro. Aqui se distingue por el signo del volumen y se vuelven a juntar.
    """
    solidos, cavidades = [], []
    for trozo in trozos:
        try:
            volumen = float(trozo.volume)
        except Exception:
            volumen = 0.0
        (solidos if volumen >= 0 else cavidades).append(trozo)
    if not cavidades:
        return list(solidos)
    if not solidos:
        return list(trozos)

    grupos = [[s] for s in solidos]
    for cavidad in cavidades:
        centro = cavidad.bounds.mean(axis=0)
        mejor, mejor_volumen = None, None
        for i, solido in enumerate(solidos):
            lo, hi = solido.bounds
            if np.all(centro >= lo - 1e-6) and np.all(centro <= hi + 1e-6):
                volumen = float(np.prod(hi - lo))
                if mejor_volumen is None or volumen < mejor_volumen:
                    mejor, mejor_volumen = i, volumen
        grupos[mejor if mejor is not None else 0].append(cavidad)
    return [g[0] if len(g) == 1 else trimesh.util.concatenate(g) for g in grupos]


def _es_util(malla: trimesh.Trimesh, cfg: SliceConfig) -> bool:
    """Descarta esquirlas: trozos tan pequenos que no se pueden fabricar.

    Se mira la segunda dimension mas pequena: un palillo de 2 x 3 x 25 mm es
    inservible aunque mida 25 mm de largo.
    """
    medidas = sorted(float(v) for v in malla.extents)
    minimo = float(cfg.min_piece)
    # por debajo de dos lineas de extrusion no hay pieza que imprimir, solo
    # una rebaba del corte
    # con la piel solidificada, un trozo mas fino que media pared es un recorte
    # de la esquina de una celda, no una pieza
    grosor_minimo = 0.05
    if minimo > 0:
        grosor_minimo = max(0.8, cfg.wall * 0.4) if cfg.hollow else 0.8
    if medidas[0] < grosor_minimo:
        return False
    if minimo <= 0:
        return True
    return medidas[1] >= minimo


def _volumen_pieza(malla: trimesh.Trimesh, cfg: SliceConfig) -> float:
    """Material de una pieza, tambien cuando la malla no ha quedado cerrada.

    Antes se sumaban solo las piezas cerradas y las demas contaban cero. Si el
    corte dejaba muchas abiertas, el programa anunciaba tan tranquilo un
    "100 % menos de material" sobre un modelo que en realidad seguia entero.
    Un numero que no se puede medir no se inventa ni se da por cero: se estima
    por la superficie de la piel, que para una cascara de espesor conocido es
    area / 2 x espesor.
    """
    try:
        volumen = float(malla.volume)
    except Exception:
        volumen = float("nan")
    if malla.is_volume and np.isfinite(volumen) and volumen > 0:
        return volumen
    try:
        area = float(malla.area)
    except Exception:
        area = 0.0
    if cfg.hollow and cfg.wall > 0 and area > 0:
        return area * 0.5 * float(cfg.wall)
    return abs(volumen) if np.isfinite(volumen) else 0.0


def _separar_islas(base: str,
                   malla: trimesh.Trimesh,
                   outline,
                   cfg: SliceConfig,
                   descartadas: Optional[List[float]] = None):
    """Parte una celda en sus trozos sueltos: cada uno es una pieza real.

    Una lamina a la altura de las piernas de una figura son dos anillos que no
    se tocan: hay que fabricarlos, nombrarlos y marcarlos por separado.
    """
    if not cfg.split_islands:
        return [(base, malla, outline)] if _es_util(malla, cfg) else []
    try:
        trozos = malla.split(only_watertight=False)
    except Exception:
        trozos = []
    if len(trozos) < 2:
        return [(base, malla, outline)] if _es_util(malla, cfg) else []

    trozos = _reunir_cavidades(trozos)
    utiles = []
    for trozo in trozos:
        if is_empty(trozo):
            continue
        if _es_util(trozo, cfg):
            utiles.append(trozo)
        elif descartadas is not None:
            volumen = float(trozo.volume) if trozo.is_volume else 0.0
            descartadas.append(volumen)
    trozos = utiles
    if not trozos:
        return []
    if len(trozos) == 1:
        return [(base, trozos[0], _recortar_contorno(outline, trozos[0]))]

    # de arriba abajo y de izquierda a derecha, para que las letras tengan logica
    trozos = sorted(trozos, key=lambda t: (-t.bounds[1][1], t.bounds[0][0]))
    salida = []
    for i, trozo in enumerate(trozos):
        sufijo = chr(ord("a") + i) if i < 26 else f"-{i + 1}"
        salida.append((f"{base}{sufijo}", trozo, _recortar_contorno(outline, trozo)))
    return salida


def _recortar_contorno(outline, trozo: trimesh.Trimesh):
    """Se queda con la parte del contorno 2D que corresponde a este trozo."""
    if outline is None:
        return None
    partes = list(outline.geoms) if hasattr(outline, "geoms") else [outline]
    lo, hi = trozo.bounds[0], trozo.bounds[1]
    from shapely.geometry import box as shapely_box
    caja = shapely_box(lo[0] - 0.05, lo[1] - 0.05, hi[0] + 0.05, hi[1] + 0.05)
    dentro = []
    for parte in partes:
        if parte.is_empty or not parte.intersects(caja):
            continue
        # se queda con los contornos que estan de verdad en este trozo, no con
        # los que solo rozan su caja (una pieza en forma de C toca varias)
        if parte.intersection(caja).area > parte.area * 0.5:
            dentro.append(parte)
    if not dentro:
        return None
    return merge_polygons(dentro)


def _hollow_slabs(raw, plan: CutPlan, cfg: SliceConfig, report):
    """Deja hueca cada rebanada solida, conservando su relieve exterior."""
    axis = plan.layer_axis
    capas = plan.counts[axis]
    salida = []
    total = len(raw)
    for i, (index, malla, outline) in enumerate(raw, start=1):
        report(i, total, "Vaciando las laminas")
        if malla is None or _es_tapa(int(index[axis]), capas, cfg):
            salida.append((index, malla, outline))
            continue
        lo, hi = plan.cell_bounds(index)
        medio = (float(lo[axis]) + float(hi[axis])) / 2.0
        seccion = merge_polygons(section_polygons(malla, axis, medio))
        if seccion is None:
            salida.append((index, malla, outline))
            continue
        hueca, _ok = hollow_slab(malla, seccion, cfg.wall,
                                 float(lo[axis]), float(hi[axis]), axis)
        salida.append((index, hueca, outline))
    return salida


def _es_tapa(indice_capa: int, total_capas: int, cfg: SliceConfig) -> bool:
    """La primera y la ultima lamina se dejan macizas para cerrar la figura."""
    if not cfg.solid_caps:
        return False
    return indice_capa == 0 or indice_capa == total_capas - 1


def _split_axis(mesh: Optional[trimesh.Trimesh],
                plan: CutPlan,
                axis: int,
                cfg: SliceConfig,
                engine: Optional[str] = None):
    """Trocea una malla a lo largo de un eje devolviendo (indice, trozo)."""
    engine = engine or cfg.engine
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
            piece = clip_slab(rest, axis, lo, hi, engine) if half > 0 else rest
            out.append((i, piece))
            break
        piece = clip_slab(rest, axis, lo, hi, engine)
        out.append((i, piece))
        rest = clip_slab(rest, axis, edges[i + 1], float(plan.bounds[1][axis]) + 1.0, engine)
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
        etapa = "Generando laminas huecas" if cfg.hollow else "Generando laminas"
        merged = merge_polygons(section_polygons(mesh, axis, mid))
        if merged is None:
            done += plan.counts[others[0]] * plan.counts[others[1]]
            report(done, total, etapa)
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
                    report(done, total, etapa)
                    continue
                limpiar_despues = True
                if cfg.hollow and not _es_tapa(k, layers, cfg):
                    tam = None
                    if cfg.labels.enabled and cfg.label_tab:
                        nombre = plan.name_for(index, cfg.naming)
                        tam = text_size(f"{cfg.labels.prefix}{nombre}x", cfg.labels.size)
                    region = hollow_region(region, cfg.wall, tam, cfg.min_piece)
                    limpiar_despues = False
                if limpiar_despues:
                    # tambien en macizo: una seccion casi tangente al plano deja
                    # decenas de motas que no son piezas
                    region = limpiar(region, cfg.min_piece)
                if region is None or region.is_empty:
                    report(done, total, etapa)
                    continue
                solid = extrude_polygons(region, height)
                if solid is None:
                    report(done, total, etapa)
                    continue
                # extrude_polygon trabaja en XY: lo llevamos al plano real
                solid.apply_transform(np.linalg.inv(plane_transform(axis, z_lo)))
                out.append((index, solid, region))
                report(done, total, etapa)
    return out


# ---------------------------------------------------------------------------
# vecinos, pasadores y marcas
# ---------------------------------------------------------------------------

def _face_key(axis: int, sign: int) -> str:
    return ("+" if sign > 0 else "-") + "xyz"[axis]


def _solapan(a: Piece, b: Piece, axis: int) -> bool:
    """True si las dos piezas se tocan de verdad en las otras dos direcciones."""
    otros = [e for e in range(3) if e != axis]
    for eje in otros:
        if a.mesh.bounds[1][eje] <= b.mesh.bounds[0][eje] + 1e-6:
            return False
        if b.mesh.bounds[1][eje] <= a.mesh.bounds[0][eje] + 1e-6:
            return False
    return True


def _link_neighbors(pieces: Sequence[Piece],
                    by_index: Dict[Tuple[int, int, int], List[Piece]],
                    plan: CutPlan) -> None:
    for piece in pieces:
        for axis, sign in FACES:
            nb_index = plan.neighbor(piece.index, axis, sign)
            if nb_index is None:
                continue
            vecinas = [n for n in by_index.get(nb_index, []) if _solapan(piece, n, axis)]
            if vecinas:
                piece.neighbors[_face_key(axis, sign)] = ", ".join(n.name for n in vecinas)


def _face_value(piece: Piece, axis: int, sign: int) -> float:
    return float(piece.cell_hi[axis] if sign > 0 else piece.cell_lo[axis])


def _apply_joinery(pieces: Sequence[Piece],
                   by_index: Dict[Tuple[int, int, int], List[Piece]],
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
            vecinas = [n for n in by_index.get(nb_index, []) if _solapan(piece, n, axis)]
            if not vecinas:
                continue
            nb = vecinas[0]
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
            # el pasador se ajusta a lo que hay: en una lamina de 4 mm con
            # pared de 3 no cabe una espiga de 6 mm de fondo
            es_lamina = cfg.mode == "slabs" and axis == plan.layer_axis
            espesor = min(float(piece.size[axis]), float(nb.size[axis]))
            pared = float(cfg.wall) if cfg.hollow else 0.0
            ajuste = jn.ajustar(opts, espesor, pared, es_lamina)

            points = jn.pick_points(common, ajuste.count,
                                    ajuste.radius + ajuste.clearance, ajuste.margin)
            if not points:
                piece.notes.append(
                    f"cara {_face_key(axis, sign)} demasiado estrecha para pasadores")
                continue
            for uv in points:
                if ajuste.mode == "holes":
                    cutters[piece.name]["difference"].append(
                        jn.hole_cylinder(axis, value_a, uv, +1, ajuste, plan.kerf))
                    cutters[nb.name]["difference"].append(
                        jn.hole_cylinder(axis, value_b, uv, -1, ajuste, plan.kerf))
                    dowels += 1
                else:  # pins: macho arriba, hembra abajo
                    cutters[piece.name]["union"].append(
                        jn.pin_cylinder(axis, value_a, uv, +1, ajuste, plan.kerf))
                    cutters[nb.name]["difference"].append(
                        jn.hole_cylinder(axis, value_b, uv, -1, ajuste, plan.kerf))

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
