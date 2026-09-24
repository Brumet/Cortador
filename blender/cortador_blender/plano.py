"""El plano de montaje en PDF, para llevarlo a produccion.

Una lista de piezas no sirve para montar. Lo que sirve es ver el piso armado y
que cada trozo tenga su nombre encima, como en las instrucciones de un juego de
piezas: se mira la hoja, se cogen las piezas de ese piso y se van poniendo en
el orden que marca la vuelta.

El render se hace con Workbench, el motor de dibujo de la propia ventana de
Blender. Es el que usa el programa para pintarte el modelo mientras trabajas,
asi que tarda un segundo por hoja en vez de los minutos de un render de
verdad, y para esto se ve igual de bien: lo que hace falta es distinguir las
piezas, no que brillen.

Los nombres no se meten en la escena en 3D: se proyecta donde cae cada pieza
en la imagen y el nombre se escribe encima, ya en el PDF. Asi salen siempre
del mismo tamano y legibles, este la pieza cerca o lejos, y se pueden apartar
unas de otras cuando se amontonan.
"""

from __future__ import annotations

import os
import tempfile
from typing import Dict, List, Optional, Sequence, Tuple

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Euler, Vector

from . import pdf

#: tamano de la hoja, A4 apaisado en puntos
HOJA = (842.0, 595.0)
#: la imagen de cada piso, en pixeles
FOTO = (1400, 1050)
#: filas de tabla que caben en una hoja de continuacion
FILAS_POR_HOJA = 34

_TINTA = (0.08, 0.13, 0.18)
_SUAVE = (0.36, 0.42, 0.47)
_GAJO = (0.85, 0.34, 0.12)
_LINEA = (0.76, 0.80, 0.83)


class _Camara:
    """Una camara de quita y pon que encuadra lo que se le diga."""

    def __init__(self, escena):
        self.escena = escena
        self.datos = bpy.data.cameras.new("cortador_camara")
        self.datos.type = "ORTHO"
        self.objeto = bpy.data.objects.new("cortador_camara", self.datos)
        escena.collection.objects.link(self.objeto)
        self.antigua = escena.camera
        escena.camera = self.objeto

    def encuadrar(self, objetos: Sequence[bpy.types.Object],
                  giro: float = 0.6, alzado: float = 1.0) -> None:
        puntos = []
        for objeto in objetos:
            puntos += [objeto.matrix_world @ Vector(v) for v in objeto.bound_box]
        if not puntos:
            return
        bajo = Vector((min(p.x for p in puntos), min(p.y for p in puntos),
                       min(p.z for p in puntos)))
        alto = Vector((max(p.x for p in puntos), max(p.y for p in puntos),
                       max(p.z for p in puntos)))
        centro = (bajo + alto) / 2.0
        tamano = max((alto - bajo).length, 1.0)
        # La direccion se saca del angulo, no de la matriz del objeto: la
        # matriz no se recalcula hasta que Blender vuelve a evaluar la escena,
        # asi que la primera vez devuelve la de antes y la camara acaba
        # mirando a otro lado. La primera hoja salia en negro.
        vueltas = Euler((alzado, 0.0, giro), "XYZ")
        hacia = (vueltas.to_matrix() @ Vector((0.0, 0.0, 1.0))).normalized()
        self.objeto.rotation_euler = vueltas
        self.objeto.location = centro + hacia * tamano * 2.0
        self.datos.ortho_scale = tamano * 1.15
        self.datos.clip_end = tamano * 6.0

    def quitar(self) -> None:
        self.escena.camera = self.antigua
        bpy.data.objects.remove(self.objeto, do_unlink=True)
        bpy.data.cameras.remove(self.datos)


def _ajustar_render(escena) -> dict:
    """Pone el render como lo queremos y devuelve como estaba."""
    antes = {
        "motor": escena.render.engine,
        "x": escena.render.resolution_x,
        "y": escena.render.resolution_y,
        "porcentaje": escena.render.resolution_percentage,
        "formato": escena.render.image_settings.file_format,
        "calidad": escena.render.image_settings.quality,
        "ruta": escena.render.filepath,
        "transparente": escena.render.film_transparent,
        "fondo": escena.display.shading.background_type,
        "hueco": escena.display.shading.show_cavity,
        "luz": escena.display.shading.light,
        "mundo": escena.world,
        "contorno": escena.display.shading.show_object_outline,
    }
    escena.render.engine = "BLENDER_WORKBENCH"
    escena.render.resolution_x, escena.render.resolution_y = FOTO
    escena.render.resolution_percentage = 100
    escena.render.image_settings.file_format = "JPEG"
    escena.render.image_settings.quality = 88
    escena.render.film_transparent = False
    # El fondo claro no sale del color del visor -en el render final Workbench
    # no lo mira-, sino de un mundo puesto a proposito. Y conviene que sea
    # claro: el plano acaba impreso en papel.
    escena.display.shading.background_type = "WORLD"
    escena.display.shading.light = "STUDIO"
    mundo = bpy.data.worlds.get("cortador_fondo")
    if mundo is None:
        mundo = bpy.data.worlds.new("cortador_fondo")
    mundo.use_nodes = False
    mundo.color = (0.94, 0.95, 0.96)
    escena.world = mundo
    escena.display.shading.show_cavity = True
    escena.display.shading.show_object_outline = True
    return antes


