// Cortador - aplicacion de escritorio (by Brumet)
//
// La ventana la pone Electron, que trae su propio Chromium: no depende de
// WebView2, ni de pythonnet, ni de que el antivirus deje correr un ejecutable
// empaquetado. Es la misma receta que ya funciona en Brumet Slicer.
//
// Por dentro se lanza el motor de corte (Python oficial embebido, en
// resources/motor) que sirve la interfaz en 127.0.0.1. Todo lo que dice el
// motor se guarda en el registro y, si algo falla, se ve en la ventana.

const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const fs = require('fs')
const os = require('os')
const net = require('net')
const http = require('http')

const TITULO = 'Cortador  ·  by Brumet'
const CARPETA_DATOS = path.join(
  process.env.LOCALAPPDATA || path.join(os.homedir(), '.local', 'share'), 'Cortador')
const REGISTRO = path.join(CARPETA_DATOS, 'arranque.log')

let ventana = null
let motor = null
let urlMotor = ''
let salidaMotor = ''

function anotar (texto) {
  const linea = `[${new Date().toISOString().slice(11, 19)}] ${texto}`
  try {
    fs.mkdirSync(CARPETA_DATOS, { recursive: true })
    fs.appendFileSync(REGISTRO, linea + '\n')
  } catch (e) { /* el registro nunca puede tumbar la app */ }
  if (ventana && !ventana.isDestroyed()) {
    ventana.webContents.send('paso', texto)
  }
}

function rutaMotor () {
  // instalado: resources/motor ; en desarrollo: escritorio/motor
  const candidatos = [
    path.join(process.resourcesPath || '', 'motor', 'python.exe'),
    path.join(__dirname, 'motor', 'python.exe'),
    path.join(process.resourcesPath || '', 'motor', 'bin', 'python3'),
    path.join(__dirname, 'motor', 'bin', 'python3')
  ]
  for (const ruta of candidatos) {
    if (ruta && fs.existsSync(ruta)) return ruta
  }
  return ''
}

function puertoLibre () {
  return new Promise((resolve) => {
    const s = net.createServer()
    s.listen(0, '127.0.0.1', () => {
      const puerto = s.address().port
      s.close(() => resolve(puerto))
    })
    s.on('error', () => resolve(8000 + Math.floor(Math.random() * 500)))
  })
}

function responde (url) {
  return new Promise((resolve) => {
    const peticion = http.get(url + 'api/version', (res) => {
      res.resume()
      resolve(res.statusCode === 200)
    })
    peticion.on('error', () => resolve(false))
    peticion.setTimeout(2000, () => { peticion.destroy(); resolve(false) })
  })
}

async function esperarMotor (url, segundos = 120) {
  const limite = Date.now() + segundos * 1000
  while (Date.now() < limite) {
    if (motor && motor.exitCode !== null) return false   // se murio por el camino
    if (await responde(url)) return true
    await new Promise(r => setTimeout(r, 400))
  }
  return false
}

function lanzarMotor (puerto) {
  const python = rutaMotor()
  if (!python) {
    anotar('ERROR: no encuentro el motor de corte (carpeta motor)')
    return null
  }
  anotar(`motor: ${python}`)
  const proceso = spawn(python, ['-m', 'cortador.cli', 'web',
    '--host', '127.0.0.1', '--puerto', String(puerto), '--sin-navegador'], {
    cwd: path.dirname(python),
    windowsHide: true,
    env: Object.assign({}, process.env, { PYTHONUNBUFFERED: '1', PYTHONUTF8: '1' })
  })
  const recoger = (datos) => {
    const texto = datos.toString()
    salidaMotor = (salidaMotor + texto).slice(-8000)
    texto.split('\n').filter(l => l.trim()).forEach(l => anotar('motor| ' + l.trim()))
  }
  proceso.stdout.on('data', recoger)
  proceso.stderr.on('data', recoger)
  proceso.on('exit', (codigo, senal) => {
    anotar(`el motor termino con codigo ${codigo} (senal ${senal})`)
    // Si el motor se muere con la ventana abierta, la pantalla se quedaria
    // girando para siempre: eso es justo lo que no puede pasar. El caso tipico
    // es un modelo enorme que agota la memoria y el sistema mata el proceso.
    if (cerrando) return
    const porMemoria = senal === 'SIGKILL' || codigo === 137 || codigo === 3221225477
    fallar(porMemoria
      ? 'El motor se ha quedado sin memoria y el sistema lo ha cerrado. ' +
        'Suele pasar con modelos de muchos millones de triangulos: prueba a ' +
        'bajar la altura del modelo, a subir el espesor de piel o a cerrar ' +
        'otros programas para dejarle mas memoria.'
      : `El motor se ha cerrado inesperadamente (codigo ${codigo}).`)
  })
  proceso.on('error', (err) => anotar(`ERROR al lanzar el motor: ${err.message}`))
  return proceso
}

/* ------------------------------------------------------------ actualizacion
   La app se actualiza sola: mira si hay version nueva en las Releases, se la
   baja por detras y la instala al cerrar. No hay que volver a descargar nada
   a mano ni desinstalar la anterior: se sobrescribe encima.                */
let cerrando = false        // para no gritar cuando el motor muere al salir
let actualizador = null

