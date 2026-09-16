from cortador.font import (GLYPHS, available_characters, normalize_text,
                           text_polygons, text_width)
from cortador.labels import text_preview_svg


def test_todos_los_caracteres_de_nombres_tienen_glifo():
    necesarios = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_>#"
    faltan = [c for c in necesarios if c not in GLYPHS]
    assert not faltan


def test_normalize_text():
    assert normalize_text("a1-l03") == "A1-L03"
    assert normalize_text("Ñandú") == "NANDU"
    assert normalize_text("€") == "?"


def test_ancho_crece_con_el_texto():
    assert text_width("AB", 10) > text_width("A", 10)
    assert text_width("A", 20) == 2 * text_width("A", 10)


def test_poligonos_centrados_y_con_area():
    geom = text_polygons("A1-L03", size=10, stroke=1.5)
    assert geom is not None and geom.area > 0
    minx, miny, maxx, maxy = geom.bounds
    assert abs((minx + maxx) / 2) < 0.2  # centrado (el trazo redondeado desvia un pelo)
    assert (maxy - miny) >= 10  # altura de mayuscula + trazo


def test_multilinea():
    una = text_polygons("AB", size=8, stroke=1.0)
    dos = text_polygons("AB\nCD", size=8, stroke=1.0)
    assert (dos.bounds[3] - dos.bounds[1]) > (una.bounds[3] - una.bounds[1])


def test_espacio_no_dibuja_nada():
    assert text_polygons(" ", size=10, stroke=1.0) is None


def test_svg_de_prueba():
    svg = text_preview_svg("L01", 10, 1.5)
    assert svg.startswith("<svg") and "path" in svg


def test_caracteres_disponibles():
    assert len(available_characters()) > 40
