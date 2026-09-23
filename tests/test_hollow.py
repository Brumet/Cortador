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


def test_no_salen_piezas_sin_grosor():
    """Las caras sueltas que deja el vaciado no deben acabar como piezas."""
    import trimesh
    from cortador.config import LabelOptions, PrinterSpec, SliceConfig
    from cortador.slicer import slice_model

    figura = trimesh.creation.icosphere(subdivisions=4, radius=120)
    cfg = SliceConfig(printer=PrinterSpec(220, 220, 250), mode="slabs",
                      slab_thickness=20.0, slab_style="prism", hollow=True, wall=3.0,
                      labels=LabelOptions(enabled=False))
    res = slice_model(figura, cfg)
    for pieza in res.pieces:
        assert min(float(v) for v in pieza.size) > 0.05, f"{pieza.name}: {pieza.size}"
        assert pieza.outline is not None, f"{pieza.name} se quedaria sin plano 2D"


def test_tambien_se_limpian_las_motas_en_macizo():
    """Una seccion casi tangente al plano no debe generar confeti."""
    import trimesh
    from cortador.config import LabelOptions, PrinterSpec, SliceConfig
    from cortador.slicer import slice_model

    # una cupula: cerca de la cima el corte roza la superficie
    esfera = trimesh.creation.icosphere(subdivisions=4, radius=150)
    try:
        trimesh.smoothing.filter_taubin(esfera, iterations=4)
    except Exception:
        pass
    cfg = SliceConfig(printer=PrinterSpec(500, 500, 500), mode="slabs",
                      slab_thickness=25.0, slab_style="prism", min_piece=6.0,
                      labels=LabelOptions(enabled=False))
    res = slice_model(esfera, cfg)
    for pieza in res.pieces:
        medidas = sorted(float(v) for v in pieza.size)
        assert medidas[1] >= 6.0, f"{pieza.name}: {pieza.size}"
    # y no debe explotar en cientos de trozos
    assert res.count < 40


def test_una_pieza_hueca_no_se_parte_en_dos():
    """Una piel con camara interior es una sola pieza, no dos."""
    import numpy as np
    import trimesh
    from cortador.slicer import _reunir_cavidades

    fuera = trimesh.creation.box(extents=[40.0, 40.0, 40.0])
    dentro = trimesh.creation.box(extents=[30.0, 30.0, 30.0])
    dentro.invert()
    partes = [fuera, dentro]
    assert len(_reunir_cavidades(partes)) == 1


def test_las_piezas_son_piel_no_cajas():
    """El corte reparte la piel del modelo; no fabrica cajitas cerradas.

    Es el fallo que se corrigio: si se corta primero y se vacia cada trozo
    despues, cada trozo sale como una caja con paredes en las caras de corte y
    los del centro salen como cubos huecos que no aportan nada.
    """
    import trimesh
    from cortador.config import LabelOptions, PrinterSpec, SliceConfig
    from cortador.slicer import slice_model

    esfera = trimesh.creation.icosphere(subdivisions=4, radius=80)
    res = slice_model(esfera, SliceConfig(printer=PrinterSpec(100, 100, 100),
                                          hollow=True, wall=4.0,
                                          labels=LabelOptions(enabled=False)))
    assert res.count == 8                    # ocho octantes, no dieciseis
    for pieza in res.pieces:
        assert pieza.mesh.is_watertight
        assert pieza.mesh.volume > 0         # el hueco no cuenta como pieza
        # una pieza de piel ocupa una fraccion pequena de su caja
        assert pieza.mesh.volume < 0.35 * float(pieza.mesh.bounding_box.volume)

    # el material total es el de la piel del modelo entero, no el de ocho cajas
    from cortador.hollow import hollow_mesh
    piel, aviso = hollow_mesh(esfera, 4.0)
    assert aviso is None
    assert res.hollow_volume < piel.volume * 1.25