function prepararActualizador () {
  if (!app.isPackaged) return null          // en desarrollo no hay nada que actualizar
  try {
    const { autoUpdater } = require('electron-updater')
    autoUpdater.autoDownload = true         // que se la baje sin preguntar
    autoUpdater.autoInstallOnAppQuit = true // y se instale al cerrar
    autoUpdater.logger = null

    autoUpdater.on('checking-for-update', () => anotar('buscando actualizaciones'))
    autoUpdater.on('update-not-available', () => anotar('la version instalada es la ultima'))
    autoUpdater.on('update-available', (info) =>
      anotar(`hay version nueva: ${info && info.version}; descargando`))
    autoUpdater.on('download-progress', (p) => {
      const pct = Math.round(p.percent || 0)
      if (pct % 25 === 0) anotar(`descargando actualizacion: ${pct} %`)
    })
    autoUpdater.on('error', (e) => anotar('ERROR al actualizar: ' + (e && e.message)))
    autoUpdater.on('update-downloaded', (info) => avisarActualizacion(info))
    return autoUpdater
  } catch (e) {
    anotar('sin actualizador automatico: ' + e.message)
    return null
  }
}

function avisarActualizacion (info) {
  const version = (info && info.version) || ''
  anotar(`actualizacion ${version} lista para instalar`)
  const opciones = {
    type: 'info',
    buttons: ['Reiniciar e instalar', 'Al cerrar la app'],
    defaultId: 0,
    cancelId: 1,
    title: 'Cortador',
    message: `Cortador ${version} esta listo`,
    detail: 'La nueva version ya esta descargada. Se instala encima de la que '
          + 'tienes, sin desinstalar nada y sin perder tus ajustes.',
  }
  dialog.showMessageBox(ventana || null, opciones).then(({ response }) => {
    if (response === 0) {
      anotar('reiniciando para instalar la actualizacion')
      try { if (motor && motor.exitCode === null) motor.kill() } catch (e) { /* ya estaba */ }
      actualizador.quitAndInstall()
    }
  }).catch(() => { /* si el dialogo falla, se instala igual al cerrar */ })
}

function buscarActualizaciones () {
  if (!actualizador) return
  try {
    actualizador.checkForUpdates()
  } catch (e) {
    anotar('no se pudo buscar actualizaciones: ' + e.message)
  }
}


function esInterno (url) {
  return url.startsWith('file://') ||
         /^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?(\/|$)/.test(url)
}


function crearVentana () {
  ventana = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: TITULO,
    backgroundColor: '#0b0b0d',
    show: true,
    autoHideMenuBar: true,
    icon: path.join(__dirname, 'assets', 'icon.png'),
    webPreferences: { nodeIntegration: true, contextIsolation: false,
                      devTools: !app.isPackaged }
  })
  ventana.setMenuBarVisibility(false)

  // Los enlaces de fuera (el repositorio, una propina) se abren en el
  // navegador del sistema: la ventana de Cortador es para Cortador.
  ventana.webContents.setWindowOpenHandler(({ url }) => {
    if (!esInterno(url)) shell.openExternal(url)
    return { action: 'deny' }
  })
  ventana.webContents.on('will-navigate', (evento, url) => {
    if (esInterno(url)) return
    evento.preventDefault()
    shell.openExternal(url)
  })

  ventana.loadFile('espera.html')
  ventana.on('closed', () => { ventana = null })
}

async function arrancar () {
  crearVentana()
  anotar(`Cortador ${app.getVersion()} · ${process.platform} · electron ${process.versions.electron}`)

  const puerto = await puertoLibre()
  urlMotor = `http://127.0.0.1:${puerto}/`
  anotar(`puerto ${puerto}`)

  motor = lanzarMotor(puerto)
  if (!motor) return fallar('No encuentro el motor de corte dentro de la aplicacion.')

  const listo = await esperarMotor(urlMotor)
  if (!listo) return fallar('El motor de corte no ha llegado a responder.')

  anotar('motor listo · cargando la interfaz')
  if (ventana && !ventana.isDestroyed()) ventana.loadURL(urlMotor)

  // la actualizacion se busca despues, para no competir con el arranque
  setTimeout(() => {
    actualizador = prepararActualizador()
    buscarActualizaciones()
  }, 8000)
  if (process.env.CORTADOR_CAPTURA) capturar(process.env.CORTADOR_CAPTURA)
}

// Foto de la ventana ya cargada, para comprobar desde la compilacion que la
// aplicacion abre de verdad y no solo que el proceso arranca.
function capturar (destino) {
  setTimeout(async () => {
    try {
      const imagen = await ventana.webContents.capturePage()
      fs.writeFileSync(destino, imagen.toPNG())
      anotar('captura guardada en ' + destino)
    } catch (e) {
      anotar('ERROR al capturar: ' + e.message)
    }
    app.quit()
  }, 6000)
}

function fallar (mensaje) {
  anotar('ERROR · ' + mensaje)
  if (ventana && !ventana.isDestroyed()) {
    ventana.webContents.send('fallo', {
      mensaje,
      registro: REGISTRO,
      salida: salidaMotor.split('\n').slice(-25).join('\n')
    })
  }
}

ipcMain.handle('abrir-registro', () => shell.openPath(REGISTRO))
ipcMain.handle('version', () => app.getVersion())
ipcMain.handle('buscar-actualizacion', () => {
  if (!actualizador) actualizador = prepararActualizador()
  buscarActualizaciones()
  return app.getVersion()
})
ipcMain.handle('reintentar', () => { arrancar() })

app.on('before-quit', () => { cerrando = true })

app.whenReady().then(arrancar)

app.on('window-all-closed', () => {
  cerrando = true
  if (motor && motor.exitCode === null) {
    try { motor.kill() } catch (e) { /* ya estaba muerto */ }
  }
  app.quit()
})

app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) arrancar() })

process.on('uncaughtException', (err) => {
  anotar('ERROR no controlado: ' + (err && err.stack ? err.stack : err))
  try {
    dialog.showErrorBox('Cortador', `Cortador ha fallado al arrancar:\n\n${err}\n\nRegistro:\n${REGISTRO}`)
  } catch (e) { /* nada que hacer */ }
})
