"""El arranque siempre debe dejar rastro: sin esto, un fallo no se ve."""

import importlib
import os
import sys


def _recargar(monkeypatch, tmp_path):
    """Modulo de registro apuntando a una carpeta de usuario de mentira."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    from cortador import registro
    importlib.reload(registro)
    return registro


def test_escribe_los_pasos_del_arranque(monkeypatch, tmp_path):
    registro = _recargar(monkeypatch, tmp_path)
    salida, error = sys.stdout, sys.stderr
    try:
        destino = registro.iniciar()
        registro.paso("probando")
        registro.fallo("algo se rompio", RuntimeError("motivo"))
    finally:
        registro.cerrar()
        sys.stdout, sys.stderr = salida, error

    assert destino and os.path.exists(destino)
    texto = open(destino, encoding="utf-8").read()
    assert "arranque del" in texto
    assert "probando" in texto
    assert "ERROR · algo se rompio" in texto
    assert "RuntimeError: motivo" in texto


def test_la_carpeta_queda_dentro_del_usuario(monkeypatch, tmp_path):
    registro = _recargar(monkeypatch, tmp_path)
    assert str(tmp_path) in registro.carpeta_datos()
    assert registro.ruta().endswith(registro.NOMBRE)


def test_imprimir_sin_consola_no_revienta(monkeypatch, tmp_path):
    """PyInstaller deja stdout en None: un print de cualquier libreria mataba la app."""
    registro = _recargar(monkeypatch, tmp_path)
    salida, error = sys.stdout, sys.stderr
    try:
        sys.stdout = None
        sys.stderr = None
        destino = registro.iniciar()
        print("hola sin consola")
        print("y un error", file=sys.stderr)
    finally:
        registro.cerrar()
        sys.stdout, sys.stderr = salida, error

    texto = open(destino, encoding="utf-8").read()
    assert "hola sin consola" in texto
    assert "y un error" in texto


def test_el_registro_no_crece_sin_fin(monkeypatch, tmp_path):
    registro = _recargar(monkeypatch, tmp_path)
    destino = os.path.join(registro.carpeta_datos(), registro.NOMBRE)
    with open(destino, "w", encoding="utf-8") as fh:
        fh.write("x" * (registro.LIMITE + 10))
    salida, error = sys.stdout, sys.stderr
    try:
        registro.iniciar()
    finally:
        registro.cerrar()
        sys.stdout, sys.stderr = salida, error
    assert os.path.getsize(destino) < registro.LIMITE
    assert os.path.exists(destino + ".anterior")
