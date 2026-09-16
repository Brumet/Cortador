"""Interfaz de linea de comandos de Cortador."""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import List, Optional

from .config import (JoineryOptions, LabelOptions, PrinterSpec, SliceConfig,
                     UNIT_SCALE, axis_index)
from .exporters import export_result, zip_directory
from .meshio import INPUT_FORMATS, load_mesh, mesh_stats
from .planner import estimate_plan
from .repair import (auto_repair, diagnose, is_windows,
                     open_in_windows_repair, repaired_copy_path)
from .slicer import slice_model

STYLE_MAP = {"grabado": "engrave", "relieve": "emboss",
             "engrave": "engrave", "emboss": "emboss"}
PLACEMENT_MAP = {"auto": "auto", "cortes": "cuts", "cuts": "cuts",
                 "abajo": "bottom", "bottom": "bottom"}
MODE_MAP = {"trozos": "chunks", "chunks": "chunks",
            "laminas": "slabs", "slabs": "slabs", "capas": "slabs"}
SLAB_STYLE_MAP = {"solido": "solid", "solid": "solid",
                  "placa": "prism", "prism": "prism", "plana": "prism"}
JOINERY_MAP = {"ninguna": "none", "none": "none", "no": "none",
               "agujeros": "holes", "holes": "holes",
               "machohembra": "pins", "espigas": "pins", "pins": "pins"}
ENGINE_MAP = {"auto": "auto", "planos": "slice", "slice": "slice",
              "booleano": "boolean", "boolean": "boolean"}


def parse_volume(text: str) -> PrinterSpec:
    """'220x220x250' -> PrinterSpec."""
    parts = str(text).lower().replace(",", ".").replace("*", "x").split("x")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            "El volumen se indica como ANCHOxFONDOxALTO, por ejemplo 220x220x250")
    try:
        x, y, z = (float(p) for p in parts)
    except ValueError:
        raise argparse.ArgumentTypeError("Las medidas del volumen deben ser numeros")
    if min(x, y, z) <= 0:
        raise argparse.ArgumentTypeError("Las medidas del volumen deben ser positivas")
    return PrinterSpec(x=x, y=y, z=z)


def parse_divisions(text: Optional[str]) -> Optional[List[Optional[int]]]:
    if not text:
        return None
    parts = str(text).lower().replace("*", "x").split("x")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("Las divisiones se indican como NxNxN, por ejemplo 3x2x4")
    out: List[Optional[int]] = []
    for part in parts:
        part = part.strip()
        out.append(None if part in ("", "-", "auto", "0") else max(1, int(part)))
    return out


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("modelo", help="archivo del modelo 3D (%s)" % ", ".join(INPUT_FORMATS))
    parser.add_argument("-i", "--impresora", type=parse_volume, default=parse_volume("220x220x250"),
                        metavar="AxBxC",
                        help="volumen util de la maquina en mm (por defecto 220x220x250)")
    parser.add_argument("--margen", type=float, default=0.0,
                        help="margen de seguridad descontado a cada eje (mm)")
    parser.add_argument("--modo", choices=sorted(MODE_MAP), default="trozos",
                        help="'trozos' para dividir por capacidad, 'laminas' para cortar por capas")
    parser.add_argument("--espesor", type=float, default=5.0,
                        help="espesor de cada lamina en mm (modo laminas)")
    parser.add_argument("--eje", default="z", choices=["x", "y", "z"],
                        help="eje de apilado de las laminas")
    parser.add_argument("--estilo-lamina", choices=sorted(SLAB_STYLE_MAP), default="solido",
                        help="'solido' conserva el relieve; 'placa' extruye el contorno (laser/CNC)")
    parser.add_argument("--ajuste-lamina", choices=["exacto", "repartido"], default="exacto",
                        help="'exacto' respeta el espesor; 'repartido' iguala todas las laminas")
    parser.add_argument("--no-subdividir-laminas", action="store_true",
                        help="no partir las laminas aunque no quepan en la maquina")
    parser.add_argument("--divisiones", type=parse_divisions, default=None, metavar="NxNxN",
                        help="forzar el numero de divisiones por eje (usa '-' para automatico)")
    parser.add_argument("--kerf", type=float, default=0.0,
                        help="holgura entre piezas en mm (se reparte entre las dos caras)")
    parser.add_argument("--escala", type=float, default=1.0, help="escala uniforme del modelo")
    parser.add_argument("--tamano", type=float, default=None,
                        help="tamano final en mm sobre el eje indicado en --tamano-eje")
    parser.add_argument("--tamano-eje", default="z", choices=["x", "y", "z"])
    parser.add_argument("--unidades", default="mm", choices=sorted(UNIT_SCALE),
                        help="unidades del archivo de entrada")
    parser.add_argument("--motor", choices=sorted(ENGINE_MAP), default="auto",
                        help="motor de corte")
    parser.add_argument("--nombres", choices=["grid", "numeric"], default="grid",
                        help="nomenclatura de las piezas")
    parser.add_argument("--no-unir", action="store_true",
                        help="no fundir los cuerpos superpuestos del modelo antes de cortar")