def _devolver_render(escena, antes: dict) -> None:
    escena.render.engine = antes["motor"]
    escena.render.resolution_x = antes["x"]
    escena.render.resolution_y = antes["y"]
    escena.render.resolution_percentage = antes["porcentaje"]
    escena.render.image_settings.file_format = antes["formato"]
    escena.render.image_settings.quality = antes["calidad"]
    escena.render.filepath = antes["ruta"]
    escena.render.film_transparent = antes["transparente"]
    escena.display.shading.background_type = antes["fondo"]
    escena.display.shading.show_cavity = antes["hueco"]
    escena.display.shading.light = antes["luz"]
    escena.world = antes["mundo"]
    sobra = bpy.data.worlds.get("cortador_fondo")
    if sobra is not None and sobra is not antes["mundo"]:
        bpy.data.worlds.remove(sobra)
    escena.display.shading.show_object_outline = antes["contorno"]


def _por_numero(nombre: str) -> Tuple:
    """Ordena P3-L2 antes que P3-L10, que es como los busca una persona."""
    trozos = []
    numero = ""
    for letra in nombre:
        if letra.isdigit():
            numero += letra
        else:
            if numero:
                trozos.append((1, int(numero)))
                numero = ""
            trozos.append((0, letra))
    if numero:
        trozos.append((1, int(numero)))
    return tuple(trozos)


def _centro(objeto: bpy.types.Object) -> Vector:
    esquinas = [objeto.matrix_world @ Vector(v) for v in objeto.bound_box]
    return sum(esquinas, Vector()) / len(esquinas)


def _separar(etiquetas: List[dict], alto: float, vueltas: int = 200) -> None:
    """Aparta unas etiquetas de otras cuando se amontonan.

    Sin esto, en un piso con veinte piezas la mitad de los nombres se pisan y
    no se lee ninguno. Se empujan poco a poco en vertical, que es donde hay
    sitio, y despues cada una se une con una raya al punto que le toca.
    """
    for _ in range(vueltas):
        movido = False
        etiquetas.sort(key=lambda e: e["y"])
        for i in range(len(etiquetas) - 1):
            a, b = etiquetas[i], etiquetas[i + 1]
            if abs(a["x"] - b["x"]) > (a["ancho"] + b["ancho"]) / 2 + 4:
                continue
            solape = alto - (b["y"] - a["y"])
            if solape > 0:
                a["y"] -= solape / 2 + 0.2
                b["y"] += solape / 2 + 0.2
                movido = True
        if not movido:
            break


def _foto(escena, carpeta: str, nombre: str) -> bytes:
    escena.render.filepath = os.path.join(carpeta, nombre)
    bpy.ops.render.render(write_still=True)
    with open(os.path.join(carpeta, nombre + ".jpg"), "rb") as archivo:
        return archivo.read()


def _cabecera(hoja, titulo: str, apunte: str) -> None:
    hoja.texto(40, HOJA[1] - 48, titulo, 22, negrita=True)
    hoja.texto(40, HOJA[1] - 66, apunte, 10, color=_SUAVE)
    hoja.raya(40, HOJA[1] - 76, HOJA[0] - 40, HOJA[1] - 76, _LINEA, 0.8)


def _pie(hoja, texto: str) -> None:
    hoja.texto(40, 28, texto, 8.5, color=_SUAVE)


