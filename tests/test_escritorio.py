"""La app de escritorio (Electron) tiene que seguir cuadrando con el motor."""

import json
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(RAIZ, "escritorio")


def _package():
    with open(os.path.join(APP, "package.json"), encoding="utf-8") as fh:
        return json.load(fh)


def test_la_app_tiene_lo_que_empaqueta():
    datos = _package()
    for archivo in datos["build"]["files"]:
        nombre = archivo.split("/")[0]
        assert os.path.exists(os.path.join(APP, nombre)), archivo
    assert datos["build"]["win"]["target"] == "nsis"
    assert datos["build"]["nsis"]["createDesktopShortcut"] is True


def test_el_motor_va_dentro_del_instalador():
    """Sin la carpeta motor la app se instala pero no corta nada."""
    extras = _package()["build"]["extraResources"]
    assert any(e["from"].rstrip("/") == "motor" for e in extras)


def test_la_app_lanza_el_motor_como_lo_entiende_la_cli():
    """Si cambian los nombres de las opciones, esto salta antes que el usuario."""
    from cortador.cli import build_parser

    with open(os.path.join(APP, "main.js"), encoding="utf-8") as fh:
        main_js = fh.read()

    orden = re.search(r"spawn\(python, \[([^\]]+)\]", main_js, re.S)
    assert orden, "no encuentro como se lanza el motor en main.js"
    trozos = re.findall(r"'([^']+)'", orden.group(1))
    assert trozos[:3] == ["-m", "cortador.cli", "web"]

    opciones = [t for t in trozos if t.startswith("--")]
    parser = build_parser()
    args = parser.parse_args(["web", "--host", "127.0.0.1", "--puerto", "8123",
                              "--sin-navegador"])
    assert args.sin_navegador and args.puerto == 8123
    for opcion in opciones:
        assert opcion in ("--host", "--puerto", "--sin-navegador"), opcion


def test_la_ventana_no_se_queda_muda():
    """Cualquier fallo del motor tiene que verse en la ventana."""
    with open(os.path.join(APP, "main.js"), encoding="utf-8") as fh:
        main_js = fh.read()
    assert "uncaughtException" in main_js
    assert "arranque.log" in main_js
    with open(os.path.join(APP, "espera.html"), encoding="utf-8") as fh:
        espera = fh.read()
    assert "Reintentar" in espera and "registro" in espera


def test_la_app_sabe_hacerse_una_foto():
    """La compilacion exige una foto de la ventana antes de publicar nada."""
    with open(os.path.join(APP, "main.js"), encoding="utf-8") as fh:
        main_js = fh.read()
    assert "CORTADOR_CAPTURA" in main_js and "capturePage" in main_js

    flujo = os.path.join(RAIZ, ".github", "workflows", "construir.yml")
    with open(flujo, encoding="utf-8") as fh:
        texto = fh.read()
    assert "CORTADOR_CAPTURA" in texto
    assert "La ventana no llego a abrirse" in texto
