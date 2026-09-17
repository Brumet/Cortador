"""Construye el ejecutable de escritorio de Cortador.

    python packaging/construir.py             un solo archivo portable
    python packaging/construir.py --carpeta   carpeta completa (arranca antes)

Deja el resultado en dist/Cortador (o dist/Cortador.exe en Windows) en el
primer caso, y en dist/Cortador/ en el segundo, que es lo que empaqueta el
instalador de Windows.
Hay que ejecutarlo en el sistema operativo de destino: PyInstaller no hace
compilacion cruzada.
"""

import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    os.chdir(RAIZ)
    carpeta = any(a.strip("-/").lower() in ("carpeta", "onedir", "dir")
                  for a in sys.argv[1:])
    os.environ["CORTADOR_MODO"] = "carpeta" if carpeta else "archivo"
    print(f"Modo de empaquetado: {os.environ['CORTADOR_MODO']}")
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Instalando PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    orden = [sys.executable, "-m", "PyInstaller",
             os.path.join("packaging", "cortador.spec"), "--noconfirm", "--clean"]
    print(" ".join(orden))
    codigo = subprocess.call(orden)
    if codigo == 0:
        salida = os.path.join(RAIZ, "dist")
        print(f"\nListo. El ejecutable esta en: {salida}")
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
