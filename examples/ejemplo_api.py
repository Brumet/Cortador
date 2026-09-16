"""Ejemplo de uso de Cortador como libreria.

    python examples/ejemplo_api.py figura.stl
"""

import sys

from cortador import (JoineryOptions, LabelOptions, PrinterSpec, SliceConfig,
                      export_result, load_mesh, slice_model)


def main() -> None:
    ruta = sys.argv[1] if len(sys.argv) > 1 else "figura.stl"
    malla = load_mesh(ruta)

    cfg = SliceConfig(
        printer=PrinterSpec(220, 220, 250, clearance=3),
        mode="chunks",            # "slabs" para cortar en laminas
        kerf=0.3,                 # holgura de montaje
        target_size=1800,         # escalar a 1,80 m de alto
        labels=LabelOptions(size=12, depth=1.0, placement="auto"),
        joinery=JoineryOptions(mode="holes", radius=3, depth=8, count=2),
    )

    def progreso(hecho, total, mensaje):
        print(f"\r{mensaje}: {hecho}/{total}", end="", flush=True)

    resultado = slice_model(malla, cfg, progress=progreso)
    print()

    for aviso in resultado.warnings:
        print("aviso:", aviso)

    print(f"{resultado.count} piezas, {resultado.dowels} espigas")
    for pieza in resultado.pieces[:5]:
        ancho, fondo, alto = pieza.size
        print(f"  {pieza.name:10s} {ancho:6.1f} x {fondo:6.1f} x {alto:6.1f} mm "
              f"-> vecinas: {', '.join(pieza.neighbors.values()) or '-'}")

    export_result(resultado, "salida", mesh_format="stl", model_name="figura")
    print("escrito en salida/")


if __name__ == "__main__":
    main()