def test_el_centro_de_un_modelo_hueco_no_genera_piezas():
    """Dentro de la camara no hay material, asi que no hay nada que cortar."""
    import trimesh
    from cortador.config import LabelOptions, PrinterSpec, SliceConfig
    from cortador.slicer import slice_model

    cubo = trimesh.creation.box(extents=[300.0, 300.0, 300.0])
    res = slice_model(cubo, SliceConfig(printer=PrinterSpec(110, 110, 110),
                                        hollow=True, wall=5.0,
                                        labels=LabelOptions(enabled=False)))
    # rejilla de 3x3x3 = 27 celdas, pero la del centro esta hueca
    assert res.plan.total_cells == 27
    centros = [p for p in res.pieces if tuple(p.index) == (1, 1, 1)]
    assert not centros, [p.name for p in centros]
    assert res.count <= 26


def test_se_descartan_las_rebabas_finas():
    """Un resto de corte de decimas de milimetro no es una pieza."""
    import trimesh
    from cortador.config import LabelOptions, PrinterSpec, SliceConfig
    from cortador.slicer import slice_model

    esfera = trimesh.creation.icosphere(subdivisions=4, radius=150)
    cfg = SliceConfig(printer=PrinterSpec(100, 100, 100), hollow=True, wall=3.0,
                      min_piece=5.0, labels=LabelOptions(enabled=False))
    res = slice_model(esfera, cfg)
    for pieza in res.pieces:
        assert min(float(v) for v in pieza.size) >= 0.8, f"{pieza.name}: {pieza.size}"


def test_el_solidificado_no_se_sale_del_modelo():
    """La piel siempre queda dentro de la superficie original, sin puas."""
    import trimesh
    from cortador.hollow import hollow_mesh

    erizo = trimesh.creation.icosphere(subdivisions=3, radius=60)
    erizo.vertices[np.arange(0, len(erizo.vertices), 7)] *= 1.6   # pliegues cerrados
    erizo.fix_normals()

    piel, aviso = hollow_mesh(erizo, 3.0)
    assert aviso is None and piel is not erizo
    fuera = trimesh.boolean.difference([piel, erizo])
    volumen_fuera = abs(float(fuera.volume)) if fuera is not None and len(fuera.faces) else 0.0
    assert volumen_fuera < piel.volume * 1e-3
    assert piel.volume < erizo.volume


def test_la_pared_se_afina_donde_no_cabe():
    """En un pliegue cerrado se reduce el avance en vez de cruzar los vertices."""
    import trimesh
    from cortador.hollow import _superficie_interior

    cuna = trimesh.creation.icosphere(subdivisions=3, radius=30)
    cuna.vertices[:, 0] *= 0.08          # casi plana: 2.4 mm de grueso
    cuna.fix_normals()
    interior = _superficie_interior(cuna, 3.0)
    assert interior is not None
    # sin limitar, el interior daria la vuelta y seria mas grande que el original
    assert interior.extents[0] <= cuna.extents[0] + 1e-6


# ------------------------------------------------- mallas de escaneo rugosas
def _peluda(subdivisiones=6, amplitud=4.0, frecuencia=2.2, radio=250.0, semilla=5):
    """Una esfera con grano fino, como un escaneo con pelo o textura."""
    import numpy as np
    import trimesh

    rs = np.random.RandomState(semilla)
    m = trimesh.creation.icosphere(subdivisions=subdivisiones, radius=radio)
    v = m.vertices.copy()
    n = m.vertex_normals
    pelo = (np.sin(v[:, 0] * frecuencia) * np.cos(v[:, 1] * frecuencia)
            * np.sin(v[:, 2] * frecuencia))
    m.vertices = v + n * (pelo[:, None] * amplitud
                          + rs.normal(0, amplitud * 0.375, (len(v), 1)))
    m.merge_vertices()
    return m


def test_la_cara_interior_queda_lisa():
    """Por dentro se ve liso, no con las puas del escaneo.

    Es lo que Brumet vio en su lobo: la pared interior salia mas rugosa que la
    superficie del modelo, porque se desplazaba la malla tal cual y cada
    rugosidad se cruzaba con sus vecinas.
    """
    from cortador.hollow import _rugosidad, _superficie_interior

    modelo = _peluda()
    interior = _superficie_interior(modelo, 5.0)

    assert interior is not None
    assert _rugosidad(interior) < _rugosidad(modelo) * 0.5


