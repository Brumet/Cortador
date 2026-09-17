"""Perfiles de maquina listos para usar.

Cada perfil trae el volumen real de la maquina, la boquilla que lleva de
serie y un margen de seguridad. El margen es importante: cortar justo al
limite de la cama es pedir un fallo de adherencia o un choque con el carro,
asi que ninguna pieza se planifica al raz de la capacidad.

Las FLSUN son delta y la cama es **redonda**: en ellas no cabe una pieza del
ancho del diametro, sino del cuadrado que cabe dentro (diametro / raiz de 2).
Por eso una V400 de 300 mm de diametro admite piezas de unos 200 mm de lado,
que es justo lo que dice el fabricante.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .config import PrinterSpec, SliceConfig


@dataclass
class Perfil:
    """Una maquina conocida, con los ajustes que le van bien."""

    id: str
    nombre: str
    printer: PrinterSpec
    #: espesor de piel recomendado (multiplo exacto del ancho de linea)
    wall: float
    #: holgura entre piezas
    kerf: float
    #: trozos por debajo de esto se descartan
    min_piece: float
    nota: str = ""

    def aplicar(self, cfg: Optional[SliceConfig] = None) -> SliceConfig:
        """Devuelve una configuracion con este perfil puesto."""
        cfg = cfg or SliceConfig()
        cfg.printer = PrinterSpec(**vars(self.printer))
        cfg.wall = self.wall
        cfg.kerf = self.kerf
        cfg.min_piece = self.min_piece
        return cfg

    def to_dict(self) -> dict:
        return {
            "id": self.id, "nombre": self.nombre, "nota": self.nota,
            "wall": self.wall, "kerf": self.kerf, "min_piece": self.min_piece,
            "printer": vars(self.printer),
            "util": [round(v, 1) for v in self.printer.usable()],
            "linea": self.printer.line_width(),
        }


def _fdm(id, nombre, *, x=0.0, y=0.0, z, diametro=0.0, boquilla=0.4,
         margen, wall, kerf=0.2, minimo=5.0, nota="") -> Perfil:
    printer = PrinterSpec(
        x=x or diametro, y=y or diametro, z=z, clearance=margen,
        shape="round" if diametro else "rect", diameter=diametro,
        nozzle=boquilla, technology="fdm", name=nombre,
    )
    return Perfil(id=id, nombre=nombre, printer=printer, wall=wall,
                  kerf=kerf, min_piece=minimo, nota=nota)


def _resina(id, nombre, *, x, y, z, margen, wall, nota="") -> Perfil:
    printer = PrinterSpec(x=x, y=y, z=z, clearance=margen, shape="rect",
                          nozzle=0.05, technology="resina", name=nombre)
    # en resina no hay boquilla: la pared la manda la rigidez de la pieza, y
    # el corte es mucho mas fino que en FDM
    return Perfil(id=id, nombre=nombre, printer=printer, wall=wall,
                  kerf=0.05, min_piece=2.0, nota=nota)


#: Todos los perfiles, en el orden en que se muestran.
PERFILES: List[Perfil] = [
    _fdm("flsun_v400", "FLSUN V400", diametro=300.0, z=410.0, margen=6.0,
         boquilla=0.4, wall=3.36, kerf=0.2, minimo=5.0,
         nota="Delta, cama redonda de 300 mm: la pieza mas grande que cabe "
              "es de unos 200 mm de lado. Boquilla Volcano de serie."),
    _fdm("flsun_t1", "FLSUN T1", diametro=260.0, z=330.0, margen=6.0,
         boquilla=0.4, wall=3.36, kerf=0.2, minimo=5.0,
         nota="Delta, cama redonda de 260 mm. El diametro completo solo esta "
              "disponible hasta unos 288 mm de altura, asi que la altura util "
              "va con margen."),
    _fdm("flsun_sr", "FLSUN SR (Super Racer)", diametro=260.0, z=330.0,
         margen=6.0, boquilla=0.4, wall=3.36, kerf=0.2, minimo=5.0,
         nota="Delta, cama redonda de 260 mm, boquilla Volcano de 0,4 mm."),
    _fdm("bambu_a1", "Bambu Lab A1", x=256.0, y=256.0, z=256.0, margen=5.0,
         boquilla=0.4, wall=3.36, kerf=0.2, minimo=5.0,
         nota="Cama cuadrada de 256 mm. Con boquilla de 0,6 o 0,8 el espesor "
              "de piel se recalcula solo."),
    _fdm("bambu_a1_mini", "Bambu Lab A1 mini", x=180.0, y=180.0, z=180.0,
         margen=5.0, boquilla=0.4, wall=3.36, kerf=0.2, minimo=4.0,
         nota="La pequena de la casa: 180 mm de lado."),
    _fdm("generica_220", "Generica 220 x 220 x 250", x=220.0, y=220.0, z=250.0,
         margen=5.0, boquilla=0.4, wall=3.36,
         nota="La medida tipica de una Ender 3 y parecidas."),
    _fdm("generica_300", "Generica 300 x 300 x 400", x=300.0, y=300.0, z=400.0,
         margen=6.0, boquilla=0.6, wall=3.78,
         nota="Formato grande con boquilla de 0,6 mm."),
    _resina("resina_pequena", "Resina 6\" (Mars / Photon)", x=143.0, y=89.0,
            z=175.0, margen=2.0, wall=2.1,
            nota="Pantalla de 6 pulgadas. En resina las piezas salen mucho mas "
                 "pequenas, pero el detalle es altisimo y las juntas encajan "
                 "con muy poca holgura."),
    _resina("resina_grande", "Resina 10\" (Saturn / Sonic)", x=218.0, y=123.0,
            z=250.0, margen=2.0, wall=2.1,
            nota="Pantalla de 10 pulgadas, el formato comodo para figuras "
                 "grandes por partes."),
]

POR_ID: Dict[str, Perfil] = {p.id: p for p in PERFILES}


def perfil(id: str) -> Perfil:
    """Busca un perfil por su id. Lanza KeyError si no existe."""
    clave = str(id or "").strip().lower()
    if clave not in POR_ID:
        raise KeyError(f"Perfil desconocido: {id!r}")
    return POR_ID[clave]


def como_lista() -> List[dict]:
    """Los perfiles en forma de diccionario, para la interfaz."""
    return [p.to_dict() for p in PERFILES]
