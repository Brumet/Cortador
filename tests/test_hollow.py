import numpy as np
import pytest
import trimesh
from shapely.geometry import Point, box as shapely_box

from cortador.config import LabelOptions, PrinterSpec, SliceConfig
from cortador.hollow import (hollow_mesh, hollow_slab, inner_polygons,
                             ring_polygons, savings)
from cortador.slicer import slice_model


def test_ring_polygons_deja_un_anillo():
    disco = Point(0, 0).buffer(50)
    anillo = ring_polygons(disco, 3.0)
    assert anillo is not None
    esperado = np.pi * (50 ** 2 - 47 ** 2)
    assert abs(anillo.area - esperado) / esperado < 0.02
    assert sum(len(p.interiors) for p in anillo.geoms) == 1


def test_ring_polygons_en_figura_fina_queda_macizo():
    fino = shapely_box(0, 0, 4, 100)
    assert ring_polygons(fino, 3.0).area == fino.area


def test_inner_polygons():
    disco = Point(0, 0).buffer(20)
    dentro = inner_polygons(disco, 5.0)
    assert abs(dentro.area - np.pi * 15 ** 2) / (np.pi * 15 ** 2) < 0.02
    assert inner_polygons(shapely_box(0, 0, 2, 2), 5.0) is None


def test_hollow_mesh_esfera():
    esfera = trimesh.creation.icosphere(subdivisions=4, radius=50)
    cascara, aviso = hollow_mesh(esfera, 3.0)
    assert aviso is None
    assert cascara.is_watertight
    teorico = 4 * np.pi * 50 ** 2 * 3
    assert abs(cascara.volume - teorico) / teorico < 0.15
    assert cascara.volume < esfera.volume * 0.25


def test_hollow_mesh_avisa_si_la_pared_no_cabe():
    fina = trimesh.creation.box(extents=[4, 60, 60])
    igual, aviso = hollow_mesh(fina, 3.0)
    assert igual is fina and "no cabe" in aviso


def test_hollow_mesh_no_toca_malla_abierta():
    m = trimesh.creation.box(extents=[50, 50, 50])
    mask = np.ones(len(m.faces), bool)
    mask[0] = False
    m.update_faces(mask)
    igual, aviso = hollow_mesh(m, 3.0)
    assert igual is m and "abierta" in aviso


def test_hollow_slab_quita_el_nucleo():
    from cortador.geometry import merge_polygons, section_polygons
    losa = trimesh.creation.box(extents=[80, 80, 10])
    losa.apply_translation([0, 0, 5])
    seccion = merge_polygons(section_polygons(losa, 2, 5.0))
    hueca, ok = hollow_slab(losa, seccion, 5.0, 0.0, 10.0, axis=2)
    assert ok and hueca.is_watertight
    esperado = (80 * 80 - 70 * 70) * 10
    assert abs(hueca.volume - esperado) / esperado < 0.02


def test_savings():
    assert "90 %" in savings(1000.0, 100.0)
    assert savings(0.0, 0.0) == ""


@pytest.fixture(scope="module")
def bloque():
    m = trimesh.creation.box(extents=[120.0, 120.0, 200.0])
    m.apply_translation([60.0, 60.0, 100.0])
    return m


def test_laminas_planas_huecas(bloque):
    cfg = SliceConfig(printer=PrinterSpec(500, 500, 500), mode="slabs",
                      slab_thickness=25.0, slab_style="prism", hollow=True, wall=5.0,
                      solid_caps=False, labels=LabelOptions(enabled=False))
    res = slice_model(bloque, cfg)
    assert res.count == 8
    for pieza in res.pieces:
        esperado = (120 * 120 - 110 * 110) * 25
        assert abs(pieza.mesh.volume - esperado) / esperado < 0.02
    assert any("vaciado" in w.lower() for w in res.warnings)


def test_tapas_macizas(bloque):
    cfg = SliceConfig(printer=PrinterSpec(500, 500, 500), mode="slabs",
                      slab_thickness=25.0, slab_style="prism", hollow=True, wall=5.0,
                      solid_caps=True, labels=LabelOptions(enabled=False))
    res = slice_model(bloque, cfg)
    por_capa = {p.layer: p for p in res.pieces}
    macizo = 120 * 120 * 25
    assert abs(por_capa[1].mesh.volume - macizo) / macizo < 0.02      # tapa de abajo
    assert abs(por_capa[8].mesh.volume - macizo) / macizo < 0.02      # tapa de arriba
    assert por_capa[4].mesh.volume < macizo * 0.5                     # intermedia hueca


def test_laminas_solidas_huecas(bloque):
    cfg = SliceConfig(printer=PrinterSpec(500, 500, 500), mode="slabs",
                      slab_thickness=50.0, slab_style="solid", hollow=True, wall=5.0,
                      solid_caps=False, labels=LabelOptions(enabled=False))
    res = slice_model(bloque, cfg)
    lleno = slice_model(bloque, SliceConfig(printer=PrinterSpec(500, 500, 500),
                                            mode="slabs", slab_thickness=50.0,
                                            labels=LabelOptions(enabled=False)))
    assert sum(p.mesh.volume for p in res.pieces) < sum(p.mesh.volume for p in lleno.pieces) * 0.4
    assert all(p.mesh.is_watertight for p in res.pieces)


