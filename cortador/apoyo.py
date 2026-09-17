"""Formas de apoyar el proyecto.

Cortador es gratis y de codigo libre, y asi se queda. Esto es solo para quien
lo use y quiera dar una mano: una propina, nada mas. Si la lista esta vacia no
se muestra nada en ninguna parte, que es como viene de fabrica.

Para activarlo basta con rellenar CANALES con lo que corresponda:

    CANALES = [
        {"nombre": "Nequi", "tipo": "copiar", "valor": "300 123 4567",
         "nota": "a nombre de Brumet"},
        {"nombre": "PayPal", "tipo": "enlace", "valor": "https://paypal.me/ejemplo"},
    ]

`tipo` puede ser:
  enlace  se abre en el navegador (PayPal, Ko-fi, GitHub Sponsors...)
  copiar  se copia al portapapeles (un numero de Nequi, una cuenta, una llave)
"""

from __future__ import annotations

from typing import Dict, List

TIPOS = ("enlace", "copiar")

# De fabrica va vacio a proposito: nadie ve una peticion de dinero hasta que
# el dueno del proyecto ponga aqui sus datos.
CANALES: List[Dict[str, str]] = []

MENSAJE = ("Cortador es gratis y seguira siendolo. Si te ahorra material o "
           "tiempo y quieres dar una mano, se agradece.")


def canales() -> List[Dict[str, str]]:
    """Canales validos, ya listos para mostrar."""
    limpios = []
    for canal in CANALES:
        nombre = str(canal.get("nombre", "")).strip()
        valor = str(canal.get("valor", "")).strip()
        tipo = str(canal.get("tipo", "enlace")).strip().lower()
        if not nombre or not valor or tipo not in TIPOS:
            continue
        if tipo == "enlace" and not valor.startswith(("http://", "https://")):
            continue
        limpios.append({"nombre": nombre, "tipo": tipo, "valor": valor,
                        "nota": str(canal.get("nota", "")).strip()})
    return limpios


def hay_apoyo() -> bool:
    return bool(canales())
