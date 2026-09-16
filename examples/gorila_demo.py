"""Genera un gorila de prueba para Cortador.

Es una figura organica (no cajas), pensada para probar el vaciado, el corte
en laminas y las marcas con algo parecido a un modelo real.

    python examples/gorila_demo.py gorila.stl --alto 1800
"""

import argparse

import numpy as np
import trimesh


def _esfera(radio, centro, escala=(1.0, 1.0, 1.0), subdiv=3):
    m = trimesh.creation.icosphere(subdivisions=subdiv, radius=radio)
    m.apply_scale(escala)
    m.apply_translation(centro)
    return m


def _capsula(radio, largo, desde, hacia, secciones=20):
    desde = np.asarray(desde, dtype=float)
    hacia = np.asarray(hacia, dtype=float)
    m = trimesh.creation.capsule(radius=radio, height=float(largo), count=[secciones, secciones])
    direccion = hacia - desde
    norma = np.linalg.norm(direccion)
    if norma > 1e-9:
        m.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], direccion / norma))
    m.apply_translation(desde)
    return m


def build_gorilla(height: float = 1800.0, smooth: bool = True) -> trimesh.Trimesh:
    partes = []

    # tronco: pecho ancho y caderas estrechas, como un gorila de espalda plateada
    partes.append(_esfera(220, [0, 0, 1000], escala=(1.0, 0.72, 1.05)))
    partes.append(_esfera(170, [0, 0, 760], escala=(1.0, 0.8, 0.9)))
    partes.append(_esfera(120, [0, -30, 1210], escala=(1.15, 0.8, 0.6)))   # hombros

    # cabeza con cresta sagital
    partes.append(_esfera(120, [0, -20, 1370], escala=(0.95, 1.05, 1.0)))
    partes.append(_esfera(70, [0, -95, 1330], escala=(0.9, 0.9, 0.7)))     # hocico
    partes.append(_esfera(60, [0, 10, 1450], escala=(0.45, 0.9, 0.7)))     # cresta
    for lado in (-1, 1):
        partes.append(_esfera(30, [lado * 110, 10, 1370], escala=(0.5, 1.0, 1.0)))

    # brazos largos apoyados en el suelo (postura de nudillos)
    for lado in (-1, 1):
        hombro = [lado * 210, -20, 1180]
        codo = [lado * 320, -60, 820]
        nudillo = [lado * 330, -150, 180]
        partes.append(_capsula(85, np.linalg.norm(np.subtract(codo, hombro)), hombro, codo))
        partes.append(_esfera(90, codo))
        partes.append(_capsula(72, np.linalg.norm(np.subtract(nudillo, codo)), codo, nudillo))
        partes.append(_esfera(85, [lado * 330, -140, 120], escala=(1.0, 1.3, 0.7)))

    # piernas cortas y flexionadas
    for lado in (-1, 1):
        cadera = [lado * 110, 0, 720]
        rodilla = [lado * 150, -90, 420]
        pie = [lado * 150, -110, 90]
        partes.append(_capsula(95, np.linalg.norm(np.subtract(rodilla, cadera)), cadera, rodilla))
        partes.append(_esfera(90, rodilla))
        partes.append(_capsula(78, np.linalg.norm(np.subtract(pie, rodilla)), rodilla, pie))
        partes.append(_esfera(80, [lado * 150, -150, 70], escala=(1.0, 1.5, 0.6)))

    malla = trimesh.boolean.union(partes)
    if smooth:
        try:
            trimesh.smoothing.filter_taubin(malla, iterations=8)
        except Exception:
            pass
    malla.apply_translation(-malla.bounds[0])
    malla.apply_scale(float(height) / malla.extents[2])
    malla.fix_normals()
    return malla


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("salida", nargs="?", default="gorila.stl")
    ap.add_argument("--alto", type=float, default=1800.0, help="altura final en mm")
    ap.add_argument("--sin-suavizar", action="store_true")
    args = ap.parse_args()
    malla = build_gorilla(args.alto, smooth=not args.sin_suavizar)
    malla.export(args.salida)
    print(f"{args.salida}: {len(malla.faces)} triangulos, "
          f"{malla.extents[0]:.0f} x {malla.extents[1]:.0f} x {malla.extents[2]:.0f} mm, "
          f"{'cerrada' if malla.is_watertight else 'ABIERTA'}")


if __name__ == "__main__":
    main()
