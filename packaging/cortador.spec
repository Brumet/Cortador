# -*- mode: python ; coding: utf-8 -*-
"""Receta de PyInstaller para el ejecutable de escritorio de Cortador.

    pyinstaller packaging/cortador.spec --noconfirm

Dos formas de empaquetar, segun la variable de entorno CORTADOR_MODO:

  archivo (por defecto)  un unico .exe portable (dist/Cortador.exe). Comodo
                         de mandar, pero cada vez que se abre descomprime
                         ~70 MB en la carpeta temporal y tarda.
  carpeta                una carpeta con todo dentro (dist/Cortador/). Arranca
                         en un segundo; es lo que instala el instalador.

Ninguna de las dos necesita Python ni conexion a internet.
"""

import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files

raiz = os.path.abspath(os.getcwd())
es_windows = sys.platform.startswith("win")

datas = [(os.path.join(raiz, "cortador", "web", "static"), "cortador/web/static"),
         (os.path.join(raiz, "packaging", "cortador.png"), "packaging"),
         (os.path.join(raiz, "packaging", "cortador.ico"), "packaging")]
binaries = []
hiddenimports = [
    "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on", "uvicorn.lifespan.off",
    "anyio", "h11", "multipart", "python_multipart",
    "click", "colorama", "logging.config", "logging.handlers",
    "manifold3d", "mapbox_earcut", "rtree", "scipy.spatial", "scipy.sparse.csgraph",
]

if es_windows:
    # la ventana de escritorio usa WebView2 a traves de WinForms, y eso pasa
    # por pythonnet: sin estos modulos pywebview no encuentra motor y la app
    # termina abriendose en el navegador
    hiddenimports += [
        "clr", "clr_loader", "pythonnet",
        "webview.platforms.winforms", "webview.platforms.edgechromium",
    ]
    for paquete in ("clr_loader", "pythonnet"):
        try:
            extra_datas, extra_binaries, extra_hidden = collect_all(paquete)
            datas += extra_datas
            binaries += extra_binaries
            hiddenimports += extra_hidden
        except Exception:
            pass

for paquete in ("trimesh", "shapely", "fastapi", "starlette", "pydantic", "webview"):
    try:
        paquete_datas, paquete_binaries, paquete_hidden = collect_all(paquete)
        datas += paquete_datas
        binaries += paquete_binaries
        hiddenimports += paquete_hidden
    except Exception:
        pass

icono = os.path.join(raiz, "packaging",
                     "cortador.ico" if es_windows else "cortador.png")

a = Analysis(
    [os.path.join(raiz, "packaging", "launcher.py")],
    pathex=[raiz],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PySide2", "IPython", "pytest",
              "playwright", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)

modo = (os.environ.get("CORTADOR_MODO") or "archivo").strip().lower()
una_pieza = modo not in ("carpeta", "onedir", "dir")

comunes = dict(
    name="Cortador",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,   # aplicacion de escritorio: sin ventana negra de consola
    disable_windowed_traceback=False,
    icon=icono if os.path.exists(icono) else None,
)

if una_pieza:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **comunes)
else:
    # la version que se instala: el .exe queda al lado de sus archivos, asi
    # no hay que descomprimir nada en cada arranque
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **comunes)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
                   name="Cortador")
