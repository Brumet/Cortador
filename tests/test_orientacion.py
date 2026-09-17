"""Girar el modelo antes de cortar."""

import numpy as np
import pytest
import trimesh

from cortador.config import PrinterSpec, SliceConfig
from cortador.slicer import apoyar_base, orientar, slice_model


def test_girar_90_en_z_intercambia_x_e_y():
    barra = trimesh.creation.box(extents=[200.0, 40.0, 40.0])
    girada = orientar(barra, SliceConfig(rotation=(0, 0, 90)))
    assert girada.extents[0] == pytest.approx(40.0, abs=1e-6)
    assert girada.extents[1] == pytest.approx(200.0, abs=1e-6)


def test_el_modelo_girado_vuelve_al_origen():
    """El plan de corte siempre empieza en cero: si no, las piezas bailan."""
    barra = trimesh.creation.box(extents=[100.0, 50.0, 30.0])
    girada = orientar(barra, SliceConfig(rotation=(30, 15, 45)))
    assert np.allclose(girada.bounds[0], 0.0, atol=1e-6)


def test_sin_giro_no_se_toca_la_malla():
    barra = trimesh.creation.box(extents=[100.0, 50.0, 30.0])
    assert orientar(barra, SliceConfig()) is barra


def test_girar_cambia_el_numero_de_piezas():
    """Es el motivo de tener giro: una barra tumbada se parte distinto."""
    barra = trimesh.creation.box(extents=[300.0, 60.0, 60.0])
    maquina = PrinterSpec(x=100.0, y=400.0, z=400.0)

    de_pie = slice_model(barra, SliceConfig(printer=maquina))
    tumbada = slice_model(barra, SliceConfig(printer=maquina, rotation=(0, 0, 90)))
    assert de_pie.count >= 3        # 300 mm en X, que solo admite 100
    assert tumbada.count < de_pie.count


def test_apoyar_la_base_deja_el_lado_corto_en_vertical():
    plancha = trimesh.creation.box(extents=[120.0, 80.0, 10.0])
    plancha.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 3, [1, 0, 0]))
    apoyada = apoyar_base(plancha)
    assert apoyada.extents[2] == pytest.approx(10.0, abs=0.5)


def test_una_malla_rara_no_revienta_el_apoyo():
    nube = trimesh.Trimesh(vertices=np.random.RandomState(0).rand(30, 3) * 10,
                           faces=[[0, 1, 2]])
    assert apoyar_base(nube) is not None
