"""Leer OBJ del mundo real, no solo el que exporta la propia libreria."""

import os

import pytest
import trimesh

from cortador.meshio import MeshError, load_mesh, sanear_texto


def _cubo_obj() -> str:
    caja = trimesh.creation.box(extents=[20.0, 20.0, 20.0])
    vertices = "".join(f"v {p[0]} {p[1]} {p[2]}\n" for p in caja.vertices)
    caras = "".join("f " + " ".join(str(i + 1) for i in t) + "\n"
                    for t in caja.faces)
    return vertices + caras


def _escribir(tmp_path, nombre, texto, binario=False):
    ruta = os.path.join(str(tmp_path), nombre)
    if binario:
        with open(ruta, "wb") as fh:
            fh.write(texto)
    else:
        with open(ruta, "w", newline="") as fh:
            fh.write(texto)
    return ruta


def test_un_obj_con_la_marca_de_windows_se_carga(tmp_path):
    """El BOM que pone Windows al principio de un archivo de texto.

    Sin quitarlo, al lector se le pierde el primer vertice y revienta con un
    "index 7 is out of bounds" que no le dice nada a nadie.
    """
    ruta = _escribir(tmp_path, "bom.obj", ("﻿" + _cubo_obj()).encode("utf-8"),
                     binario=True)
    malla = load_mesh(ruta, repair=False)

    assert len(malla.faces) == 12
    assert malla.is_watertight


def test_un_obj_con_coma_decimal_se_carga(tmp_path):
    """Un exportador configurado en espanol escribe 'v 1,5 2,0 0,0'."""
    ruta = _escribir(tmp_path, "coma.obj", _cubo_obj().replace(".", ","))
    malla = load_mesh(ruta, repair=False)

    assert len(malla.faces) == 12
    assert malla.is_watertight


def test_un_obj_con_saltos_de_windows_se_carga(tmp_path):
    ruta = _escribir(tmp_path, "crlf.obj", _cubo_obj().replace("\n", "\r\n"))
    assert len(load_mesh(ruta, repair=False).faces) == 12


def test_un_obj_sin_caras_lo_dice_con_palabras(tmp_path):
    """Una nube de puntos no es una malla, y hay que decirlo asi."""
    solo_puntos = "".join(f"v {i} {i} {i}\n" for i in range(10))
    ruta = _escribir(tmp_path, "puntos.obj", solo_puntos)

    with pytest.raises(MeshError) as fallo:
        load_mesh(ruta, repair=False)
    assert "cara" in str(fallo.value).lower()


def test_un_obj_ilegible_explica_que_hacer(tmp_path):
    ruta = _escribir(tmp_path, "roto.obj", "esto no es un obj\nni de lejos\n")

    with pytest.raises(MeshError) as fallo:
        load_mesh(ruta, repair=False)
    texto = str(fallo.value)
    assert "STL" in texto                    # le dice la salida practica


def test_sanear_no_toca_un_archivo_que_ya_esta_bien():
    assert sanear_texto(_cubo_obj().encode("utf-8")) is None


def test_sanear_no_se_lleva_por_delante_los_comentarios():
    """Una coma en un comentario no es una coma decimal."""
    texto = b"# hecho el 3, de mayo\nv 1,5 0 0\n"
    limpio = sanear_texto(texto)

    assert limpio is not None
    assert b"# hecho el 3, de mayo" in limpio
    assert b"v 1.5 0 0" in limpio


def test_un_obj_con_grupos_se_carga_entero(tmp_path):
    """ZBrush y Blender parten el modelo en grupos: son una sola pieza."""
    caja = trimesh.creation.box(extents=[20.0, 20.0, 20.0])
    lineas = ["mtllib modelo.mtl", "o Figura"]
    lineas += [f"v {p[0]} {p[1]} {p[2]}" for p in caja.vertices]
    mitad = len(caja.faces) // 2
    lineas += ["g arriba", "usemtl m0"]
    lineas += ["f " + " ".join(str(i + 1) for i in t) for t in caja.faces[:mitad]]
    lineas += ["g abajo", "usemtl m1"]
    lineas += ["f " + " ".join(str(i + 1) for i in t) for t in caja.faces[mitad:]]
    ruta = _escribir(tmp_path, "grupos.obj", "\n".join(lineas) + "\n")

    malla = load_mesh(ruta, repair=True)     # con reparacion, como hace la app
    assert len(malla.faces) == 12
    assert malla.is_watertight
