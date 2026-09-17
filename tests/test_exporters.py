import json
import os
import struct
import zipfile

import numpy as np
import pytest

from cortador.config import (JoineryOptions, LabelOptions, PrinterSpec,
                             SliceConfig)
from cortador.exporters import (assembly_guide, export_result, piece_color,
                                piece_path2d, pieces_csv, preview_glb,
                                preview_payload, safe_name, zip_directory)
from cortador.slicer import slice_model


@pytest.fixture(scope="module")
def resultado(caja_modulo):
    cfg = SliceConfig(printer=PrinterSpec(100, 100, 100),
                      labels=LabelOptions(enabled=True, size=8, depth=0.8),
                      joinery=JoineryOptions(mode="holes", radius=3, depth=6, count=1))
    return slice_model(caja_modulo, cfg)


@pytest.fixture(scope="module")
def caja_modulo():
    import trimesh
    m = trimesh.creation.box(extents=[120.0, 80.0, 200.0])
    m.apply_translation([60.0, 40.0, 100.0])
    return m


def test_colores_distintos():
    colores = {tuple(piece_color(i)) for i in range(40)}
    assert len(colores) > 35


def test_safe_name():
    assert safe_name("A1-L01") == "A1-L01"
    assert safe_name("pieza/rara*?") == "pieza_rara__"
    assert safe_name("") == "pieza"


def test_csv_tiene_una_fila_por_pieza(resultado):
    filas = pieces_csv(resultado).strip().split("\n")
    assert len(filas) == resultado.count + 1
    assert filas[0].startswith("pieza,capa")


def test_guia_menciona_todas_las_piezas(resultado):
    guia = assembly_guide(resultado, "caja")
    for pieza in resultado.pieces:
        assert pieza.name in guia
    assert "Guia de armado" in guia
    assert "Orden de montaje" in guia


def test_payload_de_vista_previa(resultado):
    datos = preview_payload(resultado)
    largo = struct.unpack("<I", datos[:4])[0]
    assert largo % 4 == 0          # los float32 deben quedar alineados
    cabecera = json.loads(datos[4:4 + largo].decode("utf-8"))
    assert len(cabecera["pieces"]) == resultado.count
    floats = np.frombuffer(datos[4 + largo:], dtype=np.float32)
    total = sum(p["count"] for p in cabecera["pieces"])
    assert len(floats) == total * 3
    for pieza in cabecera["pieces"]:
        assert len(pieza["color"]) == 3
        assert pieza["count"] % 3 == 0


def test_glb_se_genera(resultado):
    datos = preview_glb(resultado)
    assert datos[:4] == b"glTF"


def test_exportacion_completa(resultado, tmp_path):
    info = export_result(resultado, str(tmp_path), model_name="caja")
    piezas = os.listdir(tmp_path / "piezas")
    assert len(piezas) == resultado.count
    assert all(p.endswith(".stl") for p in piezas)
    assert (tmp_path / "cortador.json").exists()
    assert (tmp_path / "despiece.csv").exists()
    assert (tmp_path / "GUIA_DE_ARMADO.md").exists()
    assert (tmp_path / "espigas").is_dir()
    manifiesto = json.loads((tmp_path / "cortador.json").read_text(encoding="utf-8"))
    assert manifiesto["total_piezas"] == resultado.count
    assert info["pieces"] == resultado.count


def test_exportacion_en_obj(resultado, tmp_path):
    export_result(resultado, str(tmp_path), mesh_format="obj", write_preview=False)
    assert all(p.endswith(".obj") for p in os.listdir(tmp_path / "piezas"))


def test_formato_no_soportado(resultado, tmp_path):
    with pytest.raises(ValueError):
        export_result(resultado, str(tmp_path), mesh_format="dwg")


def test_zip(resultado, tmp_path):
    export_result(resultado, str(tmp_path), write_preview=False)
    destino = str(tmp_path / "todo.zip")
    zip_directory(str(tmp_path), destino)
    with zipfile.ZipFile(destino) as zf:
        nombres = zf.namelist()
    assert any(n.startswith("piezas/") for n in nombres)
    assert "GUIA_DE_ARMADO.md" in nombres


