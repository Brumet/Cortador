"""Exportacion de resultados: mallas, planos 2D, manifiesto y guia de armado."""

from __future__ import annotations

import colorsys
import csv
import io
import json
import os
import struct
import zipfile
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import trimesh

from .config import SliceConfig
from .font import text_polygons
from .joinery import dowel_mesh
from .labels import fit_text
from .slicer import Piece, SliceResult

MESH_FORMATS = ("stl", "obj", "ply", "3mf")


def piece_color(index: int) -> np.ndarray:
    """Color estable y bien separado para cada pieza (angulo aureo)."""
    hue = (index * 0.61803398875) % 1.0
    sat = 0.55 + 0.25 * ((index % 3) / 2.0)
    val = 0.75 + 0.2 * ((index % 2))
    r, g, b = colorsys.hsv_to_rgb(hue, sat, min(val, 1.0))
    return np.array([int(r * 255), int(g * 255), int(b * 255), 255], dtype=np.uint8)


def safe_name(name: str) -> str:
    keep = "-_.() "
    return "".join(c if c.isalnum() or c in keep else "_" for c in str(name)).strip() or "pieza"


# ---------------------------------------------------------------------------
# planos 2D para laser / CNC
# ---------------------------------------------------------------------------

def piece_path2d(piece: Piece, cfg: SliceConfig, origin: bool = True):
    """Contorno 2D de una lamina con su marca, listo para laser o fresadora."""
    if piece.outline is None:
        return None
    outline = piece.outline
    try:
        path = trimesh.load_path(outline)
    except Exception:
        return None
    for entity in path.entities:
        entity.layer = "CORTE"

    if cfg.labels.enabled:
        from shapely.geometry import Polygon
        from .geometry import largest_polygon
        polys = list(outline.geoms) if hasattr(outline, "geoms") else [outline]
        region = largest_polygon([p for p in polys if isinstance(p, Polygon)])
        fitted = fit_text(piece.label_text or piece.name, region, cfg.labels) if region else None
        if fitted is not None:
            try:
                text_path = trimesh.load_path(fitted[0])
                for entity in text_path.entities:
                    entity.layer = "MARCA"
                path = trimesh.path.util.concatenate([path, text_path])
            except Exception:
                pass
    if origin:
        path.apply_translation(-path.bounds[0])
    return path


# ---------------------------------------------------------------------------
# informes
# ---------------------------------------------------------------------------

def pieces_csv(result: SliceResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["pieza", "capa", "ix", "iy", "iz", "ancho_x_mm", "fondo_y_mm",
                     "alto_z_mm", "volumen_cm3", "vecinos", "avisos"])
    for piece in result.pieces:
        size = piece.size
        writer.writerow([
            piece.name, piece.layer, piece.index[0] + 1, piece.index[1] + 1,
            piece.index[2] + 1,
            f"{size[0]:.2f}", f"{size[1]:.2f}", f"{size[2]:.2f}",
            f"{piece.mesh.volume / 1000.0:.2f}" if piece.mesh.is_volume else "",
            " ".join(f"{k}:{v}" for k, v in piece.neighbors.items()),
            "; ".join(piece.notes),
        ])
    return buf.getvalue()


