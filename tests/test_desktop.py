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
