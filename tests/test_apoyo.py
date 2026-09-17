"""La propina es opcional y no puede estorbar a quien no le interesa."""

import json
import os

import pytest

from cortador import apoyo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESTATICOS = os.path.join(RAIZ, "cortador", "web", "static")


def test_de_fabrica_no_se_pide_nada():
    """Sin canales configurados, la app no menciona el dinero en ningun sitio."""
    assert apoyo.CANALES == []
    assert apoyo.hay_apoyo() is False


def test_descarta_lo_que_esta_mal_puesto(monkeypatch):
    monkeypatch.setattr(apoyo, "CANALES", [
        {"nombre": "Nequi", "tipo": "copiar", "valor": "300 123 4567",
         "nota": "a nombre de Brumet"},
        {"nombre": "PayPal", "tipo": "enlace", "valor": "https://paypal.me/ejemplo"},
        {"nombre": "Sin valor", "tipo": "enlace", "valor": ""},
        {"nombre": "Tipo raro", "tipo": "telepatia", "valor": "algo"},
        {"nombre": "Enlace falso", "tipo": "enlace", "valor": "javascript:alert(1)"},
    ])
    nombres = [c["nombre"] for c in apoyo.canales()]
    assert nombres == ["Nequi", "PayPal"]


def test_la_api_lo_cuenta_tal_cual(monkeypatch):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from cortador.web.server import create_app

    cliente = fastapi_testclient.TestClient(create_app())

    datos = cliente.get("/api/apoyo").json()
    assert datos == {"hay": False, "mensaje": "", "canales": []}

    monkeypatch.setattr(apoyo, "CANALES", [
        {"nombre": "Ko-fi", "tipo": "enlace", "valor": "https://ko-fi.com/ejemplo"}])
    datos = cliente.get("/api/apoyo").json()
    assert datos["hay"] is True and datos["mensaje"]
    assert datos["canales"][0]["nombre"] == "Ko-fi"


def test_la_interfaz_lo_esconde_hasta_que_haya_algo():
    html = open(os.path.join(ESTATICOS, "index.html"), encoding="utf-8").read()
    assert 'id="btn-apoyo"' in html and "hidden" in html
    js = open(os.path.join(ESTATICOS, "app.js"), encoding="utf-8").read()
    assert "if (!d.hay) return;" in js
    assert "boton.hidden = false" in js


def test_los_enlaces_salen_al_navegador_del_sistema():
    """En la app de escritorio, una propina no puede abrirse dentro de la ventana."""
    main_js = open(os.path.join(RAIZ, "escritorio", "main.js"), encoding="utf-8").read()
    assert "setWindowOpenHandler" in main_js and "openExternal" in main_js
    assert "esInterno" in main_js