def slicer_settings(result: SliceResult, line_width: float = 0.0) -> str:
    """Ajustes recomendados del laminador para una pieza solidificada.

    El ancho de linea sale de la boquilla del perfil de maquina: con una de 0,4
    y con una de 1,0 no se imprime igual, y los perimetros que hay que poner en
    el laminador tampoco son los mismos.
    """
    cfg = result.config
    pared = float(cfg.wall)
    if line_width <= 0:
        line_width = cfg.printer.line_width()
    perimetros = max(2, int(round(pared / max(line_width, 0.05))))
    lineas = [
        "AJUSTES DEL LAMINADOR (Cura, PrusaSlicer, Bambu Studio, Orca...)",
        "=" * 62,
        "",
        f"Las piezas ya vienen con la pared solidificada a {pared:g} mm, asi que el",
        "laminador NO tiene que rellenar nada: solo recorrer perimetros.",
        "",
        f"  Relleno (infill) . . . . . . . 0 %",
        f"  Perimetros / paredes . . . . . {perimetros}    (= {pared:g} mm / {line_width:g} mm de linea)",
        f"  Ancho de linea . . . . . . . . {line_width:g} mm"
        f"   (boquilla de {cfg.printer.nozzle:g} mm)",
        "  Capas superiores e inferiores  3-4",
        "  Ventilador de capa . . . . . . 100 % (y velocidad de puente baja)",
        "  Soportes . . . . . . . . . . . solo si la pieza los pide de verdad",
        "",
        "Sobre el relleno y el ventilador: con 0 % de relleno, las capas que",
        "cierran por encima del hueco se imprimen al aire, en puente. No hace",
        "falta meter relleno para sostenerlas -eso gastaria material y tiempo",
        "para nada-: lo que las sostiene es el ventilador de capa, soplando a",
        "tope para que el hilo se solidifique antes de descolgarse. Sube el",
        "ventilador y baja la velocidad de puente y salen limpias.",
        "",
        "Si tu laminador usa 'grosor de pared' en vez de numero de perimetros,",
        f"ponlo en {pared:g} mm y el resto lo calcula solo.",
        "",
        "Comprueba en la vista previa del laminador que el interior sale hueco:",
        "si aparece relleno, es que el perfil tiene un minimo de relleno activado.",
        "",
        f"Material estimado: {result.hollow_volume / 1e6:.1f} litros"
        f" (macizo serian {result.solid_volume / 1e6:.1f} litros).",
    ]
    return "\n".join(lineas) + "\n"


