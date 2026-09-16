import numpy as np
import pytest
import trimesh

from cortador.repair import (RepairReport, auto_repair, body_count, diagnose,
                             find_3d_builder, is_windows,
                             open_in_windows_repair, repaired_copy_path)


@pytest.fixture
def rota(figura):
    """Figura con caras quitadas: abierta, con normales sueltas y 19 cuerpos."""
    mesh = figura.copy()
    mask = np.ones(len(mesh.faces), bool)
    mask[::11] = False
    mesh.update_faces(mask)
    return mesh


def test_body_count_suelda_antes_de_contar(caja):
    suelta = trimesh.Trimesh(vertices=caja.triangles.reshape(-1, 3),
                             faces=np.arange(len(caja.faces) * 3).reshape(-1, 3),
                             process=False)
    assert suelta.body_count > 1          # sin soldar parece un cuerpo por cara
    assert body_count(suelta) == 1


def test_diagnose_detecta_los_fallos(rota, caja):
    problemas = diagnose(rota)
    assert any("estanca" in p for p in problemas)
    assert any("cuerpos" in p for p in problemas)
    assert diagnose(caja) == []


def test_diagnose_malla_vacia():
    assert diagnose(trimesh.Trimesh()) == ["no hay geometria"]


def test_auto_repair_cierra_la_malla(rota):
    reparada, informe = auto_repair(rota)
    assert reparada.is_watertight
    assert reparada.body_count == 1
    assert informe.ok
    assert informe.cambiada
    assert informe.cuerpos_fundidos
    assert "lista para cortar" in informe.resumen()


def test_auto_repair_no_estropea_una_malla_buena(caja):
    reparada, informe = auto_repair(caja)
    assert informe.ok and not informe.cambiada
    assert abs(reparada.volume - caja.volume) < 1e-6
    assert "ya estaba bien" in informe.resumen()


def test_auto_repair_sin_fundir(figura):
    _reparada, informe = auto_repair(figura, weld=False)
    assert not informe.cuerpos_fundidos
    assert informe.cuerpos_despues > 1


def test_informe_serializable(rota):
    _m, informe = auto_repair(rota)
    datos = informe.to_dict()
    assert set(["ok", "cambiada", "resumen", "problemas"]).issubset(datos)
    assert isinstance(datos["problemas"], list)


def test_informe_vacio():
    informe = RepairReport()
    assert not informe.cambiada
    assert isinstance(informe.resumen(), str)


def test_ruta_de_copia():
    assert repaired_copy_path("/tmp/figura.stl") == "/tmp/figura_reparado.stl"
    assert repaired_copy_path("modelo").endswith("_reparado.stl")


def test_3d_builder_solo_en_windows():
    assert is_windows() in (True, False)
    if not is_windows():
        assert find_3d_builder() is False
        abierto, mensaje = open_in_windows_repair(__file__)
        assert abierto is False
        assert "Windows" in mensaje


def test_archivo_que_no_existe():
    abierto, mensaje = open_in_windows_repair("/no/existe.stl")
    assert abierto is False and "encuentro" in mensaje
