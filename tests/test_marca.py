"""El logo es el oficial de Brumet y se usa completo, no el monograma."""

import os
import re

from cortador import marca

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESTATICOS = os.path.join(RAIZ, "cortador", "web", "static")


def test_el_logo_completo_viaja_con_la_app():
    for nombre in ("brumet.svg", "brumet-blanco.svg"):
        ruta = os.path.join(ESTATICOS, nombre)
        assert os.path.exists(ruta), nombre
        texto = open(ruta, encoding="utf-8").read()
        assert "<svg" in texto and "viewBox" in texto


def test_no_se_tocan_los_trazos_del_logo():
    """El archivo de marca lo dice: solo cambia el relleno, nunca los trazos."""
    original = open(os.path.join(ESTATICOS, "brumet.svg"), encoding="utf-8").read()
    blanco = open(os.path.join(ESTATICOS, "brumet-blanco.svg"), encoding="utf-8").read()

    def trazos(svg):
        return re.findall(r'\sd="([^"]+)"', svg)

    assert trazos(original) == trazos(blanco)
    assert 'fill="#ffffff"' in blanco


def test_el_logo_se_puede_incrustar_en_las_pantallas():
    svg = marca.logo(blanco=True)
    assert svg.startswith("<svg") and "<?xml" not in svg
    negro = marca.logo(blanco=False)
    assert negro.startswith("<svg")


def test_la_interfaz_usa_el_logo_completo():
    html = open(os.path.join(ESTATICOS, "index.html"), encoding="utf-8").read()
    assert html.count("/static/brumet.svg") >= 2     # cabecera y portada
    css = open(os.path.join(ESTATICOS, "style.css"), encoding="utf-8").read()
    assert ".nombre-app" in css


def test_las_pantallas_de_espera_llevan_el_logo_y_su_hilo_de_corte():
    from cortador import desktop, ventana

    assert "<svg" in desktop._HTML_ESPERA and "hilo" in desktop._HTML_ESPERA
    assert "LOGO_BRUMET" in ventana._HTML_ESPERA and "hilo" in ventana._HTML_ESPERA
    pagina = ventana.escribir_espera("http://127.0.0.1:1/", "/tmp/x.log")
    texto = open(pagina, encoding="utf-8").read()
    assert "<svg" in texto and "LOGO_BRUMET" not in texto


def test_las_texturas_generadas_viajan_con_la_app():
    """Matcaps y fondos: si faltan, el visor y las pantallas pierden el acabado."""
    for nombre in ("matcap-oscuro.png", "matcap-claro.png",
                   "fondo-oscuro.jpg", "fondo-claro.jpg"):
        ruta = os.path.join(ESTATICOS, nombre)
        assert os.path.exists(ruta), nombre
        assert os.path.getsize(ruta) > 10_000, nombre


def test_el_visor_usa_el_matcap_pero_no_depende_de_el():
    js = open(os.path.join(ESTATICOS, "viewer.js"), encoding="utf-8").read()
    assert "uMatcap" in js and "setMatcap" in js
    # sin textura cargada, uMatcapMix vale 0 y se ven las luces de siempre
    assert "this.matcapMix = 0;" in js
    assert "if (uMatcapMix > 0.001)" in js
    app = open(os.path.join(ESTATICOS, "app.js"), encoding="utf-8").read()
    assert "matcap-oscuro.png" in app and "matcap-claro.png" in app


def test_la_pantalla_de_espera_lleva_su_fondo():
    from cortador import marca
    uri = marca.fondo_oscuro()
    assert uri.startswith("data:image/jpeg;base64,")
