# Lo que la gente odia, lo que le falta, y por dónde empezar

**Tamaño de la muestra, antes que nada: 15 citas de 4 personas en 1 hilo de
foro.** No son cien reseñas de tres fuentes. LuBan no tiene ficha en App
Store ni en Google Play, no está en G2 ni en Capterra, Hacker News no habla
de él —sus resultados son el carpintero chino del siglo V a.C.— y Reddit está
bloqueado para la herramienta de lectura. La propia herramienta marca los
siete temas como **thin** y avisa: *«Small sample. Under 30 reviews supports a
direction, not a ranking»*. Tómalo como una dirección, no como un ranking.

Todas las citas son literales y salen del mismo sitio:
https://forum.prusa3d.com/forum/prusaslicer/large-model-splitting/

---

## 1. Lo que odian

**El precio.** 3 citas.
> «This software is insanely expensive. They want $500 for a lifetime license.»
> «While the LuBan's $500 price tag may be daunting»

**Tener que repetir el corte a mano.** 3 citas. El tema con más carga real.
> «What it doesn't let you do is split it along multiple planes
> simultaneously, or using a grid.»
> «Instead I have to repeat the process multiple times and risk screwing
> something up in the process.»

**Que las herramientas se caen pasada la docena de piezas.** 3 citas.
> «In short the cut tool in prusaslicer is only useful if you are cutting
> something into no more than 3 parts.»
> «I have to cut some things into 18-20 and that's just too much of a
> headache.»
> «It's not too hard up to a dozen or so parts»

**No poder ver si la pieza cabe sin exportarla.** 1 cita.
> «I hate that I have to import into a slicer to check fit when cutting in
> grid mode.»

**La interfaz.** 1 cita.
> «The user interface isn't as good as prusaslicer»

## 2. Lo que piden

**Que el programa decida los cortes a partir del volumen de impresión.** 1
cita, y es la más importante de todas:
> «I can't just tell it my printer's build volume and then have it decide
> cut lines»

**Eso es exactamente lo que Cortador ya hace.** Le dices la máquina y él
reparte. Es la función que el usuario de pago está pidiendo a gritos y que
ninguna de las dos herramientas que menciona —LuBan a 500 dólares,
PrusaSlicer gratis— le da.

## 3. Lo que no resuelve nadie

- **La tirada en serie.** Todas las herramientas están pensadas para *una*
  figura. Nadie habla de numerar, marcar y documentar 50 piezas para que otra
  persona las monte sin preguntar. Cortador ya graba el nombre dentro de cada
  pieza y saca el PDF de montaje; no he encontrado que ningún competidor lo
  haga.
- **El taller que no es el que modeló.** «Se apañan con Meshmixer, TinkerCAD,
  Fusion 360, Gimp y OpenSCAD»: cinco programas para una tarea. Quien imprime
  no suele ser quien modela.

---

## 4. Dos hallazgos que pesan más que las reseñas

### Hay una patente activa de Disney sobre esto

**US10025882B2, «Partitioning models into 3D-printable components».**
Cesionaria: Disney Enterprises Inc. Inventores: Ilya Baran, Linjie Luo,
Wojciech Matusik. Presentada el 14-08-2012, concedida el 17-07-2018,
**activa, con expiración ajustada al 21-10-2035**.
https://patents.google.com/patent/US10025882

La reivindicación 1, en claro: generar un conjunto de **cortes planos
candidatos**, puntuar cada uno con una o más **funciones objetivo**, elegir
uno según esa puntuación, y repetir sobre las piezas que sigan sin caber
hasta que todas quepan. Las dependientes añaden el árbol BSP y la colocación
de conectores por optimización aproximada.

Es el algoritmo *Chopper* del MIT, patentado. **Y es justo el diseño que yo
iba a proponer** para arreglar el aprovechamiento de la cama: buscar planos
candidatos y puntuarlos.

Lo que hace Cortador hoy **no es eso**: no genera candidatos ni los puntúa,
calcula un reparto determinista —pisos por altura útil y gajos por el ángulo
que cabe en la cama— y sólo al final parte por la mitad lo que se pasa. Es
una diferencia de fondo, no de matiz, y conviene conservarla.

