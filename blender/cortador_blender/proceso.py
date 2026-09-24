"""El trabajo completo: del modelo entero a las piezas listas para imprimir.

Va en dos vueltas, y no por capricho. Primero se parte la figura en pisos, se
sueltan, y solo entonces se abre cada piso en gajos **por su cuenta**. Hacerlo
al reves -calcular todos los planos de golpe y pasarlos juntos- obliga a
partir la cabeza en los mismos seis gajos que la peana, y cada corte de mas es
una junta mas que pegar.

Ademas se hace en pasos sueltos, con un generador, porque Blender dibuja la
ventana entre paso y paso. Un corte de cinco millones de triangulos son dos
minutos largos, y dos minutos con la ventana congelada es un programa que
parece colgado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Tuple

import bpy
from mathutils import Vector

from . import cortar as motor
from . import plan
from .plan import Ajustes, Piso

#: nombre de la coleccion donde se dejan las piezas
COLECCION = "Cortador"


@dataclass
class Pieza:
    """Una pieza terminada."""

    objeto: bpy.types.Object
    piso: int
    gajo: int
    ancho: float = 0.0
    fondo: float = 0.0
    alto: float = 0.0
    caras: int = 0
    cerrada: bool = True
    cabe: bool = True

    @property
    def nombre(self) -> str:
        return self.objeto.name


@dataclass
class Resultado:
    piezas: List[Pieza] = field(default_factory=list)
    pisos: List[Piso] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)

    @property
    def abiertas(self) -> List[Pieza]:
        return [p for p in self.piezas if not p.cerrada]

    @property
    def no_caben(self) -> List[Pieza]:
        return [p for p in self.piezas if not p.cabe]


def _coleccion(nombre: str = COLECCION) -> bpy.types.Collection:
    coleccion = bpy.data.collections.get(nombre)
    if coleccion is None:
        coleccion = bpy.data.collections.new(nombre)
        bpy.context.scene.collection.children.link(coleccion)
    return coleccion


def _mudar(objeto: bpy.types.Object, coleccion: bpy.types.Collection) -> None:
    for otra in list(objeto.users_collection):
        otra.objects.unlink(objeto)
    coleccion.objects.link(objeto)


def _centro(objeto: bpy.types.Object) -> Vector:
    puntos = [objeto.matrix_world @ Vector(v) for v in objeto.bound_box]
    return sum(puntos, Vector()) / len(puntos)


def _de_que_piso(objeto: bpy.types.Object, pisos: List[Piso]) -> int:
    """A que piso pertenece una pieza, por donde cae su centro."""
    z = _centro(objeto).z
    for piso in pisos:
        if piso.z0 - 1e-6 <= z <= piso.z1 + 1e-6:
            return piso.indice
    return min(range(len(pisos)),
               key=lambda i: abs(z - (pisos[i].z0 + pisos[i].z1) / 2))


def _que_gajo(objeto: bpy.types.Object, eje: Vector, cuantos: int,
              giro: float) -> int:
    """En que gajo cae una pieza, por el angulo de su centro alrededor del eje."""
    if cuantos <= 0:
        return 0
    centro = _centro(objeto)
    angulo = math.atan2(centro.y - eje.y, centro.x - eje.x) - giro
    paso = math.pi / cuantos
    return int(math.floor((angulo % (2 * math.pi)) / paso)) % (2 * cuantos)


def _apretar(objeto: bpy.types.Object, perfil, vueltas: int = 7
             ) -> List[bpy.types.Object]:
    """Parte en dos lo que siga sin caber, y vuelve a mirar.

    Los gajos resuelven casi todo, pero no todo: la tapa plana de un cilindro
    de dos metros es un disco, y un gajo de un disco llega del borde hasta el
    eje, con lo que mide un metro por muchos gajos que se hagan. Antes que
    llenar la figura entera de cortes por si acaso, se corta **solo lo que se
    pasa**, y por la mitad de su lado mas largo, que es el corte que mas
    reduce con una sola junta.
    """
    pendientes = [objeto]
    hechas: List[bpy.types.Object] = []
    for _ in range(vueltas):
        siguientes = []
        for trozo in pendientes:
            puntos = plan.nube(trozo)
            ancho, fondo, entra, rumbo = plan.planta(puntos, perfil)
            alto = float(puntos[:, 2].ptp()) if len(puntos) else 0.0
            if entra and alto <= perfil.alto_util():
                hechas.append(trozo)
                continue
            centro = Vector(puntos.mean(axis=0)) if len(puntos) else Vector()
            if alto > perfil.alto_util():
                corte = motor.Plano(tuple(centro), (0.0, 0.0, 1.0), "apretar", 0)
            else:
                corte = motor.Plano(tuple(centro),
                                    (math.cos(rumbo), math.sin(rumbo), 0.0),
                                    "apretar", 0)
            motor.cortar_objeto(trozo, [corte])
            partido = motor.separar_piezas(trozo)
            if len(partido) < 2:
                # Una pieza en anillo no se abre con un solo corte: queda en
                # forma de C. Con el corte cruzado si se abre, y se hace aqui
                # mismo en vez de dejarlo para la vuelta siguiente para no
                # llenarla de cortes de mas.
                motor.cortar_objeto(trozo, [motor.Plano(
                    tuple(centro),
                    (-math.sin(rumbo), math.cos(rumbo), 0.0), "apretar", 1)])
                partido = motor.separar_piezas(trozo)
            if len(partido) < 2:
                hechas.append(trozo)      # no hay por donde partirla mas
                continue
            siguientes += partido
        pendientes = siguientes
        if not pendientes:
            break
    return hechas + pendientes


class Trabajo:
    """El corte entero, en pasos, para poder ir contandolo."""

    def __init__(self, objeto: bpy.types.Object, ajustes: Ajustes):
        self.objeto = objeto
        self.ajustes = ajustes
        self.resultado = Resultado()
        self.eje = plan.eje_de(objeto)

    def pasos(self) -> Iterator[Tuple[str, float]]:
        ajustes = self.ajustes
        pisos = plan.pisos(self.objeto, ajustes)
        self.resultado.pisos = pisos
        yield (f"{len(pisos)} pisos, "
               f"{sum(2 * p.gajos for p in pisos)} piezas previstas", 0.02)

        coleccion = _coleccion()
        copia = self.objeto.copy()
        copia.data = self.objeto.data.copy()
        copia.name = f"{self.objeto.name}_cortado"
        coleccion.objects.link(copia)

        # --- primera vuelta: los pisos -------------------------------------
        trozos = [copia]
        if len(pisos) > 1:
            yield ("cortando los pisos", 0.05)
            motor.cortar_objeto(copia, plan.planos_de_seccion(pisos))
            trozos = motor.separar_piezas(copia)
            yield (f"{len(trozos)} trozos tras los pisos", 0.35)

        por_piso: Dict[int, List[bpy.types.Object]] = {}
        for trozo in trozos:
            por_piso.setdefault(_de_que_piso(trozo, pisos), []).append(trozo)

        # --- segunda vuelta: los gajos, piso a piso ------------------------
        finales: List[Tuple[bpy.types.Object, int, int]] = []
        for n, piso in enumerate(pisos):
            avance = 0.35 + 0.5 * (n / max(len(pisos), 1))
            suyos = por_piso.get(piso.indice, [])
            if piso.gajos <= 0 or not suyos:
                finales += [(t, piso.indice, 0) for t in suyos]
                continue
            yield (f"piso {piso.indice + 1}: {2 * piso.gajos} gajos", avance)
            planos = plan.planos_de_gajo(self.eje, piso.gajos,
                                         ajustes.giro, piso.indice)
            for trozo in suyos:
                motor.cortar_objeto(trozo, planos)
                for pieza in motor.separar_piezas(trozo):
                    finales.append((pieza, piso.indice,
                                    _que_gajo(pieza, self.eje, piso.gajos,
                                              ajustes.giro)))

        # --- tercera vuelta: apretar lo que todavia no quepa ----------------
        yield ("ajustando las piezas que se pasan", 0.85)
        apretadas: List[Tuple[bpy.types.Object, int, int]] = []
        for objeto, piso, gajo in finales:
            for trozo in _apretar(objeto, ajustes.perfil):
                apretadas.append((trozo, piso, gajo))
        finales = apretadas

        # --- rematar, medir y bautizar -------------------------------------
        yield ("cerrando y midiendo las piezas", 0.88)
        perfil = ajustes.perfil
        cuenta: Dict[Tuple[int, int], int] = {}
        for objeto, piso, gajo in finales:
            _mudar(objeto, coleccion)
            abiertas, quedan = motor.cerrar_huecos(objeto)
            if not objeto.data.polygons:
                # el remate se la comio entera: era basura del corte
                bpy.data.objects.remove(objeto, do_unlink=True)
                continue
            _, _, alto = motor.medidas(objeto)
            ancho, fondo, entra, _ = plan.planta(plan.nube(objeto), perfil)
            repetida = cuenta.get((piso, gajo), 0)
            cuenta[(piso, gajo)] = repetida + 1
            objeto.name = "P{:02d}-G{:02d}{}".format(
                piso + 1, gajo + 1,
                "" if not repetida else "-{}".format(repetida + 1))
            pieza = Pieza(objeto, piso, gajo, ancho, fondo, alto,
                          len(objeto.data.polygons))
            pieza.cerrada = not quedan
            pieza.cabe = entra and alto <= perfil.alto_util()
            self.resultado.piezas.append(pieza)
            if quedan:
                self.resultado.avisos.append(
                    f"{objeto.name}: quedan {quedan} aristas sin cerrar de "
                    f"{abiertas} que habia; la malla de partida esta rota ahi")

        self.objeto.hide_set(True)
        self._resumir()
        yield ("listo", 1.0)

    def _resumir(self) -> None:
        res = self.resultado
        if res.no_caben:
            nombres = ", ".join(p.nombre for p in res.no_caben[:6])
            res.avisos.append(
                f"{len(res.no_caben)} piezas no caben en la maquina ({nombres}"
                f"{'...' if len(res.no_caben) > 6 else ''}). "
                "Sube el numero de gajos o de pisos.")
        chicas = [p for p in res.piezas
                  if max(p.ancho, p.fondo, p.alto) < self.ajustes.minimo]
        if chicas:
            res.avisos.append(
                f"{len(chicas)} piezas son mas pequenas que "
                f"{self.ajustes.minimo:g} mm: son esquirlas del corte y "
                "seguramente no valga la pena imprimirlas.")
