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

- **Una placa mas fina que la pared se queda maciza.** El faldon de una armadura
  son cuatro milimetros: al vaciarlo con 3 mm de pared quedaban dos superficies
  pegadas sin nada entre medias. En pantalla se veian como franjas que
  parpadeaban, el laminador rechazaba la pieza y ahi no habia nada que imprimir.
  Ahora se mide y, si hay membranas, esa zona no se vacia. Medido: del 10 % de
  la piel en membrana al 0,7 %, con un 8 % mas de material.

- **Se corta por los estrechamientos.** Antes los planos caian a partes iguales,
  aunque eso partiera un muslo por la mitad. Ahora Cortador mira la figura y
  mueve cada corte al tobillo, la muneca o el cuello mas cercano -siempre que la
  pieza siga cabiendo-: la cara de corte es mucho mas pequena, la junta se
  disimula en el cambio de forma y las piezas encajan casi solas.

- **Modelos de resina muy pesados.** Una figura de 5,2 millones de triangulos
  entera: 48 s cargar, 133 s cortar, 14 s la vista previa. Los hilos se limitan
  ahora por el tamano de la malla y no solo por los nucleos, porque cada hilo se
  queda con su banda y la memoria se multiplica. Y la vista previa vuelve a
  aligerar las piezas macizas, que se habian quedado sin aligerar.

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
