"""Reconstruye una malla 3D a partir de un archivo de capas (contornos).

Sirve para recuperar un modelo guardado como contornos por capa (el formato
`{"alto", "q", "capas"}` que usa el catalogo de Brumet) y dejarlo en STL para
poder cortarlo con Cortador.

    python examples/desde_capas.py gorila.json gorila.stl --alto 1800
"""

import argparse
import json

import numpy as np
import trimesh

from cortador.geometry import polygons_from_loops


def puntos_de_contorno(codificado, q):
    """Los contornos vienen como punto inicial + incrementos, cuantizados."""
    x, y = float(codificado[0]), float(codificado[1])
    pts = [(x, y)]
    for i in range(2, len(codificado) - 1, 2):
        x += codificado[i]
        y += codificado[i + 1]
        pts.append((x, y))
    return np.asarray(pts, dtype=float) / float(q)


def mesh_from_layers(datos, altura_final=None):
    capas = datos["capas"]
    q = float(datos.get("q", 4096))
    proporcion = float(datos.get("alto", 1.0))     # alto respecto al ancho
    paso = proporcion / max(len(capas), 1)

    solidos = []
    for i, capa in enumerate(capas):
        contornos = [puntos_de_contorno(c, q) for c in capa if len(c) >= 6]
        for poligono in polygons_from_loops(contornos):
            if poligono.area <= 0:
                continue
            try:
                trozo = trimesh.creation.extrude_polygon(poligono, paso * 1.35)
            except Exception:
                continue
            trozo.apply_translation([0.0, 0.0, i * paso])
            solidos.append(trozo)

    if not solidos:
        raise SystemExit("El archivo no tiene contornos utilizables")
    malla = trimesh.util.concatenate(solidos)
    malla.merge_vertices()
    malla.apply_translation(-malla.bounds[0])
    if altura_final:
        malla.apply_scale(float(altura_final) / malla.extents[2])
    return malla


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("entrada", help="archivo JSON de capas")
    ap.add_argument("salida", nargs="?", default=None, help="archivo STL de salida")
    ap.add_argument("--alto", type=float, default=None, help="altura final en mm")
    args = ap.parse_args()

    datos = json.load(open(args.entrada, encoding="utf-8"))
    malla = mesh_from_layers(datos, args.alto)
    destino = args.salida or args.entrada.rsplit(".", 1)[0] + ".stl"
    malla.export(destino)
    print(f"{destino}: {len(malla.faces)} triangulos, "
          f"{malla.extents[0]:.0f} x {malla.extents[1]:.0f} x {malla.extents[2]:.0f} mm, "
          f"{len(datos['capas'])} capas")


if __name__ == "__main__":
    main()
