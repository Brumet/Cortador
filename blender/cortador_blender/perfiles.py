"""Las maquinas que conocemos, con lo que de verdad les cabe.

Un perfil no es solo "cuanto mide la cama". Lleva tres cosas que cambian el
resultado del corte:

* **El margen.** Cortar justo al limite de la cama es pedir un fallo de
  adherencia o un choque con el carro, asi que a cada eje se le quita un poco.
* **La forma de la cama.** Las delta la tienen redonda, y ahi no cabe una
  pieza del ancho del diametro. Pero tampoco es cierto que solo quepa el
  cuadrado inscrito: una lamina fina **si** puede cruzar la cama por el
  diametro. Lo que decide es el teorema de Pitagoras, y asi se mide aqui.
* **La boquilla.** De ella sale el ancho de linea, y de ahi el espesor de
  pared que tiene sentido: uno que sea multiplo exacto del ancho de linea,
  para que el laminador lo llene con perimetros enteros y no deje una franja
  a medias.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class Perfil:
    """Una maquina conocida."""

    id: str
    nombre: str
    #: cama: ancho y fondo (mm); en las redondas, los dos son el diametro
    x: float
    y: float
    z: float
    #: margen de seguridad que se le quita a cada eje
    margen: float
    #: 'rect' o 'redonda'
    forma: str = "rect"
    boquilla: float = 0.4
    #: 'fdm' o 'resina'
    tecnologia: str = "fdm"
    nota: str = ""

    @property
    def redonda(self) -> bool:
        return self.forma == "redonda"

    def alto_util(self) -> float:
        return max(self.z - 2 * self.margen, 1.0)

    def ancho_linea(self) -> float:
        """Lo que extruye de verdad el laminador: un pelin mas que la boquilla."""
        return round(max(self.boquilla, 0.05) * 1.05, 3)

    def pared(self, perimetros: int = 4) -> float:
        """Espesor de pared que es multiplo exacto del ancho de linea."""
        if self.tecnologia == "resina":
            return 2.1
        return round(max(1, int(perimetros)) * self.ancho_linea(), 2)

    def cabe(self, ancho: float, fondo: float) -> bool:
        """Si una pieza de esa planta cabe en la cama.

        En la cama redonda no se compara contra el cuadrado inscrito sino
        contra la diagonal de la pieza: una lamina de 290 x 20 **si** cabe
        cruzada en una cama de 300, aunque el cuadrado inscrito sea de 212.
        Es justo el caso de las piezas que salen de aqui, que son laminas.
        """
        ancho, fondo = max(ancho, fondo), min(ancho, fondo)
        if self.redonda:
            libre = max(self.x - 2 * self.margen, 1.0)
            return math.hypot(ancho, fondo) <= libre
        largo = max(self.x, self.y) - 2 * self.margen
        corto = min(self.x, self.y) - 2 * self.margen
        return ancho <= largo and fondo <= corto

    def caja(self) -> Tuple[float, float]:
        """El rectangulo seguro que siempre cabe: corto y largo.

        En la cama redonda es el cuadrado inscrito. Es menos de lo que cabe de
        verdad -una lamina fina cruza por el diametro-, pero para **contar**
        cuantas piezas van a salir conviene quedarse corto y no prometer de
        mas; quien decide de verdad si una pieza cabe es `cabe`.
        """
        if self.redonda:
            lado = (self.x - 2 * self.margen) / math.sqrt(2.0)
            return (max(lado, 1.0), max(lado, 1.0))
        return (max(min(self.x, self.y) - 2 * self.margen, 1.0),
                max(max(self.x, self.y) - 2 * self.margen, 1.0))

    def en_unidades(self, mm_por_unidad: float) -> "Perfil":
        """El mismo perfil medido en unidades de Blender, no en milimetros.

        Blender no sabe de milimetros: sabe de unidades, y cuantos milimetros
        vale una unidad lo dice la escena. En una escena metrica de serie una
        unidad es un metro, o sea mil milimetros; en una montada en milimetros
        vale uno. Sin esta cuenta, una figura de dos metros parece que mide dos
        milimetros y el plan sale disparatado.
        """
        k = 1.0 / max(mm_por_unidad, 1e-9)
        return Perfil(self.id, self.nombre, self.x * k, self.y * k,
                      self.z * k, self.margen * k, self.forma, self.boquilla,
                      self.tecnologia, self.nota)

    def ancho_para(self, fondo: float) -> float:
        """Lo mas ancha que puede ser una pieza con ese fondo.

        Para una lamina de poco fondo, en una delta esto se acerca al diametro
        entero, que es precisamente lo que se quiere aprovechar.
        """
        fondo = max(fondo, 0.0)
        if self.redonda:
            libre = max(self.x - 2 * self.margen, 1.0)
            return math.sqrt(max(libre * libre - fondo * fondo, 1.0))
        largo = max(self.x, self.y) - 2 * self.margen
        corto = min(self.x, self.y) - 2 * self.margen
        return largo if fondo <= corto else max(corto, 1.0)


PERFILES: List[Perfil] = [
    Perfil("flsun_v400", "FLSUN V400", 300.0, 300.0, 410.0, 6.0, "redonda",
           0.4, "fdm",
           "Delta de 300 mm de diametro. Como las piezas salen en lamina, "
           "puede aprovechar casi el diametro entero cruzandolas."),
    Perfil("flsun_t1", "FLSUN T1", 260.0, 260.0, 330.0, 6.0, "redonda",
           0.4, "fdm", "Delta de 260 mm."),
    Perfil("flsun_sr", "FLSUN SR (Super Racer)", 260.0, 260.0, 330.0, 6.0,
           "redonda", 0.4, "fdm", "Delta de 260 mm con boquilla Volcano."),
    Perfil("bambu_a1", "Bambu Lab A1", 256.0, 256.0, 256.0, 5.0, "rect",
           0.4, "fdm", "Cama cuadrada de 256 mm."),
    Perfil("bambu_a1_mini", "Bambu Lab A1 mini", 180.0, 180.0, 180.0, 5.0,
           "rect", 0.4, "fdm", "La pequena de la casa."),
    Perfil("generica_220", "Generica 220 x 220 x 250", 220.0, 220.0, 250.0,
           5.0, "rect", 0.4, "fdm", "La medida tipica de una Ender 3."),
    Perfil("generica_300", "Generica 300 x 300 x 400", 300.0, 300.0, 400.0,
           6.0, "rect", 0.6, "fdm", "Formato grande con boquilla de 0,6."),
    Perfil("resina_6", "Resina 6\" (Mars / Photon)", 143.0, 89.0, 175.0, 2.0,
           "rect", 0.05, "resina", "Pantalla de 6 pulgadas."),
    Perfil("resina_10", "Resina 10\" (Saturn / Sonic)", 218.0, 123.0, 250.0,
           2.0, "rect", 0.05, "resina", "Pantalla de 10 pulgadas."),
]

POR_ID: Dict[str, Perfil] = {p.id: p for p in PERFILES}


def perfil(id: str) -> Perfil:
    return POR_ID.get(str(id or "").strip().lower(), PERFILES[0])


def para_enum() -> List[Tuple[str, str, str]]:
    """La lista tal y como la quiere un EnumProperty de Blender."""
    return [(p.id, p.nombre, p.nota) for p in PERFILES]
