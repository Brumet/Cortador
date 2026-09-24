"""El motor de corte: partir una malla por planos, sin tocar un booleano.

Por que planos y no cubos de corte
----------------------------------
Un cubo de corte es, en matematicas, la interseccion de seis semiespacios: seis
planos. Hacerlo con un booleano cuesta el triple de tiempo, casi el doble de
memoria y en una malla de escaneo devuelve basura. Medido en Blender 5.0 sobre
un modelo de 5.242.880 caras:

    bisect por un plano          14 s   pico 4,5 GB   bien
    booleano EXACT con un cubo   37 s   pico 6,1 GB   devolvio 106 caras

Asi que aqui no hay booleanos en ninguna parte. Todo son planos.

Las cuatro reglas que salieron de medirlo
-----------------------------------------
1. **Un solo bmesh.** Duplicarlo (`bm.copy()`) con cinco millones de caras mata
   el proceso por falta de memoria. Se corta, se rasga y se tapa todo dentro de
   la misma malla, y solo al final se reparten las piezas en objetos.
2. **Tapar en el mismo paso que se corta, plano por plano.** Es la regla que
   costo encontrar. Si cortas con los ocho planos y dejas el tapado para el
   final, el borde de cada pieza ya no vive en un plano: da un trozo de vuelta
   por el corte horizontal, salta al radial, vuelve al horizontal... y la
   triangulacion, que trabaja aplanando sobre un plano, no tiene ningun
   contorno cerrado que rellenar y devuelve cero caras. En cambio, si nada mas
   cortar por un plano se rasga y se tapa, el contorno de ese corte **si** es
   un anillo plano cerrado, se tapa perfecto, y el plano siguiente se encuentra
   la tapa ya hecha y la corta como una cara mas.
3. **Rasgar antes de tapar, y tapar cada lado por separado.** Tras rasgar, cada
   arista del corte existe dos veces, una por lado. Si se las das todas juntas
   a la triangulacion intenta coser las dos caras en una y no cierra ninguna.
   Se separan por el lado del plano donde cae su cara y se tapa lado a lado.
4. **Separar en C, no en Python.** Recorrer cinco millones de caras buscando
   islas desde Python son minutos; `mesh.separate(type='LOOSE')` lo hace en
   segundos porque esta compilado.

Con eso, el plan entero de un modelo de 5,2 M de triangulos sale por debajo del
minuto y medio, y repartido en pasos para que la ventana no se quede muerta.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt

#: cuanto puede alejarse un punto del plano y seguir contando como suyo (mm)
TOL = 1e-6
#: a que distancia dos puntos de una tapa son el mismo punto (mm)
EPS = 1e-6


@dataclass
class Plano:
    """Un plano de corte, con de donde sale para poder explicarlo despues."""

    punto: Tuple[float, float, float]
    normal: Tuple[float, float, float]
    #: 'seccion' (horizontal) o 'gajo' (radial)
    clase: str = "seccion"
    #: para las secciones, el numero de piso; para los gajos, el numero de gajo
    indice: int = 0


#: capa de caras: guarda de que plano salio cada tapa (0 = piel del modelo)
CAPA = "cortador_plano"
#: capa de caras: de que lado de ese plano quedo la tapa, +1 o -1
LADO = "cortador_lado"


def _signo(cara: bmesh.types.BMFace, punto: Vector, normal: Vector,
           plano: int, capa, lado) -> int:
    """De que lado de un plano esta una cara: +1 o -1.

    Mira el vertice mas alejado y no el centro, porque el centro de una cara
    muy fina puede caer justo encima del plano y entonces el signo es una
    moneda al aire. Y si la cara **vive** dentro del plano -es una tapa que
    pusimos nosotros- no hay geometria que preguntar: se mira de que lado la
    apuntamos cuando la hicimos, que para eso se guarda.
    """
    lejos = 0.0
    for v in cara.verts:
        d = (v.co - punto).dot(normal)
        if abs(d) > abs(lejos):
            lejos = d
    if abs(lejos) > TOL:
        return 1 if lejos > 0.0 else -1
    if cara[capa] == plano + 1 and cara[lado]:
        return cara[lado]
    return 1


def _ejes(normal: Vector) -> Tuple[Vector, Vector]:
    """Dos direcciones perpendiculares dentro del plano, para trabajar en 2D."""
    suelto = Vector((0.0, 0.0, 1.0))
    if abs(normal.dot(suelto)) > 0.9:
        suelto = Vector((1.0, 0.0, 0.0))
    u = normal.cross(suelto).normalized()
    return u, normal.cross(u).normalized()


def _componentes(aristas):
    """Reparte las aristas en trozos que se tocan entre si."""
    porv = {}
    for arista in aristas:
        for v in arista.verts:
            porv.setdefault(v, []).append(arista)
    visto = set()
    trozos = []
    for semilla in aristas:
        if semilla in visto:
            continue
        visto.add(semilla)
        pila = [semilla]
        trozo = []
        while pila:
            arista = pila.pop()
            trozo.append(arista)
            for v in arista.verts:
                for otra in porv[v]:
                    if otra not in visto:
                        visto.add(otra)
                        pila.append(otra)
        trozos.append(trozo)
    return trozos, porv


def _recorrer(bm, trozo, porv):
    """Pone las aristas de un trozo en orden de anillo. None si no es un anillo.

    Si el trozo es una cadena abierta -pasa en alguna arista suelta que el
    corte no llego a cerrar- se cierra con una arista nueva entre las dos
    puntas, que es justo el trocito que le faltaba al contorno.
    """
    grado = {}
    for arista in trozo:
        for v in arista.verts:
            grado[v] = grado.get(v, 0) + 1
    if any(g > 2 for g in grado.values()):
        return None
    puntas = [v for v, g in grado.items() if g == 1]
    if len(puntas) > 2:
        return None

    if len(puntas) == 2:
        # cadena abierta: se cierra con la arista que le faltaba
        cierre = bm.edges.get(puntas) or bm.edges.new(puntas)
        trozo.append(cierre)
        porv.setdefault(puntas[0], []).append(cierre)
        porv.setdefault(puntas[1], []).append(cierre)
        puntas = []

    arranque = puntas[0] if puntas else trozo[0].verts[0]
    orden = [arranque]
    usadas = set()
    actual = arranque
    while True:
        siguiente = None
        for arista in porv[actual]:
            if arista in usadas:
                continue
            siguiente = arista
            break
        if siguiente is None:
            break
        usadas.add(siguiente)
        actual = siguiente.other_vert(actual)
        if actual is arranque:
            break
        orden.append(actual)
    if len(orden) < 3:
        return None
    return orden


def _dentro(px: float, py: float, xs, ys) -> bool:
    """Prueba del rayo: cuantas veces cruza el contorno una linea horizontal."""
    x2 = np.roll(xs, -1)
    y2 = np.roll(ys, -1)
    cruza = (ys > py) != (y2 > py)
    if not cruza.any():
        return False
    dy = np.where(y2 != ys, y2 - ys, 1.0)
    corte = (x2 - xs) * (py - ys) / dy + xs
    return bool(np.count_nonzero(cruza & (px < corte)) & 1)


def _por_anidamiento(bm, aristas, normal):
    """Agrupa los contornos de un corte segun quien esta dentro de quien.

    Es la parte fina. Dos piezas vecinas comparten la tapa del corte anterior,
    asi que en el corte nuevo sus contornos **se tocan** -los gajos, por
    ejemplo, se tocan todos en el eje-. Si se le dan juntos a la triangulacion
    cose un puente de una pieza a la otra y las vuelve a pegar. Y al reves:
    una pieza de piel tiene dos contornos, el de fuera y el de dentro, y esos
    si hay que darselos juntos o rellena el hueco.

    La regla que distingue los dos casos es la misma de toda la vida: un
    contorno que esta **dentro** de otro es un agujero suyo; uno que solo lo
    toca es otra pieza. Asi que se mide el anidamiento y se agrupa cada
    contorno par con los impares que cuelgan de el.
    """
    u, w = _ejes(normal)
    trozos, porv = _componentes(aristas)
    sueltos = []
    anillos = []
    for trozo in trozos:
        orden = _recorrer(bm, trozo, porv)
        if orden is None:
            sueltos.append(trozo)
            continue
        xs = np.fromiter((v.co.dot(u) for v in orden), float, len(orden))
        ys = np.fromiter((v.co.dot(w) for v in orden), float, len(orden))
        anillos.append((trozo, orden, xs, ys))

    # un punto claramente dentro de cada anillo: el medio de su arista mas
    # larga, empujado un pelin hacia dentro
    dentros = []
    for _, orden, xs, ys in anillos:
        area = float(np.dot(xs, np.roll(ys, -1)) - np.dot(ys, np.roll(xs, -1)))
        dx = np.roll(xs, -1) - xs
        dy = np.roll(ys, -1) - ys
        k = int(np.argmax(dx * dx + dy * dy))
        largo = math.hypot(dx[k], dy[k]) or 1.0
        giro = 1.0 if area >= 0.0 else -1.0
        paso = 1e-3 * largo
        dentros.append((xs[k] + dx[k] / 2 - giro * dy[k] / largo * paso,
                        ys[k] + dy[k] / 2 + giro * dx[k] / largo * paso))

    cajas = [(xs.min(), xs.max(), ys.min(), ys.max()) for _, _, xs, ys in anillos]
    hondo = []
    padres = []
    for i, (px, py) in enumerate(dentros):
        mete = []
        for j, (_, _, xs, ys) in enumerate(anillos):
            if i == j:
                continue
            x0, x1, y0, y1 = cajas[j]
            if not (x0 <= px <= x1 and y0 <= py <= y1):
                continue
            if _dentro(px, py, xs, ys):
                mete.append(j)
        hondo.append(len(mete))
        padres.append(mete)

    grupos = {}
    for i, mete in enumerate(padres):
        if hondo[i] % 2 == 0:
            jefe = i
        else:
            jefe = max(mete, key=lambda j: hondo[j])
        grupos.setdefault(jefe, []).extend(anillos[i][0])
    return list(grupos.values()) + sueltos


def _partir(arista, puntos):
    """Mete vertices nuevos dentro de una arista, en el orden en que van.

    `puntos` son pares (t, coordenada) con t medido desde el primer vertice.
    Se parte la arista de verdad, con lo que la cara de al lado tambien se
    parte: esa es la gracia, porque si no la tapa se apoya en unos vertices y
    la piel en otros, y entre las dos queda una rendija.
    """
    primero = arista.verts[0]
    actual = arista
    desde = 0.0
    salida = []
    for t, co in puntos:
        resto = max(1.0 - desde, 1e-12)
        fraccion = min(max((t - desde) / resto, 1e-6), 1.0 - 1e-6)
        nueva, vertice = bmesh.utils.edge_split(actual, primero, fraccion)
        vertice.co = co
        salida.append(vertice)
        primero = vertice
        actual = nueva
        desde = t
    return salida


def _rellenar(bm, aristas, punto: Vector, normal: Vector, u: Vector, w: Vector,
              capa, lado, indice: int, signo: int) -> int:
    """Cierra un contorno de corte con una tapa plana. Devuelve las caras.

    No se usa `triangle_fill` -el relleno de toda la vida de Blender- porque se
    atraganta con lo que sale de verdad de un corte: aristas de largo cero,
    vertices repetidos y contornos que se tocan a si mismos. Medido en el
    samurai, dejaba un tercio de los bordes sin tapar. Aqui se hace en tres
    pasos que si aguantan eso:

    1. Se triangula el plano entero con Delaunay restringido -el mismo motor
       que usa Blender por dentro para los booleanos-, que respeta cada arista
       del contorno como una pared.
    2. Si el contorno se cruza consigo mismo -y pasa, porque Solidificar mete
       la cara de dentro por la de fuera en los sitios estrechos-, la
       triangulacion parte las aristas por donde se cruzan. Entonces hay que
       partirlas tambien en la malla, o la tapa se queda apoyada en vertices
       que la piel no tiene.
    3. Se inunda desde fuera contando paredes: cada vez que se cruza una se
       cambia de dentro a fuera. Los triangulos que quedan dentro son la tapa;
       los de fuera y los de los huecos se tiran.

    Asi los huecos de una pieza de piel salen solos, sin decirle a nadie cual
    es el contorno de dentro y cual el de fuera.
    """
    # una arista sin cara no tiene contorno que orientar: es basura suelta
    aristas = [a for a in aristas if a.is_valid and a.link_faces]
    sitio = {}
    planos2d = []
    for arista in aristas:
        for v in arista.verts:
            if v not in sitio:
                sitio[v] = len(planos2d)
                planos2d.append(Vector((v.co.dot(u), v.co.dot(w))))
    # Cada arista se guarda **orientada** como la ve su cara: de donde sale a
    # donde va. Con eso se puede contar vueltas mas adelante, que es lo que
    # distingue un hueco de verdad de un sitio donde la piel se monta sobre si
    # misma.
    pares = []
    duenas = []
    for arista in aristas:
        primero = arista.verts[0]
        for lazo in arista.link_faces[0].loops:
            if lazo.edge is arista:
                primero = lazo.vert
                break
        segundo = arista.other_vert(primero)
        a, b = sitio[primero], sitio[segundo]
        if a != b:
            pares.append((a, b))
            duenas.append(arista)
    if len(pares) < 3:
        return 0

    try:
        coords, salidas, triangulos, de_vert, de_arista, _ = delaunay_2d_cdt(
            planos2d, pares, [], 0, EPS, True)
    except Exception:
        return 0
    if not triangulos:
        return 0

    atras = {}
    for v, i in sitio.items():
        atras.setdefault(i, v)
    donde = {}
    for i, viejos in enumerate(de_vert):
        for viejo in viejos:
            donde.setdefault(viejo, i)

    altura = punto.dot(normal)
    verts = [None] * len(coords)
    for i, viejos in enumerate(de_vert):
        for viejo in viejos:
            if viejo in atras:
                verts[i] = atras[viejo]
                break

    # las aristas que la triangulacion partio por la mitad
    trozos = {}
    for k, (a, b) in enumerate(salidas):
        for viejo in de_arista[k]:
            if viejo < len(pares):
                trozos.setdefault(viejo, set()).update((a, b))
    soldar = {}
    for k, tocados in trozos.items():
        extremos = {donde.get(pares[k][0]), donde.get(pares[k][1])}
        medios = [i for i in tocados if i not in extremos]
        if not medios:
            continue
        arista = duenas[k]
        if not arista.is_valid:
            continue
        origen = Vector((arista.verts[0].co.dot(u), arista.verts[0].co.dot(w)))
        hacia = Vector((arista.verts[1].co.dot(u),
                        arista.verts[1].co.dot(w))) - origen
        largo = hacia.length_squared or 1.0
        seguidos = sorted(
            ((coords[i] - origen).dot(hacia) / largo, i) for i in medios)
        puestos = _partir(
            arista,
            [(t, coords[i].x * u + coords[i].y * w + altura * normal)
             for t, i in seguidos])
        for (_, i), vertice in zip(seguidos, puestos):
            if verts[i] is None:
                verts[i] = vertice
            elif verts[i] is not vertice:
                # el cruce cayo justo encima de un vertice que ya existia:
                # se parte igual y luego se sueldan los dos, que es lo que
                # deshace la T y deja la malla cerrada
                soldar[vertice] = verts[i]
    if soldar:
        bmesh.ops.weld_verts(bm, targetmap=soldar)

    for i, co in enumerate(coords):
        if verts[i] is None:
            verts[i] = bm.verts.new(co.x * u + co.y * w + altura * normal)

    # Cada arista de la triangulacion apunta a que contornos la pisan y en que
    # sentido. Se cuenta por sentidos y no por veces -par o impar- a proposito:
    # Solidificar mete la cara de dentro por fuera de la de fuera en los
    # sitios estrechos, y ahi la piel se monta sobre si misma. Contando par o
    # impar, ese trozo montado sale como si fuera un hueco y la tapa se abre
    # justo donde hay mas material. Contando vueltas, dos capas de material
    # siguen siendo material, que es lo que se ve en la pieza.
    muros = {}
    for k, (a, b) in enumerate(salidas):
        for viejo in de_arista[k]:
            if viejo >= len(pares):
                continue
            p, q = pares[viejo]
            rumbo = coords[donde[q]] - coords[donde[p]]
            derecho = (coords[b] - coords[a]).dot(rumbo) >= 0
            llave = (a, b) if a < b else (b, a)
            muros.setdefault(llave, []).append((a, b) if derecho else (b, a))

    # Se le da la vuelta a los triangulos que vengan del reves. Contar vueltas
    # depende de que todos giren igual, y no se puede dar por hecho que la
    # triangulacion los devuelva asi.
    derechos = []
    for cara in triangulos:
        p0, p1, p2 = (coords[i] for i in cara[:3])
        area = ((p1.x - p0.x) * (p2.y - p0.y) - (p1.y - p0.y) * (p2.x - p0.x))
        derechos.append(list(cara) if area >= 0 else list(reversed(cara)))
    triangulos = derechos

    vecinos = {}
    for t, cara in enumerate(triangulos):
        for k in range(len(cara)):
            a, b = cara[k], cara[(k + 1) % len(cara)]
            vecinos.setdefault((a, b) if a < b else (b, a), []).append(t)

    def salto(triangulo: int, llave) -> int:
        """Cuantas vueltas se ganan al entrar en este triangulo por esa arista."""
        rumbos = muros.get(llave)
        if not rumbos:
            return 0
        cara = triangulos[triangulo]
        suma = 0
        for k in range(len(cara)):
            paso = (cara[k], cara[(k + 1) % len(cara)])
            for rumbo in rumbos:
                if paso == rumbo:
                    suma += 1
                elif paso == (rumbo[1], rumbo[0]):
                    suma -= 1
        return suma

    # Se cuentan las dos cosas a la vez: las vueltas, que es lo fino, y el par
    # o impar de toda la vida, que es lo bruto. Y se queda el triangulo si
    # cualquiera de las dos dice que esta dentro.
    #
    # Hace falta el bruto por un caso concreto: cuando la piel se pliega sobre
    # si misma, el contorno pasa dos veces por el mismo sitio en sentidos
    # contrarios y las vueltas se anulan, con lo que ni un lado ni el otro
    # llevan tapa y la arista se queda al aire para siempre. Con el par o
    # impar uno de los dos lados si la lleva. Es una lamina de espesor cero,
    # o sea que no anade material, pero cierra la pieza, que es de lo que se
    # trata.
    vueltas = [None] * len(triangulos)
    pares_impares = [0] * len(triangulos)
    cola = []
    for llave, tocan in vecinos.items():
        if len(tocan) == 1 and vueltas[tocan[0]] is None:
            vueltas[tocan[0]] = salto(tocan[0], llave)
            pares_impares[tocan[0]] = 1 if llave in muros else 0
            cola.append(tocan[0])
    while cola:
        t = cola.pop()
        cara = triangulos[t]
        for k in range(len(cara)):
            a, b = cara[k], cara[(k + 1) % len(cara)]
            llave = (a, b) if a < b else (b, a)
            for otro in vecinos[llave]:
                if otro == t or vueltas[otro] is not None:
                    continue
                vueltas[otro] = vueltas[t] + salto(otro, llave)
                pares_impares[otro] = pares_impares[t] ^ (
                    1 if llave in muros else 0)
                cola.append(otro)

    hechas = 0
    for t, cara in enumerate(triangulos):
        if not vueltas[t] and not pares_impares[t]:
            continue
        trio = [verts[i] for i in cara]
        if len(set(trio)) < len(trio):
            continue
        if bm.faces.get(trio):
            continue
        try:
            nueva = bm.faces.new(trio)
        except ValueError:
            continue
        # La tapa tiene que mirar hacia afuera de su pieza: la de la pieza de
        # arriba mira hacia abajo y al reves. No se deja para el final: los
        # planos siguientes leen de estas caras por donde va el contorno, y si
        # una mira al reves, el corte siguiente cuenta las vueltas al reves y
        # se abre justo por ahi.
        nueva.normal_update()   # recien creada, la normal aun no esta calculada
        if nueva.normal.dot(normal) * signo > 0.0:
            nueva.normal_flip()
        nueva[capa] = indice + 1
        nueva[lado] = signo
        hechas += 1
    return hechas


def _coser(bm, abiertas, soldadura: float) -> int:
    """Vuelve a juntar los bordes sueltos que se quedaron sin tapa.

    Donde el plano corre pegado a la superficie -por una pared fina, o por el
    eje que comparten los gajos- el corte sale sin area: una linea de ida y
    vuelta, que no tiene tapa posible porque no tiene nada dentro. Ahi no hay
    nada que separar, asi que lo correcto es deshacer el rasgado y coser los
    dos lados otra vez. Devuelve cuantas aristas cerro.
    """
    if not abiertas:
        return 0
    antes = len(abiertas)
    sueltos = set()
    for arista in abiertas:
        sueltos.update(arista.verts)
    bmesh.ops.remove_doubles(bm, verts=list(sueltos), dist=soldadura)
    return antes - sum(1 for e in abiertas if e.is_valid and e.is_boundary)


def _soltar_pajaritas(bm, vertices, capa, lado) -> int:
    """Desdobla los vertices por los que dos piezas siguen cogidas de la mano.

    Pasa en cualquier punta: en el polo de una esfera, en la punta de un cono,
    en el vertice de una piramide. Todos los planos radiales pasan justo por
    ahi, asi que ninguno lo **corta**: lo tocan. El resultado es que dos gajos
    opuestos siguen unidos por ese unico vertice -una pajarita- y `separar por
    trozos sueltos`, que va por vertices, los da por la misma pieza. En la
    esfera de prueba salian piezas de un metro de largo en vez de medio.

    La cura es mirar, en cada vertice del corte, si las caras que lo rodean
    forman un solo abanico o varios. Si son varios, cada uno se queda con su
    propio vertice y las piezas se sueltan de verdad.
    """
    sueltos = 0
    for v in vertices:
        if not v.is_valid or len(v.link_faces) < 2:
            continue
        jefe = {}

        def raiz(cara):
            while jefe.get(cara, cara) is not cara:
                cara = jefe[cara]
            return cara

        for cara in v.link_faces:
            jefe.setdefault(cara, cara)
        for arista in v.link_edges:
            caras = [f for f in arista.link_faces]
            for otra in caras[1:]:
                a, b = raiz(caras[0]), raiz(otra)
                if a is not b:
                    jefe[b] = a
        grupos = {}
        for cara in v.link_faces:
            grupos.setdefault(raiz(cara), []).append(cara)
        if len(grupos) < 2:
            continue
        for grupo in list(grupos.values())[1:]:
            nuevo = bm.verts.new(v.co)
            for cara in list(grupo):
                orden = [nuevo if x is v else x for x in cara.verts]
                marca = (cara[capa], cara[lado])
                bm.faces.remove(cara)
                try:
                    rehecha = bm.faces.new(orden)
                except ValueError:
                    continue
                rehecha[capa], rehecha[lado] = marca
            sueltos += 1
    return sueltos


def cortar(bm: bmesh.types.BMesh, planos: Sequence[Plano], avisar=None,
           pizca: float = TOL, soldadura: float = 1e-4) -> int:
    """Corta, rasga y tapa la malla plano por plano. Devuelve las tapas hechas.

    Al salir, los trozos ya estan sueltos unos de otros y cerrados, todavia
    dentro del mismo bmesh. Repartirlos en objetos es el paso siguiente.
    """
    capa = bm.faces.layers.int.get(CAPA) or bm.faces.layers.int.new(CAPA)
    lado = bm.faces.layers.int.get(LADO) or bm.faces.layers.int.new(LADO)
    puntos = [Vector(p.punto) for p in planos]
    normales = [Vector(p.normal).normalized() for p in planos]
    tapadas = 0

    for i in range(len(planos)):
        if avisar is not None:
            avisar(i, len(planos))
        punto, normal = puntos[i], normales[i]

        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        salida = bmesh.ops.bisect_plane(
            bm, geom=geom, dist=pizca,
            plane_co=punto, plane_no=normal,
            use_snap_center=False, clear_outer=False, clear_inner=False)
        # El bisect marca tambien donde el plano solo **roza** la malla sin
        # partirla -los gajos se rozan todos en el eje-. Eso no es un corte:
        # si se rasga, quedan dos aristas encima la una de la otra que ya no
        # hay manera de tapar. Un corte de verdad tiene una cara a cada lado.
        cortadas = []
        for arista in salida["geom_cut"]:
            if not isinstance(arista, bmesh.types.BMEdge) or not arista.is_valid:
                continue
            if len(arista.link_faces) != 2:
                continue
            if (_signo(arista.link_faces[0], punto, normal, i, capa, lado)
                    != _signo(arista.link_faces[1], punto, normal, i, capa, lado)):
                cortadas.append(arista)
        if not cortadas:
            continue

        nuevas = bmesh.ops.split_edges(bm, edges=cortadas)["edges"]
        bm.edges.index_update()
        # `split_edges` devuelve tambien las aristas que ya le habiamos dado,
        # asi que hay que quitar repetidas o la triangulacion protesta.
        bordes = {}
        for arista in list(cortadas) + list(nuevas):
            if isinstance(arista, bmesh.types.BMEdge) and arista.is_valid:
                bordes[arista.index] = arista
        # Una arista de largo cero no la puede usar ninguna cara, asi que se
        # quedaria de borde para siempre y la pieza nunca cerraria. Salen
        # solas cuando varios planos se cruzan en la misma linea -los gajos,
        # todos por el eje-, y aqui se derriten antes de tapar.
        bmesh.ops.dissolve_degenerate(bm, dist=EPS, edges=list(bordes.values()))
        bordes = {i: e for i, e in bordes.items() if e.is_valid}

        caras = {1: [], -1: []}
        for arista in bordes.values():
            if not arista.is_boundary:
                continue
            caras[_signo(arista.link_faces[0], punto, normal, i, capa, lado)
                  ].append(arista)

        u, w = _ejes(normal)
        for signo, sueltas in caras.items():
            if len(sueltas) < 3:
                continue
            for grupo in _por_anidamiento(bm, sueltas, normal):
                tapadas += _rellenar(bm, grupo, punto, normal, u, w,
                                     capa, lado, i, signo)

        _soltar_pajaritas(
            bm, {v for e in bordes.values() if e.is_valid for v in e.verts},
            capa, lado)

    # Aqui **no** se cose nada de lo que quede abierto, y es a proposito.
    # Coser junta los dos labios del corte, y en un sitio donde el corte salio
    # sin area eso vuelve a pegar las dos piezas: se corta la figura y sale
    # entera. El remate se hace despues, pieza por pieza y cada una en su
    # objeto, donde coser ya no puede pegar una con otra.
    return tapadas


def cortar_objeto(objeto: bpy.types.Object,
                  planos: Sequence[Plano],
                  avisar=None) -> int:
    """`cortar` sobre la malla de un objeto. Devuelve las tapas hechas."""
    malla = objeto.data
    # Lo que se cose es siempre un desperfecto, asi que la distancia puede ser
    # generosa; se mide contra el tamano del modelo para que valga igual en una
    # figura de dos metros que en una de veinte centimetros.
    diagonal = Vector(objeto.dimensions).length or 1.0
    bm = bmesh.new()
    bm.from_mesh(malla)
    try:
        tapadas = cortar(bm, planos, avisar, soldadura=max(1e-5, diagonal * 1e-5))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(malla)
    finally:
        bm.free()
    malla.update()
    return tapadas


def separar_piezas(objeto: bpy.types.Object,
                   contexto=None) -> List[bpy.types.Object]:
    """Reparte los trozos sueltos en objetos, usando el separador compilado.

    Recorrer las islas desde Python con millones de caras son minutos;
    `mesh.separate(type='LOOSE')` lo hace en segundos porque esta en C.
    """
    contexto = contexto or bpy.context
    for otro in list(contexto.selected_objects):
        otro.select_set(False)
    objeto.select_set(True)
    contexto.view_layer.objects.active = objeto
    antes = set(bpy.data.objects)
    bpy.ops.mesh.separate(type="LOOSE")
    nuevos = [o for o in bpy.data.objects if o not in antes]
    piezas = []
    for pieza in [objeto] + nuevos:
        if pieza.data.polygons:
            piezas.append(pieza)
        else:
            bpy.data.objects.remove(pieza, do_unlink=True)
    return piezas


def cerrar_huecos(objeto: bpy.types.Object) -> Tuple[int, int]:
    """Remata una pieza tapando lo poco que haya quedado abierto.

    Despues de cortar y tapar bien puede sobrevivir algun agujero minusculo.
    Salen donde la malla de partida ya venia mal: vertices repetidos, caras de
    area cero, un pico que se cierra sobre si mismo. Son unas pocas aristas
    entre miles, pero una pieza abierta no se puede imprimir, asi que se
    intenta cerrar de cuatro maneras, de la mas fina a la mas bruta: soldar lo
    que este pegado, tapar los agujeros que sean anillos limpios, un abanico
    desde el centro para los que no lo sean, y quitar las aletas -una cara
    suelta pegada solo por dos aristas, que no es un agujero sino una cara de
    mas-.

    Todo el remate trabaja **solo alrededor de los bordes sueltos**, no
    recorriendo la pieza entera. Recorrer un millon de aristas desde Python
    una docena de veces son minutos; mirar las cuatro que estan rotas es
    instantaneo, y el resultado es el mismo porque un agujero no se mueve de
    donde esta.

    Devuelve cuantas aristas estaban abiertas antes y cuantas quedan despues.
    (0, 0) es que la pieza ya venia perfecta; un segundo numero distinto de
    cero es una pieza que no se ha podido cerrar y hay que avisar de ella.
    """
    bm = bmesh.new()
    bm.from_mesh(objeto.data)
    try:
        primeras = [e for e in bm.edges if e.is_boundary]
        abiertas = len(primeras)
        if not abiertas:
            return (0, 0)
        diagonal = Vector(objeto.dimensions).length or 1.0
        soldadura = max(1e-5, diagonal * 1e-5)

        zona = {v for arista in primeras for v in arista.verts}

        def sueltas():
            """Los bordes abiertos que hay ahora mismo cerca del destrozo."""
            for v in list(zona):
                if not v.is_valid:
                    zona.discard(v)
            fuera = {arista for v in zona for arista in v.link_edges
                     if arista.is_boundary}
            for arista in fuera:
                zona.update(arista.verts)
            return list(fuera)

        for _ in range(6):
            if not _coser(bm, sueltas(), soldadura):
                break

        pendientes = sueltas()
        if pendientes:
            bmesh.ops.holes_fill(bm, edges=pendientes, sides=0)

        for _ in range(3):
            pendientes = sueltas()
            if not pendientes or not _abanicos(bm, pendientes):
                break

        # Si todavia queda algo abierto es que el borde esta enredado: la
        # malla de partida tenia ahi caras encima de caras. Se muerde el
        # reborde -las caras que tocan el agujero- hasta que el contorno es un
        # anillo limpio, y entonces si se tapa.
        for _ in range(8):
            pendientes = sueltas()
            if not pendientes:
                break
            bmesh.ops.delete(
                bm, geom=list({f for e in pendientes for f in e.link_faces}),
                context="FACES")
            _limpiar(bm, zona)
            pendientes = sueltas()
            if not pendientes:
                break
            bmesh.ops.holes_fill(bm, edges=pendientes, sides=0)
            pendientes = sueltas()
            if pendientes:
                _abanicos(bm, pendientes)

        # Y las aletas: un triangulo pegado a la malla por dos aristas con la
        # tercera al aire. No es un agujero, es una cara de mas, asi que no se
        # tapa: se quita.
        for _ in range(8):
            pendientes = sueltas()
            if not pendientes:
                break
            trozos, _ = _componentes(pendientes)
            aletas = {f for trozo in trozos if len(trozo) < 3
                      for arista in trozo for f in arista.link_faces}
            if not aletas:
                break
            bmesh.ops.delete(bm, geom=list(aletas), context="FACES")
            _limpiar(bm, zona)
            pendientes = sueltas()
            if pendientes:
                bmesh.ops.holes_fill(bm, edges=pendientes, sides=0)
                pendientes = sueltas()
                if pendientes:
                    _abanicos(bm, pendientes)

        _limpiar(bm, zona)
        quedan = len(sueltas())
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(objeto.data)
        objeto.data.update()
    finally:
        bm.free()
    return (abiertas, quedan)


def _limpiar(bm, zona=None) -> None:
    """Tira las aristas y los vertices que no sostienen ninguna cara.

    Una arista sin caras se cuenta como borde abierto y no hay tapa que la
    cierre, porque no hay nada que tapar: es basura de la malla de partida.
    """
    if zona is None:
        aristas = bm.edges
        verts = bm.verts
    else:
        vivos = [v for v in zona if v.is_valid]
        aristas = {e for v in vivos for e in v.link_edges}
        verts = vivos
    hilos = [e for e in aristas if not e.link_faces]
    if hilos:
        bmesh.ops.delete(bm, geom=hilos, context="EDGES")
    solos = [v for v in verts if v.is_valid and not v.link_edges]
    if solos:
        bmesh.ops.delete(bm, geom=solos, context="VERTS")


def _abanicos(bm, sueltas) -> int:
    """Tapa a lo bruto: un abanico de triangulos desde el centro del agujero.

    Es el ultimo recurso, para agujeros que ni son planos ni son un anillo
    limpio. No queda bonito, pero cierra, y cerrar es lo que hace falta para
    imprimir. Solo llega aqui lo que venia roto de la malla original.

    El abanico se monta sobre el **recorrido** del agujero, no arista por
    arista. Si se hace arista por arista, los dos radios de los extremos se
    quedan con una sola cara cada uno y el agujero no se cierra: se hace mas
    pequeno y vuelve a empezar, sin acabar nunca.
    """
    trozos, porv = _componentes(sueltas)
    hechas = 0
    for trozo in trozos:
        orden = _recorrer(bm, trozo, porv)
        if orden is None or len(orden) < 3:
            continue
        centro = Vector((0.0, 0.0, 0.0))
        for v in orden:
            centro += v.co
        centro /= len(orden)
        medio = bm.verts.new(centro)
        for k in range(len(orden)):
            a, b = orden[k], orden[(k + 1) % len(orden)]
            if a is b:
                continue
            try:
                bm.faces.new((a, b, medio))
                hechas += 1
            except ValueError:
                continue
        if not medio.link_faces:
            bm.verts.remove(medio)
    return hechas


def medidas(objeto: bpy.types.Object) -> Tuple[float, float, float]:
    """Tamano de la caja de la pieza, en milimetros de mundo."""
    esquinas = [objeto.matrix_world @ Vector(v) for v in objeto.bound_box]
    xs = [p.x for p in esquinas]
    ys = [p.y for p in esquinas]
    zs = [p.z for p in esquinas]
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def cuenta_caras(objeto: bpy.types.Object) -> int:
    return len(objeto.data.polygons)
