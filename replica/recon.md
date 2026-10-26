# Recon map: LuBan (escritorio, Windows y Mac)

Alcance: el módulo **Mesh Processing**. Cuatro áreas, por orden de interés:
el **corte** en piezas imprimibles con conectores, las **cajas de luz**, los
**moldes de galleta** y los **rompecabezas**.
Para: Cortador, el complemento de Blender para talleres de impresión 3D.
Fecha: 2026-10-26

> **Esto no es un clon.** La intención, en palabras del dueño: *«no es
> copiarlo tal cual, es saber cómo realizan los cortes y mejorar todo
> apoyándome en Blender para tener más potencia»*. Se inventaría qué hace y
> con qué parámetros, para rehacerlo mejor. No se copia código, ni textos, ni
> imágenes.

> **Corrección (26-10).** En la primera pasada dije que el `LuBan_1.exe` del
> chat no era LuBan, y era falso: busqué los nombres de los módulos en UTF-16
> cuando están en ASCII. El ejecutable **sí es LuBan**, y lleva dentro su
> tabla de textos completa: los nombres de los modos, los de cada parámetro y
> los mensajes de error. Eso es lo que alimenta el apartado siguiente. Lo que
> me despistó fue el DICOM que lleva dentro, que está ahí porque importa
> tomografías para convertirlas en modelos.

---

## Fuentes

| # | fuente | URL | notas |
| --- | --- | --- | --- |
| 1 | sitio oficial | https://www.luban3d.com/ | **primaria**. Lista los módulos y los tipos de modelo generado |
| 2 | licencias oficial | https://www.luban3d.com/license | **primaria**. Precios y condiciones reales, distintos de los de la prensa |
| 3 | noticias oficial | https://www.luban3d.com/news | entradas sueltas (Thermal, Squama, Teacup, Photo clicker); no es un changelog de versiones |
| 4 | MeshSafe | https://www.luban3d.com/meshsafe | producto aparte del mismo equipo: firma oculta en la malla para rastrear autoría |
| 5 | Project LuBan (MIT DDF) | https://ddf.mit.edu/?p=814 | **el origen**. Prof. Lujie Chen (SUTD) y Prof. Lawrence Sass (MIT), 2018 |
| 6 | Make: | https://makezine.com/article/maker-news/luban-helps-you-make-big-stuff-with-your-3d-printer-or-laser/ | modos, ahuecado, paneles planos con juntas de dedo |
| 7 | Fabbaloo 2019 | https://www.fabbaloo.com/2019/05/luban-3d-printing-very-large-objects | editor de planos de corte, tipos de conector, guía de montaje |
| 8 | Fabbaloo 2025 | https://www.fabbaloo.com/news/luban-expands-3d-printing-tools-more-ways-to-customize-and-print-large-models | ampliación de funciones |
| 9 | Fabbaloo / Split3r | https://www.fabbaloo.com/news/split3r-launches-as-low-cost-alternative-to-luban-for-large-scale-3d-printing | competidor directo, licencia perpetua |
| 10 | 3Druck | https://3druck.com/en/programs/luban-extends-functions-for-3d-printing-more-possibilities-for-model-customization-55144165/ | cobertura de la ampliación de 2025 |
| 11 | foro PrusaSlicer | https://forum.prusa3d.com/forum/prusaslicer/large-model-splitting/ | voz de usuario: precio y alternativas gratis |
| 12 | guía Neural4D | https://blog.neural4d.com/user-guide/how-to-split-3d-model-into-parts/ | cómo resuelven esto PrusaSlicer y Blender |

**Fuentes que no se pudieron leer** y conviene recuperar:

- *Hello LuBan*, el manual completo (PDF en OneDrive, enlazado desde el sitio
  oficial). Es la fuente que más falta hace: OneDrive exige JavaScript y no se
  pudo descargar. **Todo lo marcado como confianza media o baja se resolvería
  con este documento.**
- *LuBan Get started.pdf*, en la carpeta «Doc» de las descargas.
- El canal de YouTube: https://www.youtube.com/channel/UChbeOwTaHYc8sxpPFp6g-nA
- Fabbaloo y 3Druck devuelven 403 a la lectura directa; su contenido llegó
  citado a través del buscador, no leído entero.
- **No se instaló ni se ejecutó el programa.** No hay cuenta ni licencia.

---

## Bucle principal

Cargar un modelo demasiado grande para la máquina, colocarle planos de corte
hasta que las porciones quepan, generar conectores automáticos en las juntas,
y exportar las piezas numeradas con una secuencia de montaje.

---

## El producto completo (para situar el alcance)

LuBan no es un partidor de figuras: es una suite. El sitio oficial lista
cuatro módulos:

