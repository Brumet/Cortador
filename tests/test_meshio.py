import numpy as np
import pytest
import trimesh

from cortador.meshio import (MeshError, apply_units_and_scale, drop_to_floor,
                             export_mesh, is_empty, load_mesh, mesh_stats,
                             move_to_origin, repair_mesh, weld_bodies)


def test_cargar_stl(tmp_path, caja):
    ruta = tmp_path / "caja.stl"
    caja.export(str(ruta))
    cargada = load_mesh(str(ruta))
    assert abs(cargada.volume - caja.volume) < 1e-6


def test_cargar_bytes(caja):
    datos = caja.export(file_type="stl")
    cargada = load_mesh(datos, file_type="stl")
    assert len(cargada.faces) == len(caja.faces)


def test_cargar_obj_y_escena(tmp_path, figura):
    ruta = tmp_path / "figura.obj"
    figura.export(str(ruta))
    cargada = load_mesh(str(ruta))
    assert len(cargada.faces) == len(figura.faces)


def test_archivo_inexistente():
    with pytest.raises(MeshError):
        load_mesh("/no/existe.stl")


def test_bytes_sin_formato():
    with pytest.raises(MeshError):
        load_mesh(b"algo")


def test_estadisticas(caja):
    stats = mesh_stats(caja)
    assert stats["triangles"] == 12
    assert stats["watertight"] is True
    assert np.allclose(stats["size"], [120, 80, 200])


def test_escala_y_unidades(caja):
    en_cm = apply_units_and_scale(caja, units="cm")
    assert np.allclose(en_cm.extents, np.array([120, 80, 200]) * 10)
    doble = apply_units_and_scale(caja, scale=2.0)
    assert np.allclose(doble.extents, np.array([120, 80, 200]) * 2)
    objetivo = apply_units_and_scale(caja, target_size=1000.0, target_axis="z")
    assert abs(objetivo.extents[2] - 1000.0) < 1e-6
    # el tamano objetivo manda sobre la escala
    ambos = apply_units_and_scale(caja, scale=3.0, target_size=400.0)
    assert abs(ambos.extents[2] - 400.0) < 1e-6


def test_weld_bodies_funde_solapes(figura):
    assert figura.body_count > 1
    unido = weld_bodies(figura)
    assert unido.body_count == 1
    assert unido.volume < figura.volume     # los solapes ya no se cuentan dos veces


def test_weld_bodies_no_toca_un_solo_cuerpo(caja):
    assert weld_bodies(caja) is caja


def test_mover_a_origen_y_al_suelo(caja):
    movida = move_to_origin(caja)
    assert np.allclose(movida.bounds[0], [0, 0, 0])
    caja2 = caja.copy()
    caja2.apply_translation([0, 0, 50])
    assert abs(drop_to_floor(caja2).bounds[0][2]) < 1e-9


def test_is_empty(caja):
    assert not is_empty(caja)
    assert is_empty(None)
    assert is_empty(trimesh.Trimesh())


def test_exportar(tmp_path, caja):
    for ext in (".stl", ".obj", ".ply", ".glb"):
        destino = str(tmp_path / f"c{ext}")
        export_mesh(caja, destino)
        assert (tmp_path / f"c{ext}").stat().st_size > 0
    with pytest.raises(MeshError):
        export_mesh(caja, str(tmp_path / "c.dwg"))


def test_reparar_malla_con_caras_duplicadas(caja):
    sucia = trimesh.util.concatenate([caja, caja])
    limpia = repair_mesh(sucia)
    assert len(limpia.faces) <= len(caja.faces) * 1.1
