"""El diario: todo lo que pasa, apuntado para poder mandarlo.

Cuando algo sale mal en la maquina de otro, lo unico que suele llegar es «me
dio error» o una captura de pantalla. Con eso no se arregla nada. Este modulo
apunta, paso a paso, que se hizo, cuanto tardo, cuanta memoria gasto y que
salio, y ademas guarda el modelo y los ajustes de partida. El resultado es un
texto que se copia al portapapeles o se guarda en un archivo y se manda tal
cual: con eso se puede reproducir el problema sin tener el modelo delante.

Tres detalles pensados para que sirva de verdad:

* **Se apunta aunque reviente.** Si el corte falla a mitad, el diario ya lleva
  escrito todo lo anterior y encima el error entero con su traza. El caso
  interesante es justo ese.
* **La memoria se mide en Windows tambien.** El modulo `resource` de Python no
  existe alli, asi que se pregunta al sistema por su cuenta. Un corte que se
  queda sin memoria se ve en la ultima linea del diario y en ningun otro sitio.
* **Nada de datos personales.** Se apunta la version de Blender, el sistema, el
  tamano del modelo y los ajustes. No se apunta ni el archivo ni las rutas de
  la maquina.
"""

from __future__ import annotations

import datetime
import platform
import sys
import time
import traceback
from typing import List, Optional, Sequence

import bpy

#: nombre del bloque de texto donde se deja el diario dentro de Blender
BLOQUE = "Cortador · registro"
#: cuantas lineas se ensenan en el panel
ASOMA = 10


def memoria_mb() -> float:
    """Cuanta memoria lleva gastada Blender, en megas. 0 si no se sabe.

    En Linux y en Mac lo dice `resource`; en Windows ese modulo no existe y hay
    que preguntarle al sistema con `ctypes`. Vale la pena la molestia: cuando
    un corte grande se cae sin decir nada, casi siempre es que se quedo sin
    memoria, y eso solo se ve aqui.
    """
    try:
        import resource
        uso = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return uso / (1024.0 * 1024.0) if sys.platform == "darwin" else uso / 1024.0
    except Exception:
        pass
    try:
        import ctypes
        import ctypes.wintypes

        class Cuenta(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.wintypes.DWORD),
                ("PageFaultCount", ctypes.wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        cuenta = Cuenta()
        cuenta.cb = ctypes.sizeof(Cuenta)
        ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(cuenta), cuenta.cb)
        return cuenta.PeakWorkingSetSize / (1024.0 * 1024.0)
    except Exception:
        return 0.0


class Paso:
    """Un paso cronometrado. Se usa con `with`."""

    def __init__(self, diario: "Diario", texto: str):
        self.diario = diario
        self.texto = texto
        self.reloj = 0.0

    def __enter__(self) -> "Paso":
        self.reloj = time.perf_counter()
        return self

    def __exit__(self, clase, valor, traza) -> bool:
        tardo = time.perf_counter() - self.reloj
        if valor is None:
            self.diario.linea(f"{self.texto}: {tardo:.1f} s, "
                              f"memoria {memoria_mb():.0f} MB")
        else:
            self.diario.linea(f"{self.texto}: REVENTO a los {tardo:.1f} s")
            self.diario.fallo(valor)
        return False