def test_trozos_huecos():
    esfera = trimesh.creation.icosphere(subdivisions=4, radius=80)
    cfg = SliceConfig(printer=PrinterSpec(100, 100, 100), hollow=True, wall=4.0,
                      labels=LabelOptions(enabled=False))
    res = slice_model(esfera, cfg)
    assert res.count == 8
    assert res.hollow_volume < res.solid_volume * 0.3
    assert res.solid_volume > 0


def test_volumenes_en_el_manifiesto(bloque):
    cfg = SliceConfig(printer=PrinterSpec(500, 500, 500), mode="slabs",
                      slab_thickness=50.0, slab_style="prism", hollow=True, wall=5.0,
                      labels=LabelOptions(enabled=False))
    man = slice_model(bloque, cfg).manifest()
    assert man["volumen_cm3"] < man["volumen_macizo_cm3"]
    assert man["configuracion"]["hollow"] is True


def test_lengueta_da_sitio_para_la_marca():
    from shapely.geometry import Point
    from cortador.hollow import add_label_tab
    disco = Point(0, 0).buffer(100)
    hueco = disco.buffer(-3.0)
    anillo = disco.difference(hueco)
    con_tab, tab = add_label_tab(anillo, hueco, 30.0, 8.0)
    assert tab is not None
    assert con_tab.area > anillo.area
    # la plaquita queda unida al anillo, no suelta
    from shapely.ops import unary_union
    piezas = list(con_tab.geoms) if hasattr(con_tab, "geoms") else [con_tab]
    assert len(piezas) == 1


def test_lengueta_no_cabe_en_hueco_minusculo():
    from shapely.geometry import Point
    from cortador.hollow import add_label_tab
    disco = Point(0, 0).buffer(12)
    hueco = disco.buffer(-3.0)
    anillo = disco.difference(hueco)
    igual, tab = add_label_tab(anillo, hueco, 60.0, 20.0)
    assert tab is None and igual is anillo


def test_laminas_huecas_se_marcan_todas():
    import trimesh
    from cortador.config import LabelOptions, PrinterSpec, SliceConfig
    from cortador.slicer import slice_model
    cono = trimesh.creation.cone(radius=90, height=300, sections=48)
    cfg = SliceConfig(printer=PrinterSpec(500, 500, 500), mode="slabs",
                      slab_thickness=30.0, slab_style="prism", hollow=True, wall=3.0,
                      labels=LabelOptions(size=8, depth=0.8))
    res = slice_model(cono, cfg)
    assert res.count >= 8
    fallos = [p.name for p in res.pieces if p.notes]
    assert not fallos, f"piezas sin marcar: {fallos}"
    assert all(p.mesh.is_watertight for p in res.pieces)


def test_limpiar_quita_motas_e_hilos():
    from shapely.geometry import Point, box as sbox
    from shapely.ops import unary_union
    from cortador.hollow import limpiar
    grande = sbox(0, 0, 100, 100)
    mota = Point(200, 200).buffer(0.4)
    hilo = sbox(0, 200, 60, 200.3)
    sucio = unary_union([grande, mota, hilo])
    limpio = limpiar(sucio, 5.0)
    assert limpio is not None
    piezas = list(limpio.geoms) if hasattr(limpio, "geoms") else [limpio]
    assert len(piezas) == 1
    assert abs(piezas[0].area - grande.area) / grande.area < 0.05


def test_limpiar_sin_minimo_no_toca_nada():
    from shapely.geometry import box as sbox
    from cortador.hollow import limpiar
    figura = sbox(0, 0, 10, 10)
    assert limpiar(figura, 0).equals(figura)


def test_el_vaciado_no_genera_esquirlas():
    import trimesh
    from cortador.config import LabelOptions, PrinterSpec, SliceConfig
    from cortador.slicer import slice_model
    # una estrella de picos finos: al encoger el contorno salen esquirlas
    angulos = np.linspace(0, 2 * np.pi, 24, endpoint=False)
    radios = np.where(np.arange(24) % 2 == 0, 120.0, 40.0)
    puntos = np.column_stack([radios * np.cos(angulos), radios * np.sin(angulos)])
    from shapely.geometry import Polygon as SPoly
    estrella = trimesh.creation.extrude_polygon(SPoly(puntos), 200)
    cfg = SliceConfig(printer=PrinterSpec(500, 500, 500), mode="slabs",
                      slab_thickness=25.0, slab_style="prism", hollow=True, wall=6.0,
                      min_piece=5.0, labels=LabelOptions(enabled=False))
    res = slice_model(estrella, cfg)
    for pieza in res.pieces:
        medidas = sorted(float(v) for v in pieza.size)
        assert medidas[1] >= 5.0, f"{pieza.name} es una esquirla: {pieza.size}"


def test_el_filtro_no_parte_los_anillos_buenos():
    """Limpiar esquirlas no debe romper una pared fina que si es valida."""
    import trimesh
    from cortador.config import LabelOptions, PrinterSpec, SliceConfig
    from cortador.slicer import slice_model

    cono = trimesh.creation.cone(radius=60, height=200, sections=32)
    comun = dict(printer=PrinterSpec(500, 500, 500), mode="slabs",
                 slab_thickness=25.0, slab_style="prism", hollow=True, wall=4.0,
                 labels=LabelOptions(enabled=False))
    con_filtro = slice_model(cono, SliceConfig(min_piece=8.0, **comun))
    sin_filtro = slice_model(cono, SliceConfig(min_piece=0.0, **comun))
    # el filtro puede quitar la punta del cono, pero nunca partir un anillo bueno
    assert con_filtro.count <= sin_filtro.count
    for pieza in con_filtro.pieces:
        assert pieza.mesh.body_count == 1