def test_una_malla_rugosa_y_densa_se_vacia_de_verdad():
    """Con un escaneo, el vaciado tiene que dar piel, no migajas."""
    from cortador.hollow import hollow_mesh

    modelo = _peluda(subdivisiones=6, amplitud=6.0, frecuencia=3.0)
    hueca, aviso = hollow_mesh(modelo, 5.0)

    assert aviso is None
    assert hueca is not modelo
    # una piel conserva la cara de fuera y anade la de dentro
    assert hueca.area > modelo.area * 1.2
    # y ahorra material de verdad, sin quedarse en nada
    assert 0.02 < hueca.volume / modelo.volume < 0.6


def test_no_se_entrega_una_piel_hecha_migajas():
    """Antes se devolvian esquirlas diciendo '100 % menos de material'."""
    import trimesh

    from cortador.hollow import _es_piel

    modelo = trimesh.creation.icosphere(subdivisions=3, radius=100.0)
    migajas = trimesh.creation.box(extents=[2.0, 2.0, 2.0])

    assert _es_piel(migajas, modelo) is False
    # una piel de verdad si pasa
    from cortador.hollow import hollow_mesh
    piel, aviso = hollow_mesh(modelo, 5.0)
    assert aviso is None and _es_piel(piel, modelo) is True


# ------------------------------------------- la piel entera no se estropea
def _cascara_de_prueba(radio=60.0, pared=5.0, subdivisiones=3):
    """Una piel de verdad: esfera menos esfera, hecha con el motor booleano."""
    import trimesh
    fuera = trimesh.creation.icosphere(subdivisions=subdivisiones, radius=radio)
    dentro = trimesh.creation.icosphere(subdivisions=subdivisiones,
                                        radius=radio - pared)
    return trimesh.boolean.difference([fuera, dentro])


def test_soldar_no_sustituye_una_piel_que_ya_estaba_bien():
    """El error que dejaba el lobo hecho migajas.

    El motor booleano entrega la piel cerrada. Soldar vertices encima solo vale
    para *mirar* como la vera el laminador: donde el modelo es mas fino que la
    pared las dos caras se funden y aparecen aristas con cuatro triangulos, y
    entonces la malla soldada ya no es estanca. Si se devolvia esa, el corte
    posterior dejaba los trozos abiertos, el volumen se contaba como cero y el
    programa anunciaba "100 % menos de material" sobre un modelo intacto.
    """
    from cortador.hollow import _cascara_limpia

    piel = _cascara_de_prueba()
    assert piel.is_watertight
    salida = _cascara_limpia(piel)
    assert salida.is_watertight
    assert len(salida.faces) == len(piel.faces)


def test_una_piel_finisima_de_un_modelo_enorme_no_se_rechaza():
    """En una figura de dos metros la piel es menos del 0,5 % del bloque.

    Con el limite fijo de antes esa piel -perfectamente buena- se daba por
    migajas y el vaciado se descartaba entero.
    """
    import trimesh
    from cortador.hollow import _es_piel

    modelo = trimesh.creation.box(extents=[1900.0, 700.0, 1900.0])
    piel = trimesh.boolean.difference(
        [modelo, trimesh.creation.box(extents=[1898.0, 698.0, 1898.0])])

    assert piel.volume / modelo.volume < 0.005          # menos del limite viejo
    assert _es_piel(piel, modelo, 1.0) is True
    # y unas migajas siguen sin colar
    assert _es_piel(trimesh.creation.box(extents=[2.0, 2.0, 2.0]),
                    modelo, 1.0) is False


def test_el_ahorro_nunca_dice_el_cien_por_cien():
    from cortador.hollow import savings

    assert "100 %" not in savings(1000.0, 0.5)
    assert "99 %" in savings(1000.0, 0.5)


