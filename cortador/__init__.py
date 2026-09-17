"""Cortador: corta modelos 3D para gran formato.

Uso rapido:

    from cortador import SliceConfig, PrinterSpec, load_mesh, slice_model, export_result

    malla = load_mesh("modelo.stl")
    cfg = SliceConfig(printer=PrinterSpec(220, 220, 250))
    resultado = slice_model(malla, cfg)
    export_result(resultado, "salida")
"""

from .config import (JoineryOptions, LabelOptions, PrinterSpec, SliceConfig)
from .exporters import (assembly_guide, export_result, pieces_csv, preview_glb,
                        preview_payload, zip_directory)
from .meshio import load_mesh, mesh_stats
from .planner import CutPlan, estimate_plan, plan_cuts
from .slicer import Piece, SliceResult, slice_model

__version__ = "0.7.0"

__all__ = [
    "PrinterSpec", "LabelOptions", "JoineryOptions", "SliceConfig",
    "load_mesh", "mesh_stats", "plan_cuts", "estimate_plan", "CutPlan",
    "slice_model", "SliceResult", "Piece",
    "export_result", "assembly_guide", "pieces_csv", "preview_payload",
    "preview_glb", "zip_directory", "__version__",
]
