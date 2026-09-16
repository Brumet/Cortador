"""Genera un modelo de prueba (figura humanoide) para probar Cortador.

    python examples/figura_demo.py figura.stl --alto 1800
"""

import argparse

import numpy as np
import trimesh


def build_figure(height: float = 1800.0) -> trimesh.Trimesh:
    """Figura de pie muy simplificada: sirve para probar cortes y marcas."""
    parts = []

    def box(extents, translate):
        m = trimesh.creation.box(extents=extents)
        m.apply_translation(translate)
        return m

    def ball(radius, translate):
        m = trimesh.creation.icosphere(subdivisions=3, radius=radius)
        m.apply_translation(translate)
        return m

    def leg(x):
        parts.append(box([90, 110, 620], [x, 0, 310]))
        parts.append(ball(60, [x, 0, 620]))
        parts.append(box([100, 150, 560], [x, 0, 900]))
        parts.append(box([120, 220, 70], [x, 30, 35]))

    leg(-90)
    leg(90)
    parts.append(box([300, 160, 420], [0, 0, 1290]))       # torso
    parts.append(ball(150, [0, 0, 1180]))                  # cadera
    parts.append(ball(120, [0, 0, 1480]))                  # pecho
    parts.append(box([90, 90, 90], [0, 0, 1540]))          # cuello
    parts.append(ball(130, [0, 0, 1660]))                  # cabeza
    for side in (-1, 1):
        arm = trimesh.creation.cylinder(radius=45, height=420, sections=24)
        arm.apply_transform(trimesh.transformations.rotation_matrix(np.radians(70), [0, 1, 0]))
        arm.apply_translation([side * 250, -40, 1330])
        parts.append(arm)
        parts.append(ball(55, [side * 175, -40, 1450]))
        parts.append(ball(50, [side * 330, -40, 1210]))

    mesh = trimesh.util.concatenate(parts)
    mesh.merge_vertices()
    mesh.apply_translation(-mesh.bounds[0])
    current = mesh.extents[2]
    mesh.apply_scale(float(height) / current)
    return mesh


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("salida", nargs="?", default="figura.stl")
    ap.add_argument("--alto", type=float, default=1800.0, help="altura final en mm")
    args = ap.parse_args()
    mesh = build_figure(args.alto)
    mesh.export(args.salida)
    print(f"{args.salida}: {len(mesh.faces)} triangulos, "
          f"{mesh.extents[0]:.0f} x {mesh.extents[1]:.0f} x {mesh.extents[2]:.0f} mm")


if __name__ == "__main__":
    main()