# -------------------------------------------------- vaciado por capas
def test_el_vaciado_por_capas_da_una_piel_cerrada():
    """La herramienta de reserva: encoger secciones no puede cruzarse nunca."""
    import trimesh
    from cortador.hollow import _es_piel, _piel_por_capas

    modelo = trimesh.creation.icosphere(subdivisions=4, radius=80.0)
    piel = _piel_por_capas(modelo, 6.0)

    assert piel is not None
    assert piel.is_watertight
    assert _es_piel(piel, modelo, 6.0) is True
    # la piel mide aproximadamente superficie x espesor
    esperado = modelo.area * 6.0
    assert 0.5 * esperado < piel.volume < 1.9 * esperado


def test_el_vaciado_por_capas_deja_tapa_arriba_y_abajo():
    """El hueco no puede salir por el techo: en Z tambien hay pared."""
    import numpy as np
    import trimesh
    from cortador.hollow import _piel_por_capas

    cilindro = trimesh.creation.cylinder(radius=40.0, height=120.0, sections=64)
    piel = _piel_por_capas(cilindro, 5.0)

    assert piel is not None and piel.is_watertight
    # el eje del cilindro sigue lleno de material en los extremos
    rayos = piel.ray.intersects_location(
        ray_origins=np.array([[0.0, 0.0, 200.0]]),
        ray_directions=np.array([[0.0, 0.0, -1.0]]))[0]
    alturas = sorted(float(p[2]) for p in rayos)
    assert len(alturas) >= 4                    # techo, camara, suelo
    assert alturas[-1] - alturas[-2] >= 4.0     # tapa de arriba, unos 5 mm


def test_una_piel_rota_por_picos_se_rehace_por_capas():
    """Si el desplazamiento falla, se entrega piel igual: nunca migajas."""
    import trimesh
    from cortador.hollow import hollow_mesh

    modelo = _peluda(subdivisiones=5, amplitud=8.0, frecuencia=4.0, radio=120.0)
    piel, aviso = hollow_mesh(modelo, 5.0)

    assert aviso is None
    assert piel is not modelo
    assert piel.area > modelo.area * 1.2
    assert 0.0 < piel.volume < modelo.volume * 0.9


# ---------------------------------------------- el informe no puede mentir
def test_el_material_de_una_pieza_abierta_no_cuenta_cero():
    """Una pieza que no queda cerrada tiene material aunque no se pueda medir."""
    import trimesh
    from cortador.config import SliceConfig
    from cortador.slicer import _volumen_pieza

    cfg = SliceConfig(hollow=True, wall=3.0)
    tapa = trimesh.Trimesh(vertices=[[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]],
                           faces=[[0, 1, 2], [0, 2, 3]])
    assert not tapa.is_volume
    # 100 mm2 de piel de 3 mm: unos 150 mm3, no cero
    assert _volumen_pieza(tapa, cfg) == 150.0

    cubo = trimesh.creation.box(extents=[10.0, 10.0, 10.0])
    assert abs(_volumen_pieza(cubo, cfg) - 1000.0) < 1e-6


def test_el_ahorro_que_se_anuncia_es_el_de_las_piezas():
    """El numero del informe tiene que salir de lo que se va a imprimir."""
    import trimesh
    from cortador.config import LabelOptions, PrinterSpec, SliceConfig
    from cortador.hollow import hollow_mesh
    from cortador.slicer import slice_model

    esfera = trimesh.creation.icosphere(subdivisions=4, radius=150.0)
    cfg = SliceConfig(printer=PrinterSpec(110, 110, 110), hollow=True, wall=4.0,
                      labels=LabelOptions(enabled=False))
    res = slice_model(esfera, cfg)

    piel, aviso = hollow_mesh(esfera, 4.0)
    assert aviso is None
    # el material contado no puede desplomarse a casi nada
    assert res.hollow_volume > piel.volume * 0.6
    assert res.hollow_volume < piel.volume * 1.4
    assert all("100 %" not in a for a in res.warnings)


def test_las_piezas_de_un_modelo_vaciado_salen_cerradas():
    """Cortar una piel con el recorte rapido dejaba trozos abiertos."""
    import trimesh
    from cortador.config import LabelOptions, PrinterSpec, SliceConfig
    from cortador.slicer import slice_model

    esfera = trimesh.creation.icosphere(subdivisions=4, radius=150.0)
    res = slice_model(esfera, SliceConfig(printer=PrinterSpec(110, 110, 110),
                                          hollow=True, wall=4.0,
                                          labels=LabelOptions(enabled=False)))
    abiertas = [p.name for p in res.pieces if not p.mesh.is_volume]
    assert not abiertas, abiertas


