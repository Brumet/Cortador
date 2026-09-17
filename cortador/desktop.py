"""Cortador como aplicacion de escritorio.

Abre una ventana propia del sistema (no el navegador). Por dentro sigue
sirviendo la misma interfaz en un servidor local que solo escucha en
127.0.0.1, pero el usuario ve una ventana normal, con su icono y su barra de
titulo, sin barra de direcciones ni pestanas.

En Windows usa WebView2 (viene con el sistema). En Linux hace falta
WebKitGTK (`python3-gi` + `gir1.2-webkit2-4.1`) o Qt (`pip install pyqt5
pyqtwebengine`). Si no hay ninguna de las dos, avisa y abre el navegador
como ultimo recurso, para que la app nunca se quede sin arrancar.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Optional, Tuple

TITULO = "Cortador  ·  by Brumet"
ANCHO, ALTO = 1440, 900

ICONO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "packaging", "cortador.png")


def backend_disponible() -> Tuple[bool, str]:
    """Comprueba si hay motor de ventana y devuelve (hay, nombre o motivo)."""
    try:
        import webview  # noqa: F401
    except ImportError:
        return False, "falta el paquete pywebview"

    candidatos = [
        ("edgechromium", "WebView2"), ("winforms", "WinForms"),
        ("cocoa", "Cocoa"), ("gtk", "WebKitGTK"), ("qt", "Qt"),
    ]
    for modulo, nombre in candidatos:
        try:
            __import__(f"webview.platforms.{modulo}")
            return True, nombre
        except Exception:
            continue
    return False, "no hay motor de ventana instalado en el sistema"


def _arrancar_servidor(host: str, port: int):
    """Levanta uvicorn en un hilo y devuelve (servidor, hilo)."""
    import uvicorn

    from .web.server import create_app

    # log_config=None a proposito: el diccionario de logging por defecto de
    # uvicorn referencia sus formatters por nombre y, dentro del ejecutable
    # empaquetado, dictConfig no los encuentra ("Unable to configure formatter
    # 'default'"). Sin el, el servidor arranca igual y registra por la raiz.
    config = uvicorn.Config(create_app(), host=host, port=port,
                            log_level="warning", log_config=None)
    servidor = uvicorn.Server(config)
    hilo = threading.Thread(target=servidor.run, daemon=True)
    hilo.start()
    return servidor, hilo


def _esperar(url: str, servidor, segundos: float = 25.0) -> bool:
    """Espera a que el servidor conteste antes de abrir la ventana."""
    import urllib.request

    limite = time.time() + segundos
    while time.time() < limite:
        if getattr(servidor, "started", False):
            try:
                urllib.request.urlopen(url + "api/version", timeout=2).read()
                return True
            except Exception:
                pass
        time.sleep(0.2)
    return False


def run(host: str = "127.0.0.1",
        port: int = 8000,
        forzar_navegador: bool = False,
        debug: bool = False) -> int:
    """Arranca Cortador como aplicacion de escritorio."""
    from .web.server import free_port

    port = free_port(host, port)
    url = f"http://{host}:{port}/"
    servidor, _hilo = _arrancar_servidor(host, port)

    if not _esperar(url, servidor):
        print("Cortador no ha podido arrancar su servidor interno.", file=sys.stderr)
        return 1

    hay_ventana, motor = backend_disponible()
    if forzar_navegador or not hay_ventana:
        if not forzar_navegador:
            print(f"Sin ventana de escritorio ({motor}); abriendo el navegador.")
            print("Para tener ventana propia instala WebKitGTK o Qt "
                  "(ver README, apartado Instalacion).")
        import webbrowser
        webbrowser.open(url)
        print(f"Cortador esta en {url}  (Ctrl+C para salir)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        servidor.should_exit = True
        return 0

    import webview

    ventana = webview.create_window(
        TITULO, url,
        width=ANCHO, height=ALTO, min_size=(1024, 700),
        confirm_close=False, text_select=True,
    )
    try:
        if os.path.exists(ICONO):
            webview.start(debug=debug, icon=ICONO)
        else:
            webview.start(debug=debug)
    except TypeError:                      # versiones sin soporte de icono
        webview.start(debug=debug)
    finally:
        servidor.should_exit = True
    del ventana
    return 0
