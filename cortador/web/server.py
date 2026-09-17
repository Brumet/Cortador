"""Servidor local de Cortador: panel web con visor 3D.

Se levanta con `cortador web` y sirve una sola pagina que permite cargar el
modelo, configurar la maquina y el corte, ver el resultado en 3D y descargar
todas las piezas en un ZIP.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               PlainTextResponse, Response)
from fastapi.staticfiles import StaticFiles

from ..config import SliceConfig
from ..exporters import (assembly_guide, export_result, preview_payload,
                         safe_name, zip_directory)
from ..meshio import MeshError, apply_units_and_scale, load_mesh, mesh_stats
from ..repair import (auto_repair, diagnose, is_windows, open_in_windows_repair)
from ..planner import estimate_plan
from ..slicer import SliceResult, slice_model

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_UPLOAD = 400 * 1024 * 1024  # 400 MB
JOB_TTL = 6 * 3600


@dataclass
class Job:
    id: str
    directory: str
    filename: str = ""
    source_path: str = ""
    mesh: object = None
    report: object = None
    result: Optional[SliceResult] = None
    state: str = "vacio"          # vacio | cortando | listo | error
    done: int = 0
    total: int = 1
    message: str = ""
    error: str = ""
    created: float = field(default_factory=time.time)
    zip_path: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock)


JOBS: Dict[str, Job] = {}
ROOT = os.path.join(tempfile.gettempdir(), "cortador_trabajos")


def _cleanup_old_jobs() -> None:
    now = time.time()
    for job_id in list(JOBS):
        job = JOBS[job_id]
        if now - job.created > JOB_TTL and job.state != "cortando":
            shutil.rmtree(job.directory, ignore_errors=True)
            JOBS.pop(job_id, None)


def _get_job(job_id: str) -> Job:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado o caducado")
    return job


def create_app() -> FastAPI:
    app = FastAPI(title="Cortador", docs_url="/api/docs")
    os.makedirs(ROOT, exist_ok=True)

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as fh:
            return HTMLResponse(fh.read())

    @app.get("/api/version")
    def version():
        from .. import __version__
        return {"version": __version__, "windows": is_windows()}

    @app.post("/api/modelo")
    async def subir_modelo(archivo: UploadFile = File(...)):
        _cleanup_old_jobs()
        data = await archivo.read()
        if not data:
            raise HTTPException(status_code=400, detail="El archivo esta vacio")
        if len(data) > MAX_UPLOAD:
            raise HTTPException(status_code=413, detail="El archivo supera los 400 MB")
        job_id = uuid.uuid4().hex[:12]
        directory = os.path.join(ROOT, job_id)
        os.makedirs(directory, exist_ok=True)
        ext = os.path.splitext(archivo.filename or "modelo.stl")[1].lower() or ".stl"
        path = os.path.join(directory, f"entrada{ext}")
        with open(path, "wb") as fh:
            fh.write(data)
        try:
            mesh = load_mesh(path, repair=False)
        except MeshError as exc:
            shutil.rmtree(directory, ignore_errors=True)
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            shutil.rmtree(directory, ignore_errors=True)
            raise HTTPException(status_code=400, detail=f"No se pudo leer el modelo: {exc}")

        problemas = diagnose(mesh)
        reparada, informe = auto_repair(mesh)
        job = Job(id=job_id, directory=directory, filename=archivo.filename or "modelo",
                  source_path=path, mesh=reparada, report=informe)
        JOBS[job_id] = job
        return {"trabajo": job_id, "archivo": job.filename,
                "modelo": mesh_stats(reparada),
                "original": {"problemas": problemas},
                "reparacion": informe.to_dict(),
                "windows": is_windows()}

    @app.post("/api/plan")
    def calcular_plan(payload: dict = Body(...)):
        job = _get_job(payload.get("trabajo", ""))
        cfg = _config_from(payload.get("config"))
        work = apply_units_and_scale(job.mesh, cfg.units, cfg.scale, cfg.target_size,
                                     cfg.target_axis)
        plan = estimate_plan(work.bounds, cfg)
        plan["modelo"] = mesh_stats(work)
        # factor total aplicado, para que la rejilla encaje con la vista previa
        original = float(job.mesh.extents[0]) or 1.0
        plan["factor"] = float(work.extents[0]) / original
        return plan

    @app.post("/api/cortar")
    def cortar(payload: dict = Body(...)):
        job = _get_job(payload.get("trabajo", ""))
        cfg = _config_from(payload.get("config"))
        formato = str(payload.get("formato", "stl")).lower()
        al_origen = bool(payload.get("origen", True))
        with job.lock:
            if job.state == "cortando":
                raise HTTPException(status_code=409, detail="Ya hay un corte en marcha")
            job.state = "cortando"
            job.done, job.total, job.message, job.error = 0, 1, "Preparando", ""
            job.result = None
            job.zip_path = ""

        thread = threading.Thread(target=_run_job, args=(job, cfg, formato, al_origen),
                                  daemon=True)
        thread.start()
        return {"estado": "cortando"}

    @app.get("/api/progreso/{job_id}")
    def progreso(job_id: str):
        job = _get_job(job_id)
        data = {"estado": job.state, "hecho": job.done, "total": job.total,
                "mensaje": job.message, "error": job.error}
        if job.state == "listo" and job.result is not None:
            data["resumen"] = _summary(job)
        return data

    @app.get("/api/vista/{job_id}")
    def vista(job_id: str, fuente: str = "piezas"):
        job = _get_job(job_id)
        if fuente == "original" or job.result is None:
            payload = _original_payload(job)
        else:
            payload = preview_payload(job.result)
        return Response(content=payload, media_type="application/octet-stream")

    @app.get("/api/guia/{job_id}")
    def guia(job_id: str):
        job = _get_job(job_id)
        if job.result is None:
            raise HTTPException(status_code=404, detail="Todavia no hay resultado")
        return PlainTextResponse(assembly_guide(job.result, job.filename),
                                 media_type="text/markdown; charset=utf-8")

    @app.get("/api/manifiesto/{job_id}")
    def manifiesto(job_id: str):
        job = _get_job(job_id)
        if job.result is None:
            raise HTTPException(status_code=404, detail="Todavia no hay resultado")
        return JSONResponse(job.result.manifest())

    @app.post("/api/reparar/{job_id}")
    def reparar(job_id: str):
        """Abre el modelo en 3D Builder (Windows) para usar su reparador."""
        job = _get_job(job_id)
        ruta = job.source_path
        if not ruta or not os.path.exists(ruta):
            raise HTTPException(status_code=404, detail="El archivo original ya no esta")
        abierto, mensaje = open_in_windows_repair(ruta)
        return {"abierto": abierto, "mensaje": mensaje, "windows": is_windows(),
                "archivo": ruta}

    @app.get("/api/malla/{job_id}")
    def descargar_malla(job_id: str):
        """Descarga la malla ya reparada por Cortador, en STL."""
        job = _get_job(job_id)
        destino = os.path.join(job.directory, "reparado.stl")
        if not os.path.exists(destino):
            job.mesh.export(destino)
        nombre = os.path.splitext(os.path.basename(job.filename))[0] or "modelo"
        return FileResponse(destino, media_type="model/stl",
                            filename=f"{nombre}_reparado.stl")

    @app.get("/api/pieza/{job_id}/{nombre}")
    def descargar_pieza(job_id: str, nombre: str):
        """Descarga una sola pieza, para mandarla directa al laminador."""
        job = _get_job(job_id)
        if job.result is None:
            raise HTTPException(status_code=404, detail="Todavia no hay piezas")
        pieza = next((p for p in job.result.pieces if p.name == nombre), None)
        if pieza is None:
            raise HTTPException(status_code=404, detail=f"No existe la pieza {nombre}")
        carpeta = os.path.join(job.directory, "sueltas")
        os.makedirs(carpeta, exist_ok=True)
        destino = os.path.join(carpeta, f"{safe_name(nombre)}.stl")
        if not os.path.exists(destino):
            malla = pieza.mesh.copy()
            malla.apply_translation(-pieza.mesh.bounds[0])
            malla.export(destino)
        return FileResponse(destino, media_type="model/stl",
                            filename=f"{safe_name(nombre)}.stl")

    @app.post("/api/abrir/{job_id}")
    def abrir_carpeta(job_id: str):
        """Abre la carpeta con las piezas en el explorador del sistema."""
        job = _get_job(job_id)
        carpeta = os.path.join(job.directory, "salida", "piezas")
        if not os.path.isdir(carpeta):
            raise HTTPException(status_code=404, detail="Todavia no hay piezas")
        ok, mensaje = _abrir_en_el_sistema(carpeta)
        return {"abierto": ok, "mensaje": mensaje, "carpeta": carpeta}

    @app.get("/api/descargar/{job_id}")
    def descargar(job_id: str):
        job = _get_job(job_id)
        if job.state != "listo" or not job.zip_path or not os.path.exists(job.zip_path):
            raise HTTPException(status_code=404, detail="Todavia no hay nada que descargar")
        name = os.path.splitext(os.path.basename(job.filename))[0] or "modelo"
        return FileResponse(job.zip_path, media_type="application/zip",
                            filename=f"{name}_cortado.zip")

    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _abrir_en_el_sistema(carpeta: str):
    """Abre una carpeta con el explorador de archivos del sistema."""
    import subprocess
    import sys
    try:
        if sys.platform.startswith("win"):
            os.startfile(carpeta)       # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", carpeta])
        else:
            subprocess.Popen(["xdg-open", carpeta])
        return True, "Carpeta abierta"
    except Exception as exc:
        return False, f"No he podido abrir la carpeta ({exc}). Esta en: {carpeta}"


def _config_from(data) -> SliceConfig:
    try:
        return SliceConfig.from_dict(data or {})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Configuracion invalida: {exc}")


def _run_job(job: Job, cfg: SliceConfig, formato: str, al_origen: bool = True) -> None:
    def progress(done: int, total: int, msg: str) -> None:
        job.done, job.total, job.message = int(done), int(max(total, 1)), msg

    try:
        result = slice_model(job.mesh, cfg, progress=progress)
        job.result = result
        job.message = "Exportando las piezas"
        outdir = os.path.join(job.directory, "salida")
        shutil.rmtree(outdir, ignore_errors=True)
        os.makedirs(outdir, exist_ok=True)
        name = os.path.splitext(os.path.basename(job.filename))[0] or "modelo"
        export_result(result, outdir, mesh_format=formato, model_name=name,
                      place_at_origin=al_origen, progress=progress)
        progress(0, 1, "Comprimiendo el ZIP")
        job.zip_path = zip_directory(outdir, os.path.join(job.directory, f"{name}_cortado.zip"))
        job.state = "listo"
        job.message = "Listo"
    except Exception as exc:
        job.state = "error"
        job.error = f"{exc}"
        job.message = "Error"
        traceback.print_exc()


def _summary(job: Job) -> dict:
    result = job.result
    assert result is not None
    return {
        "piezas": result.count,
        "rejilla": list(result.plan.counts),
        "capas": int(result.plan.counts[result.plan.layer_axis]),
        "espigas": result.dowels,
        "litros": round(result.hollow_volume / 1e6, 2),
        "litros_macizo": round(result.solid_volume / 1e6, 2),
        "avisos": list(result.warnings),
        "fuera_de_capacidad": [p.name for p in result.oversized()],
        "lista": [{"nombre": p.name, "capa": p.layer,
                   "medidas": [round(float(v), 1) for v in p.size],
                   "volumen_cm3": round(float(p.mesh.volume) / 1000.0, 1) if p.mesh.is_volume else None,
                   "vecinos": p.neighbors, "avisos": p.notes}
                  for p in result.pieces],
    }


def _original_payload(job: Job) -> bytes:
    """Vista previa del modelo sin cortar (una sola 'pieza' gris)."""
    import json
    import struct

    import numpy as np

    mesh = job.mesh
    if len(mesh.faces) > 300_000:
        try:
            mesh = mesh.simplify_quadric_decimation(face_count=300_000)
        except Exception:
            pass
    tris = mesh.vertices[mesh.faces].astype(np.float32).reshape(-1, 3)
    header = {
        "pieces": [{"name": job.filename or "modelo", "layer": 1, "index": [0, 0, 0],
                    "color": [176, 182, 194], "offset": 0, "count": int(len(tris)),
                    "center": [float(v) for v in mesh.bounds.mean(axis=0)],
                    "size": [float(v) for v in mesh.extents],
                    "bounds": [[float(v) for v in mesh.bounds[0]],
                               [float(v) for v in mesh.bounds[1]]],
                    "notes": []}],
        "bounds": [[float(v) for v in mesh.bounds[0]], [float(v) for v in mesh.bounds[1]]],
    }
    from ..exporters import _padded_header
    raw = _padded_header(header)
    return struct.pack("<I", len(raw)) + raw + np.ascontiguousarray(tris).tobytes()


def free_port(host: str, port: int, intentos: int = 20) -> int:
    """Busca un puerto libre a partir del pedido (util al abrir dos veces la app)."""
    import socket
    for salto in range(intentos):
        candidato = port + salto
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, candidato))
                return candidato
            except OSError:
                continue
    return port


def run(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True) -> None:
    import uvicorn

    port = free_port(host, port)
    url = f"http://{host}:{port}/"
    if open_browser:
        def _open() -> None:
            import webbrowser
            time.sleep(1.0)
            try:
                webbrowser.open(url)
            except Exception:
                pass
        threading.Thread(target=_open, daemon=True).start()
    print(f"Cortador esta en {url}  (Ctrl+C para salir)")
    uvicorn.run(create_app(), host=host, port=port, log_level="warning",
                log_config=None)


app = None


def get_app() -> FastAPI:
    global app
    if app is None:
        app = create_app()
    return app
