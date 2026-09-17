"""Cortador como aplicacion de escritorio.

Abre una ventana propia del sistema (no el navegador). Por dentro sigue
sirviendo la misma interfaz en un servidor local que solo escucha en
127.0.0.1, pero el usuario ve una ventana normal, con su icono y su barra de
titulo, sin barra de direcciones ni pestanas.

La ventana aparece primero con una pantalla de espera y el servidor arranca
detras: asi se ve algo en cuanto se hace doble clic, aunque cargar el motor
de corte tarde unos segundos. Si algo falla, el motivo se muestra en la
propia ventana y queda escrito en el registro de arranque.

En Windows usa WebView2 (viene con el sistema). En Linux hace falta
WebKitGTK (`python3-gi` + `gir1.2-webkit2-4.1`) o Qt (`pip install pyqt5
pyqtwebengine`). Si no hay ninguna de las dos, avisa y abre el navegador
como ultimo recurso, para que la app nunca se quede sin arrancar.
"""

from __future__ import annotations

import os
import socket

import threading
import time
from typing import Tuple

from .registro import fallo, paso, ruta as ruta_registro

TITULO = "Cortador  ·  by Brumet"
ANCHO, ALTO = 1440, 900

ICONO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "packaging", "cortador.png")

# codigos de salida de run(): 0 bien, 1 fallo ya avisado en pantalla,
# 2 fallo sin avisar (quien llama debe mostrarlo)
OK, FALLO_AVISADO, FALLO_MUDO = 0, 1, 2


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


def puerto_libre(host: str, port: int, intentos: int = 20) -> int:
    """Primer puerto libre a partir del pedido, sin cargar el servidor entero.

    Se repite a proposito lo que hace `web.server.free_port` porque aqui
    interesa no importar todavia el motor de corte: la ventana tiene que
    aparecer antes.
    """
    for salto in range(intentos):
        candidato = port + salto
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, candidato))
                return candidato
            except OSError:
                continue
    return port


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
    hilo = threading.Thread(target=servidor.run, daemon=True, name="servidor")
    hilo.start()
    return servidor, hilo


def _esperar(url: str, servidor, segundos: float = 60.0) -> bool:
    """Espera a que el servidor conteste antes de cargar la interfaz."""
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


