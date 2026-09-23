"""Cortar por donde la figura se estrecha, no por la mitad del muslo."""

import numpy as np
import trimesh

from cortador.config import LabelOptions, PrinterSpec, SliceConfig
from cortador.estrechamientos import ajustar_cortes, estrechamientos, perfil_de_grosor
from cortador.planner import plan_cuts
from cortador.slicer import slice_model


def _mancuerna():
    """Dos bolas unidas por un cuello corto, como un tobillo.

    Las bolas son de distinto tamano y el cuello va bajo a proposito: asi el
    reparto a partes iguales cae en 150, dentro de la bola gorda, y el cuello en
    110. Con una figura simetrica el reparto acertaria de casualidad y la prueba
    no probaria nada.
    """
    a = trimesh.creation.icosphere(subdivisions=4, radius=50.0)
    a.apply_translation([0, 0, 50.0])                    # ocupa de 0 a 100
    b = trimesh.creation.icosphere(subdivisions=4, radius=90.0)
    b.apply_translation([0, 0, 210.0])                   # de 120 a 300
    c = trimesh.creation.cylinder(radius=14.0, height=50.0, sections=48)
    c.apply_translation([0, 0, 110.0])                   # de 85 a 135
    return trimesh.boolean.union([a, b, c])


#: donde esta el cuello y donde caeria el corte sin mirar la figura
CUELLO, REPARTO = 110.0, 150.0


def test_el_perfil_ve_donde_hay_menos_contorno():
    modelo = _mancuerna()
    alturas, medida = perfil_de_grosor(modelo, 2, muestras=120)

    assert len(alturas) == len(medida) == 120
    centro = int(np.argmin(np.abs(alturas - CUELLO)))
    bola = int(np.argmin(np.abs(alturas - 210.0)))
    assert medida[centro] < medida[bola] * 0.4      # el cuello tiene mucho menos


def test_el_cuello_sale_como_estrechamiento_marcado():
    modelo = _mancuerna()
    hallados = estrechamientos(modelo, 2)

    assert hallados, "no ha encontrado el cuello"
    altura, marca = hallados[0]
    assert abs(altura - CUELLO) < 25.0, altura      # en el cuello, no en la bola
    assert marca > 0.5                              # y marcado de verdad


def test_una_figura_sin_estrechamientos_no_inventa_ninguno():
    """Una caja no tiene tobillos: no hay nada que mover."""
    caja = trimesh.creation.box(extents=[100.0, 100.0, 300.0])
    assert estrechamientos(caja, 2) == []


def test_el_corte_se_mueve_al_cuello():
    modelo = _mancuerna()
    lo, hi = float(modelo.bounds[0][2]), float(modelo.bounds[1][2])
    bordes = np.linspace(lo, hi, 3)                 # reparto a partes iguales
    nuevos, movidos = ajustar_cortes(bordes, estrechamientos(modelo, 2),
                                     capacidad=200.0)

    assert movidos == 1
    assert abs(nuevos[1] - CUELLO) < 25.0
    assert nuevos[0] == bordes[0] and nuevos[-1] == bordes[-1]


def test_nunca_se_mueve_un_corte_si_la_pieza_deja_de_caber():
    """Lo primero es que entre en la maquina; lo segundo, que sea comoda."""
    bordes = np.array([0.0, 100.0, 200.0])
    # el estrechamiento esta en 60: mover el corte ahi dejaria una pieza de 140
    nuevos, movidos = ajustar_cortes(bordes, [(60.0, 0.9)], capacidad=110.0)

    assert movidos == 0
    assert list(nuevos) == list(bordes)


def test_un_corte_no_se_va_al_otro_lado_del_modelo():
    """Solo se mueve dentro de su propio margen, no a cualquier sitio."""
    bordes = np.array([0.0, 100.0, 200.0])
    nuevos, movidos = ajustar_cortes(bordes, [(12.0, 1.0)], capacidad=1000.0)

    assert movidos == 0


def test_el_plan_completo_corta_por_el_cuello():
    modelo = _mancuerna()
    cfg = SliceConfig(printer=PrinterSpec(200, 200, 200),
                      labels=LabelOptions(enabled=False))
    plan = plan_cuts(modelo.bounds, cfg, mesh=modelo)

    corte = plan.edges[2][1]
    assert abs(corte - CUELLO) < 25.0, plan.edges[2]
    assert any("estrechamiento" in a for a in plan.warnings), plan.warnings


def test_se_puede_apagar():
    modelo = _mancuerna()
    cfg = SliceConfig(printer=PrinterSpec(200, 200, 200), snap_cuts=False,
                      labels=LabelOptions(enabled=False))
    plan = plan_cuts(modelo.bounds, cfg, mesh=modelo)

    assert abs(plan.edges[2][1] - REPARTO) < 1e-6   # el reparto a partes iguales
    assert not any("estrechamiento" in a for a in plan.warnings)


def test_la_cara_de_corte_sale_mas_pequena():
    """Que es de lo que se trata: menos junta que pegar y menos que se vea."""
    modelo = _mancuerna()
    base = SliceConfig(printer=PrinterSpec(200, 200, 200),
                       labels=LabelOptions(enabled=False))
    listo = slice_model(modelo, base)

    tonto = SliceConfig(printer=PrinterSpec(200, 200, 200), snap_cuts=False,
                        labels=LabelOptions(enabled=False))
    recto = slice_model(modelo, tonto)

    def cara(res):
        from cortador.geometry import section_area
        return section_area(modelo, 2, float(res.plan.edges[2][1]))

    assert cara(listo) < cara(recto) * 0.25
