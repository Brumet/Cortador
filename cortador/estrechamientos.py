"""Donde conviene cortar: los estrechamientos del modelo.

Cortar una figura por la mitad del muslo es lo peor de los dos mundos: la cara
de corte es enorme -mucha superficie que pegar y mucha junta a la vista- y cae
justo donde mas se nota. Cortar por el tobillo, por la muneca o por el cuello es
lo que hace cualquiera que haya montado una figura: la union es pequena, cae en
un cambio de forma que la disimula, y las dos piezas encajan casi solas porque
el contorno es inconfundible.

Este modulo busca esos sitios. El planificador mueve alli los planos de corte
siempre que las piezas sigan cabiendo en la maquina; si no cabe, se queda donde
estaba, porque lo primero es que la pieza entre.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np
import trimesh


def perfil_de_grosor(mesh: trimesh.Trimesh,
                     axis: int = 2,
                     muestras: int = 400) -> Tuple[np.ndarray, np.ndarray]:
    """Cuanto contorno tiene el modelo a cada altura del eje.

    Devuelve (alturas, medida). La medida es el area de las caras que caen en
    cada franja, contando solo la parte que mira "de lado": una cara horizontal
    -el suelo de un pie, la tapa de un sombrero- no aporta contorno, y si se
    contara entera meteria un pico falso en esa altura.

    No es el area de la seccion, pero para **comparar** alturas entre si sirve
    igual, y se calcula de una pasada sobre las caras. En una figura de cinco
    millones de triangulos son milisegundos; cortar secciones de verdad serian
    minutos.
    """
    axis = int(axis)
    triangulos = np.asarray(mesh.triangles, dtype=float)[:, :, axis]
    lo, hi = float(mesh.bounds[0][axis]), float(mesh.bounds[1][axis])
    if hi - lo <= 0 or not len(triangulos):
        return np.zeros(0), np.zeros(0)

    normales = np.asarray(mesh.face_normals, dtype=float)[:, axis]
    # sin(angulo con el eje): 1 para una pared vertical, 0 para una horizontal
    de_lado = np.sqrt(np.clip(1.0 - normales * normales, 0.0, 1.0))
    peso = np.asarray(mesh.area_faces, dtype=float) * de_lado

    muestras = max(8, int(muestras))
    paso = (hi - lo) / muestras
    # Cada triangulo reparte su area entre todas las franjas que cruza, no la
    # suelta entera donde caiga su centro. En una malla fina da lo mismo, pero
    # un cubo tiene seis caras que van de arriba abajo: contarlas en su centro
    # dejaria el perfil como un pico y todo lo demas a cero, y de ahi saldrian
    # estrechamientos que no existen.
    desde = np.clip(((triangulos.min(axis=1) - lo) / paso).astype(int), 0, muestras - 1)
    hasta = np.clip(((triangulos.max(axis=1) - lo) / paso).astype(int), 0, muestras - 1)
    reparto = peso / (hasta - desde + 1)
    saltos = np.zeros(muestras + 1)
    np.add.at(saltos, desde, reparto)
    np.add.at(saltos, hasta + 1, -reparto)
    medida = np.cumsum(saltos)[:muestras]

    bordes = np.linspace(lo, hi, muestras + 1)
    alturas = (bordes[:-1] + bordes[1:]) / 2.0
    return alturas, medida


def _suavizar(valores: np.ndarray, ventana: int = 5) -> np.ndarray:
    """Media movil, para que el ruido del escaneo no invente estrechamientos."""
    ventana = max(1, int(ventana) | 1)          # impar, para que quede centrada
    if ventana <= 1 or len(valores) < ventana:
        return valores.astype(float)
    nucleo = np.ones(ventana) / ventana
    relleno = ventana // 2
    extendido = np.concatenate([np.full(relleno, valores[0]), valores,
                                np.full(relleno, valores[-1])])
    return np.convolve(extendido, nucleo, mode="valid")


def estrechamientos(mesh: trimesh.Trimesh,
                    axis: int = 2,
                    muestras: int = 400,
                    minimo: float = 0.12) -> List[Tuple[float, float]]:
    """Alturas donde el modelo se estrecha, de mas marcada a menos.

    Devuelve una lista de (altura, cuanto se marca), donde "cuanto se marca" va
    de 0 a 1: es lo que baja el contorno respecto a lo que tiene a los lados. Un
    tobillo de una figura de pie sale cerca de 0,6; la ondulacion de un pliegue
    de ropa, en 0,02. Con `minimo` se descarta lo que no llega a ser un
    estrechamiento de verdad.
    """
    alturas, medida = perfil_de_grosor(mesh, axis, muestras)
    if len(alturas) < 5:
        return []
    suave = _suavizar(medida, max(3, len(medida) // 60))
    if not np.any(suave > 0):
        return []

    # marca de cada altura: cuanto baja el contorno respecto a lo que tiene a
    # los lados. Se mira el lado que menos sube, que es el que manda -un escalon
    # no es un estrechamiento-, y se normaliza para poder comparar figuras.
    marcas = np.zeros(len(suave))
    for i in range(1, len(suave) - 1):
        if suave[i] > suave[i - 1] or suave[i] > suave[i + 1]:
            continue                             # ni siquiera es un minimo
        hombro = min(suave[:i].max(), suave[i + 1:].max())
        if hombro > 0:
            marcas[i] = (hombro - suave[i]) / hombro

    # Un cuello no es un punto, es un tramo: en un tobillo recto todas las
    # alturas del tramo puntuan igual. Cortar por el borde del tramo deja un
    # resalte incomodo, asi que de cada tramo se coge el centro de su parte mas
    # estrecha, que es donde la union queda mas limpia.
    # Los extremos no cuentan. Toda figura se estrecha hasta cero en la punta
    # -la coronilla, la planta del pie-, y cortar ahi solo daria una tapita
    # inutil. Se dejan fuera las franjas del principio y del final.
    borde = max(1, int(len(marcas) * 0.06))
    marcas[:borde] = 0.0
    marcas[-borde:] = 0.0

    encontrados: List[Tuple[float, float]] = []
    dentro = marcas >= float(minimo)
    i = 0
    while i < len(dentro):
        if not dentro[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(dentro) and dentro[j + 1]:
            j += 1
        tramo = suave[i:j + 1]
        fondo = np.flatnonzero(tramo <= tramo.min() + 1e-12) + i
        centro = int(fondo[len(fondo) // 2])
        encontrados.append((float(alturas[centro]), float(marcas[i:j + 1].max())))
        i = j + 1

    encontrados.sort(key=lambda par: par[1], reverse=True)
    return encontrados


def ajustar_cortes(edges: Sequence[float],
                   candidatos: Sequence[Tuple[float, float]],
                   capacidad: float,
                   margen: float = 0.35) -> Tuple[np.ndarray, int]:
    """Mueve cada plano de corte al estrechamiento util mas cercano.

    Devuelve (bordes nuevos, cuantos se han movido). Reglas, por orden:

    1. Un plano solo se mueve dentro de su propio margen (una fraccion del
       tamano de celda): si el estrechamiento esta lejos, mover el corte ahi
       dejaria una pieza enorme y otra ridicula.
    2. Ninguna celda puede pasarse de la capacidad de la maquina. Lo primero es
       que la pieza entre; lo segundo, que la union sea comoda.
    3. Los planos se mueven de uno en uno y siempre en orden, de modo que no se
       pueden cruzar ni juntarse dos en el mismo sitio.
    """
    bordes = [float(v) for v in edges]
    if len(bordes) < 3 or not candidatos:
        return np.asarray(bordes, dtype=float), 0

    ordenados = sorted(candidatos, key=lambda par: par[1], reverse=True)
    movidos = 0
    for i in range(1, len(bordes) - 1):
        celda = min(bordes[i] - bordes[i - 1], bordes[i + 1] - bordes[i])
        alcance = celda * float(margen)
        posibles = []
        for altura, marca in ordenados:
            if abs(altura - bordes[i]) > alcance:
                continue
            if altura <= bordes[i - 1] or altura >= bordes[i + 1]:
                continue
            if capacidad > 0 and (altura - bordes[i - 1] > capacidad + 1e-6
                                  or bordes[i + 1] - altura > capacidad + 1e-6):
                continue
            posibles.append((marca, altura))
        # manda lo marcado que este el estrechamiento; a igualdad, el que menos
        # mueva el corte, para no descuadrar el reparto de las piezas
        mejor = None
        if posibles:
            tope = max(p[0] for p in posibles)
            mejor = min((a for mrc, a in posibles if mrc >= tope - 1e-9),
                        key=lambda a: abs(a - bordes[i]))
        if mejor is not None and abs(mejor - bordes[i]) > 1e-9:
            bordes[i] = mejor
            movidos += 1
    return np.asarray(bordes, dtype=float), movidos
