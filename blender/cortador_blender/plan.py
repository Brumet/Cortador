"""Donde van los cortes. Aqui no se toca geometria, solo se decide.

El reparto que se hace aqui es el que se hace a mano en el taller, y en ese
orden:

1. **Secciones horizontales.** Se parte la figura en pisos de la misma altura.
   De la misma, no del maximo que quepa: si la figura mide 60 cm y en la
   maquina caben 25, tres pisos de 20 son mucho mejores que dos de 25 y uno de
   10, porque las tres piezas salen iguales, tardan lo mismo y no sobra un
   trozo raro al final.
2. **Gajos.** Cada piso se abre en gajos como una naranja. No en cuadricula:
   una cuadricula corta por donde se cruzan los cubos y deja piezas pequenas
   que solo anaden trabajo de pegado. Un gajo, en cambio, es la pieza natural
   de una figura hueca: un trozo de cascara que, puesto de canto en la cama,
   ocupa poquisimo fondo.

Y de ahi sale lo que mas se aprovecha en una maquina delta. La cama es
redonda, y la costumbre dice que solo cabe el cuadrado inscrito -212 mm en una
de 300-. Pero eso vale para una caja, no para una lamina: una lamina de 30 mm
de fondo cabe cruzada hasta 298 mm. Por eso los gajos se miden con Pitagoras
contra el diametro y no contra el cuadrado, y salen bastantes menos piezas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import bpy
import numpy as np
from mathutils import Vector

from .cortar import Plano
from .perfiles import Perfil

#: cuantos puntos como mucho se usan para medir un gajo
MUESTRA = 60_000
#: por debajo de esto no se molesta en hacer gajos
GAJOS_MIN = 1
#: y por encima tampoco, que ya seria una figura imposible de montar
GAJOS_MAX = 24


@dataclass
class Ajustes:
    """Lo que el usuario decide antes de cortar."""

    perfil: Perfil
    #: numero de pisos; 0 = los que hagan falta
    secciones: int = 0
    #: altura de piso pedida a mano; 0 = repartir por igual
    alto_seccion: float = 0.0
    #: gajos por piso; 0 = los que hagan falta
    gajos: int = 0
    #: espesor de la pared que le puso el usuario con Solidificar
    pared: float = 3.0
    #: girar el reparto de gajos, para que un corte no caiga en una cara
    giro: float = 0.0
    #: piezas mas pequenas que esto se avisan
    minimo: float = 5.0
    #: grabar en cada pieza su nombre y el de sus vecinas
    marcar: bool = True
    #: hondo del grabado
    hondo: float = 0.6


@dataclass
class Piso:
    """Un piso de la figura y lo que se sabe de el."""

    indice: int
    z0: float
    z1: float
    radio: float = 0.0
    gajos: int = 1

    @property
    def alto(self) -> float:
        return self.z1 - self.z0


def alturas(z0: float, z1: float, alto_util: float,
            cuantas: int = 0, alto_pedido: float = 0.0) -> List[float]:
    """Las cotas donde cortar en horizontal, sin contar el suelo ni el techo.

    Siempre a partes iguales. Es la diferencia entre tres piezas de 20 y dos de
    25 mas una de 10: las tres iguales se imprimen en tandas identicas, se
    apilan derechas y no dejan un ultimo trozo raro.
    """
    alto = max(z1 - z0, 0.0)
    if alto <= 0.0:
        return []
    if alto_pedido > 0.0:
        cuantas = max(1, int(math.ceil(alto / alto_pedido - 1e-9)))
    elif cuantas <= 0:
        cuantas = max(1, int(math.ceil(alto / max(alto_util, 1.0) - 1e-9)))
    return [z0 + alto * (i + 1) / cuantas for i in range(cuantas - 1)]


def cuantos_gajos(radio: float, perfil: Perfil, pared: float,
                  tope: int = 0) -> int:
    """Cuantos planos radiales hacen falta para que el gajo quepa en la cama.

    Con G planos salen 2G gajos, cada uno de un angulo de 180/G grados. De ese
    angulo salen las dos medidas de la pieza:

        cuerda  = 2 R sen(a/2)      lo ancho que es el gajo
        flecha  = R (1 - cos(a/2))  lo hondo que es, mas la pared

    Se prueba con un plano, con dos, con tres, y se para en el primero que
    cabe. Como el fondo se mide de verdad, en una cama redonda los gajos salen
    mucho mas anchos de lo que saldrian usando el cuadrado inscrito.
    """
    radio = max(radio, 1e-6)
    limite = int(tope) if tope and tope > 0 else GAJOS_MAX
    for g in range(GAJOS_MIN, max(limite, GAJOS_MIN) + 1):
        medio = math.pi / (2 * g)
        cuerda = 2 * radio * math.sin(medio)
        fondo = radio * (1 - math.cos(medio)) + pared
        if perfil.cabe(cuerda, fondo):
            return g
    return max(limite, GAJOS_MIN)


def nube(objeto: bpy.types.Object) -> "np.ndarray":
    """Los vertices de la figura en coordenadas de mundo, como tabla de numpy.

    Se saca de una vez con `foreach_get`, que copia el bloque entero de
    memoria. Recorrer cinco millones de vertices uno a uno desde Python son
    minutos; asi son decimas de segundo.
    """
    cuantos = len(objeto.data.vertices)
    plano = np.empty(cuantos * 3, dtype=np.float64)
    objeto.data.vertices.foreach_get("co", plano)
    puntos = plano.reshape(cuantos, 3)
    matriz = np.array(objeto.matrix_world)
    return puntos @ matriz[:3, :3].T + matriz[:3, 3]


def _piezas_del_reparto(radios, angulos, perfil: Perfil, cuantos: int,
                        giro: float) -> int:
    """Cuantas piezas saldrian con ese numero de cortes radiales.

    Esto **se mide**, no se estima con una formula. La cuenta de la cuerda y
    la flecha vale para una pieza de pared fina y bien redonda, pero un gajo
    de una figura de verdad llega hasta el eje por arriba y por abajo -el gajo
    de una naranja es ancho en el centro y acaba en punta-, y entonces lo
    hondo que es no tiene nada que ver con la flecha. Estimandolo salian
    piezas que no cabian en la cama por el doble.

    Y no se busca el primer reparto que quepa, sino el que deje **menos
    piezas**. Cuando una figura es tan grande que ningun reparto radial cabe
    -la tapa de un cilindro de dos metros es un disco de un metro de radio, y
    un gajo de un disco mide un metro se corten los que se corten-, el que
    parece que va ganando es el de mas cortes, y es justo el peor: deja
    cuarenta y ocho tiras larguisimas que luego hay que partir otra vez. Con
    menos gajos y un par de cortes despues salen la mitad de piezas.
    """
    ancho_cama, largo_cama = perfil.caja()
    paso = math.pi / cuantos
    cual = np.floor(((angulos - giro) % (2 * math.pi)) / paso).astype(np.intp)
    cual = np.clip(cual, 0, 2 * cuantos - 1)
    centro = giro + (cual + 0.5) * paso
    girado = angulos - centro
    largo = radios * np.cos(girado)
    ancho = radios * np.sin(girado)

    total = 0
    for j in range(2 * cuantos):
        suyos = cual == j
        if not suyos.any():
            continue
        mide = sorted((float(ancho[suyos].ptp()), float(largo[suyos].ptp())),
                      reverse=True)
        if perfil.cabe(mide[0], mide[1]):
            total += 1
        else:
            total += (math.ceil(mide[0] / largo_cama)
                      * math.ceil(mide[1] / ancho_cama))
    return total


def medida_gajo(radio: float, gajos: int, pared: float) -> Tuple[float, float]:
    """Lo ancho y lo hondo que va a salir un gajo, para poder ensenarlo."""
    medio = math.pi / (2 * max(gajos, 1))
    return (2 * radio * math.sin(medio),
            radio * (1 - math.cos(medio)) + pared)


def eje_de(objeto: bpy.types.Object) -> Vector:
    """El eje vertical de la figura: el centro de su planta.

    Se usa el centro de la caja y no el centro de masas porque una figura con
    un brazo estirado tiene el centro de masas descolocado, y los gajos
    saldrian todos torcidos hacia el otro lado.
    """
    puntos = [objeto.matrix_world @ Vector(v) for v in objeto.bound_box]
    xs = [p.x for p in puntos]
    ys = [p.y for p in puntos]
    return Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, 0.0))


def radio_de(objeto: bpy.types.Object, eje: Vector,
             z0: Optional[float] = None, z1: Optional[float] = None) -> float:
    """Lo lejos del eje que llega la figura, mirando solo entre dos alturas."""
    matriz = objeto.matrix_world
    lejos = 0.0
    for v in objeto.data.vertices:
        p = matriz @ v.co
        if z0 is not None and p.z < z0 - 1e-6:
            continue
        if z1 is not None and p.z > z1 + 1e-6:
            continue
        d = math.hypot(p.x - eje.x, p.y - eje.y)
        if d > lejos:
            lejos = d
    return lejos


def _envolvente(puntos):
    """La envolvente convexa de una nube de puntos en 2D (cadena monotona).

    Hace falta para medir bien la planta de una pieza: para saber si cabe en la
    cama no vale la caja alineada con los ejes del mundo, porque la pieza se
    puede girar al ponerla. La caja buena se apoya siempre en un lado de la
    envolvente, asi que probando esos lados salen todas las opciones que
    importan.
    """
    orden = sorted(map(tuple, puntos))
    if len(orden) < 3:
        return orden

    def media(lista):
        salida = []
        for punto in lista:
            while len(salida) >= 2:
                (x0, y0), (x1, y1) = salida[-2], salida[-1]
                if ((x1 - x0) * (punto[1] - y0)
                        - (y1 - y0) * (punto[0] - x0)) > 0:
                    break
                salida.pop()
            salida.append(punto)
        return salida

    return media(orden)[:-1] + media(orden[::-1])[:-1]


def planta(puntos, perfil: Perfil) -> Tuple[float, float, bool, float]:
    """Lo que mide la planta de una pieza girada lo mejor posible, y si cabe.

    Se devuelve la caja mas pequena que la envuelve, si **alguna** de las
    orientaciones posibles entra en la cama -que no siempre es la mas pequena:
    en una cama rectangular puede caber una caja larga y estrecha y no caber
    otra mas cuadrada del mismo area- y hacia donde apunta el lado largo, que
    es por donde hay que partirla si no cabe.
    """
    if len(puntos) == 0:
        return (0.0, 0.0, True, 0.0)
    if len(puntos) > 4000:
        puntos = puntos[::max(1, len(puntos) // 4000)]
    borde = _envolvente(puntos[:, :2])
    if len(borde) < 2:
        return (0.0, 0.0, True, 0.0)
    nube2d = np.array(borde)
    mejor = None
    cabe = False
    for i in range(len(borde)):
        x0, y0 = borde[i]
        x1, y1 = borde[(i + 1) % len(borde)]
        largo = math.hypot(x1 - x0, y1 - y0)
        if largo < 1e-9:
            continue
        cos, sen = (x1 - x0) / largo, (y1 - y0) / largo
        gira = nube2d @ np.array([[cos, -sen], [sen, cos]])
        ancho = float(gira[:, 0].ptp())
        fondo = float(gira[:, 1].ptp())
        if perfil.cabe(ancho, fondo):
            cabe = True
        area = ancho * fondo
        if mejor is None or area < mejor[0]:
            rumbo = (math.atan2(sen, cos) if ancho >= fondo
                     else math.atan2(sen, cos) + math.pi / 2)
            mejor = (area, max(ancho, fondo), min(ancho, fondo), rumbo)
    if mejor is None:
        return (0.0, 0.0, True, 0.0)
    return (mejor[1], mejor[2], cabe, mejor[3])


def gajos_medidos(puntos, eje: Vector, perfil: Perfil, giro: float,
                  tope: int = 0) -> int:
    """Los cortes radiales que hacen falta, midiendo los gajos de verdad."""
    if len(puntos) == 0:
        return 0
    if len(puntos) > MUESTRA:
        puntos = puntos[::max(1, len(puntos) // MUESTRA)]
    dx = puntos[:, 0] - eje.x
    dy = puntos[:, 1] - eje.y
    radios = np.hypot(dx, dy)
    angulos = np.arctan2(dy, dx)
    limite = int(tope) if tope and tope > 0 else GAJOS_MAX
    mejor, cuantas = GAJOS_MIN, None
    for g in range(GAJOS_MIN, max(limite, GAJOS_MIN) + 1):
        piezas = _piezas_del_reparto(radios, angulos, perfil, g, giro)
        if cuantas is None or piezas < cuantas:
            mejor, cuantas = g, piezas
        if piezas == 2 * g:
            break        # ya cabe entero, mas cortes solo anaden juntas
    return mejor


def pisos(objeto: bpy.types.Object, ajustes: Ajustes) -> List[Piso]:
    """El plan entero: en cuantos pisos, y cuantos gajos lleva cada uno.

    Los gajos se cuentan piso a piso y no de una vez para toda la figura. Una
    peana ancha necesita seis y la cabeza a lo mejor no necesita ninguno;
    calcularlos juntos obligaria a partir la cabeza en seis para nada, que es
    justo el trabajo de pegado que se quiere evitar.
    """
    puntos = [objeto.matrix_world @ Vector(v) for v in objeto.bound_box]
    z0 = min(p.z for p in puntos)
    z1 = max(p.z for p in puntos)
    eje = eje_de(objeto)
    cortes = alturas(z0, z1, ajustes.perfil.alto_util(),
                     ajustes.secciones, ajustes.alto_seccion)
    bordes = [z0] + cortes + [z1]

    puntos = nube(objeto)
    alturas_z = puntos[:, 2]

    salida = []
    for i in range(len(bordes) - 1):
        piso = Piso(i, bordes[i], bordes[i + 1])
        dentro = puntos[(alturas_z >= piso.z0 - 1e-6)
                        & (alturas_z <= piso.z1 + 1e-6)]
        if len(dentro):
            piso.radio = float(np.hypot(dentro[:, 0] - eje.x,
                                        dentro[:, 1] - eje.y).max())
        if ajustes.gajos < 0:
            piso.gajos = 0          # el usuario pidio dejar los pisos enteros
        elif ajustes.gajos > 0:
            piso.gajos = ajustes.gajos
        else:
            piso.gajos = gajos_medidos(dentro, eje, ajustes.perfil,
                                       ajustes.giro)
        salida.append(piso)
    return salida


def planos_de_seccion(pisos: Sequence[Piso]) -> List[Plano]:
    """Los planos horizontales que separan unos pisos de otros."""
    return [Plano((0.0, 0.0, piso.z1), (0.0, 0.0, 1.0), "seccion", piso.indice)
            for piso in list(pisos)[:-1]]


def planos_de_gajo(eje: Vector, cuantos: int, giro: float = 0.0,
                   piso: int = 0) -> List[Plano]:
    """Los planos radiales de un piso, repartidos por igual alrededor del eje.

    Son `cuantos` planos y salen `2 * cuantos` gajos: un plano atraviesa la
    figura de lado a lado y corta por los dos lados a la vez.
    """
    salida = []
    for k in range(max(cuantos, 0)):
        angulo = giro + math.pi * k / max(cuantos, 1)
        salida.append(Plano((eje.x, eje.y, 0.0),
                            (math.cos(angulo), math.sin(angulo), 0.0),
                            "gajo", k))
    return salida