def test_planos_2d_de_laminas(caja_modulo, tmp_path):
    cfg = SliceConfig(printer=PrinterSpec(500, 500, 500), mode="slabs",
                      slab_thickness=25.0, slab_style="prism",
                      labels=LabelOptions(enabled=True, size=10))
    res = slice_model(caja_modulo, cfg)
    export_result(res, str(tmp_path), write_preview=False)
    archivos = os.listdir(tmp_path / "2d")
    assert len([a for a in archivos if a.endswith(".svg")]) == res.count
    assert len([a for a in archivos if a.endswith(".dxf")]) == res.count
    contenido = (tmp_path / "2d" / archivos[0]).read_text(encoding="utf-8", errors="ignore")
    assert contenido
    ruta = piece_path2d(res.pieces[0], cfg)
    capas = {e.layer for e in ruta.entities if hasattr(e, "layer")}
    assert "CORTE" in capas and "MARCA" in capas


def test_piezas_se_guardan_en_el_origen(resultado, tmp_path):
    export_result(resultado, str(tmp_path), write_preview=False, write_2d=False)
    import trimesh
    for nombre in os.listdir(tmp_path / "piezas"):
        malla = trimesh.load(str(tmp_path / "piezas" / nombre))
        assert np.allclose(malla.bounds[0], [0, 0, 0], atol=1e-6)
    manifiesto = json.loads((tmp_path / "cortador.json").read_text(encoding="utf-8"))
    assert manifiesto["piezas_en_el_origen"] is True
    # y el manifiesto conserva la posicion real dentro del modelo
    assert any(p["bounds"][0] != [0.0, 0.0, 0.0] for p in manifiesto["piezas"])


def test_exportar_en_su_sitio(resultado, tmp_path):
    export_result(resultado, str(tmp_path), write_preview=False, write_2d=False,
                  place_at_origin=False)
    import trimesh
    lejos = [trimesh.load(str(tmp_path / "piezas" / n)).bounds[0]
             for n in os.listdir(tmp_path / "piezas")]
    assert any(not np.allclose(b, [0, 0, 0], atol=1e-6) for b in lejos)


def test_ajustes_del_laminador(caja_modulo, tmp_path):
    from cortador.config import PrinterSpec, SliceConfig
    from cortador.exporters import slicer_settings
    from cortador.slicer import slice_model
    cfg = SliceConfig(printer=PrinterSpec(100, 100, 100), hollow=True, wall=2.0,
                      labels=LabelOptions(enabled=False))
    res = slice_model(caja_modulo, cfg)
    texto = slicer_settings(res, line_width=0.4)
    assert "Relleno (infill) . . . . . . . 0 %" in texto
    assert "5" in texto                      # 2.0 mm / 0.4 mm = 5 perimetros
    export_result(res, str(tmp_path), write_preview=False, write_2d=False)
    assert (tmp_path / "AJUSTES_LAMINADOR.txt").exists()


def test_sin_vaciado_no_hay_archivo_de_ajustes(resultado, tmp_path):
    export_result(resultado, str(tmp_path), write_preview=False, write_2d=False)
    assert not (tmp_path / "AJUSTES_LAMINADOR.txt").exists()


def test_los_ajustes_del_laminador_siguen_a_la_boquilla():
    """Con una boquilla de 1,0 no se ponen los mismos perimetros que con 0,4."""
    import trimesh
    from cortador.config import PrinterSpec, SliceConfig
    from cortador.exporters import slicer_settings
    from cortador.slicer import slice_model

    esfera = trimesh.creation.icosphere(subdivisions=2, radius=50.0)

    fina = SliceConfig(printer=PrinterSpec(x=300, y=300, z=300, nozzle=0.4),
                       hollow=True, wall=3.36)
    gorda = SliceConfig(printer=PrinterSpec(x=300, y=300, z=300, nozzle=1.0),
                        hollow=True, wall=3.15)

    texto_fino = slicer_settings(slice_model(esfera, fina))
    texto_gordo = slicer_settings(slice_model(esfera, gorda))

    assert "0.42 mm" in texto_fino and "boquilla de 0.4 mm" in texto_fino
    assert "1.05 mm" in texto_gordo and "boquilla de 1 mm" in texto_gordo
    # la pared fina necesita el doble de perimetros que la gorda
    assert "8    (" in texto_fino
    assert "3    (" in texto_gordo