def _add_marking(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--sin-marcas", action="store_true", help="no marcar las piezas")
    parser.add_argument("--marca-estilo", choices=sorted(STYLE_MAP), default="grabado")
    parser.add_argument("--marca-tam", type=float, default=8.0, help="altura de letra en mm")
    parser.add_argument("--marca-prof", type=float, default=0.8,
                        help="profundidad del grabado o altura del relieve en mm")
    parser.add_argument("--marca-trazo", type=float, default=1.2, help="grosor del trazo en mm")
    parser.add_argument("--marca-caras", choices=sorted(PLACEMENT_MAP), default="auto",
                        help="'auto' una marca por pieza, 'cortes' una en cada cara de corte")
    parser.add_argument("--prefijo", default="", help="texto que se anade delante de cada nombre")
    parser.add_argument("--espigas", choices=sorted(JOINERY_MAP), default="ninguna",
                        help="pasadores de alineacion en las caras de corte")
    parser.add_argument("--espiga-radio", type=float, default=3.0)
    parser.add_argument("--espiga-prof", type=float, default=6.0)
    parser.add_argument("--espiga-num", type=int, default=2, help="pasadores por cara")
    parser.add_argument("--espiga-holgura", type=float, default=0.2)


def build_config(args) -> SliceConfig:
    printer = args.impresora
    printer.clearance = float(args.margen)
    labels = LabelOptions(
        enabled=not args.sin_marcas,
        style=STYLE_MAP[args.marca_estilo],
        size=args.marca_tam,
        depth=args.marca_prof,
        stroke=args.marca_trazo,
        placement=PLACEMENT_MAP[args.marca_caras],
        prefix=args.prefijo,
    )
    joinery = JoineryOptions(
        mode=JOINERY_MAP[args.espigas],
        radius=args.espiga_radio,
        depth=args.espiga_prof,
        clearance=args.espiga_holgura,
        count=max(1, args.espiga_num),
    )
    cfg = SliceConfig(
        printer=printer,
        mode=MODE_MAP[args.modo],
        slab_thickness=args.espesor,
        slab_axis=args.eje,
        slab_style=SLAB_STYLE_MAP[args.estilo_lamina],
        slab_fit="exact" if args.ajuste_lamina == "exacto" else "even",
        split_slabs_to_fit=not args.no_subdividir_laminas,
        divisions=args.divisiones,
        kerf=args.kerf,
        scale=args.escala,
        target_size=args.tamano,
        target_axis=args.tamano_eje,
        units=args.unidades,
        engine=ENGINE_MAP[args.motor],
        weld=not args.no_unir,
        naming=args.nombres,
        labels=labels,
        joinery=joinery,
    )
    cfg.validate()
    return cfg


class _Bar:
    """Barra de progreso minima para la terminal."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled and sys.stderr.isatty()
        self.last = 0.0

    def __call__(self, done: int, total: int, msg: str) -> None:
        if not self.enabled:
            return
        now = time.time()
        if now - self.last < 0.08 and done < total:
            return
        self.last = now
        total = max(total, 1)
        width = 28
        filled = int(width * done / total)
        sys.stderr.write(f"\r{msg:<22} [{'#' * filled}{'.' * (width - filled)}] {done}/{total}")
        sys.stderr.flush()
        if done >= total:
            sys.stderr.write("\n")


def cmd_info(args) -> int:
    # sin reparar: aqui queremos ver el archivo tal y como esta
    mesh = load_mesh(args.modelo, repair=False)
    stats = mesh_stats(mesh)
    print(f"Archivo      : {args.modelo}")
    print(f"Triangulos   : {stats['triangles']:,}".replace(",", "."))
    print(f"Tamano (mm)  : {stats['size'][0]:.2f} x {stats['size'][1]:.2f} x {stats['size'][2]:.2f}")
    print(f"Estanca      : {'si' if stats['watertight'] else 'NO (conviene reparar)'}")
    print(f"Cuerpos      : {stats['bodies']}")
    if stats["volume"]:
        print(f"Volumen      : {stats['volume'] / 1000.0:.1f} cm3")
    problemas = diagnose(mesh)
    if problemas:
        print("Problemas    :")
        for p in problemas:
            print(f"  - {p}")
        _reparada, informe = auto_repair(mesh)
        print(f"Si se repara : {informe.resumen()}")
        print(f"Hazlo con    : cortador reparar \"{args.modelo}\"")
    else:
        print("Problemas    : ninguno, lista para cortar")
    return 0


def cmd_plan(args) -> int:
    cfg = build_config(args)
    mesh = load_mesh(args.modelo, repair=True)
    from .meshio import apply_units_and_scale
    work = apply_units_and_scale(mesh, cfg.units, cfg.scale, cfg.target_size, cfg.target_axis)
    plan = estimate_plan(work.bounds, cfg)
    size = work.extents
    print(f"Modelo       : {size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm")
    print(f"Maquina      : {cfg.printer.x:.0f} x {cfg.printer.y:.0f} x {cfg.printer.z:.0f} mm")
    print(f"Rejilla      : {plan['counts'][0]} x {plan['counts'][1]} x {plan['counts'][2]}")
    print(f"Piezas (max) : {plan['total_cells']}")
    print("Pieza mayor  : {:.1f} x {:.1f} x {:.1f} mm".format(*plan["piece_size"]))
    print(f"Capas        : {plan['layers']} sobre el eje {'XYZ'[plan['layer_axis']]}")
    for warn in plan["warnings"]:
        print(f"  aviso: {warn}")
    return 0


def cmd_cut(args) -> int:
    cfg = build_config(args)
    bar = _Bar(not args.silencioso)
    print(f"Cargando {args.modelo} ...")
    mesh = load_mesh(args.modelo, repair=True)
    mesh, informe = auto_repair(mesh, weld=not args.no_unir)
    if informe.cambiada or informe.problemas:
        print(informe.resumen())
    start = time.time()
    result = slice_model(mesh, cfg, progress=bar)
    model_name = os.path.splitext(os.path.basename(args.modelo))[0]
    outdir = args.salida or os.path.join(os.getcwd(), f"{model_name}_cortado")
    os.makedirs(outdir, exist_ok=True)
    info = export_result(result, outdir, mesh_format=args.formato,
                         place_at_origin=not args.en_sitio,
                         model_name=model_name, progress=bar)
    if args.zip:
        zip_path = os.path.join(outdir, f"{model_name}_cortado.zip")
        zip_directory(outdir, zip_path)
        print(f"ZIP          : {zip_path}")
    print(f"Piezas       : {result.count}")
    print(f"Tiempo       : {time.time() - start:.1f} s")
    print(f"Carpeta      : {info['outdir']}")
    if result.dowels:
        print(f"Espigas      : {result.dowels}")
    for warn in result.warnings:
        print(f"  aviso: {warn}")
    return 0


def cmd_repair(args) -> int:
    if args.windows:
        abierto, mensaje = open_in_windows_repair(args.modelo)
        print(mensaje)
        return 0 if abierto else 1

    mesh = load_mesh(args.modelo, repair=False)
    antes = diagnose(mesh)
    if antes:
        print("Problemas encontrados:")
        for p in antes:
            print(f"  - {p}")
    else:
        print("La malla no tiene problemas evidentes.")

    reparada, informe = auto_repair(mesh, weld=not args.no_unir)
    print(informe.resumen())

    destino = args.salida or repaired_copy_path(args.modelo)
    reparada.export(destino)
    print(f"Guardado     : {destino}")
    if not informe.estanca_despues:
        if is_windows():
            print("Sigue abierta. Prueba con:  cortador reparar "
                  f"\"{args.modelo}\" --windows")
        else:
            print("Sigue abierta. Abrela con Meshlab, Blender o 3D Builder (Windows) "
                  "y usa su reparador.")
        return 2
    return 0


def cmd_web(args) -> int:
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        print("Falta el extra 'web': instala con  pip install 'cortador[web]'", file=sys.stderr)
        return 2
    from .web.server import run
    run(host=args.host, port=args.puerto, open_browser=not args.sin_navegador)
    return 0


def cmd_font(args) -> int:
    from .labels import text_preview_svg
    svg = text_preview_svg(args.texto, size=args.tam, stroke=args.trazo)
    if args.salida:
        with open(args.salida, "w", encoding="utf-8") as fh:
            fh.write(svg)
        print(args.salida)
    else:
        print(svg)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortador",
        description="Corta modelos 3D en piezas imprimibles o en laminas, y las marca "
                    "para poder armarlas despues.",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p_cut = sub.add_parser("cortar", aliases=["cut"], help="cortar un modelo y exportar las piezas")
    _add_common(p_cut)
    _add_marking(p_cut)
    p_cut.add_argument("-o", "--salida", default=None, help="carpeta de salida")
    p_cut.add_argument("--formato", default="stl", choices=["stl", "obj", "ply", "3mf"])
    p_cut.add_argument("--en-sitio", action="store_true",
                       help="exportar las piezas en su posicion dentro del modelo "
                            "(por defecto cada pieza se guarda en el origen)")
    p_cut.add_argument("--zip", action="store_true", help="comprimir la carpeta al terminar")
    p_cut.add_argument("--silencioso", action="store_true")
    p_cut.set_defaults(func=cmd_cut)

    p_plan = sub.add_parser("plan", help="ver el plan de corte sin generar piezas")
    _add_common(p_plan)
    _add_marking(p_plan)
    p_plan.set_defaults(func=cmd_plan)

    p_info = sub.add_parser("info", help="informacion del modelo")
    p_info.add_argument("modelo")
    p_info.set_defaults(func=cmd_info)

    p_rep = sub.add_parser("reparar", help="reparar la malla antes de cortar")
    p_rep.add_argument("modelo")
    p_rep.add_argument("-o", "--salida", default=None,
                       help="archivo reparado (por defecto  <modelo>_reparado.stl)")
    p_rep.add_argument("--no-unir", action="store_true",
                       help="no fundir los cuerpos superpuestos")
    p_rep.add_argument("--windows", action="store_true",
                       help="abrir el modelo en 3D Builder de Windows para repararlo a mano")
    p_rep.set_defaults(func=cmd_repair)

    p_web = sub.add_parser("web", help="abrir la interfaz grafica en el navegador")
    p_web.add_argument("--puerto", type=int, default=8000)
    p_web.add_argument("--host", default="127.0.0.1")
    p_web.add_argument("--sin-navegador", action="store_true")
    p_web.set_defaults(func=cmd_web)

    p_font = sub.add_parser("texto", help="previsualizar la tipografia de las marcas en SVG")
    p_font.add_argument("texto")
    p_font.add_argument("--tam", type=float, default=10.0)
    p_font.add_argument("--trazo", type=float, default=1.5)
    p_font.add_argument("-o", "--salida", default=None)
    p_font.set_defaults(func=cmd_font)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nCancelado.", file=sys.stderr)
        return 130
    except Exception as exc:  # errores de usuario: mensaje claro, sin traza
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
