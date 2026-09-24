"""Un escritor de PDF de andar por casa, para el plano de montaje.

Blender no trae ninguna libreria de PDF y no se le pueden instalar cosas: el
complemento tiene que funcionar con lo que hay dentro. Por suerte un PDF con
imagenes y texto es un formato sencillo de escribir a mano, y aqui solo hace
falta eso: pegar el render de cada piso y escribir encima el nombre de cada
pieza.

Las imagenes van en JPEG y se meten tal cual, sin tocarlas: el visor de PDF
sabe descomprimirlas el solo -es lo que significa el filtro `DCTDecode`-, asi
que no hay que convertir nada. Y las letras usan Helvetica, que todos los
visores llevan puesta de serie, asi que tampoco hay que empotrar ninguna
fuente. El archivo que sale se abre igual en una tablet que en el ordenador de
la imprenta.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

#: anchos de Helvetica, en milesimas de punto, para los caracteres que usamos
_ANCHOS = {
    " ": 278, "!": 278, "\"": 355, "#": 556, "$": 556, "%": 889, "&": 667,
    "'": 191, "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333,
    ".": 278, "/": 278, "0": 556, "1": 556, "2": 556, "3": 556, "4": 556,
    "5": 556, "6": 556, "7": 556, "8": 556, "9": 556, ":": 278, ";": 278,
    "<": 584, "=": 584, ">": 584, "?": 556, "@": 1015, "[": 278, "\\": 278,
    "]": 278, "^": 469, "_": 556, "`": 333, "{": 334, "|": 260, "}": 334,
    "~": 584,
}
for _letra, _ancho in zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                          (667, 667, 722, 722, 667, 611, 778, 722, 278, 500,
                           667, 556, 833, 722, 778, 667, 778, 722, 667, 611,
                           722, 667, 944, 667, 667, 611)):
    _ANCHOS[_letra] = _ancho
for _letra, _ancho in zip("abcdefghijklmnopqrstuvwxyz",
                          (556, 556, 500, 556, 556, 278, 556, 556, 222, 222,
                           500, 222, 833, 556, 556, 556, 556, 333, 500, 278,
                           556, 500, 722, 500, 500, 500)):
    _ANCHOS[_letra] = _ancho


def ancho_de(texto: str, tamano: float, negrita: bool = False) -> float:
    """Lo que va a medir un texto en puntos. Sirve para centrarlo."""
    suma = sum(_ANCHOS.get(c, 556) for c in texto)
    return suma / 1000.0 * tamano * (1.06 if negrita else 1.0)


def _escapar(texto: str) -> bytes:
    crudo = texto.encode("cp1252", "replace")
    salida = bytearray()
    for byte in crudo:
        if byte in (0x28, 0x29, 0x5C):      # ( ) \
            salida.append(0x5C)
        salida.append(byte)
    return bytes(salida)


class Pagina:
    """Una hoja que se va llenando de ordenes de dibujo."""

    def __init__(self, ancho: float, alto: float):
        self.ancho = ancho
        self.alto = alto
        self.ordenes: List[bytes] = []
        self.imagenes: List[int] = []

    def caja(self, x, y, ancho, alto, color=(1, 1, 1), borde=None,
             grosor=0.6) -> None:
        r, v, a = color
        if color is not None:
            self.ordenes.append(
                f"{r:.3f} {v:.3f} {a:.3f} rg {x:.2f} {y:.2f} {ancho:.2f} "
                f"{alto:.2f} re f".encode("ascii"))
        if borde is not None:
            r, v, a = borde
            self.ordenes.append(
                f"{r:.3f} {v:.3f} {a:.3f} RG {grosor:.2f} w {x:.2f} {y:.2f} "
                f"{ancho:.2f} {alto:.2f} re S".encode("ascii"))

    def raya(self, x1, y1, x2, y2, color=(0.4, 0.4, 0.4), grosor=0.6) -> None:
        r, v, a = color
        self.ordenes.append(
            f"{r:.3f} {v:.3f} {a:.3f} RG {grosor:.2f} w {x1:.2f} {y1:.2f} m "
            f"{x2:.2f} {y2:.2f} l S".encode("ascii"))

    def texto(self, x, y, texto, tamano=10, negrita=False,
              color=(0.08, 0.13, 0.18), centrado=False) -> None:
        if centrado:
            x -= ancho_de(texto, tamano, negrita) / 2.0
        r, v, a = color
        fuente = "F2" if negrita else "F1"
        self.ordenes.append(
            b"BT /" + fuente.encode("ascii")
            + f" {tamano:.2f} Tf {r:.3f} {v:.3f} {a:.3f} rg 1 0 0 1 "
              f"{x:.2f} {y:.2f} Tm (".encode("ascii")
            + _escapar(texto) + b") Tj ET")

    def imagen(self, indice: int, x, y, ancho, alto) -> None:
        self.imagenes.append(indice)
        self.ordenes.append(
            f"q {ancho:.2f} 0 0 {alto:.2f} {x:.2f} {y:.2f} cm /Im{indice} Do Q"
            .encode("ascii"))


class Documento:
    """El PDF entero. Se le van anadiendo paginas y al final se guarda."""

    def __init__(self, ancho: float = 842.0, alto: float = 595.0):
        self.ancho = ancho
        self.alto = alto
        self.paginas: List[Pagina] = []
        self.fotos: List[Tuple[bytes, int, int]] = []

    def pagina(self) -> Pagina:
        hoja = Pagina(self.ancho, self.alto)
        self.paginas.append(hoja)
        return hoja

    def foto(self, datos: bytes, ancho: int, alto: int) -> int:
        """Guarda un JPEG y devuelve su numero para poder colocarlo."""
        self.fotos.append((datos, ancho, alto))
        return len(self.fotos)

    def guardar(self, ruta: str) -> None:
        cuerpos: List[bytes] = []

        def apuntar(cuerpo: bytes) -> int:
            cuerpos.append(cuerpo)
            return len(cuerpos)

        catalogo = apuntar(b"")                     # 1, se rellena al final
        arbol = apuntar(b"")                        # 2
        normal = apuntar(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica"
                         b" /Encoding /WinAnsiEncoding >>")
        negrita = apuntar(b"<< /Type /Font /Subtype /Type1 /BaseFont "
                          b"/Helvetica-Bold /Encoding /WinAnsiEncoding >>")

        numeros_foto = []
        for datos, ancho, alto in self.fotos:
            cabecera = (f"<< /Type /XObject /Subtype /Image /Width {ancho} "
                        f"/Height {alto} /ColorSpace /DeviceRGB "
                        f"/BitsPerComponent 8 /Filter /DCTDecode "
                        f"/Length {len(datos)} >>\nstream\n").encode("ascii")
            numeros_foto.append(apuntar(cabecera + datos + b"\nendstream"))

        numeros_pagina = []
        for hoja in self.paginas:
            flujo = b"\n".join(hoja.ordenes)
            contenido = apuntar(
                f"<< /Length {len(flujo)} >>\nstream\n".encode("ascii")
                + flujo + b"\nendstream")
            usadas = "".join(
                f"/Im{i} {numeros_foto[i - 1]} 0 R " for i in
                sorted(set(hoja.imagenes)))
            numeros_pagina.append(apuntar(
                (f"<< /Type /Page /Parent {arbol} 0 R /MediaBox "
                 f"[0 0 {self.ancho:.0f} {self.alto:.0f}] /Resources << "
                 f"/XObject << {usadas}>> /Font << /F1 {normal} 0 R "
                 f"/F2 {negrita} 0 R >> >> /Contents {contenido} 0 R >>"
                 ).encode("ascii")))

        hijos = " ".join(f"{n} 0 R" for n in numeros_pagina)
        cuerpos[arbol - 1] = (f"<< /Type /Pages /Kids [{hijos}] /Count "
                              f"{len(numeros_pagina)} >>").encode("ascii")
        cuerpos[catalogo - 1] = (f"<< /Type /Catalog /Pages {arbol} 0 R >>"
                                 ).encode("ascii")

        salida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        sitios = []
        for numero, cuerpo in enumerate(cuerpos, 1):
            sitios.append(len(salida))
            salida += f"{numero} 0 obj\n".encode("ascii") + cuerpo + b"\nendobj\n"
        tabla = len(salida)
        salida += f"xref\n0 {len(cuerpos) + 1}\n".encode("ascii")
        salida += b"0000000000 65535 f \n"
        for sitio in sitios:
            salida += f"{sitio:010d} 00000 n \n".encode("ascii")
        salida += (f"trailer\n<< /Size {len(cuerpos) + 1} /Root {catalogo} 0 R"
                   f" >>\nstartxref\n{tabla}\n%%EOF\n").encode("ascii")

        with open(ruta, "wb") as archivo:
            archivo.write(bytes(salida))