def test_si_no_se_puede_vaciar_las_piezas_quedan_macizas_y_se_dice():
    """Nunca se vacia trozo a trozo: eso llenaba el centro de cajas huecas."""
    import trimesh
    from cortador.config import LabelOptions, PrinterSpec, SliceConfig
    from cortador.slicer import slice_model

    # una plancha de 5 mm con 4 mm de piel: no hay hueco posible
    plancha = trimesh.creation.box(extents=[200.0, 200.0, 5.0])

    res = slice_model(plancha, SliceConfig(printer=PrinterSpec(110, 110, 110),
                                           hollow=True, wall=4.0,
                                           labels=LabelOptions(enabled=False)))
    assert any("macizas" in a for a in res.warnings), res.warnings
    for pieza in res.pieces:
        assert pieza.mesh.is_volume


# ------------------------------------------------ la vista previa no enga�a
def test_la_vista_previa_no_rompe_una_pieza_de_piel():
    """Aligerar una cascara funde sus dos caras y la pared desaparece.

    Los STL estaban bien; lo que se veia hecho un amasijo de picos era la vista
    previa, que para que cupiera en su presupuesto de triangulos aligeraba cada
    pieza y en una piel de 3 mm eso la destroza.
    """
    import trimesh
    from cortador.exporters import _decimate

    fuera = trimesh.creation.icosphere(subdivisions=4, radius=60.0)
    dentro = trimesh.creation.icosphere(subdivisions=4, radius=57.0)
    piel = trimesh.boolean.difference([fuera, dentro])
    assert piel.is_watertight

    ligera = _decimate(piel, max(60, int(len(piel.faces) * 0.1)))
    assert ligera.is_watertight, "la vista previa no puede abrir una pieza"


def test_la_previa_de_un_modelo_vaciado_ensena_lo_que_hay():
    """Lo que se ve en pantalla tiene que ser la pieza, no un terron.

    Con un presupuesto de triangulos ridiculo, el visor puede aligerar todo lo
    que quiera siempre que la pieza siga siendo la misma: si la camara interior
    se derrumba, el volumen se dispara y eso es lo que Brumet veia como un
    amasijo de picos.
    """
    import json
    import struct

    import numpy as np
    import trimesh
    from cortador.config import LabelOptions, PrinterSpec, SliceConfig
    from cortador.exporters import preview_payload
    from cortador.slicer import slice_model

    esfera = trimesh.creation.icosphere(subdivisions=4, radius=150.0)
    res = slice_model(esfera, SliceConfig(printer=PrinterSpec(110, 110, 110),
                                          hollow=True, wall=4.0,
                                          labels=LabelOptions(enabled=False)))
    datos = preview_payload(res, max_triangles=1000)      # presupuesto ridiculo
    largo = struct.unpack("<I", datos[:4])[0]
    cabecera = json.loads(datos[4:4 + largo])
    puntos = np.frombuffer(datos[4 + largo:], dtype=np.float32).reshape(-1, 3)

    for pieza, info in zip(res.pieces, cabecera["pieces"]):
        trozo = puntos[info["offset"]:info["offset"] + info["count"]]
        pintada = trimesh.Trimesh(vertices=trozo,
                                  faces=np.arange(len(trozo)).reshape(-1, 3))
        pintada.merge_vertices()
        assert abs(pintada.volume - pieza.mesh.volume) < abs(pieza.mesh.volume) * 0.1, \
            f"{pieza.name}: el visor ensena {pintada.volume:.0f} y la pieza es {pieza.mesh.volume:.0f}"


