# Cortador — aplicacion de escritorio

La ventana de Cortador, hecha con Electron (el mismo enfoque que Brumet
Slicer). Dentro lleva el motor de corte: un Python oficial embebido con el
paquete `cortador` y sus librerias.

```
escritorio/
  main.js        arranca el motor, espera a que responda y carga la interfaz
  espera.html    pantalla de espera y, si algo falla, el motivo y el registro
  motor/         Python embebido + Cortador  (lo genera el script, no va a git)
```

## Probarla en local (Windows)

```bash
python packaging/motor_embebido.py   # arma escritorio/motor (~1 min)
cd escritorio
npm install
npm start
```

## Construir el instalador

```bash
cd escritorio
npm run build        # deja dist/Cortador-Setup.exe
```

En GitHub Actions lo hace el trabajo `escritorio` de *Construir la app*.

## Por que asi

El motor se lanza como `motor\python.exe -m cortador.cli web --puerto N
--sin-navegador` y la ventana carga `http://127.0.0.1:N`. Todo lo que el motor
escribe se guarda en `%LOCALAPPDATA%\Cortador\arranque.log` y se ve en la
ventana si el arranque falla: la aplicacion no puede cerrarse sin decir por que.
