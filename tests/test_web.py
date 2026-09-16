import io
import json
import time

import pytest
import trimesh
from fastapi.testclient import TestClient

from cortador.web.server import create_app


@pytest.fixture(scope="module")
def cliente():
    return TestClient(create_app())


@pytest.fixture(scope="module")
def stl_bytes():
    m = trimesh.creation.box(extents=[120.0, 80.0, 200.0])
    return m.export(file_type="stl")


def _subir(cliente, stl_bytes):
    res = cliente.post("/api/modelo",
                       files={"archivo": ("caja.stl", io.BytesIO(stl_bytes), "model/stl")})
    assert res.status_code == 200
    return res.json()["trabajo"]


def test_pagina_principal(cliente):
    res = cliente.get("/")
    assert res.status_code == 200 and "Cortador" in res.text


def test_subir_y_planificar(cliente, stl_bytes):
    trabajo = _subir(cliente, stl_bytes)
    res = cliente.post("/api/plan", json={
        "trabajo": trabajo,
        "config": {"printer": {"x": 100, "y": 100, "z": 100}, "mode": "chunks"}})
    assert res.status_code == 200
    plan = res.json()
    assert plan["counts"] == [2, 1, 2]
    assert plan["factor"] == 1.0
    assert plan["modelo"]["triangles"] == 12


def test_archivo_invalido(cliente):
    res = cliente.post("/api/modelo",
                       files={"archivo": ("malo.stl", io.BytesIO(b"no soy un stl"), "model/stl")})
    assert res.status_code == 400


def test_trabajo_desconocido(cliente):
    res = cliente.post("/api/plan", json={"trabajo": "nada", "config": {}})
    assert res.status_code == 404


def test_configuracion_invalida(cliente, stl_bytes):
    trabajo = _subir(cliente, stl_bytes)
    res = cliente.post("/api/plan", json={"trabajo": trabajo, "config": {"mode": "raro"}})
    assert res.status_code == 400


def test_corte_completo(cliente, stl_bytes):
    trabajo = _subir(cliente, stl_bytes)
    res = cliente.post("/api/cortar", json={
        "trabajo": trabajo,
        "config": {"printer": {"x": 100, "y": 100, "z": 100},
                   "labels": {"enabled": True, "size": 8}},
        "formato": "stl"})
    assert res.status_code == 200

    for _ in range(120):
        estado = cliente.get(f"/api/progreso/{trabajo}").json()
        if estado["estado"] in ("listo", "error"):
            break
        time.sleep(0.25)
    assert estado["estado"] == "listo", estado.get("error")
    assert estado["resumen"]["piezas"] == 4
    assert len(estado["resumen"]["lista"]) == 4

    vista = cliente.get(f"/api/vista/{trabajo}?fuente=piezas")
    assert vista.status_code == 200 and len(vista.content) > 100

    original = cliente.get(f"/api/vista/{trabajo}?fuente=original")
    assert original.status_code == 200

    guia = cliente.get(f"/api/guia/{trabajo}")
    assert "Guia de armado" in guia.text

    manifiesto = cliente.get(f"/api/manifiesto/{trabajo}").json()
    assert manifiesto["total_piezas"] == 4

    zip_res = cliente.get(f"/api/descargar/{trabajo}")
    assert zip_res.status_code == 200
    assert zip_res.content[:2] == b"PK"


def test_descarga_antes_de_cortar(cliente, stl_bytes):
    trabajo = _subir(cliente, stl_bytes)
    assert cliente.get(f"/api/descargar/{trabajo}").status_code == 404
    assert cliente.get(f"/api/guia/{trabajo}").status_code == 404


def test_version(cliente):
    datos = cliente.get("/api/version").json()
    assert datos["version"]
    assert "windows" in datos


def test_informe_de_reparacion_al_subir(cliente):
    import numpy as np
    m = trimesh.creation.box(extents=[50.0, 50.0, 50.0])
    mask = np.ones(len(m.faces), bool)
    mask[0] = False
    m.update_faces(mask)
    res = cliente.post("/api/modelo",
                       files={"archivo": ("rota.stl", io.BytesIO(m.export(file_type="stl")),
                                          "model/stl")})
    datos = res.json()
    assert "reparacion" in datos and "resumen" in datos["reparacion"]
    assert datos["original"]["problemas"]
    assert datos["modelo"]["watertight"] is True      # se repara al vuelo


def test_descargar_malla_reparada(cliente, stl_bytes):
    trabajo = _subir(cliente, stl_bytes)
    res = cliente.get(f"/api/malla/{trabajo}")
    assert res.status_code == 200
    assert b"solid" in res.content[:200].lower() or len(res.content) > 84


def test_reparar_fuera_de_windows(cliente, stl_bytes):
    trabajo = _subir(cliente, stl_bytes)
    datos = cliente.post(f"/api/reparar/{trabajo}").json()
    assert "mensaje" in datos
    assert datos["abierto"] is datos["windows"] or datos["abierto"] is False


def test_descargar_una_pieza(cliente, stl_bytes):
    trabajo = _subir(cliente, stl_bytes)
    assert cliente.get(f"/api/pieza/{trabajo}/A-L01").status_code == 404
    cliente.post("/api/cortar", json={
        "trabajo": trabajo,
        "config": {"printer": {"x": 100, "y": 100, "z": 100},
                   "labels": {"enabled": False}}})
    for _ in range(120):
        estado = cliente.get(f"/api/progreso/{trabajo}").json()
        if estado["estado"] in ("listo", "error"):
            break
        time.sleep(0.25)
    assert estado["estado"] == "listo"
    nombre = estado["resumen"]["lista"][0]["nombre"]
    res = cliente.get(f"/api/pieza/{trabajo}/{nombre}")
    assert res.status_code == 200 and len(res.content) > 84
    assert cliente.get(f"/api/pieza/{trabajo}/NO-EXISTE").status_code == 404


def test_abrir_carpeta_antes_de_cortar(cliente, stl_bytes):
    trabajo = _subir(cliente, stl_bytes)
    assert cliente.post(f"/api/abrir/{trabajo}").status_code == 404
