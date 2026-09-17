"""Deja listas para la app las imagenes que salen de una IA.

    python herramientas/preparar_arte.py crudo/ --salida cortador/web/static

Lo que sale de Grok o de Gemini viene en vertical, pesado y con margenes:
no sirve tal cual. Esto hace el trabajo aburrido, siempre igual:

  esfera  -> matcap de 512x512 recortado al circulo, que es lo que come el
             visor 3D para sombrear las piezas
  fondo   -> JPEG de 1200 px de ancho, progresivo, por debajo de 150 KB

Adivina cual es cual mirando la imagen (una esfera es una mancha compacta y
centrada sobre un fondo liso), y se puede forzar con --tipo.

Necesita Pillow:  pip install pillow
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional, Tuple

try:
    import numpy as np
    from PIL import Image, ImageDraw
except ImportError:                                    # pragma: no cover
    print("Falta Pillow: pip install pillow numpy", file=sys.stderr)
    raise SystemExit(2)

EXTENSIONES = (".png", ".jpg", ".jpeg", ".webp")


def _mascara(im: "Image.Image") -> Tuple["np.ndarray", float]:
    """Pixeles que se salen del fondo, y el brillo del fondo."""
    a = np.asarray(im.convert("RGB")).astype(np.float32)
    lum = a @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    borde = np.concatenate([lum[:8].ravel(), lum[-8:].ravel(),
                            lum[:, :8].ravel(), lum[:, -8:].ravel()])
    fondo = float(np.median(borde))
    # con fondo oscuro la diferencia es pequena (una esfera negra sobre gris
    # muy oscuro): si se pide demasiado, la esfera no se encuentra
    umbral = 8.0 if fondo < 90 else 25.0
    return np.abs(lum - fondo) > umbral, fondo


def parece_esfera(im: "Image.Image") -> bool:
    """Una esfera ocupa una mancha compacta, centrada y casi cuadrada."""
    masc, _ = _mascara(im)
    if masc.mean() < 0.05 or masc.mean() > 0.85:
        return False
    ys, xs = np.where(masc)
    ancho, alto = xs.max() - xs.min(), ys.max() - ys.min()
    if not ancho or not alto:
        return False
    proporcion = ancho / alto
    if not 0.8 < proporcion < 1.25:
        return False
    # que la mancha llene su caja como la llenaria un circulo (~78%)
    caja = masc[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return bool(caja.mean() > 0.6)


def matcap(origen: str, destino: str, lado: int = 512) -> str:
    """Recorta la esfera, la cuadra y deja negro fuera del circulo."""
    im = Image.open(origen).convert("RGB")
    masc, _ = _mascara(im)
    ys, xs = np.where(masc)
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    radio = max(xs.max() - xs.min(), ys.max() - ys.min()) / 2
    caja = (int(cx - radio), int(cy - radio), int(cx + radio), int(cy + radio))
    esfera = im.crop(caja).resize((lado, lado), Image.LANCZOS)

    suave = Image.new("L", (lado * 4, lado * 4), 0)
    ImageDraw.Draw(suave).ellipse((0, 0, lado * 4 - 1, lado * 4 - 1), fill=255)
    recorte = Image.new("RGB", (lado, lado), (0, 0, 0))
    recorte.paste(esfera, (0, 0), suave.resize((lado, lado), Image.LANCZOS))
    recorte.save(destino, "PNG", optimize=True)
    return destino


def fondo(origen: str, destino: str, ancho: int = 1200, calidad: int = 80) -> str:
    """Reduce y comprime, que un fondo no puede costar la mitad del arranque."""
    im = Image.open(origen).convert("RGB")
    if im.width > ancho:
        im = im.resize((ancho, round(im.height * ancho / im.width)), Image.LANCZOS)
    im.save(destino, "JPEG", quality=calidad, optimize=True, progressive=True)
    return destino


def preparar(origen: str, salida: str, tipo: Optional[str] = None) -> str:
    im = Image.open(origen)
    clase = tipo or ("matcap" if parece_esfera(im) else "fondo")
    base = os.path.splitext(os.path.basename(origen))[0]
    if clase == "matcap":
        return matcap(origen, os.path.join(salida, f"{base}.png"))
    return fondo(origen, os.path.join(salida, f"{base}.jpg"))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("entrada", help="archivo o carpeta con las imagenes crudas")
    p.add_argument("--salida", default="cortador/web/static")
    p.add_argument("--tipo", choices=("matcap", "fondo"),
                   help="forzar el tipo en vez de adivinarlo")
    args = p.parse_args(argv)

    if os.path.isdir(args.entrada):
        archivos = [os.path.join(args.entrada, n) for n in sorted(os.listdir(args.entrada))
                    if n.lower().endswith(EXTENSIONES)]
    else:
        archivos = [args.entrada]
    if not archivos:
        print("No hay imagenes ahi.", file=sys.stderr)
        return 1

    os.makedirs(args.salida, exist_ok=True)
    for archivo in archivos:
        destino = preparar(archivo, args.salida, args.tipo)
        kb = os.path.getsize(destino) / 1024
        print(f"{os.path.basename(archivo)}  ->  {destino}  ({kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
