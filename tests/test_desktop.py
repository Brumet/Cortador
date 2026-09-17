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
