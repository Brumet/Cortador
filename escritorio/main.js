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
  proceso.on('exit', (codigo) => anotar(`el motor termino con codigo ${codigo}`))
  proceso.on('error', (err) => anotar(`ERROR al lanzar el motor: ${err.message}`))
  return proceso
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
ipcMain.handle('reintentar', () => { arrancar() })

app.whenReady().then(arrancar)

app.on('window-all-closed', () => {
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