# ------------------------------------------------------- corte en paralelo
def test_cortar_con_varios_hilos_da_exactamente_lo_mismo():
    """Repartir las bandas entre hilos no puede cambiar ni una pieza."""
    import trimesh
    from cortador import slicer
    from cortador.config import LabelOptions, PrinterSpec, SliceConfig
    from cortador.slicer import slice_model

    modelo = trimesh.creation.icosphere(subdivisions=4, radius=150.0)
    cfg = lambda: SliceConfig(printer=PrinterSpec(90, 90, 90), hollow=True,
                              wall=4.0, labels=LabelOptions(enabled=False))

    original = slicer.hilos_de_corte
    try:
        slicer.hilos_de_corte = lambda: 1
        uno = slice_model(modelo, cfg())
        slicer.hilos_de_corte = lambda: 4
        varios = slice_model(modelo, cfg())
    finally:
        slicer.hilos_de_corte = original

    assert [p.name for p in uno.pieces] == [p.name for p in varios.pieces]
    assert abs(uno.hollow_volume - varios.hollow_volume) < 1e-6


# ------------------------------------------- el espesor de pared se cumple
def _erizo(radio=60.0, pico=1.9, subdivisiones=4, cada=5):
    """Una esfera con picos: los picos son mas finos que dos paredes."""
    import trimesh
    m = trimesh.creation.icosphere(subdivisions=subdivisiones, radius=radio)
    v = m.vertices.copy()
    v[np.arange(0, len(v), cada)] *= pico
    m.vertices = v
    m.fix_normals()
    return m


def test_la_pared_que_sale_se_mide_y_se_recomienda_la_que_hay_que_pedir():
    """En un escaneo la pared no puede ser igual en todas partes.

    La cara interior es lisa y la de fuera no: por los picos sobra pared y por
    los valles falta, y lo que falta es el relieve del modelo. Eso no se puede
    tapar sin devolverle la textura al interior, asi que se **mide** y se dice
    que espesor habria que pedir para que el minimo real sea el que se quiere.
    """
    from cortador.hollow import espesor_recomendado, hollow_mesh, medir_pared

    modelo = _peluda(subdivisiones=5, amplitud=6.0, frecuencia=3.0, radio=120.0)
    pared = 5.0
    piel, aviso = hollow_mesh(modelo, pared)
    assert aviso is None

    medida = medir_pared(modelo, piel, muestras=8000)
    assert medida is not None
    pedir = espesor_recomendado(pared, medida)
    assert pedir is not None and pedir > pared

    # y pidiendo eso, el minimo real sube de verdad
    gruesa, _ = hollow_mesh(modelo, pedir)
    assert medir_pared(modelo, gruesa, 8000)[1] > medida[1]


def test_medir_pared_ve_una_piel_fina():
    """La medida tiene que detectar de verdad una pared delgada."""
    import trimesh
    from cortador.hollow import medir_pared

    fuera = trimesh.creation.icosphere(subdivisions=4, radius=60.0)
    dentro = trimesh.creation.icosphere(subdivisions=4, radius=59.0)
    piel = trimesh.boolean.difference([fuera, dentro])

    medida = medir_pared(fuera, piel, muestras=4000)
    assert medida is not None
    assert 0.7 < medida[2] < 1.3        # la mediana es ese milimetro de pared


def test_el_informe_dice_el_espesor_que_ha_salido():
    import trimesh
    from cortador.config import LabelOptions, PrinterSpec, SliceConfig
    from cortador.slicer import slice_model

    esfera = trimesh.creation.icosphere(subdivisions=4, radius=150.0)
    res = slice_model(esfera, SliceConfig(printer=PrinterSpec(110, 110, 110),
                                          hollow=True, wall=4.0,
                                          labels=LabelOptions(enabled=False)))
    assert any("Pared medida" in a and "mediana" in a for a in res.warnings), res.warnings


def test_los_ajustes_hablan_del_ventilador_y_no_del_relleno():
    """Con 0 % de relleno, lo que sostiene las capas de arriba es el ventilador."""
    import trimesh
    from cortador.config import LabelOptions, PrinterSpec, SliceConfig
    from cortador.exporters import slicer_settings
    from cortador.slicer import slice_model

    esfera = trimesh.creation.icosphere(subdivisions=3, radius=150.0)
    res = slice_model(esfera, SliceConfig(printer=PrinterSpec(110, 110, 110),
                                          hollow=True, wall=4.0,
                                          labels=LabelOptions(enabled=False)))
    texto = slicer_settings(res)
    assert "0 %" in texto
    assert "entilador" in texto
    assert "puente" in texto


