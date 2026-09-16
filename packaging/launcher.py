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
    from cortador.web.server import run
    try:
        run(host="127.0.0.1", port=8000, open_browser=True)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # que el usuario vea el error antes de cerrarse
        print(f"\nCortador no ha podido arrancar: {exc}\n")
        input("Pulsa Intro para cerrar...")
        sys.exit(1)


if __name__ == "__main__":
    main()
