import numpy as np
import trimesh
from shapely.geometry import Polygon

from cortador.geometry import (boxes_overlap, box_mesh, clip_slab, clip_to_box,
                               extrude_polygons, largest_polygon, merge_polygons,
                               plane_frame, plane_transform, polygons_from_loops,
                               section_area, section_polygons, to_world)


def test_plane_frame_es_dextrogiro():
    for axis in range(3):
        u, v = plane_frame(axis)
        eu, ev = np.zeros(3), np.zeros(3)
        eu[u] = ev[v] = 1.0
        assert np.allclose(np.cross(eu, ev)[axis], 1.0)


def test_plane_transform_ida_y_vuelta():
    T = plane_transform(1, 7.0)
    punto = np.array([3.0, 7.0, -2.0, 1.0])
    local = T @ punto
    assert np.allclose(local[2], 0.0)
    de_vuelta = np.linalg.inv(T) @ local
    assert np.allclose(de_vuelta[:3], punto[:3])


def test_to_world():
    pts = to_world(2, [(1.0, 2.0)], 5.0)
    assert np.allclose(pts[0], [1.0, 2.0, 5.0])


def test_box_mesh_y_solape():
    box = box_mesh([0, 0, 0], [10, 20, 30])
    assert np.allclose(box.extents, [10, 20, 30])
    assert abs(box.volume - 6000) < 1e-6
    assert boxes_overlap(box.bounds, [5, 5, 5], [50, 50, 50])
    assert not boxes_overlap(box.bounds, [50, 50, 50], [60, 60, 60])


def test_clip_to_box_recorta_volumen(caja):
    trozo = clip_to_box(caja, [0, 0, 0], [60, 80, 200])
    assert trozo is not None and trozo.is_watertight
    assert abs(trozo.volume - caja.volume / 2) / caja.volume < 0.01
    assert clip_to_box(caja, [500, 500, 500], [600, 600, 600]) is None


def test_los_dos_motores_dan_el_mismo_volumen(esfera):
    a = clip_to_box(esfera, [-50, -50, 0], [0, 50, 50], engine="slice")
    b = clip_to_box(esfera, [-50, -50, 0], [0, 50, 50], engine="boolean")
    assert abs(a.volume - b.volume) / a.volume < 0.02


def test_clip_slab(caja):
    banda = clip_slab(caja, 2, 50.0, 90.0)
    assert banda is not None
    assert abs(banda.extents[2] - 40.0) < 1e-6


def test_section_polygons(esfera):
    polys = section_polygons(esfera, 2, 0.0)
    assert len(polys) == 1
    assert abs(polys[0].area - np.pi * 50 ** 2) / (np.pi * 50 ** 2) < 0.02
    assert section_polygons(esfera, 2, 500.0) == []
    assert section_area(esfera, 2, 0.0) > 0


def test_polygons_from_loops_anida_agujeros():
    fuera = np.array([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], dtype=float)
    dentro = np.array([[3, 3], [6, 3], [6, 6], [3, 6], [3, 3]], dtype=float)
    polys = polygons_from_loops([fuera, dentro])
    assert len(polys) == 1
    assert abs(polys[0].area - (100 - 9)) < 1e-6


def test_merge_y_mayor():
    a = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    b = Polygon([(5, 5), (9, 5), (9, 9), (5, 9)])
    merged = merge_polygons([a, b])
    assert len(merged.geoms) == 2
    assert largest_polygon([a, b]) is b
    assert merge_polygons([]) is None


def test_extrude_polygons():
    a = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    solido = extrude_polygons(merge_polygons([a]), 3.0)
    assert solido.is_watertight
    assert abs(solido.volume - 300.0) < 1e-6
    assert extrude_polygons(None, 3.0) is None