| módulo | qué hace |
| --- | --- |
| Eyeglasses | diseña monturas de gafas a partir de una imagen plantilla |
| Lithophane | convierte una foto en una pieza imprimible |
| Photo Magic | genera modelos 3D a partir de una foto |
| **Mesh Processing** | **genera modelos a partir de un modelo 3D existente** ← lo nuestro |

Y siete formas de modelo generado: *lithophane, stack, hash, plate, relief,
**module**, wireframe*. El sitio las nombra y no las explica. Por lo que
describen el proyecto del MIT y Make:, y a falta del manual:

- **stack** — rebanadas planas apiladas, para cortar en láser y apilar
- **plate** — paneles planos con juntas de dedo (*finger joints*)
- **module** — la partición en piezas sólidas imprimibles ← **lo nuestro**
- **hash / relief / wireframe** — otras descomposiciones (rejilla, relieve,
  estructura de alambre)

Fabricación declarada: impresión 3D, corte láser y fresado CNC.

**El origen importa.** Project LuBan nació en el MIT Digital Design
Fabrication Group con SUTD en 2018, para prototipos de más de un metro con
materiales baratos y máquinas sencillas. Descomponía por *contouring*,
*cross-contour slicing* y *finger jointing*, y —esto es lo relevante—
**empaquetaba las piezas en hojas del tamaño que pidiera el usuario**. Es
decir: el empaquetado contra el tamaño de la plancha estaba en el ADN del
proyecto desde el principio. Es justo lo que Cortador hace peor.

---

## Inventario desde el propio programa

Sacado de la tabla de textos del ejecutable: los rótulos de los diálogos, los
nombres de los parámetros y los mensajes de error. Es, en la práctica, leer
los menús del programa sin abrirlo. **No se ha decompilado nada**: no hay
código desensamblado aquí, y no lo habría a un coste razonable —son 20 MB de
C++ con CGAL dentro—. El flujo, en sus propias palabras:
`File -> Open the model, then Mesh -> LuBan`.

### Los 21 modos de Mesh Processing

`Block · Clicker · Cocoon · Connectors · Contour · Folding · Grill · Hash ·
Helix · Pipe · Pipes · Relief · Revolving · Slide · Spinner · Spring · Stack ·
Tiling · Tumbler · Wave · Wireframe`

Y los patrones de teselado: `Triangle · Square · Pentagon · Hexagon ·
Octagon · Quadrangle · Voronoi`.

El sitio web sólo nombraba siete formas. Son veintiuna.

### Corte y uniones

Formas de conector **reales**, leídas del programa: `Plug · Dowel · Clip ·
Puzzle · Pyramid`. La prensa hablaba de *terrace*; esa palabra no aparece por
ningún lado, y en cambio sí `Clip` y `Puzzle`, que nadie había mencionado.

Parámetros alrededor del corte y las uniones:

`Dowel size · Tolerance · Socket width · Socket height · Tab size · Dual ·
Separation · Slide width · Axle diameter · Bury · Finger width · Base offset ·
Top offset · Base height · Top height · Position (-1,1) · Direction ·
Offset X/Y/Z`

Piezas y nombres de salida: `Part_1`, `Part_2`, `Plane`, `Conn_`, `Pipe_`,
`Outer`, `Inner`, `Body`.

Avisos que da cuando algo no cabe —útiles, porque dicen dónde están sus
límites—: *«Tolerance must be less than half of the slide width»*,
*«Tolerance must be less than half of the sheet thickness»*, *«Boolean
operation failed»*, *«Try changing the tolerance slightly»*.

Ese último par importa: **LuBan también se pelea con los booleanos**, y
también resuelve la holgura como fracción del espesor. Es exactamente el
problema que dio las espigas de Cortador.

### Empaquetado en hojas

Diálogos `Dlg_Nest` y `Dlg_Nest3D`. Etiquetas `Sheet_`, `G_sheet_`,
`B_sheet_`, `BEGIN_PLATE`, `END_PLATE`, y el error *«Failed to generate
plates»*, *«Sheet width is too large»*, *«Sheet height is too large»*.

**Hay empaquetado en 2D y en 3D, en diálogos separados.** Es lo que falta en
Cortador, y es la función con la que nació el proyecto en el MIT.

### Cajas de luz

`Box inner height · Box thickness · Lid · Lip thickness · Stopper width ·
Base of color · Color layer · Solid top · Layer height · Layer offset ·
Reinforced bar · Bar thickness · Slit width · Chamber height · Duct gap ·
Duct length · Opening · Wire width · Base light socket · Backlight ·
Text 1 / Text 2 / Text 3 · Text baseline · Level of detail · Ridge scale ·
Width in X · Depth in Y · Height in Z · X/Y/Z section · Clipping`

