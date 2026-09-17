"""Arma el motor de Cortador con el Python oficial embebido (sin PyInstaller).

    python packaging/motor_embebido.py

Deja en `escritorio/motor/` un interprete de python.org (firmado por la Python
Software Foundation) con el paquete `cortador` y todas sus librerias dentro.
La aplicacion de escritorio (Electron) lo lanza como proceso hijo.

Se hace asi a proposito: un ejecutable de PyInstaller es un binario opaco que
algunos antivirus paran sin decir nada, y ese es justo el fallo que estabamos
persiguiendo. Aqui lo que se ejecuta es el python.exe oficial.
"""

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(RAIZ, "escritorio", "motor")
VERSION_PYTHON = "3.11.9"
URL = (f"https://www.python.org/ftp/python/{VERSION_PYTHON}/"
       f"python-{VERSION_PYTHON}-embed-amd64.zip")


def descargar(destino_zip: str) -> None:
    if os.path.exists(destino_zip):
        print(f"ya descargado: {destino_zip}")
        return
    print(f"descargando {URL}")
    urllib.request.urlretrieve(URL, destino_zip)


def preparar_interprete(zip_local: str) -> None:
    if os.path.isdir(DESTINO):
        shutil.rmtree(DESTINO)
    os.makedirs(DESTINO, exist_ok=True)
    with zipfile.ZipFile(zip_local) as z:
        z.extractall(DESTINO)

    # el interprete embebido ignora site-packages hasta que se le dice
    for nombre in os.listdir(DESTINO):
        if nombre.endswith("._pth"):
            ruta = os.path.join(DESTINO, nombre)
            with open(ruta, "w", encoding="utf-8") as fh:
                fh.write(os.path.splitext(nombre)[0] + ".zip\n")   # python311.zip
                fh.write(".\n")
                fh.write("Lib\\site-packages\n")
                fh.write("import site\n")
            print(f"ajustado {nombre}")


def instalar_librerias() -> None:
    paquetes = os.path.join(DESTINO, "Lib", "site-packages")
    os.makedirs(paquetes, exist_ok=True)
    orden = [sys.executable, "-m", "pip", "install", "--no-compile",
             "--target", paquetes, f"{RAIZ}[web]"]
    print(" ".join(orden))
    subprocess.check_call(orden)


def comprobar() -> None:
    exe = os.path.join(DESTINO, "python.exe")
    if not os.path.exists(exe):
        exe = os.path.join(DESTINO, "bin", "python3")
    orden = [exe, "-c",
             "import cortador, trimesh, shapely, manifold3d, fastapi, uvicorn;"
             "from cortador.web.server import create_app; create_app();"
             "print('motor listo', cortador.__version__)"]
    print(" ".join(orden))
    subprocess.check_call(orden)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", default=os.path.join(RAIZ, "build",
                                                      f"python-{VERSION_PYTHON}-embed.zip"))
    args = parser.parse_args()

    if not sys.platform.startswith("win"):
        print("Este motor embebido es para Windows: en Linux y macOS la app usa "
              "el Python del sistema.", file=sys.stderr)
        return 2

    os.makedirs(os.path.dirname(args.zip), exist_ok=True)
    descargar(args.zip)
    preparar_interprete(args.zip)
    instalar_librerias()
    comprobar()
    tam = sum(os.path.getsize(os.path.join(base, f))
              for base, _d, fs_ in os.walk(DESTINO) for f in fs_)
    print(f"\nMotor listo en {DESTINO} ({tam / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
