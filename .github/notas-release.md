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

- **La vista previa ya no engana.** Para que todo cupiera en su presupuesto de
  triangulos, el visor aligeraba cada pieza; en una piel de 3 mm eso funde las
  dos caras y la pared desaparece. Los STL estaban bien, pero **en pantalla se
  veia un amasijo de picos**. Ahora una pieza solo se aligera si sigue siendo la
  misma pieza -cerrada y con el mismo volumen- y el techo de triangulos es ocho
  veces mayor.

- **El espesor de la pared se mide y se dice.** En un escaneo, la cara de fuera
  tiene relieve y la de dentro es lisa, asi que la pared no puede medir lo mismo
  en todas partes. En vez de prometerlo, Cortador siembra puntos por toda la
  piel, mide lo que hay hasta la superficie y te dice el resultado y que espesor
  pedir para que el minimo sea el que quieres. Probado: si pides 3 y el 1 % mas
  fino sale en 1,2, pidiendo 4,8 sale en 3,05.

- **El corte usa todos los nucleos** y el vaciado tambien. En un escaneo de
  1,3 M de triangulos con cuatro nucleos: 157 s -> 133 s el corte, y x2,9 el
  encogido de contornos.

- **Menos memoria.** El vaciado por capas llegaba a diez gigas y el sistema
  mataba el proceso. Ahora las rebanadas se guardan como triangulos sueltos en
  vez de como mallas y se sueltan en cuanto no hacen falta.

- **Si el motor se muere, la ventana se entera.** Antes se quedaba girando para
  siempre; ahora dice que ha pasado y por que.

- **Los ajustes del laminador hablan del ventilador.** Con 0 % de relleno, las
  capas que cierran sobre el hueco van en puente: no hace falta relleno para
  sostenerlas, hace falta ventilador de capa a tope y velocidad de puente baja.

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
