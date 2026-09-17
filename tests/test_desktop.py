import threading
import time
import urllib.request

import pytest

from cortador import desktop


def test_backend_devuelve_motivo():
    hay, texto = desktop.backend_disponible()
    assert isinstance(hay, bool)
    assert isinstance(texto, str) and texto


def test_el_servidor_interno_arranca_y_responde():
    from cortador.web.server import free_port
    puerto = free_port("127.0.0.1", 8931)
    servidor, hilo = desktop._arrancar_servidor("127.0.0.1", puerto)
    url = f"http://127.0.0.1:{puerto}/"
    try:
        assert desktop._esperar(url, servidor, segundos=25)
        with urllib.request.urlopen(url, timeout=5) as r:
            assert b"Cortador" in r.read()
    finally:
        servidor.should_exit = True
        hilo.join(timeout=10)


def test_esperar_se_rinde_si_no_hay_servidor():
    class Falso:
        started = False
    assert desktop._esperar("http://127.0.0.1:9/", Falso(), segundos=0.5) is False


def test_el_servidor_no_usa_el_logging_de_uvicorn():
    """El dictConfig de uvicorn no sobrevive al empaquetado: no debe usarse."""
    import inspect

    from cortador import desktop
    from cortador.web import server

    assert "log_config=None" in inspect.getsource(desktop._arrancar_servidor)
    assert "log_config=None" in inspect.getsource(server.run)


def test_arranca_sin_configurar_el_logging(tmp_path):
    """Comprobacion de verdad: levantar el servidor como lo hace el ejecutable."""
    import urllib.request

    from cortador.web.server import free_port
    puerto = free_port("127.0.0.1", 8941)
    servidor, hilo = desktop._arrancar_servidor("127.0.0.1", puerto)
    try:
        assert desktop._esperar(f"http://127.0.0.1:{puerto}/", servidor, segundos=25)
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/version", timeout=5) as r:
            assert b"version" in r.read()
    finally:
        servidor.should_exit = True
        hilo.join(timeout=10)


def test_si_la_ventana_falla_se_abre_el_navegador(monkeypatch):
    """Sin WebView2 no se puede abrir ventana: no dejar al usuario sin app."""
    import sys
    import types

    from cortador.web.server import free_port

    falso = types.ModuleType("webview")
    falso.create_window = lambda *a, **k: None

    def revienta(*a, **k):
        raise RuntimeError("WebView2 no esta instalado")

    falso.start = revienta
    monkeypatch.setitem(sys.modules, "webview", falso)
    monkeypatch.setattr(desktop, "backend_disponible", lambda: (True, "WebView2"))

    abierto = {}
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda url: abierto.setdefault("url", url))

    # que no se quede esperando para siempre en el bucle del navegador
    monkeypatch.setattr(desktop, "_mantener_vivo", lambda url: None)

    puerto = free_port("127.0.0.1", 8951)
    assert desktop.run(port=puerto) == 0
    assert abierto.get("url", "").endswith(f":{puerto}/")


def test_la_ventana_aparece_antes_que_el_servidor(monkeypatch):
    """Doble clic -> ventana con pantalla de espera ya, servidor por detras."""
    import sys
    import types

    orden = []

    class VentanaFalsa:
        def __init__(self):
            self.url = ""

        def load_url(self, url):
            orden.append("cargar")
            self.url = url

        def load_html(self, html):
            orden.append("html")

    ventana = VentanaFalsa()
    falso = types.ModuleType("webview")

    def crear(titulo, html=None, **kwargs):
        orden.append("ventana")
        assert html and "Preparando" in html
        return ventana

    def arrancar(func=None, **kwargs):
        orden.append("start")
        if func is not None:
            func()

    falso.create_window = crear
    falso.start = arrancar
    monkeypatch.setitem(sys.modules, "webview", falso)
    monkeypatch.setattr(desktop, "backend_disponible", lambda: (True, "WebView2"))

    puerto = desktop.puerto_libre("127.0.0.1", 8961)
    assert desktop.run(port=puerto) == desktop.OK
    assert orden[0] == "ventana" and orden.index("ventana") < orden.index("cargar")
    assert ventana.url.endswith(f":{puerto}/")


def test_si_el_servidor_no_responde_se_ve_en_la_ventana(monkeypatch):
    """Nunca cerrarse en silencio: el motivo se muestra y se registra."""
    import sys
    import types

    visto = {}

    class VentanaFalsa:
        def load_url(self, url):
            raise AssertionError("no deberia cargar la interfaz")

        def load_html(self, html):
            visto["html"] = html

    falso = types.ModuleType("webview")
    falso.create_window = lambda *a, **k: VentanaFalsa()
    falso.start = lambda func=None, **k: func() if func else None
    monkeypatch.setitem(sys.modules, "webview", falso)
    monkeypatch.setattr(desktop, "backend_disponible", lambda: (True, "WebView2"))
    monkeypatch.setattr(desktop, "_esperar", lambda *a, **k: False)

    puerto = desktop.puerto_libre("127.0.0.1", 8971)
    assert desktop.run(port=puerto) == desktop.FALLO_AVISADO
    assert "No he podido arrancar" in visto.get("html", "")
    assert "arranque.log" in visto["html"]


def test_sin_ventana_y_sin_servidor_avisa_quien_llama(monkeypatch):
    """Modo navegador: si el servidor no levanta, hay que decirlo fuera."""
    monkeypatch.setattr(desktop, "backend_disponible",
                        lambda: (False, "sin motor"))
    monkeypatch.setattr(desktop, "_esperar", lambda *a, **k: False)
    monkeypatch.setattr(desktop, "_mantener_vivo", lambda url: None)

    puerto = desktop.puerto_libre("127.0.0.1", 8981)
    assert desktop.run(port=puerto) == desktop.FALLO_MUDO
