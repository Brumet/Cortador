"""Punto de entrada del ejecutable de escritorio de Cortador.

PyInstaller empaqueta esto: al abrirlo levanta el servidor local y abre el
navegador. No necesita Python instalado ni conexion a internet.
"""

import multiprocessing
import os
import sys


def main() -> None:
    multiprocessing.freeze_support()
    if any(a in ("--comprobar", "--check", "--version") for a in sys.argv[1:]):
        # lo usa la compilacion automatica para verificar que el binario arranca
        from cortador import __version__
        from cortador.web.server import create_app
        create_app()
        print(f"Cortador {__version__} listo")
        return
    os.environ.setdefault("CORTADOR_EMPAQUETADO", "1")
    from cortador.desktop import run
    try:
        run(host="127.0.0.1", port=8000)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # sin consola visible: dejar rastro y avisar
        _reportar(exc)
        sys.exit(1)


def _reportar(exc: Exception) -> None:
    import traceback
    mensaje = f"Cortador no ha podido arrancar:\n\n{exc}"
    try:
        destino = os.path.join(os.path.dirname(sys.executable), "cortador_error.log")
        with open(destino, "w", encoding="utf-8") as fh:
            fh.write(traceback.format_exc())
        mensaje += f"\n\nDetalles en:\n{destino}"
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, mensaje, "Cortador", 0x10)
    except Exception:
        print(mensaje)


if __name__ == "__main__":
    main()