Avisos: *«Box thickness too big»*, *«Big thickness, strong color»*.

No es sólo un litofano: es la **caja entera** —tapa con labio, tope, hueco
para el portalámparas, conducto del cable, barra de refuerzo— con hasta tres
textos y línea base.

### Moldes de galleta

`Number of blades · Blade angle · Blade length · Blade width · Blade root
width · Blade thickness · Blade height · Shaft diameter · Shaft length ·
Tolerance · One body · Assembly · Base offset · Bottom offset · Brim ·
Contour width · Base thickness`

Con una nota del propio programa que explica su tolerancia: *«A negative
value compensates for material expansion in 3D printing of the shaft hole»*.

Dos modos de salida: **One body** (todo de una pieza) y **Assembly** (cortador
y mango por separado, unidos por un eje). Prefijos `BC_ONE`, `BC_NB`,
`BC_BA`, `BC_BL`, `BC_BW`.

### Rompecabezas y piezas que encajan

`Tab size · Dual · Cell · Cell size X · Cell size Y · Block size · Wall
thickness · Clicker size XY · Pressed length · Base size XY · Base length ·
Max fold · Thickness · Scale X/Y · Angle X/Y/Z`

Avisos: *«The position should have one contour only»*, *«The model size is
too small for the clicker»*, *«Position must be in between (-1, 1)»*.

`Clicker` es un mecanismo de clic impreso —de ahí *Pressed length*—, no un
rompecabezas plano. El rompecabezas propiamente dicho sale de `Puzzle` como
forma de conector y de `Tab size`.


## Pantallas

**Advertencia de honestidad:** no hay inventario real de pantallas. No se
instaló el programa y no se consiguieron capturas (Fabbaloo bloquea la
lectura directa y no se descargó nada). `replica/screens/` está vacía. Lo que
sigue está **inferido de descripciones de terceros** y no sirve para copiar
una interfaz, sólo para saber qué piezas de interfaz existen.

| ID | pantalla | cómo se llega | para qué | componentes | estados | confianza |
| --- | --- | --- | --- | --- | --- | --- |
| S01 | selector de módulo | al abrir | elegir Eyeglasses / Lithophane / Photo Magic / Mesh Processing | lista de módulos | — | media |
| S02 | editor de corte de malla | Mesh Processing → module | colocar planos de corte sobre el modelo | visor 3D girable, lista de planos, controles de plano | vacío, con planos, porción que no cabe | media |
| S03 | ajustes de conector | dentro de S02 | elegir forma, profundidad y tolerancia | selector de forma (plug/dowel/terrace/pyramid), numéricos | — | alta |
| S04 | resultado y guía de montaje | tras generar | ver piezas numeradas y la secuencia | lista de piezas, numeración, secuencia | — | media |
| S05 | exportación | tras S04 | guardar ficheros | diálogo de guardado | limitado a 1 MB sin licencia | alta |
| S06 | Help → About | menú | leer el License ID para registrar | texto con el ID entre llaves | sin licencia / registrado | alta |

---

## Flujos

```
F01  Partir una figura grande en piezas imprimibles
     S01 selector -> S02 editor de corte -> S03 conectores -> S04 guía -> S05 exportar
     clics del camino feliz: desconocido (no se ejecutó el programa)
     borde: una porción sigue sin caber; conector que no cabe en la pared;
            modelo con la malla rota; sin licencia, exportación limitada a 1 MB

F02  Registrar la licencia
     S06 Help->About (copiar License ID con las llaves y el sistema operativo)
     -> formulario web o correo -> esperan hasta 48 h -> registrado
     nota: las licencias temporales exigen conexión a internet; la permanente
           y la de USB, no
```

---

## Componentes

| componente | variantes | estados | dónde |
| --- | --- | --- | --- |
| Visor 3D girable | — | vacío, con modelo, con planos | S02 |
| Plano de corte | libre, por eje | activo, inactivo | S02 |
| Selector de conector | plug, dowel, terrace, pyramid | — | S03 |
| Numérico con tolerancia | profundidad, tolerancia geométrica | — | S03 |
| Lista de piezas numeradas | — | — | S04 |

---

## Modelo de datos inferido

No es una aplicación con base de datos: es un programa de escritorio con un
documento. Lo que sigue es el modelo del **documento**, que es lo que de
verdad se puede comparar con Cortador.