def _tabla(hoja, x: float, y: float, ancho: float, filas: Sequence[Sequence[str]],
           titulos: Sequence[str], anchos: Sequence[float]) -> float:
    """Escribe una tabla y devuelve la altura que ha ocupado."""
    alto_fila = 13.0
    cursor = y
    sitio = x
    for titulo, parte in zip(titulos, anchos):
        hoja.texto(sitio, cursor, titulo.upper(), 7.5, negrita=True, color=_SUAVE)
        sitio += parte * ancho
    cursor -= 4
    hoja.raya(x, cursor, x + ancho, cursor, _LINEA, 0.6)
    cursor -= alto_fila
    for numero, fila in enumerate(filas):
        if numero % 2 == 1:
            hoja.caja(x - 3, cursor - 3.5, ancho + 6, alto_fila,
                      color=(0.965, 0.972, 0.977))
        sitio = x
        for celda, parte in zip(fila, anchos):
            hoja.texto(sitio, cursor, celda, 8.5,
                       negrita=(parte is anchos[0]))
            sitio += parte * ancho
        cursor -= alto_fila
    return y - cursor


def montar(resultado, ajustes, mm_por_unidad: float, ruta: str,
           figura: str = "", avisar=None) -> str:
    """Escribe el plano de montaje entero. Devuelve la ruta del PDF."""
    escena = bpy.context.scene
    antes = _ajustar_render(escena)
    camara = _Camara(escena)
    carpeta = tempfile.mkdtemp(prefix="cortador_")
    documento = pdf.Documento(*HOJA)

    escondidas = {}
    for objeto in bpy.data.objects:
        escondidas[objeto.name] = objeto.hide_render

    try:
        piezas = list(resultado.piezas)
        todas = [p.objeto for p in piezas]
        for objeto in bpy.data.objects:
            objeto.hide_render = objeto not in todas

        if avisar:
            avisar("dibujando la portada")
        camara.encuadrar(todas)
        datos = _foto(escena, carpeta, "figura")
        _portada(documento, datos, resultado, ajustes, mm_por_unidad, figura)

        pisos = sorted({p.piso for p in piezas})
        for numero, piso in enumerate(pisos):
            if avisar:
                avisar(f"dibujando el piso {piso + 1} de {len(pisos)}")
            suyas = [p for p in piezas if p.piso == piso]
            for objeto in todas:
                objeto.hide_render = objeto not in [p.objeto for p in suyas]
            camara.encuadrar([p.objeto for p in suyas])
            datos = _foto(escena, carpeta, f"piso{piso + 1}")
            _hoja_de_piso(documento, datos, suyas, piso, len(pisos),
                          resultado, mm_por_unidad, escena, camara)

        documento.guardar(ruta)
    finally:
        for objeto in bpy.data.objects:
            if objeto.name in escondidas:
                objeto.hide_render = escondidas[objeto.name]
        camara.quitar()
        _devolver_render(escena, antes)
    return ruta


def _portada(documento, datos: bytes, resultado, ajustes,
             mm_por_unidad: float, figura: str) -> None:
    hoja = documento.pagina()
    _cabecera(hoja, "Plan de montaje",
              figura or "figura sin nombre")

    foto = documento.foto(datos, *FOTO)
    hoja.imagen(foto, 40, 90, 430, 322)

    x = 510
    y = HOJA[1] - 110
    hoja.texto(x, y, "La figura", 12, negrita=True)
    y -= 20
    perfil = ajustes.perfil
    total = len(resultado.piezas)
    lineas = [
        ("Piezas", str(total)),
        ("Pisos", str(len(resultado.pisos))),
        ("Maquina", perfil.nombre),
        ("Cama", "{:.0f} x {:.0f} x {:.0f} mm{}".format(
            perfil.x * mm_por_unidad, perfil.y * mm_por_unidad,
            perfil.z * mm_por_unidad, ", redonda" if perfil.redonda else "")),
        ("Pared", "{:.2f} mm".format(ajustes.pared * mm_por_unidad)),
    ]
    for titulo, valor in lineas:
        hoja.texto(x, y, titulo, 8.5, color=_SUAVE)
        hoja.texto(x + 78, y, valor, 9.5)
        y -= 16

    y -= 12
    hoja.texto(x, y, "Como leer una pieza", 12, negrita=True)
    y -= 20
    for linea in (
            "Cada pieza lleva grabado por dentro su",
            "nombre en el centro y, mas pequeno, el",
            "de la que va pegada por cada lado:",
    ):
        hoja.texto(x, y, linea, 9, color=_SUAVE)
        y -= 13

    y -= 6
    hoja.caja(x, y - 46, 200, 62, color=(0.97, 0.94, 0.91),
              borde=(0.90, 0.84, 0.79))
    hoja.texto(x + 100, y - 2, "P1/L3", 8.5, centrado=True, color=_SUAVE)
    hoja.texto(x + 24, y - 18, "P2/L2", 8.5, color=_SUAVE)
    hoja.texto(x + 100, y - 18, "P2/L3", 12, negrita=True, centrado=True,
               color=_GAJO)
    hoja.texto(x + 152, y - 18, "P2/L4", 8.5, color=_SUAVE)
    hoja.texto(x + 100, y - 36, "P3/L3", 8.5, centrado=True, color=_SUAVE)
    y -= 62

    hoja.texto(x, y, "P = piso, L = lamina.", 9, color=_SUAVE)
    y -= 13
    hoja.texto(x, y, "Las laminas van en orden dando", 9, color=_SUAVE)
    y -= 13
    hoja.texto(x, y, "la vuelta al piso.", 9, color=_SUAVE)

    _pie(hoja, "Cortador para Blender  ·  se monta de abajo arriba, "
               "piso por piso")