def test_la_cara_interior_no_lleva_la_textura_del_modelo():
    """Lo que Brumet pidio: por fuera todo el pelo, por dentro liso.

    Garantizar el espesor recortando el interior contra el modelo le devolveria
    el relieve y saldria escalonado, asi que no se hace: el interior es la forma
    lisa y punto.
    """
    import numpy as np
    import trimesh
    from cortador.hollow import hollow_mesh

    def grano(malla):
        return float(np.degrees(np.asarray(malla.face_adjacency_angles)).mean())

    modelo = _peluda(subdivisiones=5, amplitud=6.0, frecuencia=3.0, radio=120.0)
    piel, aviso = hollow_mesh(modelo, 5.0)
    assert aviso is None

    # la cara interior son los triangulos que quedan lejos de la superficie
    centros = piel.triangles_center
    _, distancia, _ = trimesh.proximity.closest_point(modelo, centros)
    dentro = piel.submesh([np.where(distancia > 1.0)[0]], append=True)

    assert grano(dentro) < grano(modelo) * 0.35, (grano(dentro), grano(modelo))


# -------------------------------------------- placas mas finas que la pared
def _con_faldon():
    """Dos piernas y una placa de 4 mm colgando entre ellas.

    Es la forma del samurai de Brumet: el faldon de la armadura es mas fino que
    dos paredes de 3 mm, asi que no se puede vaciar.
    """
    import trimesh
    piezas = []
    for x in (-45.0, 45.0):
        p = trimesh.creation.cylinder(radius=32.0, height=340.0, sections=48)
        p.apply_translation([x, 0, 170.0])
        piezas.append(p)
    tronco = trimesh.creation.box(extents=[150.0, 70.0, 160.0])
    tronco.apply_translation([0, 0, 420.0])
    piezas.append(tronco)
    faldon = trimesh.creation.box(extents=[130.0, 4.0, 150.0])
    faldon.apply_translation([0, 0, 265.0])
    piezas.append(faldon)
    return trimesh.boolean.union(piezas)


def test_una_placa_mas_fina_que_la_pared_se_queda_maciza():
    """El error que Brumet vio como franjas parpadeando en el samurai.

    Al vaciar una placa de 4 mm con 3 mm de pared, la cara interior sale por el
    otro lado y quedan dos superficies pegadas sin nada entre medias. En el
    visor eso son dos capas peleandose por el mismo pixel, y el laminador
    rechaza la pieza. Lo correcto es no vaciar ahi.
    """
    from cortador.hollow import fraccion_membrana, hollow_mesh

    modelo = _con_faldon()
    piel, aviso = hollow_mesh(modelo, 3.0)

    assert aviso is None and piel is not modelo
    assert piel.is_watertight
    assert fraccion_membrana(modelo, piel, 3.0, 12000) < 0.02
    # y sigue siendo una piel: el faldon macizo no puede volver macizo el resto
    assert piel.volume < modelo.volume * 0.25


def test_un_escaneo_normal_no_paga_el_rehacer():
    """Rehacer el hueco cuesta un minuto: solo cuando hay membranas de verdad.

    En un escaneo rugoso sin placas finas, el 1 % de piel fina son esquirlas
    del borde donde la camara se cierra. Rehacer por eso saldria carisimo y
    devolveria el relieve a la cara interior.
    """
    from cortador.hollow import fraccion_membrana, _cascara, _superficie_interior

    modelo = _peluda(subdivisiones=5, amplitud=6.0, frecuencia=3.0, radio=120.0)
    cruda = _cascara(modelo, _superficie_interior(modelo, 5.0))

    from cortador.hollow import MEMBRANA_MAX
    assert fraccion_membrana(modelo, cruda, 5.0, 8000) < MEMBRANA_MAX


def test_el_grosor_util_son_dos_lineas_de_extrusion():
    from cortador.hollow import grosor_util

    assert abs(grosor_util(3.0) - 1.2) < 1e-9
    assert grosor_util(1.0) == 0.8          # nunca por debajo de 0,8 mm
