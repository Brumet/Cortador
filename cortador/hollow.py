"""Vaciado del modelo: convertir el solido en una piel de espesor constante.

Es lo que hace el modificador *Solidify* de Blender o la funcion *hueco* de
los laminadores: en vez de imprimir un bloque macizo, solo se fabrica la
cascara exterior del modelo y el interior queda vacio. Asi una figura de dos
metros se construye con laminas que pesan y cuestan una fraccion.

Hay dos caminos, segun lo que se vaya a cortar despues:

* **2D (por rebanada)**: al contorno de la rebanada se le resta su propio
  contorno encogido `pared` milimetros, y queda un anillo con la forma
  exterior del modelo. Exacto, rapido y no falla nunca. Es el que se usa en
  el modo laminas.
* **3D (toda la malla)**: se desplazan los vertices hacia dentro a lo largo de
  la normal y se resta ese solido interior del original. Es el que se usa en
  el modo trozos.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np
import trimesh
from shapely.geometry import MultiPolygon, Polygon

from .geometry import (EPS, boolean_op, en_paralelo, extrude_polygons,
                       merge_polygons)

#: por debajo de este espesor de pared no tiene sentido vaciar
MIN_WALL = 0.2


def limpiar(geom, minimo: float):
    """Quita del contorno los hilos y las motas mas pequenos que `minimo`.

    Al encoger un contorno con detalles finos aparecen esquirlas de decimas de
    milimetro: no se pueden fabricar ni pegar, y multiplican por cien el numero
    de piezas. Se quitan aqui, antes de extruir nada.
    """
    from shapely.geometry import Polygon as _Polygon
    from shapely.ops import unary_union

    if geom is None or geom.is_empty or minimo <= 0:
        return geom
    # apertura morfologica muy suave: mata los hilos de decimas de milimetro
    # sin llegar a partir una pared fina que si es buena
    fino = min(0.15, max(minimo * 0.02, 0.02))
    try:
        abierto = geom.buffer(-fino).buffer(fino)
        if not abierto.is_empty:
            geom = abierto
    except Exception:
        pass
    partes = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    area_minima = minimo * minimo * 0.5
    ancho_minimo = minimo * 0.3
    utiles = []
    for parte in partes:
        if not isinstance(parte, _Polygon) or parte.is_empty:
            continue
        minx, miny, maxx, maxy = parte.bounds
        if max(maxx - minx, maxy - miny) < minimo:
            continue                      # una mota
        if parte.area < area_minima:
            continue
        # ancho medio de la banda: descarta hilos largos pero finisimos
        if parte.length > 0 and 4.0 * parte.area / parte.length < ancho_minimo:
            continue
        utiles.append(parte)
    if not utiles:
        return None
    return unary_union(utiles)


def ring_polygons(geom, wall: float):
    """Convierte un contorno relleno en un anillo de `wall` mm de pared.

    Devuelve None si la figura es tan fina que no queda hueco (entonces la
    pieza se deja maciza, que es lo correcto).
    """
    if geom is None or geom.is_empty or wall < MIN_WALL:
        return geom
    interior = geom.buffer(-float(wall))
    if interior.is_empty or interior.area <= EPS:
        return geom               # pared mas gruesa que la pieza: queda maciza
    anillo = geom.difference(interior)
    if anillo.is_empty or anillo.area <= EPS:
        return None
    if isinstance(anillo, Polygon):
        anillo = MultiPolygon([anillo])
    return anillo


def inner_polygons(geom, wall: float):
    """El hueco interior (lo que se quita), o None si no queda nada dentro."""
    if geom is None or geom.is_empty or wall < MIN_WALL:
        return None
    interior = geom.buffer(-float(wall))
    if interior.is_empty or interior.area <= EPS:
        return None
    if isinstance(interior, Polygon):
        interior = MultiPolygon([interior])
    return interior


def hollow_slab(slab: trimesh.Trimesh,
                section,
                wall: float,
                z_lo: float,
                z_hi: float,
                axis: int = 2) -> Tuple[trimesh.Trimesh, bool]:
    """Vacia una rebanada solida dejando una pared de `wall` mm.

    `section` es el contorno de la rebanada en coordenadas del plano. Se
    extruye su version encogida y se resta, de modo que la rebanada conserva
    todo su relieve exterior pero queda hueca por dentro.
    """
    interior = inner_polygons(section, wall)
    if interior is None:
        return slab, False
    altura = float(z_hi) - float(z_lo)
    nucleo = extrude_polygons(interior, altura + 2.0)
    if nucleo is None:
        return slab, False
    from .geometry import plane_transform
    nucleo.apply_translation([0.0, 0.0, -1.0])
    nucleo.apply_transform(np.linalg.inv(plane_transform(axis, z_lo)))
    resultado = boolean_op("difference", slab, nucleo)
    if resultado is None:
        return slab, False
    return resultado, True


def hollow_mesh(mesh: trimesh.Trimesh,
                wall: float,
                report=None) -> Tuple[trimesh.Trimesh, Optional[str]]:
    """Convierte la malla entera en una cascara de `wall` mm de pared.

    Devuelve (malla, aviso). Si el vaciado no sale bien se devuelve la malla
    original y un aviso, nunca una pieza rota.
    """
    wall = float(wall)
    if wall < MIN_WALL:
        return mesh, None
    if not mesh.is_watertight:
        return mesh, ("No se puede vaciar una malla abierta: reparala primero "
                      "y vuelve a intentarlo.")

    grosor_minimo = float(np.min(mesh.extents))
    if wall * 2.0 >= grosor_minimo:
        return mesh, (f"La pared de {wall:g} mm no cabe en un modelo de "
                      f"{grosor_minimo:.1f} mm de grueso: se deja macizo.")

    # Dos herramientas, y cada una aporta lo que la otra no puede:
    #
    #   1. desplazamiento de la superficie (tipo *Solidify*). Rapido, y deja la
    #      cara interior lisa: es la que da el acabado. Pero en un escaneo con
    #      picos o con paredes finas se cruza consigo misma y la pared se queda
    #      en nada por algunos sitios.
    #   2. vaciado por capas. Se corta el modelo en secciones horizontales, se
    #      encoge cada una `wall` milimetros y se apilan. Encoger un contorno
    #      plano no puede cruzarse nunca, asi que el espesor esta garantizado
    #      por construccion; a cambio la cara interior queda escalonada.
    #
    # La primera es la que se usa siempre; la segunda entra solo si la primera
    # no llega a dar una piel cerrada. Lo que no se hace es mezclarlas: recortar
    # la cara lisa contra el vaciado por capas garantizaria el espesor, si, pero
    # le devolveria el relieve al interior y saldria escalonada (medido: el
    # grano interior sube de 3,2 a 10,6 grados). Antes que eso, se mide la pared
    # que ha salido y se dice, con lo que habria que pedir para que el minimo
    # sea el que se quiere (`espesor_recomendado`).
    def _avisar(texto):
        if report is not None:
            try:
                report(texto)
            except Exception:
                pass

    mejor = mejor_hueco = None
    for factor in (1.0, 0.8, 0.6):
        _avisar("Solidificando la piel")
        interior = _superficie_interior(mesh, wall * factor)
        if interior is None:
            break
        cascara = _cascara(mesh, interior)
        if cascara is None or not _es_piel(cascara, mesh, wall * factor):
            continue
        if cascara.is_watertight:
            mejor, mejor_hueco = cascara, interior
            break
        if mejor is None:
            mejor, mejor_hueco = cascara, interior

    if mejor is not None:
        return _sin_membranas(mesh, mejor, mejor_hueco, wall, _avisar), None

    _avisar("Vaciando por capas")
    cascara = _piel_por_capas(mesh, wall, _avisar)
    if cascara is not None and _es_piel(cascara, mesh, wall) and cascara.is_watertight:
        return cascara, None

    return mesh, ("Este trozo no admite el vaciado (recovecos muy cerrados o "
                  "paredes mas finas que el espesor): se deja macizo.")


def _cascara(mesh: trimesh.Trimesh,
             interior: trimesh.Trimesh) -> Optional[trimesh.Trimesh]:
    """Resta el interior del modelo y deja la piel lista para cortar.

    El motor booleano ya entrega una malla cerrada. Soldar vertices encima solo
    sirve para comprobar como la vera el laminador, **nunca para sustituirla**:
    donde la pared queda a espesor cero (un pico mas fino que la piel) el
    soldado funde las dos caras y aparecen aristas con cuatro triangulos. Una
    malla asi ya no se puede cortar en trozos cerrados, y todo lo que viene
    despues -el volumen, el ahorro, la vista previa- sale mal.
    """
    return _cascara_limpia(boolean_op("difference", mesh, interior))


def _sin_membranas(mesh: trimesh.Trimesh,
                   cascara: trimesh.Trimesh,
                   interior: Optional[trimesh.Trimesh],
                   wall: float,
                   avisar=None) -> trimesh.Trimesh:
    """Quita del hueco las zonas donde no queda pared, solo una membrana.

    Es lo que le paso al samurai: el faldon de la armadura es una placa de
    cuatro milimetros, mas fina que dos paredes de tres. Al vaciarla, la cara de
    dentro sale por el otro lado y quedan **dos superficies pegadas sin nada
    entre medias**. En la vista previa eso se ve como franjas que parpadean -dos
    capas peleandose por el mismo pixel-, el laminador rechaza la pieza y no hay
    nada que imprimir ahi.

    Lo correcto es no vaciar: si la placa es mas fina que la pared, la placa se
    queda maciza. Se consigue recortando el hueco contra el modelo encogido el
    **grosor minimo imprimible** -dos lineas de extrusion-, y no la pared
    entera. Encogerlo la pared entera tambien quita las membranas, pero gasta el
    doble de material y devuelve el relieve a la cara interior; medido en el
    modelo de prueba:

        sin recortar        391 cm3   10,3 % de la piel en membrana
        recortado a 1,5 mm  446 cm3    0,8 %
        recortado a 3,0 mm  757 cm3    0,0 %  pero el grano interior se triplica

    Cuesta un minuto en un modelo mediano, asi que primero se mide y solo se
    rehace si hay membranas de verdad.
    """
    def paso(texto):
        if avisar is not None:
            avisar(texto)

    if interior is None:
        return cascara
    if fraccion_membrana(mesh, cascara, wall, MUESTRAS_MEMBRANA) <= MEMBRANA_MAX:
        return cascara

    paso("Quitando las membranas")
    minimo = grosor_util(wall)
    grupos = _prismas_interiores(mesh, minimo, avisar, paso_z=wall)
    if grupos is None:
        return cascara

    partes = []
    for grupo in grupos:
        nucleo = _juntar_trozos(grupo)
        grupo.clear()
        if nucleo is None:
            continue
        trozo = boolean_op("intersection", interior, nucleo)
        nucleo = None
        if trozo is not None and len(trozo.faces):
            partes.append(trozo)
    if not partes:
        return cascara

    # los dos montones se tocan (una banda empieza donde acaba la anterior),
    # asi que hay que unirlos con CSG y no pegandolos a mano
    hueco = partes[0]
    for otra in partes[1:]:
        junto = boolean_op("union", hueco, otra)
        if junto is None:
            return cascara
        hueco = junto
    partes = None

    nueva = _cascara_limpia(boolean_op("difference", mesh, hueco))
    if nueva is None or not _es_piel(nueva, mesh, minimo) or not nueva.is_watertight:
        return cascara
    return nueva


def espesor_recomendado(wall: float, medida) -> Optional[float]:
    """Que espesor habria que pedir para que el minimo real sea el que quieres.

    En un escaneo, la cara interior es lisa y la de fuera no, asi que la pared
    no puede ser igual en todas partes: por los picos sobra y por los valles
    falta, y lo que falta es el relieve del modelo. Ese desfase se mantiene al
    subir el espesor, asi que basta con sumarlo: si pides 3 y el percentil 1
    sale en 1,5, pidiendo 4,5 el percentil 1 sale en 3.

    Devuelve None si la pared ya cumple.
    """
    if not medida:
        return None
    falta = float(wall) - float(medida[1])
    if falta <= float(wall) * (1.0 - PARED_MINIMA):
        return None
    return round(float(wall) + falta, 1)


#: por debajo de esta fraccion del espesor pedido, una pared se considera una
#: lamina fina: no aguanta el ensamble y hay que rehacerla
PARED_MINIMA = 0.95


def grosor_util(wall: float) -> float:
    """Por debajo de esto no hay pared, hay una membrana.

    Dos lineas de extrusion: menos que eso no se puede imprimir, no se puede
    pegar y, si las dos caras llegan a tocarse, el laminador rechaza la pieza.
    """
    return max(0.8, float(wall) * 0.4)


def _grosores(mesh: trimesh.Trimesh,
              cascara: trimesh.Trimesh,
              muestras: int = 4000) -> Optional[np.ndarray]:
    """Espesor de la piel en puntos repartidos por toda ella.

    Se siembran puntos por la cascara y se mide lo que hay desde cada uno hasta
    la superficie del modelo. Los que caen en la cara de fuera dan cero y no
    cuentan; los de la cara de dentro dan el espesor de la pared justo ahi.
    """
    try:
        puntos, _ = trimesh.sample.sample_surface(cascara, int(muestras))
        _, distancia, _ = trimesh.proximity.closest_point(mesh, puntos)
    except Exception:
        return None
    dentro = np.asarray(distancia, dtype=float)
    dentro = dentro[dentro > 0.02]
    return dentro if len(dentro) >= 20 else None


def medir_pared(mesh: trimesh.Trimesh,
                cascara: trimesh.Trimesh,
                muestras: int = 4000):
    """Espesor real de la piel, medido sobre la pieza terminada.

    No se da por supuesto: se mide. Devuelve (minimo, percentil 1, mediana) en
    milimetros, o None si no se ha podido medir.
    """
    dentro = _grosores(mesh, cascara, muestras)
    if dentro is None:
        return None
    return (float(dentro.min()), float(np.percentile(dentro, 1)),
            float(np.median(dentro)))


def fraccion_membrana(mesh: trimesh.Trimesh,
                      cascara: trimesh.Trimesh,
                      wall: float,
                      muestras: int = 4000) -> float:
    """Que parte de la piel se ha quedado en membrana en vez de en pared."""
    dentro = _grosores(mesh, cascara, muestras)
    if dentro is None:
        return 0.0
    return float((dentro < grosor_util(wall)).mean())


#: por encima de esta fraccion de piel en membrana hay que rehacer el hueco.
#:
#: El limite separa dos cosas distintas. Un escaneo normal se queda en torno al
#: 1 %: son las esquirlas del borde donde la camara se cierra, hilos de decimas
#: de milimetro que ni se ven ni molestan. Una placa mas fina que dos paredes
#: -el faldon de una armadura, una capa, una hoja- se va al 20 % y mas: eso ya
#: es una sabana entera de espesor cero. Rehacer el hueco cuesta un minuto, asi
#: que el limite se pone donde separa los dos casos y no donde sea mas estricto
MEMBRANA_MAX = 0.03

#: muestras para decidir si hay membranas. Con pocas, la decision cambia de una
#: pasada a otra y el vaciado tarda dos segundos o un minuto segun el sorteo
MUESTRAS_MEMBRANA = 8000


#: maximo de secciones horizontales del vaciado por capas.#: maximo de secciones horizontales del vaciado por capas. Con muchas mas, un
#: modelo de dos metros tardaria demasiado; con menos, el escalon se nota.
CAPAS_MAX = 1400

#: altura de cada banda, en fracciones del espesor de pared
PASO_CAPA = 0.5

#: cuantos vertices como mucho se apilan para formar el hueco. Por encima, el
#: motor booleano se atasca; por debajo, el contorno pierde detalle que no se ve
PUNTOS_MAX = 500_000


def _puntos(geom) -> int:
    """Cuantos vertices tiene un contorno, contando sus agujeros."""
    if geom is None or geom.is_empty:
        return 0
    partes = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    total = 0
    for parte in partes:
        anillo = getattr(parte, "exterior", None)
        if anillo is None:
            continue
        total += len(anillo.coords)
        total += sum(len(r.coords) for r in parte.interiors)
    return total


def _aligerar(geom, tolerancia: float):
    """Simplifica un contorno sin dejar que se invalide."""
    if geom is None or geom.is_empty:
        return None
    try:
        simple = geom.simplify(float(tolerancia))
        if not simple.is_valid:
            simple = simple.buffer(0)
    except Exception:
        return geom
    return None if simple.is_empty or simple.area <= EPS else simple


def _prismas_interiores(mesh: trimesh.Trimesh,
                        wall: float,
                        avisar=None,
                        paso_z: float = 0.0) -> Optional[List[List]]:
    """El hueco calculado por secciones, en dos montones de rebanadas.

    Esta es la herramienta que no se rompe nunca.

    En vez de empujar la superficie hacia dentro -que en un escaneo con picos
    acaba cruzandose consigo misma y dejando la pieza hecha migajas- se corta el
    modelo en secciones horizontales, se encoge cada seccion `wall` milimetros
    con el mismo encogido exacto que ya se usa en el modo laminas, y se apila lo
    que queda. Encoger un contorno plano es una operacion 2D: no puede cruzarse,
    no puede dar la vuelta y, donde la pieza es mas fina que la pared, el
    contorno encogido simplemente desaparece y ahi el modelo queda macizo, que
    es justo lo correcto.

    Para que la piel tambien tenga espesor **por arriba y por abajo** no basta
    con encoger cada seccion por su cuenta: una seccion se encoge en X e Y, pero
    en Z hay que mirar las vecinas. Por eso cada rebanada del interior se
    interseca ademas con las secciones que quedan a menos de `wall` de
    distancia, encogidas lo que marca la esfera de radio `wall`. Asi la bola de
    la pared cabe entera dentro del modelo en cualquier direccion.

    A cambio, la cara interior queda escalonada en vez de lisa. No se ve y no se
    imprime, pero por eso este camino no es el principal.

    Devuelve dos listas de rebanadas -las de altura par y las de altura impar-,
    cada una como (vertices, caras). Van separadas porque dentro de un mismo
    monton las rebanadas no se tocan entre si: eso permite juntarlas sin pasar
    por el motor booleano.
    """
    def paso(texto):
        if avisar is not None:
            avisar(texto)

    wall = float(wall)
    lo, hi = float(mesh.bounds[0][2]), float(mesh.bounds[1][2])
    util = (hi - wall) - (lo + wall)
    if util <= wall:
        return None                      # no hay sitio para nada de hueco

    # la altura de banda decide cuanto puede esconderse la superficie *entre*
    # dos secciones: con bandas del grosor de la pared, un pliegue horizontal
    # que caiga justo en medio no lo ve nadie. A media pared el hueco se parte
    # por la mitad y el espesor medido sube; mas fino que eso ya no compensa lo
    # que tarda.
    # `paso_z` separa la altura de banda del radio de encogido: cuando esto se
    # usa solo para quitar las membranas, el radio es pequeno pero las bandas
    # deben seguir siendo del tamano de la pared, o salen miles y no acaba.
    grueso = float(paso_z) if paso_z and paso_z > 0 else wall
    bandas = max(1, min(CAPAS_MAX, int(round(util / (grueso * PASO_CAPA)))))
    altura = util / bandas
    planos = (lo + wall) + np.arange(bandas + 1) * altura

    paso("Cortando secciones")
    secciones = _secciones(mesh, planos)
    if secciones is None:
        return None

    paso("Encogiendo cada seccion")
    # margen de simplificacion: los contornos de un escaneo traen miles de
    # puntos y apilarlos tal cual daria una malla interior de veinte millones de
    # triangulos que ningun motor booleano digiere. Se encoge `tol` mm de mas y
    # luego se simplifica otro tanto: la pared queda ese pelo mas gruesa, que es
    # el lado seguro, y la malla interior baja a una decima parte.
    tol = max(0.2, wall * 0.15)

    # La distancia de una banda a cada seccion vecina siempre es un multiplo de
    # la altura de banda, asi que los radios posibles son un punado. Se calculan
    # todos de una vez y en paralelo: encoger contornos es lo que mas tarda de
    # todo esto y shapely suelta el interprete mientras lo hace.
    alcance = int(np.ceil(wall / altura))
    radios = [float(np.sqrt(max(wall * wall - (i * altura) ** 2, 0.0)))
              for i in range(alcance + 1)]

    def encoger(indice: int):
        base = secciones[indice]
        if base is None or base.is_empty:
            return [None] * len(radios)
        salida = []
        for radio in radios:
            try:
                trozo = base.buffer(-(radio + tol))
                if not trozo.is_valid:
                    trozo = trozo.buffer(0)
            except Exception:
                trozo = None
            salida.append(None if trozo is None or trozo.is_empty else trozo)
        return salida

    encogidas = en_paralelo(encoger, range(len(planos)))

    def perfil_de(k: int):
        z0, z1 = float(planos[k]), float(planos[k + 1])
        perfil = None
        for j in range(max(0, k - alcance), min(len(planos), k + 2 + alcance)):
            distancia = max(planos[j] - z1, z0 - planos[j], 0.0)
            if distancia > wall:
                continue             # esa seccion cae fuera de la bola
            nivel = int(round(distancia / altura))
            if nivel >= len(radios):
                continue
            trozo = encogidas[j][nivel]
            if trozo is None:
                return None
            perfil = trozo if perfil is None else perfil.intersection(trozo)
            if perfil is None or perfil.is_empty:
                return None
        if perfil is None or perfil.is_empty:
            return None
        perfil = perfil.simplify(tol)
        if not perfil.is_valid:
            perfil = perfil.buffer(0)
        return None if perfil.is_empty or perfil.area <= EPS else perfil

    paso("Apilando el interior")
    perfiles = en_paralelo(perfil_de, range(bandas))

    # Presupuesto de puntos. Los contornos de un escaneo de dos metros traen
    # miles de vertices cada uno y, apilados, dan una malla que el motor
    # booleano tarda mas de un cuarto de hora en digerir. Si se pasan, se
    # simplifican otra vez mas fuerte: eso encoge un pelo mas el hueco, o sea
    # deja la pared un pelo mas gruesa, que es el lado bueno del error.
    puntos = sum(_puntos(p) for p in perfiles if p is not None)
    if puntos > PUNTOS_MAX:
        grueso = min(float(wall) * 0.8, tol * puntos / PUNTOS_MAX)
        if grueso > tol:
            perfiles = en_paralelo(lambda p: _aligerar(p, grueso), perfiles)
    # las secciones y sus versiones encogidas ya no hacen falta, y en un modelo
    # de dos metros son cientos de megas: se sueltan antes de construir la malla
    encogidas = None
    secciones = None

    def bloque_de(k: int):
        """Rebanada del interior, devuelta como puros vertices y caras.

        Se sueltan las mallas y solo se guardan los dos arrays. Un modelo de dos
        metros da mas de mil rebanadas, y mil objetos Trimesh vivos a la vez -con
        sus normales, sus arboles y sus cachés- son varios gigas de memoria para
        nada: lo unico que hace falta de cada uno son sus triangulos.
        """
        perfil = perfiles[k]
        if perfil is None:
            return None
        bloque = extrude_polygons(perfil, float(planos[k + 1]) - float(planos[k]))
        if bloque is None:
            return None
        if not bloque.is_volume:
            bloque.merge_vertices()
            bloque.fix_normals()
            if not bloque.is_volume:
                return None       # un contorno imposible de triangular: se salta
        vertices = np.array(bloque.vertices, dtype=np.float64)
        vertices[:, 2] += float(planos[k])
        return vertices, np.array(bloque.faces, dtype=np.int64)

    prismas = [[], []]           # pares e impares: nunca se tocan entre si
    for k, trozo in enumerate(en_paralelo(bloque_de, range(bandas))):
        if trozo is not None:
            prismas[k % 2].append(trozo)
    perfiles = None

    if not prismas[0] and not prismas[1]:
        return None
    return prismas


def _piel_por_capas(mesh: trimesh.Trimesh,
                    wall: float,
                    avisar=None) -> Optional[trimesh.Trimesh]:
    """La piel entera calculada solo por secciones, sin desplazar nada.

    Es el camino de reserva: se usa cuando el desplazamiento de la superficie no
    llega a entregar una piel. La cara interior queda escalonada, pero el
    espesor esta garantizado y la malla sale cerrada.
    """
    def paso(texto):
        if avisar is not None:
            avisar(texto)

    prismas = _prismas_interiores(mesh, wall, avisar)
    if prismas is None:
        return None

    paso("Restando el interior")
    cascara = mesh
    for grupo in prismas:
        if not grupo:
            continue
        # dentro de un mismo grupo las rebanadas estan separadas por la altura
        # de una banda entera, asi que no se tocan y se pueden restar de golpe
        nucleo = _juntar_trozos(grupo)
        grupo.clear()
        if nucleo is None:
            continue
        resultado = boolean_op("difference", cascara, nucleo)
        nucleo = None
        if resultado is None:
            return None
        cascara = resultado
    if cascara is mesh:
        return None
    return _cascara_limpia(cascara)


def _juntar_trozos(trozos) -> Optional[trimesh.Trimesh]:
    """Una sola malla a partir de muchos (vertices, caras) sueltos."""
    if not trozos:
        return None
    vertices, caras, desfase = [], [], 0
    for v, f in trozos:
        vertices.append(v)
        caras.append(f + desfase)
        desfase += len(v)
    return trimesh.Trimesh(vertices=np.concatenate(vertices),
                           faces=np.concatenate(caras), process=False)


def _secciones(mesh: trimesh.Trimesh, planos) -> Optional[List]:
    """Contorno relleno del modelo en cada altura, de una sola pasada."""
    from shapely.ops import unary_union
    from trimesh.intersections import mesh_multiplane

    try:
        lineas, _tos, _caras = mesh_multiplane(
            mesh, np.zeros(3), np.array([0.0, 0.0, 1.0]), np.asarray(planos, dtype=float))
    except Exception:
        return None

    def contorno(segmentos):
        if len(segmentos) == 0:
            return None
        try:
            camino = trimesh.load_path(segmentos)
            poligonos = [p for p in camino.polygons_full
                         if p is not None and not p.is_empty]
        except Exception:
            return None
        if not poligonos:
            return None
        try:
            unido = unary_union(poligonos)
        except Exception:
            return None
        return None if unido.is_empty else unido

    return en_paralelo(contorno, lineas)


def _cascara_limpia(cruda: Optional[trimesh.Trimesh]) -> Optional[trimesh.Trimesh]:
    """Deja la piel como la vera el laminador, sin romperla si ya estaba bien."""
    if cruda is None:
        return None
    if cruda.is_watertight:
        return cruda
    limpia = _soldar(cruda)
    return limpia if limpia.is_watertight else cruda


def _es_piel(cascara: trimesh.Trimesh,
             original: trimesh.Trimesh,
             wall: float = 0.0) -> bool:
    """Comprueba que lo que salio del vaciado es una piel y no migajas.

    La comprobacion util no es el volumen sino la **superficie**: una piel bien
    hecha conserva entera la cara de fuera y ademas anade la de dentro, asi que
    su area casi dobla la del modelo. Si el desplazamiento se cruzo consigo
    mismo y la resta se comio el modelo, el area se desploma; eso es lo que
    hay que rechazar, en vez de entregar un monton de esquirlas y decir que se
    ahorro el 100 % del material.

    El volumen tambien se mira, pero comparado con lo que **deberia** medir esa
    piel (superficie x espesor), no con un porcentaje fijo del modelo. Un
    porcentaje fijo no vale: la piel de una figura de dos metros con 3 mm de
    pared es menos del 0,5 % del bloque macizo, y con el limite de antes se
    rechazaba una piel perfectamente buena.
    """
    if cascara is None or cascara.is_empty or not len(cascara.faces):
        return False
    if original.area <= 0 or original.volume <= 0:
        return False
    if cascara.area < original.area * 1.05:
        return False
    volumen = float(cascara.volume)
    if not (0.0 < volumen < float(original.volume) * 0.999):
        return False
    if wall and wall > 0:
        # una piel de `wall` mm mide, como poco, media superficie por espesor
        minimo = min(float(original.area) * float(wall) * 0.5,
                     float(original.volume) * 0.5)
        return volumen >= minimo
    return volumen > float(original.volume) * 0.005


def _soldar(malla: trimesh.Trimesh) -> trimesh.Trimesh:
    """Deja la malla como la vera el laminador: vertices unidos y sin basura.

    Es importante comprobar la estanqueidad DESPUES de soldar: en memoria dos
    superficies que se tocan parecen cerradas cada una por su lado, pero al
    guardarlas en STL se funden y aparece la arista compartida por cuatro caras
    que hace que el laminador se queje.
    """
    limpia = malla.copy()
    limpia.merge_vertices()
    limpia.update_faces(limpia.nondegenerate_faces())
    limpia.update_faces(limpia.unique_faces())
    limpia.remove_unreferenced_vertices()
    return limpia


def hollow_region(region, wall: float, tab_size=None, minimo: float = 5.0):
    """Vacia un contorno isla por isla y le pone una plaquita a cada una.

    Cada trozo suelto de la seccion (las dos piernas de una figura, por
    ejemplo) es una pieza distinta, asi que cada uno necesita su anillo, su
    hueco y su propia marca.
    """
    from shapely.geometry import Polygon as _Polygon
    from shapely.ops import unary_union

    if region is None or region.is_empty:
        return region
    islas = list(region.geoms) if hasattr(region, "geoms") else [region]
    islas = [p for p in islas if isinstance(p, _Polygon) and p.area > EPS]
    if not islas:
        return None

    partes = []
    for isla in islas:
        anillo = ring_polygons(isla, wall)
        anillo = limpiar(anillo, minimo)
        if anillo is None or anillo.is_empty:
            continue
        hueco = inner_polygons(isla, wall)
        if hueco is not None and tab_size:
            anillo, _tab = add_label_tab(anillo, hueco, tab_size[0], tab_size[1])
        partes.append(anillo)
    if not partes:
        return None
    return unary_union(partes)


#: por encima de esto, la cara interior se calcula sobre una copia aligerada:
#: no se ve, y con millones de caras el desplazamiento se cruza consigo mismo
CARAS_INTERIOR = 120_000

#: a partir de aqui se considera que la malla tiene detalle fino de escaneo;
#: por debajo, lo que parece rugosidad son las aristas propias de la pieza
CARAS_DENSAS = 20_000


def _base_interior(mesh: trimesh.Trimesh, wall: float) -> trimesh.Trimesh:
    """Copia de la malla lista para desplazarla hacia dentro.

    La cara de dentro no se ve nunca, pero es la que decide si la pared sale
    entera o hecha puas. En un escaneo con pelo o con grano fino, desplazar la
    superficie tal cual hace que los vertices de cada rugosidad se crucen entre
    si y la pieza acaba en migajas.

    Por eso aqui se trabaja sobre una copia **aligerada y suavizada**: pierde el
    detalle mas fino que la propia pared, que es justo el que no cabe dentro, y
    deja el interior liso. El exterior no se toca: se exporta con todos sus
    triangulos originales.
    """
    base = mesh.copy()
    if len(mesh.faces) > CARAS_INTERIOR:
        try:
            aligerada = mesh.simplify_quadric_decimation(face_count=CARAS_INTERIOR)
            # aligerar abre la malla con mucha frecuencia, y una cara interior
            # abierta no sirve: el corte booleano la rechaza y el modelo se
            # queda macizo sin que nadie sepa por que
            aligerada = _cerrar(aligerada)
            if aligerada is not None and aligerada.is_watertight:
                base = aligerada
        except Exception:
            pass

    # Suavizado Taubin: quita el grano sin encoger el modelo (a diferencia del
    # laplaciano normal, que lo va desinflando en cada pasada). Solo tiene
    # sentido en mallas densas: en una pieza de pocas caras, lo que parece
    # rugosidad son sus aristas de verdad y suavizarlas seria estropearla.
    rugosidad = _rugosidad(base) if len(base.faces) > CARAS_DENSAS else 0.0
    if rugosidad > wall * 0.15:
        pasadas = int(min(24, max(4, round(rugosidad / max(wall, 0.1) * 12))))
        try:
            trimesh.smoothing.filter_taubin(base, lamb=0.53, nu=-0.53,
                                            iterations=pasadas)
        except Exception:
            pass
    return base


def _cerrar(malla: trimesh.Trimesh) -> Optional[trimesh.Trimesh]:
    """Intenta dejar cerrada una malla recien aligerada."""
    try:
        limpia = malla.copy()
        limpia.merge_vertices()
        limpia.update_faces(limpia.nondegenerate_faces())
        limpia.update_faces(limpia.unique_faces())
        limpia.remove_unreferenced_vertices()
        if not limpia.is_watertight:
            limpia.fill_holes()
            limpia.fix_normals()
        return limpia
    except Exception:
        return None


def _rugosidad(mesh: trimesh.Trimesh) -> float:
    """Cuanto se aparta la superficie de su propia media, en mm.

    Sirve para decidir cuanto suavizar: una superficie lisa no necesita nada y
    un escaneo con pelo necesita bastante.
    """
    try:
        aristas = mesh.edges_unique_length
        if len(aristas) == 0:
            return 0.0
        vecinos = mesh.vertex_neighbors
        v = np.asarray(mesh.vertices, dtype=float)
        muestra = np.linspace(0, len(v) - 1, min(len(v), 4000)).astype(int)
        desvios = []
        for i in muestra:
            vec = vecinos[i]
            if len(vec) < 3:
                continue
            desvios.append(np.linalg.norm(v[i] - v[vec].mean(axis=0)))
        return float(np.mean(desvios)) if desvios else 0.0
    except Exception:
        return 0.0


def _superficie_interior(mesh: trimesh.Trimesh,
                        wall: float,
                        intentos: int = 6) -> Optional[trimesh.Trimesh]:
    """La superficie del modelo desplazada `wall` mm hacia dentro.

    Desplazar todos los vertices lo mismo funciona en las zonas planas, pero en
    un pico o en un pliegue cerrado los vertices se cruzan y aparecen esas
    puas que atraviesan la pared. Aqui se detectan las caras que se dan la
    vuelta al desplazarlas y se reduce el avance **solo** en sus vertices: la
    pared queda algo mas fina en esos puntos, que es justo lo que hace falta.

    El desplazamiento se hace sobre la copia suavizada (`_base_interior`), no
    sobre la malla original: asi el interior queda liso aunque el modelo sea un
    escaneo lleno de grano.

    Al final se recorta con una *guarda* (ver `_recortar_con_guarda`), que es lo
    que impide que la cara de dentro llegue a tocar la de fuera.
    """
    rugosidad = _rugosidad(mesh) if len(mesh.faces) > CARAS_DENSAS else 0.0
    base = _base_interior(mesh, wall)
    # La copia suavizada pasa por la media de la superficie, asi que en los
    # valles la pared se quedaria corta justo esa rugosidad. Se compensa
    # hundiendo un poco mas la cara interior: mejor 1 mm de mas que un agujero.
    avance = float(wall) + min(rugosidad, float(wall))
    interior = _desplazar(base, avance, intentos)
    base = None                  # una copia de millones de caras que ya no sirve
    if interior is None:
        return None
    return _recortar_con_guarda(mesh, interior, wall, intentos)


def _desplazar(mesh: trimesh.Trimesh,
               avance: float,
               intentos: int = 6) -> Optional[trimesh.Trimesh]:
    """Mete la superficie `avance` mm hacia dentro, sin dejar que se de la vuelta."""
    try:
        normales = np.asarray(mesh.vertex_normals, dtype=float)
    except Exception:
        return None
    if len(normales) != len(mesh.vertices):
        return None

    originales = np.asarray(mesh.face_normals, dtype=float)
    paso = np.full(len(mesh.vertices), float(avance))
    interior = mesh.copy()
    for _ in range(intentos):
        interior.vertices = mesh.vertices - normales * paso[:, None]
        nuevas = np.asarray(interior.face_normals, dtype=float)
        if len(nuevas) != len(originales):
            break
        vueltas = np.einsum("ij,ij->i", nuevas, originales) < 0.0
        if not vueltas.any():
            break
        paso[np.unique(mesh.faces[vueltas])] *= 0.5

    interior.update_faces(interior.nondegenerate_faces())
    interior.remove_unreferenced_vertices()
    if not interior.is_volume:
        try:
            interior.fill_holes()
            interior.fix_normals()
        except Exception:
            pass
    return interior


def _recortar_con_guarda(mesh: trimesh.Trimesh,
                         interior: trimesh.Trimesh,
                         wall: float,
                         intentos: int = 6) -> trimesh.Trimesh:
    """Deja el interior siempre por debajo de la superficie, sin llegar a tocarla.

    Este es el primer remedio contra las **membranas de espesor cero**. Donde el
    modelo es mas fino que dos paredes, la superficie desplazada sale por el
    otro lado y la resta deja dos caras pegadas, una encima de otra, sin nada de
    material entre ellas. Esa pieza ya no es un solido: el laminador la rechaza,
    el volumen no se puede medir y en la vista previa se ve rota.

    La guarda es la misma superficie metida hacia dentro una pizca -decimas de
    milimetro, un desplazamiento tan corto que no puede cruzarse consigo mismo-.
    Se queda corta a proposito: su unico trabajo es que no haya caras pegadas, y
    cuanto menos muerda, mas superficie interior conserva el suavizado. Del
    Del espesor de verdad no se encarga: eso se mide despues (`medir_pared`) y
    se informa.
    """
    guarda = _desplazar(mesh, max(0.2, float(wall) * 0.1), intentos)
    if guarda is None or not len(guarda.faces):
        return interior
    recortado = boolean_op("intersection", interior, guarda)
    guarda = None
    if recortado is None or not len(recortado.faces):
        return interior
    return recortado


def savings(original: float, hueco: float) -> str:
    """Texto con el material que se ahorra al vaciar.

    Nunca dice "100 %": vaciar deja piel, y una piel pesa. Si el redondeo se
    acerca tanto es que el numero esta mal medido, y anunciar un ahorro total
    es justo la clase de mentira que hace desconfiar del resto del informe.
    """
    if original <= 0:
        return ""
    ahorro = max(0.0, 1.0 - hueco / original)
    texto = (f"mas del 99 % menos" if ahorro >= 0.995
             else f"{ahorro * 100:.0f} % menos")
    return f"{texto} de material ({hueco / 1000:.0f} cm3 en vez de {original / 1000:.0f})"


def add_label_tab(ring, hole, width: float, height: float,
                  bridge: float = 3.0):
    """Anade al anillo una lengueta interior para poder grabar el nombre.

    En una lamina hueca la pared puede tener 3 mm: ahi no cabe ningun texto
    legible. La solucion de siempre en los montajes por capas es una pequena
    plaquita hacia dentro con el numero de la pieza, que ademas refuerza el
    anillo y queda escondida cuando la figura esta montada.

    Devuelve (contorno con lengueta, rectangulo de la lengueta) o
    (contorno original, None) si no hay hueco donde ponerla.
    """
    from shapely.affinity import rotate as _rotate
    from shapely.geometry import LineString, Polygon as _Polygon, box as _box
    from shapely.ops import polylabel, unary_union

    if ring is None or hole is None or ring.is_empty or hole.is_empty:
        return ring, None
    ancho = float(width) + 2.0
    alto = float(height) + 2.0

    partes = list(hole.geoms) if hasattr(hole, "geoms") else [hole]
    partes = [p for p in partes if isinstance(p, _Polygon) and p.area > EPS]
    if not partes:
        return ring, None
    hueco = max(partes, key=lambda p: p.area)

    try:
        centro = polylabel(hueco, tolerance=max(hueco.length / 300.0, 0.05))
    except Exception:
        centro = hueco.representative_point()

    # la lengueta se orienta con su lado largo en la direccion mas holgada
    mejor, mejor_area = None, 0.0
    for paso in range(6):
        grados = 30.0 * paso
        caja = _box(centro.x - ancho / 2.0, centro.y - alto / 2.0,
                    centro.x + ancho / 2.0, centro.y + alto / 2.0)
        caja = _rotate(caja, grados, origin=(centro.x, centro.y))
        dentro = caja.intersection(hueco).area
        if dentro > mejor_area:
            mejor_area, mejor = dentro, caja
    if mejor is None or mejor_area < ancho * alto * 0.85:
        return ring, None      # no hay sitio libre para la plaquita

    # puente hasta la pared mas cercana para que la lengueta no quede suelta
    try:
        objetivo = unary_union(ring).boundary
        cercano = objetivo.interpolate(objetivo.project(centro))
        # el puente se alarga un poco mas alla de la pared para que la union
        # solape de verdad y no queden aristas tangentes que rompan el CSG
        dx, dy = cercano.x - centro.x, cercano.y - centro.y
        largo = (dx * dx + dy * dy) ** 0.5 or 1.0
        extra = 1.0 + 2.0 / largo
        final = (centro.x + dx * extra, centro.y + dy * extra)
        puente = LineString([(centro.x, centro.y), final]).buffer(
            max(float(bridge), 1.0) / 2.0)
    except Exception:
        puente = None

    piezas = [ring, mejor] + ([puente] if puente is not None else [])
    combinado = unary_union(piezas).buffer(0)
    if combinado.is_empty:
        return ring, None
    # quitar vertices casi repetidos: el CSG posterior lo agradece
    limpio = combinado.simplify(0.01, preserve_topology=True)
    if not limpio.is_empty and limpio.is_valid:
        combinado = limpio
    return combinado, mejor

