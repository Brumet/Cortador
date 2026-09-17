## Cortador — by Brumet

Corta modelos 3D para gran formato: los parte en piezas que caben en tu
impresora o en laminas del espesor que quieras, y marca cada pieza con su
nombre para que puedas armarla despues.

### Descargas

| Archivo | Para que |
|---|---|
| **Cortador-Setup.exe** | **Instalador de Windows.** Doble clic y listo: acceso directo en el menu Inicio y en el escritorio, y desinstalador. No pide permisos de administrador. |
| **Cortador-Windows.exe** | Version portable: un solo archivo, sin instalar nada. |
| **Cortador-Linux** | Linux. `chmod +x Cortador-Linux && ./Cortador-Linux` |
| **Source code (zip)** | El codigo completo, para instalarlo con Python o modificarlo. |

Se abre en **su propia ventana**, no en el navegador.

### Novedades de esta version

- **Arranca en un segundo**: la version instalada ya no se descomprime entera
  en cada apertura, y la ventana aparece nada mas hacer doble clic.
- **Nunca falla en silencio**: cada arranque queda escrito en
  `%LOCALAPPDATA%\Cortador\arranque.log` y, si algo va mal, se ve el motivo
  en la propia ventana o en un aviso. En el menu Inicio hay accesos directos a
  *Registro de arranque* y *Diagnostico de Cortador*.
- El instalador avisa si al equipo le falta **WebView2** (el motor de la ventana).

Funciona **sin conexion a internet** y todo se procesa en tu propio equipo:
ningun modelo se sube a ningun servidor.

### Que trae

- **Espesor de la malla**: solidifica la piel del modelo (como el *Solidify* de
  Blender) y deja el interior hueco. El laminador solo hace perimetros, sin
  relleno: en un gorila de 1,80 m, **22 litros en vez de 1.024**.
- **El corte siempre a la medida de tu impresora**: ninguna pieza se sale de la cama.
- Altura final del modelo ajustable (escala a 1,80 m y corta).
- `AJUSTES_LAMINADOR.txt` con el relleno al 0 % y los perimetros exactos.
- **Marcas grabadas** con el nombre de cada pieza en las caras de corte.
- Pasadores de alineacion opcionales.
- Reparacion automatica de la malla y atajo a **3D Builder** de Windows.
- Exporta **STL**, OBJ, PLY, 3MF y, en modo lamina plana, **SVG y DXF** para laser.
- Guia de armado, CSV del despiece y vista previa 3D.

Codigo libre con licencia MIT.
