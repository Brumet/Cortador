"""Ventana de aplicacion usando Edge (o Chrome) en modo aplicacion.

Es la forma mas robusta de darle una ventana propia a Cortador en Windows:
`msedge.exe --app=<url>` abre una ventana sin barra de direcciones, sin
pestanas y con su propio icono en la barra de tareas, y Edge esta en todos
los Windows 10 y 11. No depende de pywebview, ni de pythonnet, ni de que el
runtime de WebView2 este registrado, que es justo lo que fallaba.

Se usa un perfil propio (--user-data-dir) a proposito: asi el proceso que
lanzamos es el dueno de la ventana y, cuando el usuario la cierra, termina.
Eso nos deja apagar el servidor interno sin dejar nada colgado.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from typing import List, Optional, Tuple

from .marca import fondo_oscuro, logo
from .registro import paso

ANCHO, ALTO = 1440, 900


def _candidatos_windows() -> List[Tuple[str, str]]:
    programas = [os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"),
                 os.environ.get("LOCALAPPDATA")]
    relativos = [("Microsoft\\Edge\\Application\\msedge.exe", "Edge"),
                 ("Google\\Chrome\\Application\\chrome.exe", "Chrome"),
                 ("BraveSoftware\\Brave-Browser\\Application\\brave.exe", "Brave")]
    encontrados = []
    for base in programas:
        if not base:
            continue
        for relativo, nombre in relativos:
            encontrados.append((os.path.join(base, relativo), nombre))
    return encontrados


def _desde_registro() -> List[Tuple[str, str]]:
    """Ruta real de Edge/Chrome segun el registro de Windows (App Paths)."""
    try:
        import winreg
    except Exception:
        return []
    encontrados = []
    for exe, nombre in (("msedge.exe", "Edge"), ("chrome.exe", "Chrome")):
        for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                clave = (r"SOFTWARE\Microsoft\Windows\CurrentVersion"
                         r"\App Paths" "\\" + exe)
                with winreg.OpenKey(raiz, clave) as k:
                    ruta, _ = winreg.QueryValueEx(k, "")
                    if ruta:
                        encontrados.append((ruta.strip('"'), nombre))
            except OSError:
                continue
    return encontrados


def buscar_navegador() -> Optional[Tuple[str, str]]:
    """Devuelve (ruta, nombre) del navegador que puede hacer de ventana."""
    if sys.platform.startswith("win"):
        candidatos = _desde_registro() + _candidatos_windows()
    elif sys.platform == "darwin":
        candidatos = [
            ("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "Edge"),
            ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "Chrome"),
        ]
    else:
        candidatos = []
        for orden, nombre in (("microsoft-edge", "Edge"), ("google-chrome", "Chrome"),
                              ("chromium", "Chromium"), ("chromium-browser", "Chromium"),
                              ("brave-browser", "Brave")):
            ruta = shutil.which(orden)
            if ruta:
                candidatos.append((ruta, nombre))
    for ruta, nombre in candidatos:
        if ruta and os.path.exists(ruta):
            return ruta, nombre
    return None


def carpeta_perfil() -> str:
    """Perfil propio de la ventana (no toca el navegador del usuario)."""
    from .registro import carpeta_datos
    destino = os.path.join(carpeta_datos(), "ventana")
    try:
        os.makedirs(destino, exist_ok=True)
    except Exception:
        destino = os.path.join(tempfile.gettempdir(), "cortador_ventana")
        os.makedirs(destino, exist_ok=True)
    return destino


def abrir(url: str, titulo: str = "Cortador") -> Optional[subprocess.Popen]:
    """Abre la ventana de aplicacion. Devuelve el proceso, o None si no hay."""
    hallazgo = buscar_navegador()
    if not hallazgo:
        paso("no hay Edge ni Chrome para la ventana de aplicacion")
        return None
    ruta, nombre = hallazgo
    orden = [ruta, f"--app={url}",
             f"--user-data-dir={carpeta_perfil()}",
             f"--window-size={ANCHO},{ALTO}",
             "--no-first-run", "--no-default-browser-check",
             "--disable-background-mode", "--disable-features=Translate,msEdgeSplashScreen",
             "--allow-file-access-from-files"]
    paso(f"abriendo la ventana con {nombre}: {ruta}")
    try:
        creation = 0
        if sys.platform.startswith("win"):
            creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.Popen(orden, creationflags=creation) if creation else \
            subprocess.Popen(orden)
    except Exception as exc:
        from .registro import fallo
        fallo(f"no se pudo lanzar {nombre}", exc)
        return None


def escribir_espera(url: str, registro: str) -> str:
    """Pagina de espera local: se ve al instante y salta sola a la app.

    La ventana tiene que aparecer en cuanto se hace doble clic, antes de que
    el motor de corte termine de cargar. Esta pagina se abre desde el disco
    (no necesita servidor) y va probando el servidor con una imagen: cuando
    responde, salta. Si no responde, lo dice y ensena donde esta el registro.
    """
    destino = os.path.join(carpeta_perfil(), "espera.html")
    html = (_HTML_ESPERA.replace("URL_DEL_SERVIDOR", url)
            .replace("RUTA_REGISTRO", registro)
            .replace("LOGO_BRUMET", logo())
            .replace("FONDO_ARRANQUE", fondo_oscuro()))
    with open(destino, "w", encoding="utf-8") as fh:
        fh.write(html)
    return destino


_HTML_ESPERA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Cortador</title>
<style>
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body { position: relative; display: flex; align-items: center; justify-content: center;
         background: #0b0b0d center / cover no-repeat url(FONDO_ARRANQUE);
         color: #f5f5f7;
         font-family: -apple-system, 'Segoe UI', Inter, system-ui, sans-serif;
         -webkit-user-select: none; user-select: none; }
  body::before { content: ''; position: fixed; inset: 0; pointer-events: none;
                 background: radial-gradient(ellipse at center,
                             rgba(11,11,13,.20) 0%, rgba(11,11,13,.66) 58%,
                             rgba(11,11,13,.95) 100%); }
  .caja { position: relative; z-index: 1;
          text-align: center; max-width: 640px; padding: 0 32px; }
  .marca { position: relative; display: inline-block; padding: 14px 26px; }
  .marca svg { height: 74px; width: auto; display: block; }
  .marca-texto { font-size: 34px; font-weight: 650; letter-spacing: .04em; }
  .hilo { position: absolute; left: 0; right: 0; height: 2px; border-radius: 2px;
          background: linear-gradient(90deg, transparent, #64d2ff 12%, #0a84ff 50%, #64d2ff 88%, transparent);
          box-shadow: 0 0 14px rgba(10,132,255,.85);
          animation: corta 2.6s cubic-bezier(.65,0,.35,1) infinite; }
  @keyframes corta { 0% { top: -6%; opacity: 0; } 12% { opacity: 1; }
                     88% { opacity: 1; } 100% { top: 106%; opacity: 0; } }
  .app { margin-top: 18px; font-size: 12px; letter-spacing: .34em;
         text-transform: uppercase; color: #8e8e93; }
  .nota { margin-top: 14px; font-size: 14px; color: #8e8e93; }
  #malo { display: none; margin-top: 26px; text-align: left; }
  #malo h2 { font-size: 18px; margin: 0 0 8px; }
  #malo p { color: #aeaeb2; font-size: 14px; line-height: 1.55; margin: 0; }
  code { display: block; margin-top: 12px; padding: 12px 14px; border-radius: 10px;
         background: #161619; color: #ff9f0a; font-size: 12.5px;
         white-space: pre-wrap; -webkit-user-select: text; user-select: text; }
</style></head>
<body>
  <div class="caja">
    <div class="marca">LOGO_BRUMET<span class="hilo"></span></div>
    <div class="app">Cortador</div>
    <div class="nota" id="nota">Preparando el motor de corte&hellip;</div>
    <div id="malo">
      <h2>El motor interno no ha arrancado</h2>
      <p>La ventana esta bien, pero el servidor local no responde. Suele ser el
         antivirus o el cortafuegos bloqueando 127.0.0.1. Cierra esta ventana,
         vuelve a abrir Cortador y, si sigue igual, manda este archivo:</p>
      <code>RUTA_REGISTRO</code>
    </div>
  </div>
<script>
  var destino = "URL_DEL_SERVIDOR";
  var intentos = 0;
  function probar() {
    intentos++;
    if (intentos > 150) {                       // ~2 minutos
      document.querySelector('.hilo').style.display = 'none';
      document.getElementById('nota').textContent = '';
      document.getElementById('malo').style.display = 'block';
      return;
    }
    // dos sondas: fetch sin CORS (falla solo si no hay servidor) y una
    // imagen, por si el navegador no deja hacer fetch desde un archivo local
    var listo = false;
    function saltar() { if (!listo) { listo = true; location.replace(destino); } }
    try {
      fetch(destino + 'api/version', { mode: 'no-cors', cache: 'no-store' })
        .then(saltar).catch(function () {});
    } catch (e) {}
    var img = new Image();
    img.onload = saltar;
    img.src = destino + 'static/logo.svg?t=' + Date.now();
    setTimeout(function () { if (!listo) probar(); }, 800);
  }
  probar();
</script>
</body></html>
"""
