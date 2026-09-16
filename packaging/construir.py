"""Construye el ejecutable de escritorio de Cortador.

    python packaging/construir.py

Deja el resultado en dist/Cortador (o dist/Cortador.exe en Windows).
Hay que ejecutarlo en el sistema operativo de destino: PyInstaller no hace
compilacion cruzada.
"""

import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    os.chdir(RAIZ)
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
