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

Funciona **sin conexion a internet** y todo se procesa en tu propio equipo:
ningun modelo se sube a ningun servidor.

### Novedades de esta version

- **Perfiles de maquina**: FLSUN V400, T1 y SR, Bambu A1 y A1 mini, genericas y
  dos de resina. Cada uno con su margen de seguridad: ninguna pieza se planifica
  al raz de la cama.
- **Camas redondas (delta)**: en una FLSUN no cabe el diametro del plato, sino el
  cuadrado que entra dentro. Ahora se calcula bien: una V400 admite piezas de
  200 mm de lado, no de 300.
- **La boquilla manda sobre el espesor de la piel**: 0,4 y 1,0 no imprimen igual,
  y la pared se ajusta al multiplo exacto del ancho de linea.
- **Giro del modelo** antes de cortar, en cualquier eje, o apoyando sola la cara
  mas grande.
- **Ensamble macho/hembra en rebanadas**: el pasador se encoge para caber en la
  lamina y en la pared, y la cara que va contra la cama sigue siendo plana.
- **Resina** como tecnica aparte: pared fina, holgura minima y piezas pequenas.
- La pantalla de arranque lleva contador y avisa si tarda mas de lo normal.

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