def _mantener_vivo(url: str) -> None:
    """Deja el servidor en marcha hasta que el usuario corte con Ctrl+C."""
    print(f"Cortador esta en {url}  (Ctrl+C para salir)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


_ESTILO = """
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    display: flex; align-items: center; justify-content: center;
    background: #0b0b0d; color: #f5f5f7;
    font-family: -apple-system, 'Segoe UI', Inter, system-ui, sans-serif;
    -webkit-user-select: none; user-select: none;
  }
  .caja { text-align: center; max-width: 620px; padding: 0 32px; }
  .marca { font-size: 34px; font-weight: 650; letter-spacing: -.02em; }
  .marca span { opacity: .45; font-weight: 400; }
  .nota { margin-top: 10px; font-size: 14px; color: #8e8e93; }
  .barra { margin: 28px auto 0; width: 240px; height: 3px; border-radius: 3px;
           background: #1d1d20; overflow: hidden; }
  .barra i { display: block; width: 40%; height: 100%; border-radius: 3px;
             background: linear-gradient(90deg, #0a84ff, #64d2ff);
             animation: corre 1.25s ease-in-out infinite; }
  @keyframes corre { 0% { transform: translateX(-110%); }
                     100% { transform: translateX(260%); } }
  .error { text-align: left; }
  .error h1 { font-size: 22px; margin: 0 0 12px; }
  .error p { color: #aeaeb2; font-size: 14px; line-height: 1.55; }
  code { display: block; margin-top: 14px; padding: 12px 14px; border-radius: 10px;
         background: #161619; color: #ff9f0a; font-size: 12.5px;
         white-space: pre-wrap; -webkit-user-select: text; user-select: text; }
"""

_HTML_ESPERA = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Cortador</title><style>{_ESTILO}</style></head><body>
  <div class="caja">
    <div class="marca">Cortador <span>· by Brumet</span></div>
    <div class="nota">Preparando el motor de corte...</div>
    <div class="barra"><i></i></div>
  </div>
</body></html>"""


def _html_error(mensaje: str) -> str:
    registro = ruta_registro()
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Cortador</title><style>{_ESTILO}</style></head><body>
  <div class="caja error">
    <div class="marca">Cortador <span>· by Brumet</span></div>
    <h1 style="margin-top:22px">No he podido arrancar</h1>
    <p>La ventana esta bien, pero el motor interno no ha llegado a responder.
       Cierra y vuelve a abrir; si sigue igual, manda este archivo de registro
       y lo miramos:</p>
    <code>{registro}</code>
    <code>{mensaje}</code>
  </div>
</body></html>"""


def run(host: str = "127.0.0.1",
        port: int = 8000,
        forzar_navegador: bool = False,
        debug: bool = False) -> int:
    """Arranca Cortador como aplicacion de escritorio."""
    port = puerto_libre(host, port)
    url = f"http://{host}:{port}/"
    paso(f"puerto {port}")

    hay_ventana, motor = backend_disponible()
    paso(f"motor de ventana: {motor}" if hay_ventana
         else f"sin motor de ventana: {motor}")

    if forzar_navegador or not hay_ventana:
        return _por_navegador(url, host, port, forzar_navegador, motor)
    return _con_ventana(url, host, port, motor, debug)


def _con_ventana(url: str, host: str, port: int, motor: str, debug: bool) -> int:
    """Abre la ventana ya, y arranca el servidor por detras."""
    import webview

    estado = {"servidor": None, "error": ""}

    paso("creando la ventana")
    ventana = webview.create_window(
        TITULO, html=_HTML_ESPERA,
        width=ANCHO, height=ALTO, min_size=(1024, 700),
        background_color="#0b0b0d", confirm_close=False, text_select=True,
    )

    def preparar() -> None:
        try:
            paso("arrancando el servidor interno")
            servidor, _hilo = _arrancar_servidor(host, port)
            estado["servidor"] = servidor
            if not _esperar(url, servidor):
                raise RuntimeError(
                    "El servidor interno no ha respondido en 60 segundos.")
            paso("servidor listo · cargando la interfaz")
            ventana.load_url(url)
        except Exception as exc:
            estado["error"] = f"{type(exc).__name__}: {exc}"
            fallo("el servidor interno no arranco", exc)
            try:
                ventana.load_html(_html_error(estado["error"]))
            except Exception:
                pass

    try:
        if os.path.exists(ICONO):
            try:
                webview.start(preparar, debug=debug, icon=ICONO)
            except TypeError:              # versiones sin soporte de icono
                webview.start(preparar, debug=debug)
        else:
            webview.start(preparar, debug=debug)
    except Exception as exc:
        # el motor de ventana esta pero no arranca (falta WebView2, sin sesion
        # grafica...): mejor el navegador que dejar al usuario sin herramienta
        fallo(f"la ventana ({motor}) no se pudo abrir", exc)
        servidor = estado.get("servidor")
        if servidor is None:
            return _por_navegador(url, host, port, True, motor)
        print(f"No se ha podido abrir la ventana ({exc}); uso el navegador.")
        import webbrowser
        webbrowser.open(url)
        _mantener_vivo(url)
    finally:
        servidor = estado.get("servidor")
        if servidor is not None:
            servidor.should_exit = True

    paso("ventana cerrada")
    return FALLO_AVISADO if estado["error"] else OK


def _por_navegador(url: str, host: str, port: int,
                   forzar: bool, motor: str) -> int:
    """Ultimo recurso: servir la interfaz en el navegador del sistema."""
    servidor, _hilo = _arrancar_servidor(host, port)
    if not _esperar(url, servidor):
        fallo("el servidor interno no arranco (modo navegador)")
        servidor.should_exit = True
        return FALLO_MUDO

    if not forzar:
        print(f"Sin ventana de escritorio ({motor}); abriendo el navegador.")
        print("Para tener ventana propia instala WebKitGTK o Qt "
              "(ver README, apartado Instalacion).")
    import webbrowser
    webbrowser.open(url)
    _mantener_vivo(url)
    servidor.should_exit = True
    return OK
