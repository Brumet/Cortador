import numpy as np
import trimesh

from cortador.config import LabelOptions
from cortador.geometry import section_polygons
from cortador.labels import apply_label, build_text_prism, fit_text, label_region


def _placa():
    m = trimesh.creation.box(extents=[80.0, 60.0, 20.0])
    m.apply_translation([40.0, 30.0, 10.0])
    return m


def test_label_region_devuelve_la_cara():
    region = label_region(_placa(), 2, 1, 20.0)
    assert region is not None
    assert abs(region.area - 80 * 60) < 1.0


def test_fit_text_encoge_hasta_caber():
    region = label_region(_placa(), 2, 1, 20.0)
    grande = fit_text("A1", region, LabelOptions(size=200.0, stroke=20.0))
    assert grande is None or grande[1] < 200.0
    normal = fit_text("A1", region, LabelOptions(size=10.0, stroke=1.5))
    assert normal is not None and normal[1] == 10.0


def test_fit_text_en_cara_minuscula():
    chica = trimesh.creation.box(extents=[3.0, 3.0, 3.0])
    region = label_region(chica, 2, 1, 1.5)
    assert fit_text("A1-L01", region, LabelOptions(size=8.0)) is None


def test_grabado_quita_material():
    placa = _placa()
    marcada, nota = apply_label(placa, "A1-L03", 2, 1, 20.0,
                                LabelOptions(size=10, depth=1.0, stroke=1.5))
    assert nota is None
    assert marcada.is_watertight
    assert marcada.volume < placa.volume
    # el hueco debe verse al seccionar por debajo de la cara
    polys = section_polygons(marcada, 2, 19.5)
    assert sum(len(p.interiors) for p in polys) > 0


def test_relieve_anade_material():
    placa = _placa()
    marcada, nota = apply_label(placa, "B2", 2, -1, 0.0,
                                LabelOptions(style="emboss", size=10, depth=1.0))
    assert nota is None
    assert marcada.volume > placa.volume
    assert marcada.bounds[0][2] < -0.5    # el relieve sobresale


def test_marca_en_cara_lateral():
    placa = _placa()
    marcada, nota = apply_label(placa, "C3", 0, 1, 80.0,
                                LabelOptions(size=8, depth=0.8))
    assert nota is None and marcada.volume < placa.volume


def test_prisma_de_texto_orientado():
    from cortador.font import text_polygons
    geom = text_polygons("A", 10, 1.5)
    prisma = build_text_prism(geom, 2, 1, 20.0, 1.0, "engrave")
    assert prisma.bounds[0][2] < 20.0 < prisma.bounds[1][2]
    lateral = build_text_prism(geom, 0, -1, 5.0, 1.0, "engrave")
    assert lateral.bounds[0][0] < 5.0 < lateral.bounds[1][0]


def test_texto_vacio_no_toca_la_malla():
    placa = _placa()
    igual, nota = apply_label(placa, "   ", 2, 1, 20.0, LabelOptions())
    assert nota is None and igual is placa
