"""Punto de entrada del ejecutable de escritorio de Cortador.

PyInstaller empaqueta esto: al abrirlo levanta el servidor local y abre la
ventana de la aplicacion. No necesita Python instalado ni conexion a internet.

Regla de oro de este archivo: la aplicacion nunca puede cerrarse sin decir
por que. Como no hay consola, todo el arranque queda escrito en el registro
(%LOCALAPPDATA%\\Cortador\\arranque.log) y cualquier fallo se muestra ademas
en un aviso del sistema.
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
        for raro in ("‐", "‑", "‒", "–", "—", "−"):
            arg = arg.replace(raro, "-")
        limpios.add(arg.lstrip("-/"))
    return limpios


def main() -> None:
    multiprocessing.freeze_support()
    opciones = _opciones()

    registro = ""
    try:
        from cortador.registro import cerrar, fallo, iniciar, paso, ruta
        registro = iniciar()
    except Exception:   # sin registro se sigue, pero avisando de lo que pase
        def paso(texto): pass
        def fallo(texto, exc=None): pass
        def cerrar(): pass
        def ruta(): return ""

    paso(f"argumentos {sys.argv[1:]}")

    if opciones & {"registro", "log"}:
        _mostrar_registro(registro or ruta())
        return
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
        print(f"registro       : {registro or ruta()}")
        return

    os.environ.setdefault("CORTADOR_EMPAQUETADO", "1")
    try:
        paso("cargando el modulo de escritorio")
        from cortador.desktop import FALLO_MUDO, run
        paso("arrancando")
        codigo = run(host="127.0.0.1", port=8000,
                     forzar_navegador=bool(os.environ.get("CORTADOR_NAVEGADOR")))
        paso(f"salida con codigo {codigo}")
        if codigo == FALLO_MUDO:
            _avisar("Cortador no ha podido arrancar su servidor interno.\n\n"
                    "Suele ser el antivirus o el cortafuegos bloqueando la "
                    "conexion local (127.0.0.1). Prueba a permitir Cortador y "
                    "vuelve a abrirlo.")
        if codigo:
            sys.exit(codigo)
    except KeyboardInterrupt:
        pass
    except SystemExit:
        raise
    except BaseException as exc:   # sin consola visible: dejar rastro y avisar
        fallo("arranque interrumpido", exc)
        _reportar(exc)
        sys.exit(1)
    finally:
        cerrar()


def _mostrar_registro(destino: str) -> None:
    """Abre el registro de arranque con el bloc de notas (o lo imprime)."""
    if destino and os.path.exists(destino):
        try:
            os.startfile(destino)      # type: ignore[attr-defined]
            return
        except Exception:
            pass
        try:
            with open(destino, encoding="utf-8", errors="replace") as fh:
                print(fh.read())
            return
        except Exception:
            pass
    _avisar(f"Todavia no hay registro de arranque en:\n{destino}")


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
    try:
        from cortador.registro import ruta
        lineas.append(f"registro       : {ruta()}")
    except Exception as exc:
        lineas.append(f"registro       : ERROR {exc}")

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

    lineas.append(f"webview2       : {_webview2()}")

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


def _webview2() -> str:
    """Version del runtime de WebView2 instalado en Windows, si lo hay."""
    if not sys.platform.startswith("win"):
        return "no aplica (no es Windows)"
    try:
        import winreg
    except Exception:
        return "desconocido"
    clave = (r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"
             r"\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}")
    for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for ruta_clave in (clave, clave.replace("WOW6432Node\\", "")):
            try:
                with winreg.OpenKey(raiz, ruta_clave) as k:
                    version, _ = winreg.QueryValueEx(k, "pv")
                    if version and version != "0.0.0.0":
                        return version
            except OSError:
                continue
    return "NO instalado (la ventana no podra abrirse)"


def _reportar(exc: BaseException) -> None:
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
        from cortador.registro import ruta
        mensaje += f"\n\nRegistro de arranque:\n{ruta()}"
    except Exception:
        pass
    _avisar(mensaje)


def _avisar(mensaje: str) -> None:
    """Aviso visible aunque no haya consola."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, mensaje, "Cortador", 0x10)
        return
    except Exception:
        pass
    try:
        print(mensaje)
    except Exception:
        pass


if __name__ == "__main__":
    main()
