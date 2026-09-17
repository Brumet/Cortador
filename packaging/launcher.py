"""Punto de entrada del ejecutable de escritorio de Cortador.

PyInstaller empaqueta esto: al abrirlo levanta el servidor local y abre el
navegador. No necesita Python instalado ni conexion a internet.
"""

import multiprocessing
import os
import sys


def _opciones() -> set:
    """Argumentos normalizados: tolera guiones raros, barras y mayusculas.

    Al copiar un comando desde el chat o desde la web, los guiones se cuelan a
    veces como guion largo y entonces la opcion no se reconocia y el programa
    arrancaba normal, que es justo lo que confunde.
    """
    limpios = set()
    for bruto in sys.argv[1:]:
        arg = bruto.strip().lower()
        for raro in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212"):
            arg = arg.replace(raro, "-")
        limpios.add(arg.lstrip("-/"))
    return limpios


def main() -> None:
    multiprocessing.freeze_support()
    opciones = _opciones()
    if opciones & {"diagnostico", "diagnose", "d"}:
        _diagnostico()
        return
    if opciones & {"navegador", "browser"}:
        os.environ["CORTADOR_NAVEGADOR"] = "1"
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
        run(host="127.0.0.1", port=8000,
            forzar_navegador=bool(os.environ.get("CORTADOR_NAVEGADOR")))
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # sin consola visible: dejar rastro y avisar
        _reportar(exc)
        sys.exit(1)


def _diagnostico() -> None:
    """Informe de por que puede no arrancar, para poder pegarlo tal cual."""
    import importlib
    import platform

    lineas = ["Cortador - diagnostico", "=" * 40]
    try:
        from cortador import __version__
        lineas.append(f"version        : {__version__}")
    except Exception as exc:
        lineas.append(f"version        : ERROR {exc}")
    lineas.append(f"sistema        : {platform.platform()}")
    lineas.append(f"python         : {sys.version.split()[0]}")
    lineas.append(f"empaquetado    : {getattr(sys, 'frozen', False)}")

    for modulo in ("trimesh", "shapely", "manifold3d", "numpy", "scipy", "rtree",
                   "fastapi", "uvicorn", "click", "webview"):
        try:
            importlib.import_module(modulo)
            lineas.append(f"  {modulo:12s} ok")
        except Exception as exc:
            lineas.append(f"  {modulo:12s} FALTA ({exc})")

    try:
        from cortador.desktop import backend_disponible
        hay, motor = backend_disponible()
        lineas.append(f"ventana        : {'si' if hay else 'no'} ({motor})")
    except Exception as exc:
        lineas.append(f"ventana        : ERROR {exc}")

    try:
        from cortador.web.server import create_app, free_port
        create_app()
        lineas.append("servidor       : se crea bien")
        lineas.append(f"puerto libre   : {free_port('127.0.0.1', 8000)}")
    except Exception as exc:
        lineas.append(f"servidor       : ERROR {exc}")

    texto = "\n".join(lineas)
    print(texto)
    try:
        destino = os.path.join(os.path.dirname(sys.executable), "cortador_diagnostico.txt")
        with open(destino, "w", encoding="utf-8") as fh:
            fh.write(texto + "\n")
        print(f"\nGuardado en {destino}")
    except Exception:
        pass


def _reportar(exc: Exception) -> None:
    import traceback
    mensaje = (f"Cortador no ha podido arrancar:\n\n{type(exc).__name__}: {exc}\n\n"
               "Ejecutalo con  --diagnostico  desde la consola para un informe "
               "completo, o manda el archivo de detalles.")
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
