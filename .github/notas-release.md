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

- **La app se actualiza sola.** A partir de esta version, cuando salga una
  nueva Cortador se la baja solo y la instala encima, sin desinstalar nada.
  Esta es la ultima que hay que instalar a mano.

- **El vaciado ya sirve para escaneos.** Con mallas densas y rugosas (un escaneo
  con pelo, por ejemplo) la pared interior salia como un erizo de puas y el
  modelo se quedaba en migajas mientras la app decia "100 % menos de material".
  Ahora la cara de dentro se calcula sobre una copia suavizada y **queda lisa**;
  el exterior conserva todos sus triangulos. Y si el vaciado sale mal, se dice,
  en vez de entregar esquirlas.
- **Se arregla el corte hueco, que estaba al reves.** Antes se cortaba primero y
  se vaciaba cada trozo despues, asi que cada pieza salia como una cajita
  cerrada, con paredes en las caras de corte, y los trozos del centro eran cubos
  huecos que no aportaban nada. Ahora se vacia el modelo entero y se corta esa
  piel: cada pieza es un trozo de cascara. En Brumo a 1,80 m, **23 litros en vez
  de 57,8**.
- Perfiles de maquina (FLSUN V400, T1 y SR, Bambu A1 y A1 mini, genericas y dos
  de resina), todos con margen de seguridad.
- **Camas redondas**: en una delta cabe el cuadrado inscrito, no el diametro.
- El **espesor de la piel sale de la boquilla**, siempre multiplo del ancho de linea.
- **Giro del modelo** antes de cortar.
- **Macho y hembra en rebanadas**, ajustado al espesor de la lamina.
- Contador y aviso de lentitud en la pantalla de arranque.

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