```
Proyecto     modelo de entrada, máquina (tamaño de cama), unidades
             evidencia: S01, el propio bucle principal
             confianza: alta

Malla        geometría de entrada; formatos de entrada y salida desconocidos
             evidencia: "genera modelos 3D a partir de un modelo existente"
             confianza: media (los formatos no están publicados)

PlanoDeCorte posición, orientación; puestos a mano, varios por modelo
             evidencia: fuente 7, "add cutting planes wherever you like"
             confianza: alta

Pieza        geometría, número de orden, posición en la secuencia de montaje
             evidencia: fuente 7, numeración y secuencia
             confianza: alta

Conector     forma (plug | dowel | terrace | pyramid), profundidad,
             tolerancia geométrica, macho/hembra, a qué junta pertenece
             evidencia: fuente 7, literal sobre formas, profundidad y tolerancia
             confianza: alta

Hoja/Plancha empaquetado de piezas planas en hojas del tamaño pedido
             evidencia: fuente 5 (MIT), "packs the parts onto individual
             sheets in the sizes the user specifies"
             confianza: alta para el proyecto del MIT, media para el producto
```

Relaciones: Proyecto 1-n Malla · Malla 1-n PlanoDeCorte · Malla 1-n Pieza ·
Pieza 1-n Conector · Conector 2 Pieza (macho y hembra) · Pieza n-1 Hoja

---

## Precio y licencia (fuente primaria, 2026)

Esto corrige a toda la prensa, que da cifras más bajas y viejas.

| licencia | precio | notas |
| --- | --- | --- |
| sin registrar | — | funciona, pero sólo guarda ficheros de hasta 1 MB |
| prueba | gratis | 30 días con todo; se pide por formulario, responden en hasta 48 h |
| un mes | 30 USD | exige conexión a internet |
| un año | 150 USD | exige conexión a internet |
| permanente | 750 USD | sin conexión, actualizaciones gratis para siempre |
| USB | 1 200 USD | llave física; Windows 7/10 y Mac OS 10/11. **Linux no está soportado** |

Mover la licencia de ordenador es gratis. Los pagos de renovación se acumulan
y convierten la licencia en permanente al llegar a su precio. La página no
pone ninguna restricción sobre uso comercial ni sobre construir un producto
que compita.

La prensa de 2025 decía 25 / 125 / 625 USD y la de 2019 decía 30 USD al año y
150 permanente. **Vale la del sitio oficial.**

---

## Matriz de funciones

En `replica/features.csv`. La columna `clone` es el estado **de Cortador hoy**,
no de un clon por construir.

Must: 10 · Should: 7 · Could: 5 · Skip: 7

---

## Fuera de alcance

Cosas de LuBan que no se tocan, y por qué:

- **Eyeglasses, Photo Magic, Teacup, Squama, Thermal, Photo clicker** — son
  otro producto. (El **litofano** ya no está fuera: entra como parte de las
  cajas de luz.)
- **MeshSafe** — firma oculta en la malla para rastrear quién compró un
  modelo. Producto aparte, y problema ajeno a un taller que imprime lo suyo.
- **Corte láser y fresado CNC** (modos *stack*, *plate*, *hash*, *relief*,
  *wireframe*) — Cortador es para impresión 3D. Si algún día entra el láser,
  se replantea.
- **Llave USB y el aparato de licencias** — Cortador es un complemento
  gratuito dentro de Blender.
- **Su interfaz** — no se ha visto, no se va a copiar, y Cortador vive en el
  panel lateral de Blender, que es otra cosa.

---

## Tamaño

Pantallas 6 (inferidas) · flujos 2 · entidades 6.

**Lo difícil, por orden:**

1. **Empaquetar contra el tamaño de la cama.** Es lo que el proyecto del MIT
   hacía desde el principio y lo que Cortador hace peor (41–45 % de
   aprovechamiento en figuras tipo estatua). No es un conector ni un botón:
   es rediseñar el reparto de gajos.
2. **Conectores con forma.** Cortador ya saca el cilindro (*dowel*). Faltan
   *terrace* —escalón, que resiste tracción— y la tolerancia configurable.
   *Plug* y *pyramid* son variantes del mismo problema geométrico.
3. **Planos de corte a mano.** Cortador es totalmente automático. Poder decir
   «este corte aquí no, que parte la cara» es un hueco real, y en Blender se
   puede resolver con objetos vacíos como guía en vez de con una interfaz 3D
   propia.

**Tamaño: M** para los conectores con forma y los planos manuales. **L** para
el empaquetado, y además con riesgo de romper lo que ya funciona.

Siguiente paso previsto por el paquete: `/replica-architect`. **Aquí no
aplica**: no hay stack que elegir ni base de datos que diseñar, el programa ya
existe y es Python dentro de Blender. El siguiente útil es
`/replica-entrepreneur`, para leer qué les reprochan los usuarios reales a
LuBan y a Split3r antes de decidir en qué orden se construye.
