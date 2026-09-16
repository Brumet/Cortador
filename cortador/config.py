"""Opciones de configuracion del cortador.

Todas las medidas estan en milimetros salvo que se indique lo contrario.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional, Sequence

AXES = ("x", "y", "z")
AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def axis_index(axis) -> int:
    """Devuelve 0/1/2 a partir de 'x'/'y'/'z' o de un entero."""
    if isinstance(axis, int):
        if axis not in (0, 1, 2):
            raise ValueError("El eje debe ser 0, 1 o 2")
        return axis
    key = str(axis).strip().lower()
    if key not in AXIS_INDEX:
        raise ValueError(f"Eje desconocido: {axis!r} (usa x, y o z)")
    return AXIS_INDEX[key]


@dataclass
class PrinterSpec:
    """Capacidad de la maquina (volumen de impresion util)."""

    x: float = 200.0
    y: float = 200.0
    z: float = 200.0
    #: margen de seguridad que se descuenta a cada eje (adherencia, brim, etc.)
    clearance: float = 0.0

    def usable(self) -> tuple:
        return (
            max(self.x - 2 * self.clearance, 1e-6),
            max(self.y - 2 * self.clearance, 1e-6),
            max(self.z - 2 * self.clearance, 1e-6),
        )

    def fits(self, size: Sequence[float]) -> bool:
        u = self.usable()
        return all(size[i] <= u[i] + 1e-6 for i in range(3))


@dataclass
class LabelOptions:
    """Marcas (letras/numeros) grabadas o en relieve sobre cada pieza."""

    enabled: bool = True
    #: 'engrave' (hueco) o 'emboss' (relieve)
    style: str = "engrave"
    #: altura de mayuscula del texto
    size: float = 8.0
    #: profundidad del grabado / altura del relieve
    depth: float = 0.8
    #: grosor del trazo
    stroke: float = 1.2
    #: 'auto' = una marca por pieza; 'cuts' = una marca en cada cara de corte
    placement: str = "auto"
    #: cuando placement='cuts', anade el nombre de la pieza vecina (A1>B1)
    with_neighbor: bool = True
    #: numero maximo de caras marcadas por pieza cuando placement='cuts'
    max_faces: int = 6
    #: texto extra que se anade a todas las piezas (por ejemplo el proyecto)
    prefix: str = ""


@dataclass
class JoineryOptions:
    """Pasadores de alineacion en las caras de corte."""

    #: 'none' | 'holes' (agujeros en ambas caras + espigas sueltas) | 'pins' (macho/hembra)
    mode: str = "none"
    #: radio nominal de la espiga
    radius: float = 3.0
    #: profundidad dentro de cada pieza
    depth: float = 6.0
    #: holgura radial para que entre a presion suave
    clearance: float = 0.2
    #: cuantos pasadores por cara de corte
    count: int = 2
    #: separacion minima al borde de la pieza
    margin: float = 3.0


@dataclass
class SliceConfig:
    """Configuracion completa de un trabajo de corte."""

    printer: PrinterSpec = field(default_factory=PrinterSpec)
    #: 'chunks' = trozos que caben en la impresora
    #: 'slabs'  = laminas de espesor fijo (opcionalmente subdivididas para que quepan)
    mode: str = "chunks"

    # --- modo laminas -------------------------------------------------
    #: espesor de cada lamina (3 mm, 5 mm, ...)
    slab_thickness: float = 5.0
    #: eje de apilado de las laminas
    slab_axis: str = "z"
    #: 'solid'  = rebanada real del modelo (conserva el relieve dentro del espesor)
    #: 'prism'  = contorno de la seccion extruido (placa plana para laser/CNC)
    slab_style: str = "solid"
    #: 'exact' = todas las laminas del espesor pedido (la ultima puede ser menor)
    #: 'even'  = reparte el espesor para que todas sean iguales
    slab_fit: str = "exact"
    #: subdividir tambien en XY si la lamina no cabe en la maquina
    split_slabs_to_fit: bool = True

    # --- modo trozos --------------------------------------------------
    #: divisiones forzadas por eje (None = calcular a partir de la impresora)
    divisions: Optional[Sequence[Optional[int]]] = None

    # --- comunes ------------------------------------------------------
    #: separacion entre piezas (holgura de ensamble); se reparte a ambos lados del corte
    kerf: float = 0.0
    #: escala uniforme aplicada al modelo antes de cortar
    scale: float = 1.0
    #: tamano objetivo (mm) sobre un eje; sustituye a `scale` si esta definido
    target_size: Optional[float] = None
    target_axis: str = "z"
    #: unidades del archivo de entrada ('mm', 'cm', 'm', 'in')
    units: str = "mm"
    #: 'auto' | 'slice' (cortes por plano, rapido) | 'boolean' (CSG, robusto)
    engine: str = "auto"
    #: intentar reparar la malla al cargarla
    repair: bool = True
    #: fundir con CSG los cuerpos superpuestos antes de cortar (recomendado)
    weld: bool = True
    #: nomenclatura de piezas: 'grid' (A1-L01) o 'numeric' (X01Y01Z01)
    naming: str = "grid"

    labels: LabelOptions = field(default_factory=LabelOptions)
    joinery: JoineryOptions = field(default_factory=JoineryOptions)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SliceConfig":
        data = dict(data or {})
        printer = data.pop("printer", None)
        labels = data.pop("labels", None)
        joinery = data.pop("joinery", None)
        known = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in data.items() if k in known}
        cfg = cls(**clean)
        if printer:
            cfg.printer = PrinterSpec(**{k: v for k, v in printer.items()
                                         if k in PrinterSpec.__dataclass_fields__})
        if labels:
            cfg.labels = LabelOptions(**{k: v for k, v in labels.items()
                                         if k in LabelOptions.__dataclass_fields__})
        if joinery:
            cfg.joinery = JoineryOptions(**{k: v for k, v in joinery.items()
                                            if k in JoineryOptions.__dataclass_fields__})
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.mode not in ("chunks", "slabs"):
            raise ValueError("mode debe ser 'chunks' o 'slabs'")
        if self.slab_thickness <= 0:
            raise ValueError("El espesor de lamina debe ser mayor que cero")
        if self.slab_style not in ("solid", "prism"):
            raise ValueError("slab_style debe ser 'solid' o 'prism'")
        if self.slab_fit not in ("exact", "even"):
            raise ValueError("slab_fit debe ser 'exact' o 'even'")
        if self.engine not in ("auto", "slice", "boolean"):
            raise ValueError("engine debe ser 'auto', 'slice' o 'boolean'")
        if self.labels.style not in ("engrave", "emboss"):
            raise ValueError("El estilo de marca debe ser 'engrave' o 'emboss'")
        if self.joinery.mode not in ("none", "holes", "pins"):
            raise ValueError("joinery.mode debe ser 'none', 'holes' o 'pins'")
        if self.kerf < 0:
            raise ValueError("El kerf no puede ser negativo")
        axis_index(self.slab_axis)
        axis_index(self.target_axis)


UNIT_SCALE = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "inch": 25.4, "ft": 304.8}
