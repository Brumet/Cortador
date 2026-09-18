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

from .geometry import EPS, boolean_op, extrude_polygons, merge_polygons

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
                wall: float) -> Tuple[trimesh.Trimesh, Optional[str]]:
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

    # se prueba con el espesor pedido y, si la pieza no admite tanto, con algo
    # menos: mas vale una pared un poco mas fina que una pieza rota
    # se prueba con el espesor pedido y, si la pieza no lo admite, con algo menos.
    # Se prefiere el resultado que ademas queda cerrado al soldar los vertices,
    # que es como lo vera el laminador, pero no se descarta uno valido por eso.
    reserva = None
    for factor in (1.0, 0.75, 0.5):
        interior = _superficie_interior(mesh, wall * factor)
        if interior is None:
            return mesh, "No se han podido calcular las normales para vaciar el modelo."
        cascara = boolean_op("difference", mesh, interior)
        if cascara is None:
            continue
        cascara = _soldar(cascara)
        if not _es_piel(cascara, mesh):
            continue
        if cascara.is_watertight:
            return cascara, None
        if reserva is None:
            reserva = cascara
    if reserva is not None:
        return reserva, None
    return mesh, ("Este trozo no admite el vaciado (recovecos muy cerrados o "
                  "paredes mas finas que el espesor): se deja macizo.")


def _es_piel(cascara: trimesh.Trimesh, original: trimesh.Trimesh) -> bool:
    """Comprueba que lo que salio del vaciado es una piel y no migajas.

    La comprobacion util no es el volumen sino la **superficie**: una piel bien
    hecha conserva entera la cara de fuera y ademas anade la de dentro, asi que
    su area casi dobla la del modelo. Si el desplazamiento se cruzo consigo
    mismo y la resta se comio el modelo, el area se desploma; eso es lo que
    hay que rechazar, en vez de entregar un monton de esquirlas y decir que se
    ahorro el 100 % del material.
    """
    if cascara is None or cascara.is_empty or not len(cascara.faces):
        return False
    if original.area <= 0 or original.volume <= 0:
        return False
    if cascara.area < original.area * 1.05:
        return False
    proporcion = float(cascara.volume) / float(original.volume)
    return 0.005 < proporcion < 0.995


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
    """
    rugosidad = _rugosidad(mesh) if len(mesh.faces) > CARAS_DENSAS else 0.0
    mesh = _base_interior(mesh, wall)
    # La copia suavizada pasa por la media de la superficie, asi que en los
    # valles la pared se quedaria corta justo esa rugosidad. Se compensa
    # hundiendo un poco mas la cara interior: mejor 1 mm de mas que un agujero.
    wall = float(wall) + min(rugosidad, float(wall))
    try:
        normales = np.asarray(mesh.vertex_normals, dtype=float)
    except Exception:
        return None
    if len(normales) != len(mesh.vertices):
        return None

    originales = np.asarray(mesh.face_normals, dtype=float)
    avance = np.full(len(mesh.vertices), float(wall))
    interior = mesh.copy()
    for _ in range(intentos):
        interior.vertices = mesh.vertices - normales * avance[:, None]
        nuevas = np.asarray(interior.face_normals, dtype=float)
        if len(nuevas) != len(originales):
            break
        vueltas = np.einsum("ij,ij->i", nuevas, originales) < 0.0
        if not vueltas.any():
            break
        avance[np.unique(mesh.faces[vueltas])] *= 0.5

    interior.update_faces(interior.nondegenerate_faces())
    interior.remove_unreferenced_vertices()
    if not interior.is_volume:
        try:
            interior.fill_holes()
            interior.fix_normals()
        except Exception:
            pass
    return interior


def savings(original: float, hueco: float) -> str:
    """Texto con el material que se ahorra al vaciar."""
    if original <= 0:
        return ""
    ahorro = max(0.0, 1.0 - hueco / original)
    return f"{ahorro * 100:.0f} % menos de material ({hueco / 1000:.0f} cm3 en vez de {original / 1000:.0f})"


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
