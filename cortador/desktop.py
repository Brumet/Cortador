"""Cortador como aplicacion de escritorio.

Abre una ventana propia del sistema (no el navegador). Por dentro sigue
sirviendo la misma interfaz en un servidor local que solo escucha en
127.0.0.1, pero el usuario ve una ventana normal, con su icono y su barra de
titulo, sin barra de direcciones ni pestanas.

Se intenta por este orden, y cada intento queda escrito en el registro:

1. **Edge (o Chrome) en modo aplicacion**: una ventana normal, sin barra de
   direcciones ni pestanas. Es lo mas fiable en Windows porque Edge esta en
   todos los equipos y no depende de pywebview ni de pythonnet, que es lo que
   fallaba.
2. **Ventana nativa con pywebview** (WebView2 en Windows, WebKitGTK o Qt en
   Linux), si el paso anterior no puede.
3. **El navegador de siempre**, como ultimo recurso, para que la herramienta
   nunca se quede sin arrancar.

La ventana aparece *antes* de cargar el motor de corte, con una pantalla de
espera: asi al hacer doble clic se ve algo enseguida. Si algo falla, el
motivo se ve en la propia ventana y queda escrito en el registro.

Se puede forzar cualquiera de los tres modos con
CORTADOR_VENTANA=app|nativa|navegador.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from typing import Optional, Tuple

from . import ventana as ventana_app
from .registro import fallo, paso, ruta as ruta_registro

TITULO = "Cortador  ·  by Brumet"
ANCHO, ALTO = 1440, 900

ICONO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "packaging", "cortador.png")

# codigos de salida de run(): 0 bien, 1 fallo ya avisado en pantalla,
# 2 fallo sin avisar (quien llama debe mostrarlo)
OK, FALLO_AVISADO, FALLO_MUDO = 0, 1, 2


def backend_disponible() -> Tuple[bool, str]:
    """Comprueba si hay motor de ventana nativa y devuelve (hay, nombre o motivo)."""
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


def _esperar(url: str, servidor, segundos: float = 90.0) -> bool:
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


class _Motor:
    """El servidor interno: se arranca una sola vez, lo use quien lo use."""

    def __init__(self, host: str, port: int, url: str):
        self.host, self.port, self.url = host, port, url
        self.servidor = None
        self.listo: Optional[bool] = None

    def asegurar(self) -> bool:
        """Arranca el servidor si hace falta y espera a que conteste."""
        if self.listo is not None:
            return self.listo
        try:
            paso("arrancando el servidor interno")
            self.servidor, _hilo = _arrancar_servidor(self.host, self.port)
            self.listo = _esperar(self.url, self.servidor)
            if self.listo:
                paso("servidor listo")
            else:
                fallo("el servidor interno no ha contestado")
        except Exception as exc:
            fallo("el servidor interno no ha podido arrancar", exc)
            self.listo = False
        return self.listo

    def apagar(self) -> None:
        if self.servidor is not None:
            self.servidor.should_exit = True


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
       Suele ser el antivirus o el cortafuegos bloqueando 127.0.0.1. Cierra y
       vuelve a abrir; si sigue igual, manda este archivo de registro y lo
       miramos:</p>
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

    modo = (os.environ.get("CORTADOR_VENTANA") or "").strip().lower()
    if forzar_navegador:
        modo = "navegador"
    paso(f"modo de ventana: {modo or 'automatico'}")

    motor = _Motor(host, port, url)
    try:
        if modo in ("", "app", "edge", "chrome"):
            codigo = _ventana_de_aplicacion(motor)
            if codigo is not None:
                return codigo
            paso("sin ventana de aplicacion: pruebo la ventana nativa")

        if modo in ("", "app", "edge", "chrome", "nativa", "webview"):
            hay, nombre = backend_disponible()
            paso(f"ventana nativa: {nombre}" if hay
                 else f"sin ventana nativa: {nombre}")
            if hay:
                return _con_ventana(motor, nombre, debug)

        return _por_navegador(motor, modo == "navegador")
    finally:
        motor.apagar()


def _ventana_de_aplicacion(motor: _Motor):
    """Edge/Chrome en modo aplicacion. Devuelve None si no se puede usar."""
    espera = None
    try:
        espera = ventana_app.escribir_espera(motor.url, ruta_registro())
    except Exception as exc:
        fallo("no se pudo escribir la pagina de espera", exc)

    destino = motor.url
    if espera:
        destino = "file:///" + espera.replace("\\", "/").lstrip("/")

    proceso = ventana_app.abrir(destino)
    if proceso is None:
        return None

    abierta = time.time()
    motor.asegurar()
    try:
        proceso.wait()
    except KeyboardInterrupt:
        pass
    duracion = time.time() - abierta
    paso(f"ventana de aplicacion cerrada tras {duracion:.1f}s")

    if duracion < 3.0 and not motor.listo:
        # se cerro al instante y encima no hay servidor: no ha servido de nada
        return None
    if not motor.listo:
        return FALLO_AVISADO   # la pagina de espera lo ha dicho en pantalla
    return OK


def _con_ventana(motor: _Motor, nombre: str, debug: bool) -> int:
    """Ventana nativa de pywebview: se abre ya, y el servidor va por detras."""
    import webview

    estado = {"error": ""}

    paso(f"creando la ventana nativa ({nombre})")
    ventana = webview.create_window(
        TITULO, html=_HTML_ESPERA,
        width=ANCHO, height=ALTO, min_size=(1024, 700),
        background_color="#0b0b0d", confirm_close=False, text_select=True,
    )

    def preparar() -> None:
        try:
            if not motor.asegurar():
                raise RuntimeError("El servidor interno no ha respondido.")
            paso("cargando la interfaz en la ventana")
            ventana.load_url(motor.url)
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
        fallo(f"la ventana nativa ({nombre}) no se pudo abrir", exc)
        return _por_navegador(motor, True)

    paso("ventana cerrada")
    return FALLO_AVISADO if estado["error"] else OK


def _por_navegador(motor: _Motor, forzado: bool) -> int:
    """Ultimo recurso: servir la interfaz en el navegador del sistema."""
    if not motor.asegurar():
        return FALLO_MUDO

    if not forzado:
        print("Sin ventana propia; abriendo el navegador.")
    import webbrowser
    webbrowser.open(motor.url)
    _mantener_vivo(motor.url)
    return OK
