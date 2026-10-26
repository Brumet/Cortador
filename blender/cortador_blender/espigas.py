"""Espigas: que las piezas se encajen solas antes de pegarlas.

Dos piezas de pared fina pegadas a tope se apoyan en una tira de tres
milimetros. Mientras agarra el pegamento resbalan, y basta medio milimetro de
deslizamiento en cada junta para que al llegar al piso de arriba la figura ya
no cierre. El que pega lo sabe: sujeta, mide, vuelve a sujetar.

Una espiga quita ese problema de raiz. En la cara de pegado de una pieza sale
un taco, y en la de la pieza de enfrente hay el agujero que le corresponde.
Encajan en una sola posicion, se sujetan solas mientras seca y la junta aguanta
bastante mas, porque el pegamento deja de trabajar solo a cortante.

Donde van se decide **por junta y no por pieza**. Si cada pieza eligiera sus
sitios por su cuenta, el taco de una y el agujero de la otra caerian en puntos
parecidos pero no iguales, y dos piezas que no encajan son peores que dos
piezas lisas. Aqui se empareja primero -que cara de pegado va contra cual- y
los puntos se calculan una sola vez para las dos.

El taco es deliberadamente pequeno: un cuarto de la pared de diametro. En una
pared de tres milimetros son uno y medio, que se imprime sin apoyos, no se
parte al encajar y deja casi un milimetro de material a cada lado. Un taco mas
gordo se sale de la tira y asoma por la cara de fuera.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import cortar as motor

#: el diametro del taco, como parte del espesor de pared
GRUESO = 0.45
#: lo que se deja de margen al borde de la junta, como parte de la pared
MARGEN = 0.18
#: y el margen del agujero, mas suelto para que no falte ninguno
MARGEN_HUECO = 0.04
#: juego entre el taco y su agujero, en milimetros
HOLGURA = 0.15
#: lo que sobresale el taco, en veces su radio
LARGO = 2.0
#: cada cuantos milimetros se pone una espiga a lo largo de la junta
PASO = 40.0
#: y como mucho estas por junta, que no es una cremallera
POR_JUNTA = 8
#: por encima de estas caras no se ponen: el booleano exacto se dispara
CARAS_MAX = 120_000
#: juntas mas cortas que esto no llevan espiga
CORTA = 12.0

#: por que fallo el ultimo booleano, para poder contarlo en el diario
PORQUE: List[Tuple[str, int, float, float]] = []
#: las espigas del ultimo corte: que pieza, contra cual, y donde
ULTIMAS: List[Tuple[str, str, Vector, Vector]] = []


class Cara:
    """Una cara de pegado de una pieza: el sitio por donde va pegada a otra."""

    def __init__(self, pieza, normal: Vector, altura: float,
                 bordes: np.ndarray, trozos: np.ndarray):
        self.pieza = pieza
        self.normal = normal          # hacia afuera de la pieza, en el mundo
        self.altura = altura          # a que distancia del origen esta el plano
        self.bordes = bordes          # segmentos del contorno, en 2D
        self.trozos = trozos          # triangulos de la cara, en 2D

    def caja(self) -> Tuple[float, float, float, float]:
        if not len(self.trozos):
            return (0.0, 0.0, -1.0, -1.0)
        puntos = self.trozos.reshape(-1, 2)
        return (float(puntos[:, 0].min()), float(puntos[:, 1].min()),
                float(puntos[:, 0].max()), float(puntos[:, 1].max()))


def _ejes(normal: Vector) -> Tuple[Vector, Vector, Vector]:
    """Unos ejes del plano que salen iguales se mire desde el lado que se mire.

    Las dos piezas de una junta ven el mismo plano con la normal al reves, asi
    que lo primero es ponerse de acuerdo en un sentido: el de la componente
    mas grande, positiva. A partir de ahi los otros dos ejes salen solos, y los
    dos lados de la junta acaban midiendo sobre la misma cuadricula.
    """
    n = normal.normalized()
    cual = max(range(3), key=lambda k: abs(n[k]))
    if n[cual] < 0.0:
        n = -n
    guia = Vector((0.0, 0.0, 1.0)) if abs(n.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    u = n.cross(guia).normalized()
    v = n.cross(u).normalized()
    return (n, u, v)


def _clave(normal: Vector, punto: Vector) -> Tuple[int, int, int, int]:
    """Un plano, redondeado, para poder juntar las caras que caen en el mismo.

    La distancia al origen se redondea **grueso**, a cinco milimetros. Afinarla
    parece mejor y es peor: dos caras que estan pegadas uno contra la otra
    pueden caer a los dos lados del redondeo -una en 12,49 y la otra en
    12,51- y entonces el complemento cree que son planos distintos, no las
    empareja, y la junta se queda sin espiga. Con el cubo grueso puede colarse
    alguna cara de un plano vecino, y de eso ya se encarga la comprobacion de
    que de verdad se tocan.
    """
    n, _, _ = _ejes(normal)
    return (int(round(n.x * 100)), int(round(n.y * 100)),
            int(round(n.z * 100)), int(round(punto.dot(n) / 5.0)))


def normal_de_clave(clave: Tuple[int, int, int, int]) -> Vector:
    """La normal redondeada que representa a un plano.

    Es la que manda. Las dos piezas de una junta tienen cada una su normal
    exacta, parecidas pero no iguales, y si cada una montara sus ejes con la
    suya, las coordenadas de la una y las de la otra saldrian giradas medio
    grado. Medio grado en una junta de veinte centimetros son casi dos
    milimetros de desvio, y el taco se planta donde no hay agujero. Con la
    normal del cubo las dos miden sobre exactamente la misma cuadricula.
    """
    return Vector((clave[0] / 100.0, clave[1] / 100.0, clave[2] / 100.0))


def caras_de_pegado(pieza) -> List[Tuple[Tuple[int, int, int, int], Cara]]:
    """Las caras de corte de una pieza, agrupadas por el plano donde caen.

    Son las que puso el complemento al tapar, que van marcadas con la capa
    `cortador_plano`. La piel de la figura no se toca: una espiga ahi seria un
    grano en la cara buena.
    """
    objeto = pieza.objeto if hasattr(pieza, "objeto") else pieza
    malla = objeto.data
    if not malla.polygons:
        return []
    bm = bmesh.new()
    bm.from_mesh(malla)
    try:
        capa = bm.faces.layers.int.get(motor.CAPA)
        if capa is None:
            return []
        bm.faces.ensure_lookup_table()
        matriz = objeto.matrix_world
        grupos: Dict[Tuple[int, int, int, int], List] = {}
        for cara in bm.faces:
            if not cara[capa]:
                continue
            centro = matriz @ cara.calc_center_median()
            normal = (matriz.to_3x3() @ cara.normal)
            if normal.length < 1e-9:
                continue
            normal.normalize()
            grupos.setdefault(_clave(normal, centro), []).append(cara)

        # Dentro de cada cubo, las caras se separan por su distancia exacta
        # al origen. El cubo es grueso a proposito -para que las dos caras de
        # una junta caigan siempre juntas- y eso mete en el mismo saco planos
        # vecinos que estan a tres o cuatro milimetros. Si se promediaran, el
        # taco saldria flotando a medio camino entre los dos.
        finos = {}
        for clave, caras in grupos.items():
            n, _, _ = _ejes(normal_de_clave(clave))
            orden = sorted(caras, key=lambda c: (matriz @ c.calc_center_median()).dot(n))
            manojo = [orden[0]]
            ultimo = (matriz @ orden[0].calc_center_median()).dot(n)
            for cara in orden[1:]:
                donde = (matriz @ cara.calc_center_median()).dot(n)
                if donde - ultimo > 0.3:
                    finos[(clave, len(finos))] = manojo
                    manojo = []
                manojo.append(cara)
                ultimo = donde
            if manojo:
                finos[(clave, len(finos))] = manojo

        salida = []
        for (clave, _), caras in finos.items():
            n, u, v = _ejes(normal_de_clave(clave))
            # Todas las caras del grupo miran al mismo lado; con una basta para
            # saber hacia donde sale el taco.
            fuera = (matriz.to_3x3() @ caras[0].normal).normalized()
            dentro = set(c.index for c in caras)

            def plano(p):
                q = matriz @ p
                return (q.dot(u), q.dot(v))

            trozos = []
            altura = 0.0
            cuantos = 0
            for cara in caras:
                puntos = [plano(w.co) for w in cara.verts]
                for k in range(1, len(puntos) - 1):
                    trozos.append((puntos[0], puntos[k], puntos[k + 1]))
                altura += (matriz @ cara.calc_center_median()).dot(n)
                cuantos += 1
            bordes = []
            for cara in caras:
                for arista in cara.edges:
                    if sum(1 for g in arista.link_faces
                           if g.index in dentro) < 2:
                        bordes.append((plano(arista.verts[0].co),
                                       plano(arista.verts[1].co)))
            if not trozos or not bordes:
                continue
            salida.append((clave, Cara(
                pieza, fuera, altura / max(cuantos, 1),
                np.array(bordes, dtype=float).reshape(-1, 2, 2),
                np.array(trozos, dtype=float).reshape(-1, 3, 2))))
        return salida
    finally:
        bm.free()


def _borde_mas_cerca(puntos: np.ndarray, bordes: np.ndarray):
    """Lo lejos que queda cada punto del borde de la junta, y por donde."""
    a = bordes[:, 0, :]
    b = bordes[:, 1, :]
    ab = b - a
    largo = (ab * ab).sum(axis=1)
    largo[largo < 1e-12] = 1e-12
    ap = puntos[:, None, :] - a[None, :, :]
    t = np.clip((ap * ab[None, :, :]).sum(axis=2) / largo[None, :], 0.0, 1.0)
    cerca = a[None, :, :] + t[:, :, None] * ab[None, :, :]
    fuera = np.linalg.norm(puntos[:, None, :] - cerca, axis=2)
    cual = np.argmin(fuera, axis=1)
    filas = np.arange(len(puntos))
    return (fuera[filas, cual], cerca[filas, cual])


def _lejos_del_borde(puntos: np.ndarray, bordes: np.ndarray) -> np.ndarray:
    """Lo lejos que queda cada punto del borde de la junta."""
    return _borde_mas_cerca(puntos, bordes)[0]


def _al_centro(puntos: np.ndarray, bordes: np.ndarray, trozos: np.ndarray,
               salto: float, vueltas: int = 8) -> np.ndarray:
    """Empuja cada punto hacia el centro de la tira de pegado.

    Los candidatos salen de los triangulos de la tapa, y un triangulo de una
    tira de tres milimetros tiene el centro pegado a un borde: medido asi, el
    sitio mas despejado de la junta da medio milimetro y no cabe ni el taco
    mas fino. Asi que cada candidato se aparta de su borde mas cercano unas
    cuantas veces, con el paso cada vez mas corto. En una tira eso lleva
    derecho a la linea central, que es justo donde hay sitio.
    """
    vivos = puntos.copy()
    for vuelta in range(vueltas):
        fuera, cerca = _borde_mas_cerca(vivos, bordes)
        hacia = vivos - cerca
        largo = np.linalg.norm(hacia, axis=1)
        bueno = largo > 1e-9
        if not bueno.any():
            break
        paso = salto * (0.75 ** vuelta)
        probados = vivos.copy()
        probados[bueno] += hacia[bueno] / largo[bueno, None] * paso
        # Un paso que se sale de la tapa o que acerca al borde no se acepta.
        dentro = _dentro(probados, trozos)
        nuevo_fuera = _lejos_del_borde(probados, bordes)
        vale = dentro & (nuevo_fuera > fuera)
        vivos[vale] = probados[vale]
    return vivos


def _dentro(puntos: np.ndarray, trozos: np.ndarray) -> np.ndarray:
    """Si cada punto cae dentro de la cara, mirando triangulo a triangulo."""
    a, b, c = trozos[:, 0, :], trozos[:, 1, :], trozos[:, 2, :]
    v0 = b - a
    v1 = c - a
    den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
    den[np.abs(den) < 1e-12] = 1e-12
    v2 = puntos[:, None, :] - a[None, :, :]
    s = (v2[:, :, 0] * v1[None, :, 1] - v1[None, :, 0] * v2[:, :, 1]) / den
    t = (v0[None, :, 0] * v2[:, :, 1] - v2[:, :, 0] * v0[None, :, 1]) / den
    return ((s >= -1e-9) & (t >= -1e-9) & (s + t <= 1.0 + 1e-9)).any(axis=1)


def sitios(macho: Cara, hembra: Cara, radio: float, margen: float,
           holgura: float, paso: float, tope: int) -> List[Tuple[float, float]]:
    """Donde poner las espigas de una junta, en las coordenadas del plano.

    Los candidatos salen de la propia cara de pegado -el centro y los medios
    de cada triangulo- y no de una cuadricula sobre el plano. Con cuadricula
    no funciona: la junta de una figura hueca es una tira de tres milimetros,
    y un punto de rejilla cae dentro de esa tira una vez de cada veinte.

    De todos los candidatos se exige sitio para el taco **y** para el agujero
    de enfrente, y luego se van cogiendo de mas despegado del borde a menos,
    tachando cada vez los que queden a menos de un paso. Asi quedan repartidos
    a lo largo de la junta y siempre en lo mas ancho de la tira.
    """
    if not len(macho.trozos) or not len(hembra.trozos):
        return []
    trozos = macho.trozos
    if len(trozos) > 1200:
        trozos = trozos[::max(1, len(trozos) // 1200)]
    medios = (trozos[:, [0, 1, 2], :] + trozos[:, [1, 2, 0], :]) / 2.0
    candidatos = np.concatenate([trozos.mean(axis=1), medios.reshape(-1, 2)])

    suyo = macho.bordes
    ajeno = hembra.bordes
    if len(suyo) > 1500:
        suyo = suyo[::max(1, len(suyo) // 1500)]
    if len(ajeno) > 1500:
        ajeno = ajeno[::max(1, len(ajeno) // 1500)]

    hueco = _lejos_del_borde(candidatos, suyo)
    # Primero una criba barata: los que ni acercandose al centro llegarian.
    cerca = hueco >= (radio + margen) * 0.25
    if not cerca.any():
        return []
    candidatos = candidatos[cerca]
    if len(candidatos) > 400:
        candidatos = candidatos[np.argsort(-hueco[cerca])[:400]]
    candidatos = _al_centro(candidatos, suyo, macho.trozos, radio + margen)

    hueco = _lejos_del_borde(candidatos, suyo)
    sirve = hueco >= radio + margen
    if not sirve.any():
        return []
    candidatos, hueco = candidatos[sirve], hueco[sirve]

    dentro = _dentro(candidatos, hembra.trozos)
    if not dentro.any():
        return []
    candidatos, hueco = candidatos[dentro], hueco[dentro]

    suelto = _lejos_del_borde(candidatos, ajeno) >= radio + holgura + MARGEN_HUECO * margen / MARGEN
    if not suelto.any():
        return []
    candidatos, hueco = candidatos[suelto], hueco[suelto]

    orden = np.argsort(-hueco)
    puestos: List[Tuple[float, float]] = []
    tomados: List[np.ndarray] = []
    for k in orden:
        p = candidatos[k]
        if any(float(np.hypot(*(p - q))) < paso for q in tomados):
            continue
        tomados.append(p)
        puestos.append((float(p[0]), float(p[1])))
        if len(puestos) >= tope:
            break
    return puestos


def _taco(centro: Vector, hacia: Vector, radio: float, largo: float,
          hundido: float) -> bmesh.types.BMesh:
    """Un cilindro puesto en la cara de pegado, mirando hacia afuera."""
    n = hacia.normalized()
    guia = Vector((0.0, 0.0, 1.0)) if abs(n.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    u = n.cross(guia).normalized()
    v = n.cross(u).normalized()
    alto = largo + hundido
    medio = centro + n * ((largo - hundido) / 2.0)
    matriz = Matrix((
        (u.x, v.x, n.x, medio.x),
        (u.y, v.y, n.y, medio.y),
        (u.z, v.z, n.z, medio.z),
        (0.0, 0.0, 0.0, 1.0),
    ))
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=16,
                          radius1=radio, radius2=radio, depth=alto,
                          matrix=matriz)
    return bm


def _sitio_que_ocupan(radio: float, largo: float, cuantos: int) -> float:
    """Lo que ocupan unos cuantos tacos, con holgura de sobra."""
    return math.pi * radio * radio * largo * max(cuantos, 1) * 4.0


def _misma_caja(antes, ahora, crece: float, encoge: float = 0.5) -> bool:
    """Si la pieza sigue ocupando el mismo sitio despues del booleano.

    Es la prueba que de verdad distingue un booleano bueno de uno malo. El
    volumen no sirve solo: el solucionador exacto rehace la piel cruzada
    consigo misma y lo mueve de verdad sin que nada este roto. En cambio una
    pieza a la que el booleano le arranca un trozo cambia de caja, y eso se ve
    enseguida. Se deja que crezca lo que sobresale el taco, y encoger casi
    nada.
    """
    viejo = np.array(antes, dtype=float)
    nuevo = np.array([tuple(v) for v in ahora], dtype=float)
    if viejo.shape != nuevo.shape:
        return False
    v0, v1 = viejo.min(axis=0), viejo.max(axis=0)
    n0, n1 = nuevo.min(axis=0), nuevo.max(axis=0)
    return bool(((n0 >= v0 - crece) & (n0 <= v0 + encoge)
                 & (n1 <= v1 + crece) & (n1 >= v1 - encoge)).all())


def _fundir(objeto: bpy.types.Object, herramienta: bmesh.types.BMesh,
            operacion: str, aparte: float, crece: float) -> bool:
    """Suma o resta la herramienta, y deshace el cambio si sale mal.

    Igual que con las marcas: el booleano es lo unico que no controlamos por
    dentro, asi que no se le da por bueno. Si la pieza deja de estar cerrada o
    el volumen se mueve mas de lo que ocupan los tacos, se devuelve la malla de
    antes y la pieza se queda lisa. Una pieza sin espiga se pega como siempre;
    una pieza rota no se pega de ninguna manera.
    """
    malla = bpy.data.meshes.new("cortador_espiga")
    herramienta.to_mesh(malla)
    util = bpy.data.objects.new("cortador_espiga", malla)
    # La herramienta esta hecha en coordenadas del mundo, asi que su objeto va
    # sin mover. Blender ya se encarga de llevarla al sitio de la pieza.
    bpy.context.scene.collection.objects.link(util)

    antes = objeto.data
    copia = antes.copy()
    bm = bmesh.new()
    bm.from_mesh(antes)
    volumen = abs(bm.calc_volume(signed=True))
    bm.free()
    # El margen no puede ser solo lo que ocupan los tacos. El solucionador
    # exacto rehace el solido entero, y en una pieza que venia con la piel
    # cruzada consigo misma -Solidificar las deja asi en cualquier recoveco-
    # la rehace bien y el volumen se mueve miles de milimetros cubicos sin que
    # nada este mal. Se admite ese arreglo igual que se admite en las marcas;
    # lo que no se admite es que se lleve media pieza.
    tolerancia = max(volumen * 0.25, aparte)
    caja = [tuple(v) for v in objeto.bound_box]

    modificador = objeto.modifiers.new("cortador_espiga", "BOOLEAN")
    modificador.operation = operacion
    modificador.solver = "EXACT"
    modificador.object = util
    bien = False
    try:
        grafo = bpy.context.evaluated_depsgraph_get()
        nueva = bpy.data.meshes.new_from_object(objeto.evaluated_get(grafo))
        prueba = bmesh.new()
        prueba.from_mesh(nueva)
        abiertas = sum(1 for e in prueba.edges if e.is_boundary)
        cambio = abs(abs(prueba.calc_volume(signed=True)) - volumen)
        prueba.free()
        if len(PORQUE) < 500:
            PORQUE.append((objeto.name, abiertas, cambio, tolerancia))
        if len(nueva.polygons) and abiertas < 200 and cambio < tolerancia:
            # Y la prueba que de verdad importa: que la pieza siga siendo del
            # tamano que era. El volumen solo no vale para esto, porque el
            # arreglo de la piel cruzada lo mueve de verdad; en cambio una
            # pieza a la que el booleano le arranca un trozo cambia de caja.
            objeto.data = nueva
            if abiertas:
                # El booleano deja de vez en cuando unas aristas sueltas. Las
                # remata el mismo cierre de huecos que usa el corte, y despues
                # se vuelve a medir: cerrada no basta, tiene que seguir siendo
                # la misma pieza.
                motor.cerrar_huecos(objeto)
                revision = bmesh.new()
                revision.from_mesh(objeto.data)
                rematado = abs(revision.calc_volume(signed=True))
                bien = (not any(e.is_boundary for e in revision.edges)
                        and abs(rematado - volumen) < tolerancia)
                revision.free()
            else:
                bien = True
            if bien:
                bien = _misma_caja(caja, objeto.bound_box, crece)
            if bien:
                bpy.data.meshes.remove(antes)
                bpy.data.meshes.remove(copia)
            else:
                objeto.data = copia
                bpy.data.meshes.remove(nueva)
                bpy.data.meshes.remove(antes)
        else:
            bpy.data.meshes.remove(nueva)
            bpy.data.meshes.remove(copia)
    finally:
        for sobra in list(objeto.modifiers):
            if sobra.name.startswith("cortador_espiga"):
                objeto.modifiers.remove(sobra)
        bpy.data.objects.remove(util, do_unlink=True)
        bpy.data.meshes.remove(malla)
    return bool(bien)


def poner(piezas: Sequence, pared: float, holgura: float = HOLGURA,
          paso: float = PASO):
    """Pone taco y agujero en cada junta. Va soltando por donde va.

    Devuelve (juntas con espiga, espigas puestas, piezas que no admitieron).
    """
    radio = max(pared * GRUESO / 2.0, 0.35)
    margen = pared * MARGEN
    largo = radio * LARGO
    hundido = radio * 0.8

    # --- quien va contra quien ------------------------------------------
    porplano: Dict[Tuple[int, int, int, int], List[Cara]] = {}
    for n, pieza in enumerate(piezas):
        objeto = pieza.objeto if hasattr(pieza, "objeto") else pieza
        if len(objeto.data.polygons) > CARAS_MAX:
            continue
        for clave, cara in caras_de_pegado(pieza):
            porplano.setdefault(clave, []).append(cara)
        if n % 10 == 0:
            yield ("buscando las juntas", n, len(piezas), None)

    tacos: Dict[str, List[Tuple[Vector, Vector, str]]] = {}
    huecos: Dict[str, List[Tuple[Vector, Vector]]] = {}
    ULTIMAS.clear()
    juntas = 0
    for clave, caras in porplano.items():
        if len(caras) < 2:
            continue
        n, u, v = _ejes(normal_de_clave(clave))
        for i in range(len(caras)):
            for j in range(i + 1, len(caras)):
                una, otra = caras[i], caras[j]
                if una.normal.dot(otra.normal) > -0.5:
                    continue        # miran al mismo lado: no son pareja
                x0, y0, x1, y1 = una.caja()
                a0, b0, a1, b1 = otra.caja()
                if x1 < a0 or a1 < x0 or y1 < b0 or b1 < y0:
                    continue        # no se tocan
                if max(x1 - x0, y1 - y0) < CORTA:
                    continue
                if abs(una.altura - otra.altura) > 0.4:
                    continue        # planos paralelos, pero no el mismo
                # El taco va siempre en la cara que mira hacia el sentido
                # bueno del plano, y el agujero en la de enfrente. Asi las dos
                # piezas se ponen de acuerdo sin hablar entre ellas.
                macho, hembra = (una, otra) if una.normal.dot(n) > 0 else (otra, una)
                puntos = sitios(macho, hembra, radio, margen, holgura,
                                paso, POR_JUNTA)
                if not puntos:
                    continue
                juntas += 1
                for a, b in puntos:
                    centro = u * a + v * b + n * macho.altura
                    nombre_m = (macho.pieza.objeto if hasattr(macho.pieza, "objeto")
                                else macho.pieza).name
                    nombre_h = (hembra.pieza.objeto if hasattr(hembra.pieza, "objeto")
                                else hembra.pieza).name
                    tacos.setdefault(nombre_m, []).append(
                        (centro, macho.normal, nombre_h))
                    huecos.setdefault(nombre_h, []).append((centro, hembra.normal))
                    ULTIMAS.append((nombre_m, nombre_h, centro.copy(),
                                    macho.normal.copy()))

    # --- y ahora se tallan: primero los agujeros --------------------------
    # El orden no es capricho. Un agujero sin taco no estorba: la pieza se
    # pega igual. Un taco sin agujero es un desastre: las dos piezas no
    # llegan a tocarse y la junta queda abierta un milimetro y medio. Asi que
    # se taladra primero, se apunta en que piezas salio bien, y solo despues
    # se sacan los tacos que tienen su agujero esperando.
    puestas = 0
    fallos: List[str] = []
    taladradas = set()
    for n, pieza in enumerate(piezas):
        objeto = pieza.objeto if hasattr(pieza, "objeto") else pieza
        suyos = huecos.get(objeto.name, [])
        if not suyos:
            continue
        yield (f"agujeros en {objeto.name}", n, len(piezas), None)
        junto = bmesh.new()
        for centro, hacia in suyos:
            uno = _taco(centro, hacia, radio + holgura, largo * 0.2,
                        largo + hundido)
            malla = bpy.data.meshes.new("cortador_hueco")
            uno.to_mesh(malla)
            junto.from_mesh(malla)
            bpy.data.meshes.remove(malla)
            uno.free()
        tope = _sitio_que_ocupan(radio + holgura, largo + hundido, len(suyos))
        if _fundir(objeto, junto, "DIFFERENCE", tope, 0.2):
            taladradas.add(objeto.name)
            puestas += len(suyos)
        else:
            fallos.append(objeto.name)
        junto.free()

    for n, pieza in enumerate(piezas):
        objeto = pieza.objeto if hasattr(pieza, "objeto") else pieza
        mios = [(c, h, contra) for c, h, contra in tacos.get(objeto.name, [])
                if contra in taladradas]
        if not mios:
            continue
        yield (f"espigas en {objeto.name}", n, len(piezas), None)
        junto = bmesh.new()
        for centro, hacia, _ in mios:
            uno = _taco(centro, hacia, radio, largo, hundido)
            malla = bpy.data.meshes.new("cortador_taco")
            uno.to_mesh(malla)
            junto.from_mesh(malla)
            bpy.data.meshes.remove(malla)
            uno.free()
        tope = _sitio_que_ocupan(radio, largo + hundido, len(mios))
        if _fundir(objeto, junto, "UNION", tope, largo + 0.2):
            puestas += len(mios)
        else:
            fallos.append(objeto.name)
        junto.free()
    return (juntas, puestas, sorted(set(fallos)))
