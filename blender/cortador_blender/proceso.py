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
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Tuple

import bpy
from mathutils import Vector

from . import cortar as motor
from . import marcas
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


def _planos_para_partir(puntos, rumbo: float, alto_util: float
                        ) -> List[motor.Plano]:
    """Por donde probar a partir una pieza que no cabe, de mejor a peor.

    El primero es el bueno: perpendicular al lado largo y por la mitad de ese
    lado. Se mide la mitad del **recorrido**, no el centro de masas, porque una
    pieza curvada -media corona, el gajo de una cupula- tiene el centro de masas
    en el aire, fuera del material, y un plano que pase por ahi no corta nada.

    El segundo es para cuando ese falla: cruzado. Una pieza en forma de C no se
    abre con un solo corte por bien puesto que este. No se prueban mas: cada
    intento fallido deja su corte hecho en la malla, y encadenar cuatro deja la
    pieza llena de costuras y de astillas.
    """
    centro = Vector(puntos.mean(axis=0))
    hacia = Vector((math.cos(rumbo), math.sin(rumbo), 0.0))
    cruz = Vector((-math.sin(rumbo), math.cos(rumbo), 0.0))
    largo = puntos[:, :2] @ np.array([hacia.x, hacia.y])
    medio = float(largo.min() + largo.max()) / 2
    ancho = puntos[:, :2] @ np.array([cruz.x, cruz.y])
    travieso = float(ancho.min() + ancho.max()) / 2

    def en(direccion, valor):
        punto = centro - direccion * float(centro.xy.dot(direccion.xy)) + direccion * valor
        return motor.Plano((punto.x, punto.y, centro.z),
                           (direccion.x, direccion.y, direccion.z), "apretar", 0)

    salida = [en(hacia, medio), en(cruz, travieso)]
    if puntos[:, 2].ptp() > alto_util:
        salida.insert(0, motor.Plano(
            (centro.x, centro.y, float(puntos[:, 2].min() + puntos[:, 2].max()) / 2),
            (0.0, 0.0, 1.0), "apretar", 0))
    return salida


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
            if not len(puntos):
                continue
            ancho, fondo, entra, rumbo = plan.planta(puntos, perfil)
            if entra and puntos[:, 2].ptp() <= perfil.alto_util():
                hechas.append(trozo)
                continue
            partido = [trozo]
            for corte in _planos_para_partir(puntos, rumbo, perfil.alto_util()):
                motor.cortar_objeto(trozo, [corte])
                partido = motor.separar_piezas(trozo)
                if len(partido) > 1:
                    break
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
        esquinas = [objeto.matrix_world @ Vector(v) for v in objeto.bound_box]
        self.centro = sum(esquinas, Vector()) / len(esquinas)

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
        vivas: List[Tuple[bpy.types.Object, int, int]] = []
        rotas: Dict[str, Tuple[int, int]] = {}
        for objeto, piso, gajo in finales:
            _mudar(objeto, coleccion)
            abiertas, quedan = motor.cerrar_huecos(objeto)
            if not objeto.data.polygons:
                # el remate se la comio entera: era basura del corte
                bpy.data.objects.remove(objeto, do_unlink=True)
                continue
            vivas.append((objeto, piso, gajo))
            if quedan:
                rotas[objeto.name] = (abiertas, quedan)

        # Las laminas se numeran dando la vuelta al piso, no por el gajo del
        # que salieron. Es lo que hace util el nombre: la L4 esta entre la L3 y
        # la L5, se mire por donde se mire. Numerarlas por el gajo dejaba diez
        # piezas llamadas P1-L2, P1-L2b, P1-L2c... que no dicen nada.
        for piso in sorted({p for _, p, _ in vivas}):
            suyas = [o for o, q, _ in vivas if q == piso]
            suyas.sort(key=lambda o: self._vuelta(o))
            for numero, objeto in enumerate(suyas, 1):
                objeto.name = "P{:d}-L{:d}".format(piso + 1, numero)

        for objeto, piso, gajo in vivas:
            _, _, alto = motor.medidas(objeto)
            ancho, fondo, entra, _ = plan.planta(plan.nube(objeto), perfil)
            pieza = Pieza(objeto, piso, gajo, ancho, fondo, alto,
                          len(objeto.data.polygons))
            pieza.cerrada = objeto.name not in rotas
            pieza.cabe = entra and alto <= perfil.alto_util()
            self.resultado.piezas.append(pieza)
        for nombre, (abiertas, quedan) in rotas.items():
            self.resultado.avisos.append(
                f"{nombre}: quedan {quedan} aristas sin cerrar de {abiertas} "
                "que habia; la malla de partida esta rota ahi")

        # --- las marcas ------------------------------------------------------
        if ajustes.marcar and self.resultado.piezas:
            yield ("grabando las marcas", 0.94)
            for texto, avance in self._marcar():
                yield (texto, avance)

        self.objeto.hide_set(True)
        self._resumir()
        yield ("listo", 1.0)

    def _vuelta(self, objeto: bpy.types.Object) -> Tuple[float, float, float]:
        """Donde cae una pieza dando la vuelta al piso: angulo, radio y altura."""
        centro = _centro(objeto)
        return (math.atan2(centro.y - self.eje.y, centro.x - self.eje.x),
                math.hypot(centro.x - self.eje.x, centro.y - self.eje.y),
                centro.z)

    def _marcar(self):
        """Graba en cada pieza su nombre y el de las que van pegadas a ella."""
        piezas = self.resultado.piezas
        marcos = {}
        for pieza in piezas:
            marco = marcas.marco_interior(pieza.objeto, self.centro)
            if marco is not None:
                marcos[pieza.objeto.name] = marco
        vecinos = marcas.vecindario(piezas, marcos)
        hechas = 0
        for n, pieza in enumerate(piezas):
            nombre = pieza.objeto.name
            if nombre not in marcos:
                continue
            if marcas.marcar(pieza.objeto, self.centro, nombre.replace("-", "/"),
                             {lado: quien.replace("-", "/")
                              for lado, quien in vecinos.get(nombre, {}).items()},
                             self.ajustes.hondo):
                hechas += 1
            if n % 10 == 0:
                yield (f"grabando marcas ({n + 1}/{len(piezas)})",
                       0.94 + 0.05 * n / max(len(piezas), 1))
        sin = len(piezas) - hechas
        if sin:
            self.resultado.avisos.append(
                f"{sin} piezas se quedaron sin marcar: no habia cara interior "
                "suficiente o el grabado habria roto la pieza.")

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