class Diario:
    """Lo que se ha hecho y lo que ha pasado, en orden."""

    def __init__(self):
        self.lineas: List[str] = []
        self.arranque = time.perf_counter()

    # --- escribir ---------------------------------------------------------

    def linea(self, texto: str = "") -> None:
        marca = time.perf_counter() - self.arranque
        self.lineas.append(f"[{marca:7.1f}s] {texto}" if texto else "")
        print(f"Cortador | {texto}")

    def titulo(self, texto: str) -> None:
        self.lineas.append("")
        self.lineas.append(texto)
        self.lineas.append("-" * len(texto))
        print(f"Cortador | == {texto} ==")

    def dato(self, clave: str, valor) -> None:
        self.lineas.append(f"    {clave:<22} {valor}")

    def tabla(self, titulos: Sequence[str], filas: Sequence[Sequence[str]],
              tope: int = 200) -> None:
        anchos = [len(t) for t in titulos]
        for fila in filas[:tope]:
            for i, celda in enumerate(fila):
                anchos[i] = max(anchos[i], len(str(celda)))
        self.lineas.append("    " + "  ".join(
            t.ljust(anchos[i]) for i, t in enumerate(titulos)))
        self.lineas.append("    " + "  ".join("-" * a for a in anchos))
        for fila in filas[:tope]:
            self.lineas.append("    " + "  ".join(
                str(c).ljust(anchos[i]) for i, c in enumerate(fila)))
        if len(filas) > tope:
            self.lineas.append(f"    ... y {len(filas) - tope} filas mas")

    def fallo(self, error: BaseException) -> None:
        """Apunta un error con su traza entera. Es lo que hace falta para
        arreglarlo: el mensaje solo casi nunca dice donde fue."""
        self.titulo("ERROR")
        for trozo in traceback.format_exception(type(error), error,
                                                error.__traceback__):
            for renglon in trozo.rstrip().split("\n"):
                self.lineas.append("    " + renglon)
        print("Cortador | ERROR:", error)

    # --- empezar de cero --------------------------------------------------

    def nuevo(self, motivo: str) -> None:
        self.lineas = []
        self.arranque = time.perf_counter()
        ahora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        self.titulo(f"Cortador · {motivo} · {ahora}")
        self.dato("Blender", ".".join(str(n) for n in bpy.app.version))
        self.dato("sistema", f"{platform.system()} {platform.release()} "
                             f"({platform.machine()})")
        self.dato("python", platform.python_version())
        self.dato("memoria al empezar", f"{memoria_mb():.0f} MB")

    def paso(self, texto: str) -> Paso:
        return Paso(self, texto)

    # --- leerlo -----------------------------------------------------------

    def texto(self) -> str:
        return "\n".join(self.lineas) + "\n"

    def ultimas(self, cuantas: int = ASOMA) -> List[str]:
        utiles = [l for l in self.lineas if l.strip()]
        return utiles[-cuantas:]

    # --- sacarlo de aqui --------------------------------------------------

    def al_bloque(self) -> "bpy.types.Text":
        """Deja el diario en un bloque de texto de Blender, para leerlo dentro."""
        bloque = bpy.data.texts.get(BLOQUE)
        if bloque is None:
            bloque = bpy.data.texts.new(BLOQUE)
        bloque.clear()
        bloque.write(self.texto())
        return bloque

    def al_portapapeles(self) -> int:
        bpy.context.window_manager.clipboard = self.texto()
        return len(self.lineas)

    def guardar(self, ruta: str) -> str:
        with open(ruta, "w", encoding="utf-8") as archivo:
            archivo.write(self.texto())
        return ruta


#: el diario del complemento; hay uno solo y se va reescribiendo
DIARIO = Diario()


def de_la_escena(escena, mm_por_unidad: float) -> None:
    """Apunta como esta montada la escena. La escala es la culpable habitual."""
    DIARIO.dato("unidades", escena.unit_settings.system)
    DIARIO.dato("escala de la escena", escena.unit_settings.scale_length)
    DIARIO.dato("1 unidad son", f"{mm_por_unidad:g} mm")


def de_la_figura(objeto, mm_por_unidad: float) -> None:
    """Apunta el estado de la malla de partida.

    Casi todos los cortes que salen mal salen mal por esto: una malla abierta,
    con caras encima de caras, o en una escala que no es la que el usuario
    cree. Se mira antes de tocar nada.
    """
    import bmesh

    malla = objeto.data
    DIARIO.dato("figura", objeto.name)
    DIARIO.dato("caras", len(malla.polygons))
    DIARIO.dato("vertices", len(malla.vertices))
    DIARIO.dato("medidas", "{:.1f} x {:.1f} x {:.1f} mm".format(
        *[d * mm_por_unidad for d in objeto.dimensions]))
    DIARIO.dato("escala del objeto", tuple(round(s, 4) for s in objeto.scale))
    DIARIO.dato("modificadores sin aplicar",
                [m.type for m in objeto.modifiers] or "ninguno")

    if len(malla.polygons) > 3_000_000:
        DIARIO.dato("estado de la malla", "no se revisa, es muy grande")
        return
    bm = bmesh.new()
    try:
        bm.from_mesh(malla)
        abiertas = sum(1 for e in bm.edges if e.is_boundary)
        raras = sum(1 for e in bm.edges if len(e.link_faces) > 2)
        sueltos = sum(1 for v in bm.verts if not v.link_faces)
        DIARIO.dato("aristas abiertas", abiertas)
        DIARIO.dato("aristas no-manifold", raras)
        DIARIO.dato("vertices sueltos", sueltos)
        DIARIO.dato("volumen", "{:.1f} cm3".format(
            abs(bm.calc_volume(signed=True)) * (mm_por_unidad ** 3) / 1000.0))
        if abiertas or raras:
            DIARIO.linea("AVISO: la malla de partida no esta cerrada del todo. "
                         "El corte puede dejar piezas abiertas por ahi.")
    finally:
        bm.free()


