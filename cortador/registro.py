"""Registro de arranque: la app nunca debe fallar en silencio.

Cuando Cortador se abre desde su icono no hay consola: si algo sale mal, el
proceso se cierra y el usuario no ve nada. Este modulo deja siempre un
archivo de texto con cada paso del arranque, y ademas captura lo que se
imprima por pantalla para que acabe ahi en vez de perderse.

El archivo vive en:

    Windows : %LOCALAPPDATA%\\Cortador\\arranque.log
    Linux   : ~/.local/share/Cortador/arranque.log
    macOS   : ~/Library/Logs/Cortador/arranque.log
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from typing import Optional, TextIO

NOMBRE = "arranque.log"
LIMITE = 256 * 1024          # el registro se recorta para que no crezca sin fin

_archivo: Optional[TextIO] = None
_ruta: str = ""
_inicio: float = time.time()


def carpeta_datos() -> str:
    """Carpeta de datos de la app en este sistema (se crea si hace falta)."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        destino = os.path.join(base, "Cortador")
    elif sys.platform == "darwin":
        destino = os.path.expanduser("~/Library/Logs/Cortador")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        destino = os.path.join(base, "Cortador")
    try:
        os.makedirs(destino, exist_ok=True)
    except Exception:
        destino = os.path.expanduser("~")
    return destino


def ruta() -> str:
    """Ruta del registro (aunque todavia no se haya abierto)."""
    return _ruta or os.path.join(carpeta_datos(), NOMBRE)


def iniciar(capturar_salida: bool = True) -> str:
    """Abre el registro y escribe la cabecera. Se puede llamar dos veces."""
    global _archivo, _ruta, _inicio
    if _archivo is not None:
        return _ruta

    _inicio = time.time()
    destino = os.path.join(carpeta_datos(), NOMBRE)
    try:
        if os.path.exists(destino) and os.path.getsize(destino) > LIMITE:
            os.replace(destino, destino + ".anterior")
    except Exception:
        pass
    try:
        _archivo = open(destino, "a", encoding="utf-8", errors="replace")
        _ruta = destino
    except Exception:
        _archivo = None
        _ruta = ""
        return ""

    import platform
    cabecera = time.strftime("%Y-%m-%d %H:%M:%S")
    _escribir(f"\n===== Cortador · arranque del {cabecera} =====")
    try:
        from . import __version__
        paso(f"version {__version__}")
    except Exception:
        pass
    paso(f"sistema {platform.platform()}")
    paso(f"python {sys.version.split()[0]} · empaquetado={getattr(sys, 'frozen', False)}")
    paso(f"ejecutable {sys.executable}")

    if capturar_salida:
        _capturar_salida()
    return _ruta


def paso(texto: str) -> None:
    """Anota un paso del arranque con el tiempo transcurrido."""
    _escribir(f"[{time.time() - _inicio:6.2f}s] {texto}")


def fallo(texto: str, exc: BaseException | None = None) -> None:
    """Anota un error con su traza completa."""
    paso(f"ERROR · {texto}")
    if exc is not None:
        detalle = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        _escribir(detalle.rstrip())


def cerrar() -> None:
    global _archivo
    if _archivo is not None:
        try:
            paso("fin")
            _archivo.close()
        except Exception:
            pass
        _archivo = None


def _escribir(linea: str) -> None:
    if _archivo is None:
        return
    try:
        _archivo.write(linea + "\n")
        _archivo.flush()
    except Exception:
        pass


class _Eco:
    """Sustituto de stdout/stderr que escribe en el registro.

    En una app de ventana PyInstaller deja `sys.stdout` en None: cualquier
    `print` de una libreria revienta con AttributeError y tumba el arranque
    sin decir nada. Con esto, ademas de no reventar, queda registrado.
    """

    def __init__(self, etiqueta: str, original=None):
        self.etiqueta = etiqueta
        self.original = original
        self._resto = ""

    def write(self, texto) -> int:
        if not isinstance(texto, str):
            texto = str(texto)
        if self.original is not None:
            try:
                self.original.write(texto)
            except Exception:
                self.original = None
        self._resto += texto
        while "\n" in self._resto:
            linea, self._resto = self._resto.split("\n", 1)
            if linea.strip():
                _escribir(f"    {self.etiqueta}| {linea.rstrip()}")
        return len(texto)

    def flush(self) -> None:
        if self.original is not None:
            try:
                self.original.flush()
            except Exception:
                self.original = None

    def isatty(self) -> bool:
        return False

    def fileno(self):
        if self.original is not None and hasattr(self.original, "fileno"):
            return self.original.fileno()
        raise OSError("sin descriptor de archivo")

    @property
    def encoding(self) -> str:
        return "utf-8"

    def writelines(self, lineas) -> None:
        for linea in lineas:
            self.write(linea)

    def close(self) -> None:
        self.flush()


def _capturar_salida() -> None:
    sys.stdout = _Eco("out", sys.stdout)
    sys.stderr = _Eco("err", sys.stderr)
