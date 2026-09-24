"""Carga, saneamiento y exportacion de mallas."""

from __future__ import annotations

import io
import os
from typing import Optional, Union

import numpy as np
import trimesh

from .config import UNIT_SCALE, axis_index

#: formatos de entrada que aceptamos (todo lo que lee trimesh y tiene sentido aqui)
INPUT_FORMATS = (
    ".stl", ".obj", ".ply", ".off", ".3mf", ".glb", ".gltf", ".dae", ".xaml", ".zip",
)
OUTPUT_FORMATS = (".stl", ".obj", ".ply", ".3mf", ".glb")

#: formatos que son texto plano, donde un exportador puede colar suciedad que
#: atraganta al lector sin que el archivo este roto de verdad
FORMATOS_TEXTO = (".obj", ".off", ".dae", ".xaml")


class MeshError(RuntimeError):
    pass


def load_mesh(source: Union[str, bytes, os.PathLike, io.IOBase],
              file_type: Optional[str] = None,
              repair: bool = True) -> trimesh.Trimesh:
    """Carga cualquier modelo soportado y devuelve una unica malla triangular.

    Acepta una ruta, bytes o un objeto tipo archivo. Las escenas con varios
    objetos se combinan en una sola malla (es lo que queremos: cortamos el
    conjunto, no cada pieza por separado).

    Si el archivo es de texto -OBJ sobre todo- y el lector se atraganta, se
    intenta una segunda vez con el texto saneado: ver `sanear_texto`.
    """
    if isinstance(source, (bytes, bytearray)):
        if not file_type:
            raise MeshError("Hace falta indicar el formato cuando se pasan bytes")
        obj = _leer_bytes(bytes(source), file_type)
    elif isinstance(source, (str, os.PathLike)):
        path = os.fspath(source)
        if not os.path.exists(path):
            raise MeshError(f"No existe el archivo: {path}")
        obj = _leer_ruta(path)
    else:
        if not file_type:
            raise MeshError("Hace falta indicar el formato del flujo de entrada")
        obj = _leer_bytes(source.read(), file_type)

    mesh = _as_single_mesh(obj)
    if mesh is None or len(mesh.faces) == 0:
        raise MeshError(
            "El archivo no contiene ninguna cara: son solo puntos o curvas. "
            "Exportalo como malla (STL o OBJ con caras) desde tu programa."
        )
    if repair:
        mesh = repair_mesh(mesh)
    return mesh


def sanear_texto(datos: bytes) -> Optional[bytes]:
    """Quita de un modelo de texto lo que atraganta al lector, o None si no hay nada.

    Dos cosas que se ven constantemente y que no son culpa de nadie:

    * La **marca de orden de bytes** que Windows pone al principio de un archivo
      de texto. Al lector de OBJ se le pierde el primer vertice y luego revienta
      con un "index out of bounds" que no le dice nada a nadie.
    * La **coma decimal**. Un exportador configurado en espanol escribe
      `v 1,5 2,0 0,0` y el lector no puede con ello. En un OBJ una coma no
      significa nada por si sola, asi que cambiarla por un punto es seguro.
    """
    cambiado = False
    if datos.startswith(b"\xef\xbb\xbf"):
        datos = datos[3:]
        cambiado = True
    if b"," in datos:
        lineas = datos.split(b"\n")
        for i, linea in enumerate(lineas):
            cabeza = linea[:3].lstrip()
            if cabeza[:2] in (b"v ", b"vn", b"vt") or cabeza[:2] == b"f ":
                if b"," in linea:
                    lineas[i] = linea.replace(b",", b".")
                    cambiado = True
        if cambiado:
            datos = b"\n".join(lineas)
    return datos if cambiado else None


def _cargar(fuente, file_type: Optional[str] = None):
    return trimesh.load(fuente, file_type=file_type, force="mesh", process=False)


def _leer_ruta(path: str):
    ext = os.path.splitext(path)[1].lower()
    try:
        return _cargar(path)
    except Exception as exc:
        if ext not in FORMATOS_TEXTO:
            raise MeshError(_por_que(path, exc)) from exc
    with open(path, "rb") as fh:
        limpio = sanear_texto(fh.read())
    if limpio is None:
        raise MeshError(_por_que(path, None))
    try:
        return _cargar(io.BytesIO(limpio), ext.lstrip("."))
    except Exception as exc:
        raise MeshError(_por_que(path, exc)) from exc


def _leer_bytes(datos: bytes, file_type: str):
    tipo = file_type.lstrip(".").lower()
    try:
        return _cargar(io.BytesIO(datos), tipo)
    except Exception as exc:
        if f".{tipo}" not in FORMATOS_TEXTO:
            raise MeshError(_por_que(f"modelo.{tipo}", exc)) from exc
    limpio = sanear_texto(datos)
    if limpio is None:
        raise MeshError(_por_que(f"modelo.{tipo}", None))
    try:
        return _cargar(io.BytesIO(limpio), tipo)
    except Exception as exc:
        raise MeshError(_por_que(f"modelo.{tipo}", exc)) from exc


