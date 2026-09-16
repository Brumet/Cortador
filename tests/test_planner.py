import numpy as np

from cortador.config import PrinterSpec, SliceConfig
from cortador.planner import column_letters, estimate_plan, plan_cuts

BOUNDS = np.array([[0.0, 0.0, 0.0], [600.0, 400.0, 1800.0]])


def test_column_letters():
    assert [column_letters(i) for i in (0, 25, 26, 27)] == ["A", "Z", "AA", "AB"]


def test_divisiones_por_capacidad():
    cfg = SliceConfig(printer=PrinterSpec(220, 220, 250))
    plan = plan_cuts(BOUNDS, cfg)
    assert plan.counts == (3, 2, 8)
    assert plan.total_cells == 48
    for axis, cuenta in enumerate(plan.counts):
        assert np.max(np.diff(plan.edges[axis])) <= cfg.printer.usable()[axis] + 1e-6


def test_margen_reduce_capacidad():
    sin = plan_cuts(BOUNDS, SliceConfig(printer=PrinterSpec(200, 200, 200)))
    con = plan_cuts(BOUNDS, SliceConfig(printer=PrinterSpec(200, 200, 200, clearance=10)))
    assert con.total_cells >= sin.total_cells


def test_divisiones_forzadas():
    cfg = SliceConfig(printer=PrinterSpec(1000, 1000, 1000), divisions=[2, None, 3])
    plan = plan_cuts(BOUNDS, cfg)
    assert plan.counts == (2, 1, 3)


def test_laminas_espesor_exacto():
    cfg = SliceConfig(printer=PrinterSpec(1000, 1000, 1000), mode="slabs",
                      slab_thickness=5.0)
    plan = plan_cuts(BOUNDS, cfg)
    assert plan.counts[2] == 360
    assert np.allclose(np.diff(plan.edges[2]), 5.0)


def test_laminas_repartidas():
    bounds = np.array([[0.0, 0.0, 0.0], [10.0, 10.0, 103.0]])
    cfg = SliceConfig(printer=PrinterSpec(500, 500, 500), mode="slabs",
                      slab_thickness=10.0, slab_fit="even")
    plan = plan_cuts(bounds, cfg)
    gaps = np.diff(plan.edges[2])
    assert len(gaps) == 11
    assert np.allclose(gaps, gaps[0])


def test_lamina_grande_se_subdivide():
    cfg = SliceConfig(printer=PrinterSpec(220, 220, 250), mode="slabs",
                      slab_thickness=5.0)
    plan = plan_cuts(BOUNDS, cfg)
    assert plan.counts[0] == 3 and plan.counts[1] == 2


def test_nombres_de_piezas():
    cfg = SliceConfig(printer=PrinterSpec(220, 220, 250))
    plan = plan_cuts(BOUNDS, cfg)
    assert plan.name_for((0, 0, 0)) == "A1-L01"
    assert plan.name_for((2, 1, 7)) == "C2-L08"
    assert plan.name_for((1, 0, 2), naming="numeric") == "X02Y01Z03"


def test_vecinos_y_caras_interiores():
    cfg = SliceConfig(printer=PrinterSpec(220, 220, 250))
    plan = plan_cuts(BOUNDS, cfg)
    assert plan.neighbor((0, 0, 0), 0, 1) == (1, 0, 0)
    assert plan.neighbor((0, 0, 0), 0, -1) is None
    assert plan.is_interior_face((1, 0, 0), 0, -1)


def test_kerf_encoge_solo_caras_interiores():
    cfg = SliceConfig(printer=PrinterSpec(220, 220, 250), kerf=1.0)
    plan = plan_cuts(BOUNDS, cfg)
    lo, hi = plan.cell_bounds((1, 0, 1))
    assert lo[0] > plan.edges[0][1]
    lo0, _ = plan.cell_bounds((0, 0, 0))
    assert lo0[0] == plan.edges[0][0]


def test_estimacion_incluye_avisos():
    cfg = SliceConfig(printer=PrinterSpec(1000, 1000, 1000), divisions=[1, 1, 1])
    info = estimate_plan(BOUNDS, cfg)
    assert info["total_cells"] == 1
    assert any("caber" in w for w in info["warnings"])
