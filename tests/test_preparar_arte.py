"""La herramienta que deja utilizables las imagenes que salen de una IA."""

import os
import sys

import pytest

pytest.importorskip("PIL")

from PIL import Image, ImageDraw  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))

import preparar_arte  # noqa: E402


def _esfera(tmp_path, fondo, color_centro, color_borde, nombre="esfera.png"):
    """Una esfera centrada sobre fondo liso, como la que genera la IA."""
    im = Image.new("RGB", (768, 1152), fondo)
    dib = ImageDraw.Draw(im)
    cx, cy, r = 384, 576, 300
    pasos = 60
    for i in range(pasos, 0, -1):
        t = i / pasos
        color = tuple(int(color_borde[c] * t + color_centro[c] * (1 - t)) for c in range(3))
        radio = r * t
        dib.ellipse((cx - radio, cy - radio, cx + radio, cy + radio), fill=color)
    ruta = tmp_path / nombre
    im.save(ruta)
    return str(ruta)


def _fondo(tmp_path, nombre="fondo.png"):
    """Un degradado con bandas: nada compacto ni centrado."""
    im = Image.new("RGB", (768, 1152), (12, 12, 15))
    dib = ImageDraw.Draw(im)
    for y in range(0, 1152, 24):
        dib.line((0, y, 768, y + 40), fill=(30, 60, 120), width=6)
    ruta = tmp_path / nombre
    im.save(ruta)
    return str(ruta)


def test_reconoce_una_esfera_clara(tmp_path):
    ruta = _esfera(tmp_path, (14, 14, 18), (220, 218, 214), (90, 90, 95))
    assert preparar_arte.parece_esfera(Image.open(ruta)) is True


def test_reconoce_una_esfera_oscura(tmp_path):
    """El caso dificil: esfera casi negra sobre fondo casi negro."""
    ruta = _esfera(tmp_path, (28, 28, 34), (70, 72, 80), (10, 40, 120))
    assert preparar_arte.parece_esfera(Image.open(ruta)) is True


def test_un_fondo_no_pasa_por_esfera(tmp_path):
    assert preparar_arte.parece_esfera(Image.open(_fondo(tmp_path))) is False


def test_el_matcap_sale_cuadrado_y_recortado(tmp_path):
    origen = _esfera(tmp_path, (14, 14, 18), (220, 218, 214), (90, 90, 95))
    salida = tmp_path / "salida"
    salida.mkdir()
    destino = preparar_arte.preparar(origen, str(salida))
    assert destino.endswith(".png")
    im = Image.open(destino)
    assert im.size == (512, 512)
    # las esquinas quedan negras: fuera del circulo no hay material
    for punto in ((2, 2), (509, 2), (2, 509), (509, 509)):
        assert sum(im.convert("RGB").getpixel(punto)) < 30


def test_el_fondo_se_reduce_y_se_comprime(tmp_path):
    origen = _fondo(tmp_path)
    salida = tmp_path / "salida"
    salida.mkdir()
    destino = preparar_arte.preparar(origen, str(salida))
    assert destino.endswith(".jpg")
    assert Image.open(destino).width == 1200 or Image.open(destino).width == 768
    assert os.path.getsize(destino) < 400_000


def test_se_puede_forzar_el_tipo(tmp_path):
    origen = _fondo(tmp_path)
    salida = tmp_path / "salida"
    salida.mkdir()
    destino = preparar_arte.preparar(origen, str(salida), tipo="matcap")
    assert destino.endswith(".png") and Image.open(destino).size == (512, 512)
