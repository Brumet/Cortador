"""El ejecutable no puede cerrarse sin decir por que."""

import importlib.util
import os
import sys

import pytest

RUTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "packaging", "launcher.py")


@pytest.fixture()
def launcher(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location("cortador_launcher", RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_normaliza_los_guiones_raros(launcher, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["Cortador.exe", "–diagnostico", "/Navegador"])
    assert launcher._opciones() == {"diagnostico", "navegador"}


def test_avisa_si_el_servidor_no_arranca(launcher, monkeypatch):
    """El caso que dejaba al usuario mirando el escritorio sin nada."""
    from cortador import desktop

    avisos = []
    monkeypatch.setattr(sys, "argv", ["Cortador.exe"])
    monkeypatch.setattr(launcher, "_avisar", lambda mensaje: avisos.append(mensaje))
    monkeypatch.setattr(desktop, "run", lambda **k: desktop.FALLO_MUDO)

    with pytest.raises(SystemExit) as salida:
        launcher.main()

    assert salida.value.code == desktop.FALLO_MUDO
    assert avisos and "no ha podido arrancar" in avisos[0]


def test_avisa_si_algo_revienta(launcher, monkeypatch):
    from cortador import desktop

    avisos = []

    def revienta(**kwargs):
        raise RuntimeError("falta una libreria")

    monkeypatch.setattr(sys, "argv", ["Cortador.exe"])
    monkeypatch.setattr(launcher, "_avisar", lambda mensaje: avisos.append(mensaje))
    monkeypatch.setattr(desktop, "run", revienta)

    with pytest.raises(SystemExit):
        launcher.main()

    assert avisos and "falta una libreria" in avisos[0]


def test_el_arranque_queda_registrado(launcher, monkeypatch, tmp_path):
    from cortador import desktop, registro

    monkeypatch.setattr(sys, "argv", ["Cortador.exe"])
    monkeypatch.setattr(desktop, "run", lambda **k: desktop.OK)
    salida, error = sys.stdout, sys.stderr
    try:
        launcher.main()
    finally:
        sys.stdout, sys.stderr = salida, error

    destino = registro.ruta()
    assert str(tmp_path) in destino and os.path.exists(destino)
    texto = open(destino, encoding="utf-8").read()
    assert "arrancando" in texto and "salida con codigo 0" in texto
