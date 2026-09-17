import numpy as np
import trimesh
from shapely.geometry import Point, box as shapely_box

from cortador.config import JoineryOptions
from cortador.geometry import largest_polygon, section_polygons
from cortador.joinery import (apply_cutters, dowel_mesh, hole_cylinder,
                              pick_points, pin_cylinder)


def _bloque():
    m = trimesh.creation.box(extents=[80.0, 60.0, 40.0])
    m.apply_translation([40.0, 30.0, 20.0])
    return m


def test_pick_points_dentro_y_separados():
    region = shapely_box(0, 0, 80, 60)
    pts = pick_points(region, 3, 3.5, 3.0)
    assert len(pts) == 3
    for x, y in pts:
        assert region.buffer(-6.5).contains(Point(x, y))
    xs = sorted(p[0] for p in pts)
    assert xs[-1] - xs[0] > 20


def test_pick_points_en_cara_estrecha():
    assert pick_points(shapely_box(0, 0, 4, 60), 2, 3.0, 3.0) == []
    assert pick_points(None, 2, 3.0, 3.0) == []


def test_pick_points_reparte_entre_islas():
    islas = shapely_box(0, 0, 30, 30).union(shapely_box(60, 0, 90, 30))
    pts = pick_points(islas, 2, 3.0, 2.0)
    assert len(pts) == 2
    assert min(p[0] for p in pts) < 30 < max(p[0] for p in pts)


def test_agujero_perfora_hacia_dentro():
    bloque = _bloque()
    opts = JoineryOptions(radius=3.0, depth=6.0, clearance=0.2)
    region = largest_polygon(section_polygons(bloque, 2, 20.0))
    pts = pick_points(region, 2, opts.radius + opts.clearance, opts.margin)
    cortes = [hole_cylinder(2, 40.0, p, 1, opts) for p in pts]
    perforado, nota = apply_cutters(bloque, cortes, "difference")
    assert nota is None and perforado.is_watertight
    quitado = bloque.volume - perforado.volume
    esperado = 2 * np.pi * (opts.radius + opts.clearance) ** 2 * opts.depth
    assert abs(quitado - esperado) / esperado < 0.05
    assert perforado.bounds[1][2] <= 40.0 + 1e-6


def test_espiga_sobresale():
    bloque = _bloque()
    opts = JoineryOptions(radius=3.0, depth=6.0)
    espiga = pin_cylinder(2, 40.0, (40.0, 30.0), 1, opts)
    con_espiga, nota = apply_cutters(bloque, [espiga], "union")
    assert nota is None
    assert con_espiga.volume > bloque.volume
    assert con_espiga.bounds[1][2] > 40.0


def test_espiga_suelta():
    opts = JoineryOptions(radius=3.0, depth=6.0)
    dowel = dowel_mesh(opts)
    assert dowel.is_watertight
    assert abs(dowel.extents[2] - (2 * 6.0 - 1.0)) < 1e-6


def test_sin_cortadores_no_cambia_nada():
    bloque = _bloque()
    igual, nota = apply_cutters(bloque, [], "difference")
    assert igual is bloque and nota is None


# --------------------------------------------------------------- laminas
def test_el_pasador_se_encoge_para_caber_en_la_lamina():
    """Una espiga de 6 mm no cabe en una lamina de 4: se hace pequena sola."""
    from cortador.config import JoineryOptions
    from cortador.joinery import ajustar

    opts = JoineryOptions(mode="pins", radius=3.0, depth=6.0)
    ajustado = ajustar(opts, espesor=4.0, pared=3.36, es_lamina=True)

    assert ajustado.depth < 4.0 * 0.5          # nunca atraviesa la lamina
    # el pasador vive dentro de la pared: radio + holgura + margen < media pared
    assert ajustado.radius + ajustado.clearance + ajustado.margin <= 3.36 / 2
    assert ajustado.count >= opts.count        # mas puntos a lo largo del anillo


def test_sin_auto_el_pasador_se_respeta_tal_cual():
    from cortador.config import JoineryOptions
    from cortador.joinery import ajustar

    opts = JoineryOptions(mode="pins", radius=3.0, depth=6.0, auto=False)
    assert ajustar(opts, espesor=4.0, pared=3.0) is opts


def test_una_pieza_maciza_conserva_el_pasador_grande():
    from cortador.config import JoineryOptions
    from cortador.joinery import ajustar

    opts = JoineryOptions(mode="pins", radius=3.0, depth=6.0)
    ajustado = ajustar(opts, espesor=60.0, pared=0.0)
    assert ajustado.radius == 3.0 and ajustado.depth == 6.0


def test_laminas_huecas_con_macho_y_hembra_de_verdad():
    """El caso de la bota: laminas huecas que tienen que encajar entre si."""
    import trimesh
    from cortador.config import JoineryOptions, SliceConfig
    from cortador.perfiles import perfil
    from cortador.slicer import slice_model

    torre = trimesh.creation.cylinder(radius=40.0, height=120.0, sections=48)
    torre.apply_translation(-torre.bounds[0])

    cfg = perfil("flsun_v400").aplicar(
        SliceConfig(mode="slabs", slab_thickness=20.0, hollow=True))
    cfg.joinery = JoineryOptions(mode="pins", auto=True)
    res = slice_model(torre, cfg)

    assert res.count >= 4
    estrechas = [p.name for p in res.pieces
                 if any("estrecha" in n for n in p.notes)]
    assert not estrechas, estrechas
    assert all(p.mesh.is_watertight for p in res.pieces)
