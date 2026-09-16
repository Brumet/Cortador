import numpy as np
import pytest
import trimesh

from cortador.config import (JoineryOptions, LabelOptions, PrinterSpec,
                             SliceConfig)
from cortador.slicer import slice_model


def _cfg(**kw):
    base = dict(printer=PrinterSpec(100, 100, 100),
                labels=LabelOptions(enabled=False))
    base.update(kw)
    return SliceConfig(**base)


def test_trozos_cubren_el_modelo(caja):
    res = slice_model(caja, _cfg())
    assert res.count == 2 * 1 * 2
    total = sum(p.mesh.volume for p in res.pieces)
    assert abs(total - caja.volume) / caja.volume < 0.01
    assert all(p.mesh.is_watertight for p in res.pieces)
    assert not res.oversized()


def test_todas_las_piezas_caben(figura):
    res = slice_model(figura, _cfg(printer=PrinterSpec(120, 120, 120)))
    usable = res.config.printer.usable()
    for pieza in res.pieces:
        assert all(pieza.size[i] <= usable[i] + 1e-6 for i in range(3))


def test_kerf_separa_las_piezas(caja):
    res = slice_model(caja, _cfg(kerf=2.0))
    # la rejilla es 2x1x2, asi que los nombres no llevan numero de fila
    por_nombre = {p.name: p for p in res.pieces}
    a, b = por_nombre["A-L01"], por_nombre["B-L01"]
    assert b.mesh.bounds[0][0] - a.mesh.bounds[1][0] >= 1.9


def test_vecinos_se_enlazan(caja):
    res = slice_model(caja, _cfg())
    a = next(p for p in res.pieces if p.name == "A-L01")
    assert a.neighbors["+x"] == "B-L01"
    assert a.neighbors["+z"] == "A-L02"
    assert "-x" not in a.neighbors


def test_laminas_solidas(esfera):
    cfg = _cfg(printer=PrinterSpec(500, 500, 500), mode="slabs", slab_thickness=10.0)
    res = slice_model(esfera, cfg)
    assert res.count == 10
    for pieza in res.pieces:
        assert pieza.size[2] <= 10.0 + 1e-6
    total = sum(p.mesh.volume for p in res.pieces)
    assert abs(total - esfera.volume) / esfera.volume < 0.02


def test_laminas_planas_tienen_espesor_constante(esfera):
    cfg = _cfg(printer=PrinterSpec(500, 500, 500), mode="slabs",
               slab_thickness=5.0, slab_style="prism")
    res = slice_model(esfera, cfg)
    assert res.count == 20
    for pieza in res.pieces:
        assert abs(pieza.size[2] - 5.0) < 1e-6
        assert pieza.outline is not None
        assert pieza.mesh.is_watertight


def test_laminas_en_otro_eje(caja):
    cfg = _cfg(printer=PrinterSpec(500, 500, 500), mode="slabs",
               slab_thickness=20.0, slab_axis="x")
    res = slice_model(caja, cfg)
    assert res.count == 6
    assert res.plan.layer_axis == 0
    assert res.pieces[0].name.startswith("L")


def test_lamina_grande_se_subdivide_en_xy(caja):
    cfg = _cfg(printer=PrinterSpec(70, 70, 500), mode="slabs", slab_thickness=50.0)
    res = slice_model(caja, cfg)
    assert res.plan.counts[0] > 1 and res.plan.counts[1] > 1
    assert not res.oversized()


def test_marcas_quitan_material(caja):
    sin = slice_model(caja, _cfg())
    con = slice_model(caja, _cfg(labels=LabelOptions(enabled=True, size=10, depth=1.0)))
    assert con.count == sin.count
    v_sin = sum(p.mesh.volume for p in sin.pieces)
    v_con = sum(p.mesh.volume for p in con.pieces)
    assert v_con < v_sin
    assert all(p.label_text for p in con.pieces)


def test_marcas_en_relieve(caja):
    res = slice_model(caja, _cfg(labels=LabelOptions(enabled=True, style="emboss",
                                                     size=10, depth=1.0)))
    plano = slice_model(caja, _cfg())
    assert sum(p.mesh.volume for p in res.pieces) > sum(p.mesh.volume for p in plano.pieces)


def test_marcas_en_todas_las_caras_de_corte(caja):
    res = slice_model(caja, _cfg(labels=LabelOptions(enabled=True, placement="cuts",
                                                     size=8, depth=0.8)))
    assert all(p.label_text for p in res.pieces)


def test_espigas_agujeros(caja):
    res = slice_model(caja, _cfg(joinery=JoineryOptions(mode="holes", radius=4,
                                                        depth=8, count=2)))
    assert res.dowels > 0
    sin = slice_model(caja, _cfg())
    assert sum(p.mesh.volume for p in res.pieces) < sum(p.mesh.volume for p in sin.pieces)