**No soy abogado y esto no es un consejo legal.** Lo que sí digo como
ingeniero: el camino de «generar candidatos y puntuarlos» queda descartado
del plan, y si algún día vendes el complemento o lo usas en producción
comercial fuera de casa, esto lo mira un abogado de patentes en Colombia y en
los países donde vendas.

### Ya hay un competidor dentro de Blender, y cuesta 22 dólares

**Split-3DPrint**, de AUER, para Blender 4.2+.
https://superhivemarket.com/products/split-3dprint

Trae, con sus palabras: 18 perfiles de impresora con la cama dibujada en el
visor y **las piezas que no caben en rojo**; conector de clavija cónica más
casquillo; **huecos para imanes de neodimio** de 5×2 a 10×3 mm, cortados 0,1
mm más grandes para que entren a presión; holgura en milímetros reales;
vista explosionada y vista de bandeja; exportación de un STL o 3MF por pieza.

Pero **corta a mano**: *«Straight, freehand and 360° loop cutting, only the
part under your stroke is cut»*. Dibujas la línea tú. No decide nada.

O sea: hace bien lo que LuBan hace, por 22 dólares en vez de 750, y deja sin
resolver exactamente lo mismo —lo que el usuario del foro pedía—. Y además
tiene dos ideas que conviene robar: **la cama dibujada en el visor con las
piezas que no caben en rojo**, y **los huecos para imán**, que para pegar una
figura grande son mejores que una espiga.

---

## 5. El plan, de lo más fácil a lo más difícil

El orden lo pide el dueño: empezar por lo fácil e ir subiendo. Coincide
razonablemente con el riesgo: lo primero no toca el motor de corte y por
tanto no puede romper nada de lo que ya funciona.

| # | qué | tamaño | riesgo | por qué ahí |
| --- | --- | --- | --- | --- |
| 1 | **Molde de galleta** | S | ninguno | Módulo nuevo e independiente. Contorno 2D, cuchilla extruida, base y mango. No toca el corte ni los booleanos de malla pesada. Se vende mañana |
| 2 | **Cama en el visor, piezas que no caben en rojo** | S | bajo | Cortador ya sabe cuáles no caben; sólo falta enseñarlo. Lo pide la cita de «check fit» y lo tiene el competidor |
| 3 | **Huecos para imán** | S | bajo | `espigas.py` ya coloca cilindros en las juntas; un imán es un cilindro con otras medidas y sin macho |
| 4 | **Caja de luz** | M | ninguno | Módulo nuevo: litofano por capas más la caja con tapa, labio, tope, portalámparas y conducto |
| 5 | **Conectores Clip y Puzzle** | M | medio | Extiende `espigas.py`, que ya va por el camino frágil del booleano. Resisten tracción; el cilindro no |
| 6 | **Rompecabezas por celdas** | M | medio | Reutiliza el conector Puzzle del punto 5 |
| 7 | **Empaquetado contra la cama** | L | **alto** | Lo más valioso (41–45 % de aprovechamiento hoy) y lo que puede romper lo que funciona. Y hay que diseñarlo sin pasar por la patente |

## 6. El ángulo

Tres opciones, cada una apoyada en un tema de arriba:

**A. El que decide por ti.**
> Para el taller que corta figuras en 18 o 20 piezas y se encuentra con que
> toda herramienta se rinde pasada la docena, Cortador decide los cortes a
> partir del volumen de tu impresora, gratis y dentro de Blender.
> Evidencia: «se cae pasada la docena» (3 citas) y «que decida los cortes a
> partir del volumen» (1 cita), 1 fuente.

**B. El que piensa en quien monta.**
> Para quien imprime en serie y entrega a otro para que lo monte, Cortador
> graba el nombre dentro de cada pieza y saca el plano de montaje en PDF.
> Evidencia: nadie lo hace; vacío observado, no citado.

**C. El gratis.**
> Para quien no va a pagar 750 dólares por partir una figura.
> Evidencia: precio (3 citas), 1 fuente.

**Recomiendo la A**, con la B de segunda frase. La C es cierta pero es la
peor: competir por precio contra un complemento de 22 dólares no es una
posición, y además Cortador ya es gratis, así que no hay nada que anunciar.

Lo que **no** se hace: poner el nombre de LuBan en el del complemento, ni en
su descripción, ni usar las frases de esas personas como testimonios. Son
investigación, no publicidad.