def _por_que(nombre: str, exc: Optional[BaseException]) -> str:
    """Un mensaje que diga algo, en vez del error del lector.

    El lector de OBJ suelta cosas como "index 7 is out of bounds": eso no ayuda
    a nadie a arreglar su archivo. Aqui se dice que se ha intentado y que hacer.
    """
    ext = os.path.splitext(nombre)[1].lower() or "?"
    detalle = f" ({type(exc).__name__}: {str(exc)[:120]})" if exc is not None else ""
    if ext == ".obj":
        return (
            f"No se ha podido leer el OBJ{detalle}. Ya se ha probado quitando la "
            "marca de Windows del principio y cambiando las comas decimales por "
            "puntos. Lo mas rapido: abrelo en tu programa y guardalo como **STL "
            "binario**, que ademas ocupa la mitad y se lee diez veces mas rapido."
        )
    return (
        f"No se ha podido leer el archivo {ext}{detalle}. Prueba a exportarlo "
        "como STL binario desde el programa donde lo tengas."
    )


def _as_single_mesh(obj) -> Optional[trimesh.Trimesh]:
    if isinstance(obj, trimesh.Trimesh):
        return obj
    if isinstance(obj, trimesh.Scene):
        geoms = [g for g in obj.dump() if isinstance(g, trimesh.Trimesh)]
        if not geoms:
            return None
        return trimesh.util.concatenate(geoms)
    if isinstance(obj, (list, tuple)):
        geoms = [g for g in obj if isinstance(g, trimesh.Trimesh)]
        if not geoms:
            return None
        return trimesh.util.concatenate(geoms)
    return None


def repair_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Limpieza basica: soldar vertices, quitar basura y orientar normales.

    No intenta milagros con mallas rotas, pero deja la mayoria de descargas de
    internet en un estado en el que los cortes booleanos funcionan.
    """
    mesh = mesh.copy()
    mesh.merge_vertices()
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()
    if not mesh.is_winding_consistent:
        mesh.fix_normals()
    if not mesh.is_watertight:
        try:
            mesh.fill_holes()
        except Exception:
            pass
    if mesh.is_volume and mesh.volume < 0:
        mesh.invert()
    return mesh


def weld_bodies(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Funde en un solo solido los cuerpos que se solapan.

    Muchisimos modelos descargados son en realidad varias piezas superpuestas
    (brazos, pelo, ropa...). Cortar eso directamente deja secciones abiertas,
    asi que primero lo unimos con CSG. Si la union falla devolvemos la malla
    original sin tocar.
    """
    try:
        parts = mesh.split(only_watertight=False)
    except Exception:
        return mesh
    if len(parts) < 2:
        return mesh
    # el motor CSG exige cuerpos cerrados: tapamos cada trozo antes de unir
    limpias = []
    for part in parts:
        if not part.is_watertight:
            part = part.copy()
            try:
                part.fill_holes()
                part.fix_normals()
            except Exception:
                pass
        if part.is_watertight and len(part.faces):
            limpias.append(part)
    if len(limpias) < 2:
        return mesh
    try:
        welded = trimesh.boolean.union(limpias)
    except Exception:
        return mesh
    if isinstance(welded, list):
        welded = trimesh.util.concatenate(welded) if welded else None
    if welded is None or len(welded.faces) == 0:
        return mesh
    return welded


def mesh_stats(mesh: trimesh.Trimesh) -> dict:
    size = mesh.extents
    return {
        "triangles": int(len(mesh.faces)),
        "vertices": int(len(mesh.vertices)),
        "size": [float(v) for v in size],
        "bounds": [[float(v) for v in mesh.bounds[0]], [float(v) for v in mesh.bounds[1]]],
        "volume": float(mesh.volume) if mesh.is_volume else None,
        "area": float(mesh.area),
        "watertight": bool(mesh.is_watertight),
        "bodies": int(mesh.body_count),
    }


def apply_units_and_scale(mesh: trimesh.Trimesh,
                          units: str = "mm",
                          scale: float = 1.0,
                          target_size: Optional[float] = None,
                          target_axis: str = "z") -> trimesh.Trimesh:
    """Lleva el modelo a milimetros y aplica la escala pedida.

    `target_size` tiene prioridad: reescala el modelo para que mida exactamente
    eso sobre `target_axis` (util para gran formato: "quiero 1800 mm de alto").
    """
    mesh = mesh.copy()
    factor = UNIT_SCALE.get(str(units).lower(), 1.0)
    if factor != 1.0:
        mesh.apply_scale(factor)
    if target_size:
        idx = axis_index(target_axis)
        current = float(mesh.extents[idx])
        if current <= 0:
            raise MeshError("El modelo no tiene tamano sobre el eje objetivo")
        mesh.apply_scale(float(target_size) / current)
    elif scale and scale != 1.0:
        mesh.apply_scale(float(scale))
    return mesh


def export_mesh(mesh: trimesh.Trimesh, path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext not in OUTPUT_FORMATS:
        raise MeshError(f"Formato de salida no soportado: {ext}")
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    if ext == ".glb":
        data = mesh.scene().export(file_type="glb")
        with open(path, "wb") as fh:
            fh.write(data)
        return path
    mesh.export(path)
    return path


def move_to_origin(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Deja la esquina minima de la caja en (0, 0, 0)."""
    mesh = mesh.copy()
    mesh.apply_translation(-mesh.bounds[0])
    return mesh


def drop_to_floor(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Baja la pieza hasta Z=0 conservando su posicion en XY."""
    mesh = mesh.copy()
    mesh.apply_translation([0.0, 0.0, -float(mesh.bounds[0][2])])
    return mesh


def is_empty(mesh: Optional[trimesh.Trimesh], min_volume: float = 1e-9) -> bool:
    if mesh is None or len(mesh.faces) == 0 or len(mesh.vertices) == 0:
        return True
    try:
        if mesh.is_volume and abs(mesh.volume) < min_volume:
            return True
    except Exception:
        pass
    return bool(np.all(mesh.extents <= 1e-9))