def test_espigas_macho_hembra(caja):
    res = slice_model(caja, _cfg(joinery=JoineryOptions(mode="pins", radius=4,
                                                        depth=8, count=1)))
    assert res.dowels == 0
    # la pieza con espiga sobresale de su celda
    sobresale = [p for p in res.pieces if p.mesh.bounds[1][0] > p.cell_hi[0] + 1e-6]
    assert sobresale


def test_escalado_a_tamano_objetivo(caja):
    res = slice_model(caja, _cfg(target_size=600.0, target_axis="z",
                                 printer=PrinterSpec(1000, 1000, 1000)))
    assert abs(res.source["escalado"]["size"][2] - 600.0) < 1e-6


def test_unidades(caja):
    res = slice_model(caja, _cfg(units="cm", printer=PrinterSpec(5000, 5000, 5000)))
    assert abs(res.source["escalado"]["size"][2] - 2000.0) < 1e-6


def test_cuerpos_superpuestos_se_funden(figura):
    res = slice_model(figura, _cfg(printer=PrinterSpec(150, 150, 150)))
    assert any("cuerpos" in w for w in res.warnings)
    assert all(p.mesh.is_watertight for p in res.pieces)


def test_sin_fundir_avisa_menos(figura):
    res = slice_model(figura, _cfg(weld=False, printer=PrinterSpec(150, 150, 150)))
    assert not any("cuerpos" in w for w in res.warnings)


def test_modelo_pequeno_una_sola_pieza(esfera):
    res = slice_model(esfera, _cfg(printer=PrinterSpec(300, 300, 300)))
    assert res.count == 1
    assert res.pieces[0].name == "P01"


def test_divisiones_forzadas(caja):
    res = slice_model(caja, _cfg(printer=PrinterSpec(500, 500, 500),
                                 divisions=[3, 1, 2]))
    assert res.count == 6


def test_progreso_se_reporta(caja):
    eventos = []
    slice_model(caja, _cfg(), progress=lambda d, t, m: eventos.append((d, t, m)))
    assert eventos and eventos[-1][0] <= eventos[-1][1]


def test_manifiesto(caja):
    res = slice_model(caja, _cfg(labels=LabelOptions(enabled=True)))
    man = res.manifest()
    assert man["total_piezas"] == res.count
    assert len(man["piezas"]) == res.count
    assert man["plan"]["counts"] == list(res.plan.counts)
    assert "configuracion" in man and "modelo" in man


def _dos_torres():
    """Dos columnas separadas: cada lamina son dos piezas independientes."""
    import trimesh
    a = trimesh.creation.box(extents=[40, 40, 200])
    a.apply_translation([-60, 0, 100])
    b = trimesh.creation.box(extents=[40, 40, 200])
    b.apply_translation([60, 0, 100])
    return trimesh.util.concatenate([a, b])


def test_las_islas_se_separan_en_piezas():
    cfg = _cfg(printer=PrinterSpec(500, 500, 500), mode="slabs", slab_thickness=50.0,
               slab_style="prism")
    res = slice_model(_dos_torres(), cfg)
    assert res.count == 8                      # 4 capas x 2 columnas
    nombres = sorted(p.name for p in res.pieces if p.layer == 1)
    assert nombres == ["L01a", "L01b"]
    for pieza in res.pieces:
        assert pieza.mesh.body_count == 1      # cada pieza es un solo cuerpo


def test_sin_separar_islas_queda_una_pieza_por_capa():
    cfg = _cfg(printer=PrinterSpec(500, 500, 500), mode="slabs", slab_thickness=50.0,
               slab_style="prism", split_islands=False)
    res = slice_model(_dos_torres(), cfg)
    assert res.count == 4
    assert res.pieces[0].mesh.body_count == 2


def test_los_vecinos_respetan_las_islas():
    cfg = _cfg(printer=PrinterSpec(500, 500, 500), mode="slabs", slab_thickness=50.0,
               slab_style="prism")
    res = slice_model(_dos_torres(), cfg)
    por_nombre = {p.name: p for p in res.pieces}
    izquierda = por_nombre["L01a"]
    # solo se enlaza con la pieza que tiene justo encima, no con la otra columna
    assert "+z" in izquierda.neighbors
    arriba = izquierda.neighbors["+z"]
    assert arriba in ("L02a", "L02b")
    assert "," not in arriba
    assert abs(por_nombre[arriba].mesh.bounds[0][0] - izquierda.mesh.bounds[0][0]) < 1.0
