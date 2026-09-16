import json
import os

import pytest
import trimesh

from cortador.cli import build_parser, main, parse_divisions, parse_volume


@pytest.fixture(scope="module")
def modelo(tmp_path_factory):
    m = trimesh.creation.box(extents=[120.0, 80.0, 200.0])
    path = tmp_path_factory.mktemp("modelo") / "caja.stl"
    m.export(str(path))
    return str(path)


def test_parse_volume():
    p = parse_volume("220x220x250")
    assert (p.x, p.y, p.z) == (220, 220, 250)
    assert parse_volume("300X200X400").y == 200
    with pytest.raises(Exception):
        parse_volume("220x220")
    with pytest.raises(Exception):
        parse_volume("a x b x c")


def test_parse_divisions():
    assert parse_divisions("3x2x4") == [3, 2, 4]
    assert parse_divisions("3x-x4") == [3, None, 4]
    assert parse_divisions("") is None


def test_info(modelo, capsys):
    assert main(["info", modelo]) == 0
    salida = capsys.readouterr().out
    assert "Triangulos" in salida and "120.00" in salida


def test_plan(modelo, capsys):
    assert main(["plan", modelo, "-i", "100x100x100"]) == 0
    salida = capsys.readouterr().out
    assert "Rejilla      : 2 x 1 x 2" in salida


def test_cortar_completo(modelo, tmp_path):
    salida = str(tmp_path / "out")
    codigo = main(["cortar", modelo, "-i", "100x100x100", "-o", salida,
                   "--marca-tam", "8", "--espigas", "agujeros", "--zip",
                   "--silencioso"])
    assert codigo == 0
    assert len(os.listdir(os.path.join(salida, "piezas"))) == 4
    assert os.path.exists(os.path.join(salida, "GUIA_DE_ARMADO.md"))
    assert any(f.endswith(".zip") for f in os.listdir(salida))
    manifiesto = json.load(open(os.path.join(salida, "cortador.json"), encoding="utf-8"))
    assert manifiesto["total_piezas"] == 4
    assert manifiesto["espigas"] > 0


def test_cortar_laminas(modelo, tmp_path):
    salida = str(tmp_path / "laminas")
    codigo = main(["cortar", modelo, "-i", "500x500x500", "--modo", "laminas",
                   "--espesor", "25", "--estilo-lamina", "placa", "-o", salida,
                   "--silencioso"])
    assert codigo == 0
    assert len(os.listdir(os.path.join(salida, "piezas"))) == 8
    assert os.path.isdir(os.path.join(salida, "2d"))


def test_escalar_a_tamano(modelo, tmp_path):
    salida = str(tmp_path / "grande")
    assert main(["cortar", modelo, "-i", "300x300x300", "--tamano", "900",
                 "-o", salida, "--sin-marcas", "--silencioso"]) == 0
    manifiesto = json.load(open(os.path.join(salida, "cortador.json"), encoding="utf-8"))
    assert abs(manifiesto["modelo"]["escalado"]["size"][2] - 900.0) < 1e-6


def test_texto_svg(tmp_path, capsys):
    destino = str(tmp_path / "t.svg")
    assert main(["texto", "A1-L03", "-o", destino]) == 0
    assert open(destino, encoding="utf-8").read().startswith("<svg")


def test_archivo_inexistente(capsys):
    assert main(["info", "/no/existe.stl"]) == 1
    assert "Error" in capsys.readouterr().err


def test_ayuda():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])
