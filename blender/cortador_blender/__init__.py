"""Cortador: cortar figuras grandes en piezas que caben en la impresora.

Se instala como complemento de Blender y trabaja sobre la figura que tengas
seleccionada. La idea es que el espesor y la escala los pongas tu, con
Solidificar y con la escala de Blender, que para eso los tienes ahi y los ves;
el complemento solo se encarga de lo que es un lio de hacer a mano: decidir
por donde cortar, cortar sin romper la malla y dejar cada pieza cerrada.

El reparto de archivos:

    cortar.py    el motor: partir por planos y cerrar las caras de corte
    plan.py      donde van los cortes, contra la capacidad de la maquina
    perfiles.py  las maquinas conocidas
    proceso.py   el trabajo completo, en pasos
    marcas.py    grabar en cada pieza como se llama y con quien va
    plano.py     el plano de montaje en PDF
    pdf.py       un escritor de PDF de andar por casa
    registro.py  el diario: todo lo que pasa, apuntado para poder mandarlo
    interfaz.py  el panel y los botones
"""

bl_info = {
    "name": "Cortador",
    "author": "Brumet",
    "version": (0, 3, 0),
    "blender": (3, 6, 0),
    "location": "Vista 3D > barra lateral (N) > Cortador",
    "description": "Corta figuras grandes en piezas que caben en la impresora",
    "category": "Object",
    "doc_url": "https://github.com/brumet/cortador",
}

from . import interfaz


def register() -> None:
    interfaz.registrar()


def unregister() -> None:
    interfaz.olvidar()
