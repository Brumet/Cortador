"""Perfiles de maquina: lo que de verdad cabe en cada una."""

import math

import pytest
import trimesh

from cortador.config import PrinterSpec, SliceConfig
from cortador.perfiles import PERFILES, perfil
from cortador.planner import plan_cuts


def test_las_flsun_son_delta_y_la_cama_es_redonda():
    for id_ in ("flsun_v400", "flsun_t1", "flsun_sr"):
        p = perfil(id_)
        assert p.printer.is_round(), id_
        assert p.printer.diameter > 0


def test_en_cama_redonda_no_cabe_el_diametro_entero():
    """Lo que cabe es el cuadrado inscrito, no los 300 mm del plato."""
    v400 = perfil("flsun_v400").printer
    x, y, _z = v400.usable()
    assert x == pytest.approx(300 / math.sqrt(2) - 12, abs=0.1)
    assert x < 205        # el fabricante dice ~200 mm de lado
    assert x == y


def test_ningun_perfil_va_al_raz_de_la_maquina():
    """Cortar al limite exacto de la cama es pedir un fallo de adherencia."""
    for p in PERFILES:
        assert p.printer.clearance > 0, p.id
        util = p.printer.usable()
        fisico = (p.printer.diameter if p.printer.is_round() else p.printer.x)
        assert util[0] < fisico, p.id
        assert util[2] < p.printer.z, p.id


def test_la_pared_es_multiplo_exacto_del_ancho_de_linea():
    """Si no, el laminador deja una franja que no puede rellenar."""
    for p in PERFILES:
        if p.printer.technology != "fdm":
            continue
        perimetros = p.wall / p.printer.line_width()
        assert abs(perimetros - round(perimetros)) < 0.02, (p.id, perimetros)


def test_la_boquilla_manda_sobre_el_espesor():
    fina = PrinterSpec(nozzle=0.4)
    gorda = PrinterSpec(nozzle=1.0)
    assert gorda.line_width() > fina.line_width()
    # con boquilla gorda, 3 perimetros ya dan mas de 3 mm
    assert gorda.wall_for(3) > 3.0
    assert fina.wall_for(3) < 1.5
    # y el camino de vuelta
    assert gorda.perimeters_for(gorda.wall_for(4)) == 4


def test_los_perfiles_de_resina_son_mas_finos():
    resina = perfil("resina_grande")
    fdm = perfil("bambu_a1")
    assert resina.printer.technology == "resina"
    assert resina.wall < fdm.wall
    assert resina.kerf < fdm.kerf
    assert resina.min_piece < fdm.min_piece


def test_el_plan_respeta_la_cama_redonda():
    """Una pieza de 250 mm no cabe en una V400 aunque el plato mida 300."""
    cfg = perfil("flsun_v400").aplicar(SliceConfig())
    caja = trimesh.creation.box(extents=[250.0, 250.0, 100.0])
    plan = plan_cuts(caja.bounds, cfg)
    assert plan.counts[0] >= 2 and plan.counts[1] >= 2
    util = cfg.printer.usable()
    for eje in range(3):
        mayor = max(b - a for a, b in zip(plan.edges[eje][:-1], plan.edges[eje][1:]))
        assert mayor <= util[eje] + 1e-6


def test_aplicar_un_perfil_deja_la_configuracion_lista():
    cfg = perfil("bambu_a1").aplicar()
    assert cfg.printer.name == "Bambu Lab A1"
    assert cfg.wall == perfil("bambu_a1").wall
    assert cfg.kerf > 0