def assembly_guide(result: SliceResult, model_name: str = "modelo") -> str:
    """Guia de armado en Markdown: que pieza va con cual y en que orden."""
    cfg = result.config
    plan = result.plan
    nx, ny, nz = plan.counts
    axis_name = "xyz"[plan.layer_axis]
    lines: List[str] = []
    lines.append(f"# Guia de armado - {model_name}")
    lines.append("")
    lines.append(f"Generado por Cortador el {datetime.now().strftime('%d/%m/%Y %H:%M')}.")
    lines.append("")
    lines.append("## Resumen")
    lines.append("")
    size = result.source["escalado"]["size"]
    lines.append(f"- Tamano final del modelo: **{size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm**")
    lines.append(f"- Capacidad de la maquina: {cfg.printer.x:.0f} x {cfg.printer.y:.0f} x {cfg.printer.z:.0f} mm"
                 + (f" (margen {cfg.printer.clearance:.1f} mm)" if cfg.printer.clearance else ""))
    if cfg.mode == "slabs":
        estilo = "placas planas (contorno extruido)" if cfg.slab_style == "prism" else "rebanadas solidas"
        lines.append(f"- Modo: laminas de **{cfg.slab_thickness:g} mm** sobre el eje {axis_name.upper()} ({estilo})")
    else:
        lines.append("- Modo: trozos que caben en la maquina")
    lines.append(f"- Rejilla de corte: {nx} x {ny} x {nz}")
    lines.append(f"- Piezas: **{result.count}**")
    if cfg.hollow:
        lines.append(f"- Modelo **vaciado**: piel de {cfg.wall:g} mm, hueco por dentro"
                     + (" (primera y ultima lamina macizas)" if cfg.solid_caps else ""))
        if result.solid_volume > 0:
            from .hollow import savings
            lines.append(f"- Material: {savings(result.solid_volume, result.hollow_volume)}")
        lines.append("- **Imprime con relleno al 0 %**: la pared ya esta solidificada. "
                     "Mira `AJUSTES_LAMINADOR.txt`.")
    if cfg.kerf:
        lines.append(f"- Holgura entre piezas (kerf): {cfg.kerf:g} mm")
    if cfg.joinery.mode != "none":
        if cfg.joinery.mode == "holes":
            lines.append(f"- Pasadores: {result.dowels} espigas de diametro {2 * cfg.joinery.radius:g} mm "
                         f"(carpeta `espigas/`)")
        else:
            lines.append(f"- Pasadores: macho/hembra integrados, diametro {2 * cfg.joinery.radius:g} mm")
    if cfg.labels.enabled:
        verbo = "grabado" if cfg.labels.style == "engrave" else "en relieve"
        lines.append(f"- Marcas: texto {verbo} de {cfg.labels.size:g} mm en las caras de corte")
    lines.append("")

    lines.append("## Como leer el nombre de cada pieza")
    lines.append("")
    if cfg.naming == "numeric":
        lines.append("`X01Y02Z03` = columna 1, fila 2, capa 3.")
    else:
        others = [a for a in range(3) if a != plan.layer_axis]
        lines.append(
            f"`A1-L03` = columna **A** (eje {'xyz'[others[0]].upper()}), fila **1** "
            f"(eje {'xyz'[others[1]].upper()}), capa **L03** (eje {axis_name.upper()}, de abajo hacia arriba)."
        )
    lines.append("")
    lines.append("Cada pieza lleva su nombre marcado en una cara de corte, que queda oculta al pegar.")
    lines.append("")

    lines.append("## Orden de montaje")
    lines.append("")
    lines.append(f"Monta capa por capa siguiendo el eje {axis_name.upper()}, de L01 hacia arriba.")
    lines.append("")
    by_layer: Dict[int, List[Piece]] = {}
    for piece in result.pieces:
        by_layer.setdefault(piece.layer, []).append(piece)
    for layer in sorted(by_layer):
        pieces = sorted(by_layer[layer], key=lambda p: (p.index[1], p.index[0]))
        lines.append(f"### Capa L{layer:02d} ({len(pieces)} pieza(s))")
        lines.append("")
        lines.append("| Pieza | Medidas (mm) | Encaja con |")
        lines.append("|---|---|---|")
        for piece in pieces:
            size = piece.size
            vecinos = ", ".join(f"{v} ({k})" for k, v in piece.neighbors.items()) or "-"
            lines.append(f"| `{piece.name}` | {size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} | {vecinos} |")
        lines.append("")

    notes = [(p.name, n) for p in result.pieces for n in p.notes]
    if notes:
        lines.append("## Avisos por pieza")
        lines.append("")
        for name, note in notes:
            lines.append(f"- `{name}`: {note}")
        lines.append("")
    if result.warnings:
        lines.append("## Avisos generales")
        lines.append("")
        for warn in result.warnings:
            lines.append(f"- {warn}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# vista previa para el navegador
# ---------------------------------------------------------------------------

#: techo de triangulos de la vista previa. Cada triangulo ocupa 36 bytes en el
#: paquete y otros tantos de normales en la tarjeta grafica, asi que dos
#: millones y medio son unos 90 MB de descarga y 180 MB de video: nada para una
#: maquina de trabajo, y evita tener que destrozar la malla para que quepa.
PREVIA_MAX = 2_500_000


def preview_payload(result: SliceResult,
                    max_triangles: int = PREVIA_MAX) -> bytes:
    """Empaqueta las piezas para el visor: cabecera JSON + triangulos float32.

    Formato: [uint32 tamano_cabecera][cabecera JSON][posiciones float32 ...]
    """
    total = sum(len(p.mesh.faces) for p in result.pieces) or 1
    ratio = min(1.0, max_triangles / float(total))
    header = {"pieces": [], "bounds": [[float(v) for v in result.plan.bounds[0]],
                                       [float(v) for v in result.plan.bounds[1]]]}
    chunks: List[bytes] = []
    offset = 0
    for i, piece in enumerate(result.pieces):
        mesh = piece.mesh
        if ratio < 1.0 and len(mesh.faces) > 200:
            mesh = _decimate(mesh, max(60, int(len(mesh.faces) * ratio)),
                             estricto=bool(result.config.hollow))
        tris = mesh.vertices[mesh.faces].astype(np.float32).reshape(-1, 3)
        data = np.ascontiguousarray(tris).tobytes()
        color = piece_color(i)
        center = (piece.cell_lo + piece.cell_hi) / 2.0
        header["pieces"].append({
            "name": piece.name,
            "layer": int(piece.layer),
            "index": [int(v) for v in piece.index],
            "color": [int(c) for c in color[:3]],
            "offset": offset,
            "count": int(len(tris)),
            "center": [float(v) for v in center],
            "size": [float(v) for v in piece.size],
            "bounds": [[float(v) for v in piece.mesh.bounds[0]],
                       [float(v) for v in piece.mesh.bounds[1]]],
            "notes": list(piece.notes),
        })
        offset += len(tris)
        chunks.append(data)
    raw = _padded_header(header)
    return struct.pack("<I", len(raw)) + raw + b"".join(chunks)


def _padded_header(header: dict) -> bytes:
    """Cabecera JSON rellenada a multiplo de 4 bytes.

    Float32Array en el navegador exige que el buffer empiece en un offset
    multiplo de 4, y la cabecera va justo delante de los datos.
    """
    raw = json.dumps(header).encode("utf-8")
    padding = (-len(raw)) % 4
    return raw + b" " * padding


def _decimate(mesh: trimesh.Trimesh, faces: int,
              estricto: bool = True) -> trimesh.Trimesh:
    """Aligera una pieza para el visor, pero nunca a costa de romperla.

    Esto es lo que hacia que una figura vaciada se viera hecha un amasijo de
    picos aunque los STL estuvieran perfectos. Una pieza de piel son dos
    superficies separadas por 3 mm; al quitarle triangulos, el aligerado funde
    las dos caras, la pared desaparece y lo que se pinta es un desastre. El
    archivo estaba bien: lo que enganaba era la vista previa.

    `estricto` es para eso, para las piezas de piel: ahi tambien se exige que la
    pieza siga cerrada, porque una piel que se abre ya se ve mal. En una pieza
    maciza no hace falta -que el aligerado deje una arista suelta no se nota en
    pantalla- y exigirlo dejaba sin aligerar un modelo de cinco millones de
    triangulos: 192 MB de descarga para el navegador en vez de 90.
    """
    try:
        ligera = mesh.simplify_quadric_decimation(face_count=faces)
    except Exception:
        return mesh
    if ligera is None or not len(ligera.faces) or len(ligera.faces) >= len(mesh.faces):
        return mesh
    if estricto and mesh.is_watertight and not ligera.is_watertight:
        return mesh
    # cerrada puede quedarse igual y estar destrozada: si la camara interior se
    # ha derrumbado, la pieza pasa a ser un terron macizo. Eso se ve en el
    # volumen, no en la topologia.
    try:
        if mesh.is_volume and abs(ligera.volume - mesh.volume) > abs(mesh.volume) * 0.05:
            return mesh
        if not mesh.is_volume and abs(ligera.area - mesh.area) > mesh.area * 0.1:
            return mesh
    except Exception:
        return mesh
    return ligera


def preview_glb(result: SliceResult) -> bytes:
    """Escena GLB coloreada (por si se quiere abrir la vista previa fuera)."""
    scene = trimesh.Scene()
    for i, piece in enumerate(result.pieces):
        mesh = piece.mesh.copy()
        mesh.visual.face_colors = piece_color(i)
        scene.add_geometry(mesh, node_name=safe_name(piece.name))
    return scene.export(file_type="glb")


# ---------------------------------------------------------------------------
# escritura en disco
# ---------------------------------------------------------------------------

def export_result(result: SliceResult,
                  outdir: str,
                  mesh_format: str = "stl",
                  write_2d: bool = True,
                  write_preview: bool = True,
                  place_at_origin: bool = True,
                  model_name: str = "modelo",
                  progress=None) -> Dict[str, object]:
    """Escribe todo el despiece en `outdir` y devuelve el indice de archivos.

    `place_at_origin` mueve cada pieza a (0, 0, 0) al guardarla, que es lo que
    espera cualquier laminador: si no, una pieza de la parte alta de una figura
    de 1,8 m aparece flotando fuera de la cama. El manifiesto guarda la posicion
    original por si hay que recomponer el conjunto.
    """
    mesh_format = mesh_format.lower().lstrip(".")
    if mesh_format not in MESH_FORMATS:
        raise ValueError(f"Formato no soportado: {mesh_format}")
    cfg = result.config
    pieces_dir = os.path.join(outdir, "piezas")
    os.makedirs(pieces_dir, exist_ok=True)
    written: List[str] = []
    revisar: List[str] = []

    for i, piece in enumerate(result.pieces):
        path = os.path.join(pieces_dir, f"{safe_name(piece.name)}.{mesh_format}")
        malla = piece.mesh.copy()
        malla.merge_vertices()
        malla.update_faces(malla.nondegenerate_faces())
        malla.remove_unreferenced_vertices()
        if not malla.is_watertight:
            revisar.append(piece.name)
        if place_at_origin:
            malla.apply_translation(-piece.mesh.bounds[0])
        malla.export(path)
        written.append(path)
        if progress:
            progress(i + 1, len(result.pieces), f"Exportando {piece.name}")

    if write_2d and any(p.outline is not None for p in result.pieces):
        dir2d = os.path.join(outdir, "2d")
        os.makedirs(dir2d, exist_ok=True)
        for piece in result.pieces:
            path2d = piece_path2d(piece, cfg)
            if path2d is None:
                continue
            base = os.path.join(dir2d, safe_name(piece.name))
            for ext in ("svg", "dxf"):
                try:
                    data = path2d.export(file_type=ext)
                    mode = "w" if isinstance(data, str) else "wb"
                    with open(f"{base}.{ext}", mode) as fh:
                        fh.write(data)
                    written.append(f"{base}.{ext}")
                except Exception:
                    continue

    if result.dowels and cfg.joinery.mode == "holes":
        dowel_dir = os.path.join(outdir, "espigas")
        os.makedirs(dowel_dir, exist_ok=True)
        dowel = dowel_mesh(cfg.joinery, cfg.kerf)
        path = os.path.join(dowel_dir, f"espiga_d{2 * cfg.joinery.radius:g}mm.{mesh_format}")
        dowel.export(path)
        written.append(path)
        with open(os.path.join(dowel_dir, "LEEME.txt"), "w", encoding="utf-8") as fh:
            fh.write(f"Imprime {result.dowels} espigas de este archivo.\n")
        written.append(os.path.join(dowel_dir, "LEEME.txt"))

    if revisar:
        result.warnings.append(
            f"{len(revisar)} pieza(s) tienen superficies que se tocan y el laminador "
            "puede pedir repararlas (todos lo hacen solos). Suele pasar con mallas "
            "reconstruidas o escaneadas."
        )

    manifest_path = os.path.join(outdir, "cortador.json")
    manifest = result.manifest()
    manifest["piezas_en_el_origen"] = bool(place_at_origin)
    manifest["piezas_a_revisar"] = list(revisar)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    written.append(manifest_path)

    csv_path = os.path.join(outdir, "despiece.csv")
    with open(csv_path, "w", encoding="utf-8") as fh:
        fh.write(pieces_csv(result))
    written.append(csv_path)

    if cfg.hollow:
        ajustes_path = os.path.join(outdir, "AJUSTES_LAMINADOR.txt")
        with open(ajustes_path, "w", encoding="utf-8") as fh:
            fh.write(slicer_settings(result))
        written.append(ajustes_path)

    guide_path = os.path.join(outdir, "GUIA_DE_ARMADO.md")
    with open(guide_path, "w", encoding="utf-8") as fh:
        fh.write(assembly_guide(result, model_name))
    written.append(guide_path)

    if write_preview:
        try:
            glb_path = os.path.join(outdir, "vista_previa.glb")
            with open(glb_path, "wb") as fh:
                fh.write(preview_glb(result))
            written.append(glb_path)
        except Exception:
            pass

    return {"outdir": outdir, "files": written, "pieces": len(result.pieces)}


def zip_directory(directory: str, zip_path: str) -> str:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(directory):
            for name in files:
                full = os.path.join(root, name)
                if os.path.abspath(full) == os.path.abspath(zip_path):
                    continue
                zf.write(full, os.path.relpath(full, directory))
    return zip_path
