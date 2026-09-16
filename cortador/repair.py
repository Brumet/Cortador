"""Diagnostico y reparacion de mallas, incluida la herramienta de Windows.

La reparacion automatica resuelve la mayoria de los casos (vertices sueltos,
caras duplicadas, normales del reves, agujeros pequenos, cuerpos superpuestos).
Cuando la malla esta demasiado rota, lo mas practico en Windows es abrirla con
**3D Builder**, que trae un reparador muy bueno y viene con el sistema.
"""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import trimesh

from .meshio import repair_mesh, weld_bodies

#: identificador de 3D Builder en la Microsoft Store
BUILDER_PACKAGE = "Microsoft.3DBuilder"
BUILDER_APPID = "Microsoft.3DBuilder_8wekyb3d8bbwe!App"
STORE_SEARCH = "ms-windows-store://search/?query=3D%20Builder"


def is_windows() -> bool:
    return platform.system().lower().startswith("win")


@dataclass
class RepairReport:
    """Que tenia la malla y que se ha arreglado."""

    caras_antes: int = 0
    caras_despues: int = 0
    cuerpos_antes: int = 0
    cuerpos_despues: int = 0
    estanca_antes: bool = False
    estanca_despues: bool = False
    normales_corregidas: bool = False
    agujeros_tapados: bool = False
    cuerpos_fundidos: bool = False
    problemas: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True si la malla ya sirve para cortar sin sustos.

        Que queden varios solidos separados no es un fallo: hay modelos que son
        de verdad varias piezas sueltas. Lo que rompe el corte es que la malla
        no este cerrada.
        """
        return self.estanca_despues and self.caras_despues > 0

    @property
    def cambiada(self) -> bool:
        return (self.caras_antes != self.caras_despues
                or self.cuerpos_antes != self.cuerpos_despues
                or self.normales_corregidas or self.agujeros_tapados
                or self.cuerpos_fundidos)

    def acciones(self) -> List[str]:
        hechas = []
        if self.caras_despues != self.caras_antes:
            hechas.append(f"caras: {self.caras_antes} -> {self.caras_despues}")
        if self.normales_corregidas:
            hechas.append("normales reorientadas")
        if self.agujeros_tapados:
            hechas.append("agujeros tapados")
        if self.cuerpos_fundidos:
            hechas.append(f"{self.cuerpos_antes} cuerpos fundidos en uno")
        return hechas

    def resumen(self) -> str:
        sueltos = ""
        if self.estanca_despues and self.cuerpos_despues > 1:
            sueltos = (f" Son {self.cuerpos_despues} solidos que no se tocan; "
                       "se cortan igual, cada uno por su lado.")
        if self.ok and not self.cambiada:
            return "La malla ya estaba bien: cerrada y lista para cortar." + sueltos
        partes = self.acciones()
        texto = "Reparacion automatica: " + (", ".join(partes) if partes else "sin cambios")
        if self.estanca_despues:
            return texto + ". La malla queda cerrada y lista para cortar." + sueltos
        return texto + ". La malla SIGUE ABIERTA: conviene repararla con 3D Builder."

    def to_dict(self) -> dict:
        return {
            "caras_antes": self.caras_antes, "caras_despues": self.caras_despues,
            "cuerpos_antes": self.cuerpos_antes, "cuerpos_despues": self.cuerpos_despues,
            "estanca_antes": self.estanca_antes, "estanca_despues": self.estanca_despues,
            "normales_corregidas": self.normales_corregidas,
            "agujeros_tapados": self.agujeros_tapados,
            "cuerpos_fundidos": self.cuerpos_fundidos,
            "ok": self.ok, "cambiada": self.cambiada,
            "problemas": list(self.problemas), "resumen": self.resumen(),
        }


def body_count(mesh: trimesh.Trimesh) -> int:
    """Cuerpos reales, soldando antes los vertices repetidos.

    Un STL recien leido tiene un vertice por esquina de triangulo, asi que sin
    soldar parece tener tantos 'cuerpos' como caras.
    """
    try:
        copia = mesh.copy()
        copia.merge_vertices()
        return int(copia.body_count)
    except Exception:
        return int(mesh.body_count)


def diagnose(mesh: trimesh.Trimesh) -> List[str]:
    """Lista de problemas que impiden un corte limpio."""
    problemas = []
    if len(mesh.faces) == 0:
        return ["no hay geometria"]
    if not mesh.is_watertight:
        problemas.append("la malla no es estanca (tiene agujeros o bordes sueltos)")
    if not mesh.is_winding_consistent:
        problemas.append("hay caras con la normal invertida")
    cuerpos = body_count(mesh)
    if cuerpos > 1:
        problemas.append(f"son {cuerpos} cuerpos separados o superpuestos")
    return problemas


def auto_repair(mesh: trimesh.Trimesh,
                weld: bool = True) -> Tuple[trimesh.Trimesh, RepairReport]:
    """Repara lo que se puede sin intervencion del usuario."""
    report = RepairReport(
        caras_antes=int(len(mesh.faces)),
        cuerpos_antes=body_count(mesh),
        estanca_antes=bool(mesh.is_watertight),
    )
    tenia_normales_mal = not mesh.is_winding_consistent
    tenia_agujeros = not mesh.is_watertight

    limpia = repair_mesh(mesh)
    if weld and limpia.body_count > 1:
        fundida = weld_bodies(limpia)
        if fundida is not limpia:
            report.cuerpos_fundidos = True
            limpia = fundida

    report.caras_despues = int(len(limpia.faces))
    report.cuerpos_despues = int(limpia.body_count)
    report.estanca_despues = bool(limpia.is_watertight)
    report.normales_corregidas = tenia_normales_mal and limpia.is_winding_consistent
    report.agujeros_tapados = tenia_agujeros and limpia.is_watertight
    report.problemas = diagnose(limpia)
    return limpia, report


# ---------------------------------------------------------------------------
# 3D Builder (Windows)
# ---------------------------------------------------------------------------

def find_3d_builder() -> bool:
    """Comprueba si 3D Builder esta instalado (solo Windows)."""
    if not is_windows():
        return False
    try:
        salida = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"if (Get-AppxPackage -Name {BUILDER_PACKAGE}) {{ 'si' }} else {{ 'no' }}"],
            capture_output=True, text=True, timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return False
    return "si" in (salida.stdout or "").lower()


def open_in_windows_repair(path: str) -> Tuple[bool, str]:
    """Abre el modelo en 3D Builder para usar su reparador.

    Devuelve (se_ha_abierto, mensaje para el usuario).
    """
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return False, f"No encuentro el archivo {path}"
    if not is_windows():
        return False, ("La reparacion con 3D Builder solo esta disponible en Windows. "
                       "En Linux o macOS puedes usar Meshlab o Blender "
                       "(Modificador 'Remesh' o el complemento 3D Print Toolbox).")

    instalado = find_3d_builder()
    intentos = []
    if instalado:
        # con el archivo asociado a 3D Builder basta con abrirlo
        intentos.append(("open", None))
    intentos.append(("openas", None))   # dialogo "Abrir con..."

    for verbo, _ in intentos:
        try:
            os.startfile(path, verbo)   # type: ignore[attr-defined]
            if verbo == "open" and instalado:
                return True, _INSTRUCCIONES
            return True, ("Elige **3D Builder** en la ventana 'Abrir con'.\n\n" + _INSTRUCCIONES)
        except Exception:
            continue

    if not instalado:
        try:
            os.startfile(STORE_SEARCH)  # type: ignore[attr-defined]
            return False, ("3D Builder no esta instalado. Te he abierto la Microsoft "
                           "Store para que lo instales (es gratis) y vuelvas a intentarlo.")
        except Exception:
            pass
    return False, ("No he podido abrir el archivo. Abrelo a mano con 3D Builder:\n"
                   f"{path}")


_INSTRUCCIONES = (
    "En 3D Builder:\n"
    "1. Si la malla tiene fallos, aparece abajo el aviso **'Reparar'**: pulsalo.\n"
    "2. Espera a que termine (en modelos grandes tarda un poco).\n"
    "3. **Menu > Guardar como > Guardar en el equipo** y elige formato STL o 3MF.\n"
    "4. Vuelve a Cortador y carga el archivo reparado."
)


def repaired_copy_path(path: str) -> str:
    base, ext = os.path.splitext(path)
    return f"{base}_reparado{ext or '.stl'}"
