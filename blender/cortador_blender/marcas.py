"""Grabar en cada pieza como se llama y con quien va pegada.

Una pieza suelta encima de la mesa no dice nada. Cien piezas sueltas encima de
la mesa son un problema. Por eso cada una lleva grabado su nombre en el centro
de la cara interior y, mas pequeno, el nombre de la pieza que va pegada por
arriba, por abajo, por la izquierda y por la derecha:

              P1/L3
        P2/L2  P2/L3  P2/L4
              P3/L3

Asi, sin plano ni lista, quien la coge ya sabe donde va y por donde sigue.

Va en la cara de dentro, que es la que no se ve cuando la figura esta montada,
nunca en la cara de corte: la de corte es la que se pega, y ademas en una
figura hueca es una tira de tres milimetros donde no cabe ni una letra.

Cada etiqueta se coloca por separado. Si se hiciera una sola plancha de texto
para toda la pieza, en una pieza curvada las letras de los extremos se
quedarian en el aire: una lamina de 268 mm de cuerda sobre un radio de 600 se
separa 15 mm de su propia tangente, y el grabado tiene medio milimetro. Cada
etiqueta busca su punto en la superficie con un rayo y se apoya en la
inclinacion que encuentra ahi.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import cortar as motor

#: hondo del grabado, en milimetros de mundo
HONDO = 0.6
#: cuanto sobresale la talla por fuera de la piel antes de restar
SOBRA = 0.4
#: la letra mas pequena que se graba; por debajo no se lee ni se imprime
ALTO_MIN = 3.5
#: y la mas grande, que tampoco hace falta un cartel
ALTO_MAX = 28.0
#: por encima de estas caras no se graba: el booleano exacto se dispara
CARAS_MAX = 120_000


class Marco:
    """El sistema de referencia de la cara interior de una pieza."""

    def __init__(self, punto: Vector, normal: Vector, arriba: Vector,
                 derecha: Vector, alto: float, ancho: float):
        self.punto = punto
        self.normal = normal
        self.arriba = arriba
        self.derecha = derecha
        self.alto = alto
        self.ancho = ancho


def _caras(objeto: bpy.types.Object):
    """Centros, normales y areas de todas las caras, de golpe."""
    malla = objeto.data
    cuantas = len(malla.polygons)
    if not cuantas:
        return None
    centros = np.empty(cuantas * 3)
    normales = np.empty(cuantas * 3)
    areas = np.empty(cuantas)
    malla.polygons.foreach_get("center", centros)
    malla.polygons.foreach_get("normal", normales)
    malla.polygons.foreach_get("area", areas)
    return (centros.reshape(cuantas, 3), normales.reshape(cuantas, 3), areas)


def marco_interior(objeto: bpy.types.Object, centro_figura: Vector) -> Optional[Marco]:
    """Encuentra la cara de dentro de una pieza y monta ejes sobre ella.

    La de dentro es la que mira hacia el centro de la figura. En una pieza de
    piel las dos caras grandes son casi iguales y por la normal sola no se
    distinguen, pero una mira hacia dentro y la otra hacia afuera. Se mira
    contra el centro y no contra el eje vertical porque en el casquete de
    arriba y en el de abajo la cara de dentro no mira al eje: mira al suelo o
    al techo.
    """
    datos = _caras(objeto)
    if datos is None:
        return None
    centros, normales, areas = datos
    local = objeto.matrix_world.inverted() @ centro_figura

    hacia = np.array(local) - centros
    largo = np.linalg.norm(hacia, axis=1)
    largo[largo < 1e-9] = 1.0
    mira = (normales * hacia).sum(axis=1) / largo

    dentro = mira > 0.25
    if areas[dentro].sum() < 0.05 * areas.sum():
        dentro = mira > 0.0
    if not dentro.any():
        return None

    peso = areas[dentro]
    total = peso.sum() or 1.0
    centro = Vector((centros[dentro] * peso[:, None]).sum(axis=0) / total)
    normal = Vector((normales[dentro] * peso[:, None]).sum(axis=0) / total)
    if normal.length < 1e-6:
        return None
    normal.normalize()

    # El texto se lee de pie: hacia arriba es el arriba del mundo. En una cara
    # horizontal -la tapa de una peana- no hay arriba que valga, asi que se
    # orienta como un plano: el norte hacia arriba y el este a la derecha.
    vertical = Vector((0.0, 0.0, 1.0))
    if abs(normal.dot(vertical)) > 0.9:
        vertical = Vector((0.0, 1.0, 0.0))
    arriba = (vertical - normal * vertical.dot(normal)).normalized()
    derecha = arriba.cross(normal).normalized()

    # El tamano se mide sobre los vertices, no sobre los centros de las caras.
    # Una pieza basta puede tener la cara de dentro hecha de un solo poligono,
    # y entonces por centros mide cero y no se le graba nada.
    cuantos = len(objeto.data.vertices)
    plano = np.empty(cuantos * 3)
    objeto.data.vertices.foreach_get("co", plano)
    puntos = plano.reshape(cuantos, 3) - np.array(centro)
    ancho = float(np.ptp(puntos @ np.array(derecha)))
    alto = float(np.ptp(puntos @ np.array(arriba)))
    return Marco(centro, normal, arriba, derecha, alto, ancho)


def _malla_de_texto(texto: str, alto: float, hondo: float) -> Optional[bmesh.types.BMesh]:
    """Un bloque solido con la forma del texto, centrado en el origen.

    La curva de texto de Blender, pasada a malla, viene con los vertices del
    contorno repetidos -mil doscientos vertices para cinco letras- y sin cerrar.
    Soldandolos queda un solido limpio y estanco, que es lo que necesita el
    booleano para restar sin dejar basura.
    """
    curva = bpy.data.curves.new("cortador_texto", type="FONT")
    curva.body = texto
    curva.size = alto
    curva.extrude = hondo / 2.0
    curva.align_x = "CENTER"
    curva.align_y = "CENTER"
    curva.resolution_u = 6
    letrero = bpy.data.objects.new("cortador_texto", curva)
    bpy.context.scene.collection.objects.link(letrero)
    try:
        grafo = bpy.context.evaluated_depsgraph_get()
        malla = letrero.evaluated_get(grafo).to_mesh()
        if not malla.polygons:
            return None
        bm = bmesh.new()
        bm.from_mesh(malla)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
        letrero.evaluated_get(grafo).to_mesh_clear()
    finally:
        bpy.data.objects.remove(letrero, do_unlink=True)
        bpy.data.curves.remove(curva)
    return bm


def _encajar(bm: bmesh.types.BMesh, ancho_max: float, alto_max: float) -> bool:
    """Encoge el texto si se sale del sitio. False si ya no se puede leer."""
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    ancho = max(xs) - min(xs)
    alto = max(ys) - min(ys)
    if ancho <= 1e-9 or alto <= 1e-9:
        return False
    escala = min(ancho_max / ancho, alto_max / alto, 1.0)
    if escala < 1.0:
        if alto * escala < ALTO_MIN:
            return False
        bmesh.ops.scale(bm, vec=Vector((escala, escala, 1.0)),
                        verts=bm.verts[:])
    return True


def _posar(bm: bmesh.types.BMesh, sitio: Vector, normal: Vector,
           arriba: Vector, derecha: Vector) -> None:
    """Lleva el texto plano a su sitio sobre la superficie."""
    giro = Matrix((
        (derecha.x, arriba.x, normal.x, sitio.x),
        (derecha.y, arriba.y, normal.y, sitio.y),
        (derecha.z, arriba.z, normal.z, sitio.z),
        (0.0, 0.0, 0.0, 1.0),
    ))
    bmesh.ops.transform(bm, matrix=giro, verts=bm.verts[:])


def _apoyo(objeto: bpy.types.Object, marco: Marco,
           dx: float, dy: float) -> Optional[Tuple[Vector, Vector]]:
    """Donde cae en la superficie un punto del marco, y con que inclinacion.

    Se tira un rayo desde dentro del hueco hacia la pieza. Lo que devuelve es
    el sitio real de la piel y su normal ahi mismo, que es lo que hace que el
    grabado tenga el mismo hondo en una pieza curvada que en una plana.
    """
    fuera = max(marco.alto, marco.ancho, 10.0) * 2.0
    origen = (marco.punto + marco.derecha * dx + marco.arriba * dy
              + marco.normal * fuera)
    hubo, sitio, normal, _ = objeto.ray_cast(origen, -marco.normal, distance=fuera * 3)
    if not hubo or normal.dot(marco.normal) < 0.4:
        return None
    return (sitio, normal.normalized())


def _restar(objeto: bpy.types.Object, talla: bmesh.types.BMesh) -> bool:
    """Resta la talla de la pieza y deshace el cambio si sale mal.

    El booleano es la unica pieza de este complemento que no controlamos por
    dentro, asi que no se le da por bueno: se guarda la malla, se resta, y si
    la pieza deja de estar cerrada o el volumen cambia mas de lo que ocupan
    unas letras, se devuelve la malla de antes y se sigue sin marca. Mejor una
    pieza sin marcar que una pieza rota.

    Lo que si se acepta es que el booleano deje unas pocas aristas sueltas por
    el camino: eso lo remata el mismo cierre de huecos que usa el corte, y la
    pieza queda igual de estanca.
    """
    malla = bpy.data.meshes.new("cortador_talla")
    talla.to_mesh(malla)
    tallado = bpy.data.objects.new("cortador_talla", malla)
    bpy.context.scene.collection.objects.link(tallado)

    antes = objeto.data
    copia = antes.copy()
    bm = bmesh.new()
    bm.from_mesh(antes)
    volumen = abs(bm.calc_volume(signed=True))
    bm.free()

    modificador = objeto.modifiers.new("cortador_marca", "BOOLEAN")
    modificador.operation = "DIFFERENCE"
    modificador.solver = "EXACT"
    modificador.object = tallado
    bien = False
    try:
        grafo = bpy.context.evaluated_depsgraph_get()
        nueva = bpy.data.meshes.new_from_object(objeto.evaluated_get(grafo))
        prueba = bmesh.new()
        prueba.from_mesh(nueva)
        abiertas = sum(1 for e in prueba.edges if e.is_boundary)
        cambio = abs(abs(prueba.calc_volume(signed=True)) - volumen)
        prueba.free()
        razonable = (len(nueva.polygons) > 0
                     and cambio < max(volumen * 0.03, 1.0)
                     and abiertas < 200)
        if razonable:
            objeto.data = nueva
            if abiertas:
                motor.cerrar_huecos(objeto)
                revision = bmesh.new()
                revision.from_mesh(objeto.data)
                bien = not any(e.is_boundary for e in revision.edges)
                revision.free()
            else:
                bien = True
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
            if sobra.name.startswith("cortador_marca"):
                objeto.modifiers.remove(sobra)
        bpy.data.objects.remove(tallado, do_unlink=True)
        bpy.data.meshes.remove(malla)
    return bool(bien)


def marcar(objeto: bpy.types.Object, centro_figura: Vector, propio: str,
           vecinos: Dict[str, str], hondo: float = HONDO) -> bool:
    """Graba en la cara interior el nombre de la pieza y el de sus vecinas.

    `vecinos` lleva las claves 'arriba', 'abajo', 'izquierda' y 'derecha' con
    el nombre de la pieza que va pegada por cada lado; las que falten
    sencillamente no se graban.
    """
    # En una pieza muy densa el booleano exacto de Blender se dispara: puede
    # tardar mas en grabar cinco letras que el corte entero de la figura, y
    # mientras tanto no hay manera de pararlo. Por encima de este tamano se
    # deja sin marcar y se avisa, que es mucho mejor que parecer colgado.
    if len(objeto.data.polygons) > CARAS_MAX:
        return False
    marco = marco_interior(objeto, centro_figura)
    if marco is None or marco.alto <= 0 or marco.ancho <= 0:
        return False
    # Si no cabe una letra legible, no se intenta siquiera. Parece una
    # tonteria y no lo es: en un escaneo con basura suelta salen cientos de
    # piezas de diez caras, y probar en cada una -cinco rayos, cinco mallas de
    # texto y dos intentos- son minutos tirados en algo que no puede salir.
    if min(marco.alto, marco.ancho) < ALTO_MIN * 6.0:
        return False
    for encogido in (1.0, 0.7):
        if _un_intento(objeto, marco, propio, vecinos, hondo, encogido):
            return True
    return False


def _un_intento(objeto, marco: Marco, propio: str, vecinos: Dict[str, str],
                hondo: float, encogido: float) -> bool:
    """Un intento de grabado. Si el booleano se atraganta se prueba mas chico.

    El solucionador exacto de Blender falla de vez en cuando con una malla
    basta y un texto grande -devuelve la pieza vacia-, y en esos casos con unas
    letras mas pequenas suele pasar sin problema.
    """
    # El reparto es el de una hoja: el nombre propio en el centro, y el de cada
    # vecina pegada a su borde. Los topes de ancho y alto estan puestos para
    # que el nombre del centro no llegue a tocar los de los lados; si el texto
    # no cabe dentro de su tope, se encoge, y si encogido ya no se leeria, esa
    # etiqueta se queda fuera.
    grande = min(marco.alto, marco.ancho) / 6.0 * encogido
    grande = max(min(grande, ALTO_MAX), ALTO_MIN)
    chica = grande * 0.6
    borde = 0.40
    reparto = [
        (propio, grande, 0.0, 0.0, marco.ancho * 0.55, marco.alto * 0.22),
        (vecinos.get("arriba"), chica, 0.0, marco.alto * borde,
         marco.ancho * 0.40, marco.alto * 0.13),
        (vecinos.get("abajo"), chica, 0.0, -marco.alto * borde,
         marco.ancho * 0.40, marco.alto * 0.13),
        (vecinos.get("izquierda"), chica, -marco.ancho * borde, 0.0,
         marco.ancho * 0.30, marco.alto * 0.13),
        (vecinos.get("derecha"), chica, marco.ancho * borde, 0.0,
         marco.ancho * 0.30, marco.alto * 0.13),
    ]

    talla = bmesh.new()
    puestas = 0
    for texto, alto, dx, dy, ancho_max, alto_max in reparto:
        if not texto:
            continue
        apoyo = _apoyo(objeto, marco, dx, dy)
        if apoyo is None:
            continue
        sitio, normal = apoyo
        letras = _malla_de_texto(texto, alto, hondo + SOBRA)
        if letras is None:
            continue
        if not _encajar(letras, ancho_max, alto_max):
            letras.free()
            continue
        arriba = marco.arriba - normal * marco.arriba.dot(normal)
        if arriba.length < 1e-6:
            letras.free()
            continue
        arriba.normalize()
        derecha = arriba.cross(normal).normalized()
        _posar(letras, sitio + normal * (SOBRA - (hondo + SOBRA) / 2.0),
               normal, arriba, derecha)
        malla = bpy.data.meshes.new("cortador_letras")
        letras.to_mesh(malla)
        talla.from_mesh(malla)
        bpy.data.meshes.remove(malla)
        letras.free()
        puestas += 1

    hecho = False
    if puestas:
        hecho = _restar(objeto, talla)
    talla.free()
    return hecho


def vecindario(piezas: Sequence, marcos: Dict[str, Marco],
               holgura: float = 0.5) -> Dict[str, Dict[str, str]]:
    """Quien esta pegado a quien, y por que lado.

    Dos piezas son vecinas si sus cajas se tocan: como todas salen de cortar la
    misma figura, solo se tocan por donde se corto. El lado sale de mirar hacia
    donde queda la vecina en los ejes de la propia pieza, que es lo que hace
    que la marca de la izquierda este de verdad a la izquierda cuando tienes la
    pieza en la mano por su cara de dentro.
    """
    cajas = {}
    centros = {}
    for pieza in piezas:
        objeto = pieza.objeto
        esquinas = [objeto.matrix_world @ Vector(v) for v in objeto.bound_box]
        bajo = Vector((min(p.x for p in esquinas), min(p.y for p in esquinas),
                       min(p.z for p in esquinas)))
        alto = Vector((max(p.x for p in esquinas), max(p.y for p in esquinas),
                       max(p.z for p in esquinas)))
        cajas[objeto.name] = (bajo, alto)
        centros[objeto.name] = (bajo + alto) / 2.0

    salida: Dict[str, Dict[str, str]] = {}
    for pieza in piezas:
        nombre = pieza.objeto.name
        marco = marcos.get(nombre)
        if marco is None:
            continue
        propio = centros[nombre]
        bajo, alto = cajas[nombre]
        mejor: Dict[str, Tuple[float, str]] = {}
        for otra in piezas:
            ajeno = otra.objeto.name
            if ajeno == nombre:
                continue
            b2, a2 = cajas[ajeno]
            if (b2.x > alto.x + holgura or a2.x < bajo.x - holgura
                    or b2.y > alto.y + holgura or a2.y < bajo.y - holgura
                    or b2.z > alto.z + holgura or a2.z < bajo.z - holgura):
                continue
            hacia = pieza.objeto.matrix_world.inverted() @ centros[ajeno] \
                - pieza.objeto.matrix_world.inverted() @ propio
            if hacia.length < 1e-9:
                continue
            x = hacia.dot(marco.derecha)
            y = hacia.dot(marco.arriba)
            if abs(y) >= abs(x):
                lado = "arriba" if y > 0 else "abajo"
                fuerza = abs(y)
            else:
                lado = "derecha" if x > 0 else "izquierda"
                fuerza = abs(x)
            if lado not in mejor or fuerza > mejor[lado][0]:
                mejor[lado] = (fuerza, ajeno)
        salida[nombre] = {lado: quien for lado, (_, quien) in mejor.items()}
    return salida
