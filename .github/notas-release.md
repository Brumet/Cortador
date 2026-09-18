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

- **Se arregla el vaciado de escaneos grandes.** Un lobo de 1,9 M de triangulos
  a 1,9 m salia en 220 piezas rotas, 0,3 L de material y un "100 % menos" que
  era imposible. Eran cuatro fallos encadenados: soldar la piel la rompia,
  cortar una cascara con el recorte rapido dejaba agujeros, el material se
  contaba sumando solo las piezas cerradas (las demas valian cero) y el limite
  para dar por buena una piel era un porcentaje fijo que una figura de dos
  metros nunca alcanza. En el mismo modelo: **de 158 piezas abiertas a
  ninguna**, y el material que se anuncia es el que se va a gastar.

- **La vista previa ya no engana.** Para que todo cupiera en su presupuesto de
  triangulos, el visor aligeraba cada pieza; en una piel de 3 mm eso funde las
  dos caras y la pared desaparece. Los STL estaban bien, pero **en pantalla se
  veia un amasijo de picos**. Ahora una pieza solo se aligera si sigue siendo la
  misma pieza, y el techo de triangulos es ocho veces mayor.

- **El corte usa todos los nucleos.** Las bandas se reparten entre hilos. En un
  escaneo de 1,3 M de triangulos con cuatro nucleos: **157 s -> 133 s**.

- **Vaciado por capas, de reserva.** Si el desplazamiento de la superficie no
  entrega una piel cerrada, se corta el modelo en secciones, se encoge cada una
  y se apilan. Encoger un contorno plano no puede cruzarse nunca. Y si nada
  funciona, las piezas salen macizas y se dice por que: **nunca se entregan
  esquirlas**.

- **La pared nunca llega a cero.** Donde el modelo es mas fino que dos paredes,
  antes quedaban dos caras pegadas sin material entre ellas y el laminador
  rechazaba la pieza. Ahora queda pared fina, pero pieza cerrada.

- **Se quita el vaciado trozo a trozo**, que era lo que llenaba el centro de la
  figura de cajitas huecas.

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