def _hoja_de_piso(documento, datos: bytes, suyas, piso: int, cuantos: int,
                  resultado, mm_por_unidad: float, escena, camara) -> None:
    hoja = documento.pagina()
    _cabecera(hoja, f"Piso {piso + 1} de {cuantos}",
              f"{len(suyas)} piezas  ·  se pegan entre si dando la vuelta, "
              f"y el piso entero va sobre el piso {piso}"
              if piso else f"{len(suyas)} piezas  ·  este es el de abajo, "
                           "el que apoya en el suelo")

    ancho_foto, alto_foto = 470.0, 396.0
    x0, y0 = 40.0, 88.0
    foto = documento.foto(datos, *FOTO)
    hoja.imagen(foto, x0, y0, ancho_foto, alto_foto)

    # donde cae cada pieza dentro de la imagen
    etiquetas = []
    for pieza in suyas:
        sitio = world_to_camera_view(escena, camara.objeto, _centro(pieza.objeto))
        if not (0.0 <= sitio.x <= 1.0 and 0.0 <= sitio.y <= 1.0):
            continue
        texto = pieza.nombre
        etiquetas.append({
            "texto": texto,
            "x": x0 + sitio.x * ancho_foto,
            "y": y0 + sitio.y * alto_foto,
            "ax": x0 + sitio.x * ancho_foto,
            "ay": y0 + sitio.y * alto_foto,
            "ancho": pdf.ancho_de(texto, 8, True) + 8,
        })
    _separar(etiquetas, 13.0)
    for etiqueta in etiquetas:
        if abs(etiqueta["y"] - etiqueta["ay"]) > 3:
            hoja.raya(etiqueta["ax"], etiqueta["ay"], etiqueta["x"],
                      etiqueta["y"] + 3.5, _LINEA, 0.5)
        hoja.caja(etiqueta["x"] - etiqueta["ancho"] / 2, etiqueta["y"] - 2.5,
                  etiqueta["ancho"], 11.5, color=(1, 1, 1),
                  borde=(0.86, 0.89, 0.91), grosor=0.5)
        hoja.texto(etiqueta["x"], etiqueta["y"], etiqueta["texto"], 8,
                   negrita=True, centrado=True, color=_GAJO)

    vecinos = getattr(resultado, "vecinos", {}) or {}
    filas = []
    for pieza in sorted(suyas, key=lambda p: _por_numero(p.nombre)):
        lado = vecinos.get(pieza.nombre, {})
        filas.append([
            pieza.nombre,
            "{:.0f}x{:.0f}x{:.0f}".format(pieza.ancho * mm_por_unidad,
                                          pieza.fondo * mm_por_unidad,
                                          pieza.alto * mm_por_unidad),
            lado.get("izquierda", "-"),
            lado.get("derecha", "-"),
            lado.get("arriba", "-"),
            lado.get("abajo", "-"),
        ])

    titulos = ["Pieza", "Medidas mm", "Izq", "Der", "Arriba", "Abajo"]
    anchos = [0.20, 0.26, 0.135, 0.135, 0.135, 0.135]
    cabe = 30
    _tabla(hoja, 540, HOJA[1] - 110, 262, filas[:cabe], titulos, anchos)
    _pie(hoja, f"Piso {piso + 1}  ·  Cortador para Blender")

    resto = filas[cabe:]
    while resto:
        otra = documento.pagina()
        _cabecera(otra, f"Piso {piso + 1} de {cuantos}", "continuacion")
        _tabla(otra, 40, HOJA[1] - 110, 500, resto[:FILAS_POR_HOJA],
               titulos, anchos)
        _pie(otra, f"Piso {piso + 1}  ·  Cortador para Blender")
        resto = resto[FILAS_POR_HOJA:]