def de_los_ajustes(datos, ajustes, mm_por_unidad: float) -> None:
    """Apunta con que ajustes se corto, para poder repetirlo igual."""
    DIARIO.dato("maquina", datos.perfil)
    DIARIO.dato("pisos", datos.modo_pisos
                + (f" = {datos.pisos}" if datos.modo_pisos == "NUMERO" else "")
                + (f" = {datos.alto_piso:g} mm"
                   if datos.modo_pisos == "ALTURA" else ""))
    DIARIO.dato("gajos", datos.modo_gajos
                + (f" = {datos.gajos}" if datos.modo_gajos == "NUMERO" else ""))
    DIARIO.dato("pared", f"{datos.pared:g} mm")
    DIARIO.dato("giro", f"{datos.giro:g} grados")
    DIARIO.dato("esquirla", f"{datos.minimo:g} mm")
    DIARIO.dato("marcar", "si" if datos.marcar else "no")
    if datos.marcar:
        DIARIO.dato("hondo de la marca", f"{datos.hondo:g} mm")
    DIARIO.dato("cama util", "{:.0f} x {:.0f} x {:.0f} mm".format(
        ajustes.perfil.x * mm_por_unidad, ajustes.perfil.y * mm_por_unidad,
        ajustes.perfil.alto_util() * mm_por_unidad))


def del_resultado(resultado, mm_por_unidad: float) -> None:
    """Apunta como quedo la cosa, pieza por pieza."""
    piezas = resultado.piezas
    DIARIO.titulo("Resultado")
    DIARIO.dato("piezas", len(piezas))
    DIARIO.dato("cerradas", f"{sum(1 for p in piezas if p.cerrada)} de {len(piezas)}")
    DIARIO.dato("caben en la maquina",
                f"{sum(1 for p in piezas if p.cabe)} de {len(piezas)}")
    DIARIO.dato("memoria al acabar", f"{memoria_mb():.0f} MB")

    for piso in resultado.pisos:
        DIARIO.dato(f"piso {piso.indice + 1}",
                    "{:.0f} mm de alto, radio {:.0f} mm, {} gajos, "
                    "{} piezas previstas".format(
                        piso.alto * mm_por_unidad, piso.radio * mm_por_unidad,
                        2 * piso.gajos, piso.piezas))

    if resultado.avisos:
        DIARIO.titulo("Avisos")
        for aviso in resultado.avisos:
            DIARIO.linea(aviso)

    DIARIO.titulo("Piezas")
    filas = []
    for pieza in piezas:
        lados = resultado.vecinos.get(pieza.nombre, {})
        filas.append([
            pieza.nombre,
            "{:.0f}x{:.0f}x{:.0f}".format(pieza.ancho * mm_por_unidad,
                                          pieza.fondo * mm_por_unidad,
                                          pieza.alto * mm_por_unidad),
            pieza.caras,
            "si" if pieza.cerrada else "NO",
            "si" if pieza.cabe else "NO",
            lados.get("izquierda", "-"), lados.get("derecha", "-"),
            lados.get("arriba", "-"), lados.get("abajo", "-"),
        ])
    DIARIO.tabla(["pieza", "medidas mm", "caras", "cerrada", "cabe",
                  "izq", "der", "arriba", "abajo"], filas)
