# -*- mode: python ; coding: utf-8 -*-
"""Receta de PyInstaller para el ejecutable de escritorio de Cortador.

    pyinstaller packaging/cortador.spec --noconfirm

Genera un unico archivo que no necesita Python ni conexion a internet.
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
    "manifold3d", "mapbox_earcut", "rtree", "scipy.spatial", "scipy.sparse.csgraph",
]

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

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="Cortador",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,   # aplicacion de escritorio: sin ventana negra de consola
    disable_windowed_traceback=False,
    icon=icono if os.path.exists(icono) else None,
)
