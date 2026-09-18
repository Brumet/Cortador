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


def test_la_pantalla_de_espera_lleva_el_logo_completo():
    with open(os.path.join(APP, "espera.html"), encoding="utf-8") as fh:
        espera = fh.read()
    assert "brumet-blanco.svg" in espera
    assert 'class="hilo"' in espera and "@keyframes corta" in espera
    assert os.path.exists(os.path.join(APP, "assets", "brumet-blanco.svg"))


def test_la_app_se_actualiza_sola():
    """Descargar una version nueva no puede obligar a reinstalar a mano."""
    datos = _package()
    assert "electron-updater" in datos.get("dependencies", {})

    publicacion = datos["build"]["publish"]
    assert publicacion, "sin publish, electron-updater no sabe donde mirar"
    destino = publicacion[0] if isinstance(publicacion, list) else publicacion
    assert destino["provider"] == "github"
    assert destino["repo"] == "Cortador"

    # instalacion de un clic: la actualizacion entra sin asistente
    nsis = datos["build"]["nsis"]
    assert nsis["oneClick"] is True
    assert nsis["perMachine"] is False

    with open(os.path.join(APP, "main.js"), encoding="utf-8") as fh:
        main_js = fh.read()
    assert "electron-updater" in main_js
    assert "autoInstallOnAppQuit = true" in main_js
    assert "update-downloaded" in main_js
    assert "quitAndInstall" in main_js
    # y no se busca actualizacion antes de que la app este viva
    assert main_js.index("prepararActualizador()") > main_js.index("motor listo")


def test_la_compilacion_publica_el_archivo_que_avisa_de_la_version():
    """Sin latest.yml en la Release, la app instalada nunca se entera."""
    flujo = os.path.join(RAIZ, ".github", "workflows", "construir.yml")
    with open(flujo, encoding="utf-8") as fh:
        texto = fh.read()
    assert "escritorio/dist/latest.yml" in texto
    assert "la app no podria actualizarse sola" in texto
