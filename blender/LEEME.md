# Cortador para Blender

Corta una figura grande en piezas que caben en la impresora, sin salir de
Blender.

## Instalar

1. Descarga `cortador-blender.zip` (o comprime la carpeta `cortador_blender`).
2. En Blender: **Editar → Preferencias → Complementos → Instalar desde
   disco**, y elige el zip.
3. Actívalo. Aparece en la **barra lateral de la vista 3D** (tecla `N`),
   pestaña **Cortador**.

Funciona en Blender 3.6 y posteriores. En 4.2 y posteriores se instala como
extensión.

## Cómo se usa

El espesor y la escala los pones tú, que para eso los ves:

1. **Escala** la figura al tamaño real. Ten en cuenta cuántos milímetros vale
   una unidad de Blender en tu escena: el panel te dice las medidas en
   milímetros para que lo compruebes de un vistazo.
2. Aplica **Solidificar** con el espesor que quieras (desplazamiento hacia
   dentro) y aplica el modificador.
3. Abre el panel **Cortador**, elige la máquina y pulsa **Ver el plan**. Te
   dice en cuántos pisos va a partirla y cuántos gajos lleva cada piso, con
   las medidas de cada pieza.
4. Pulsa **Cortar**. Las piezas quedan en una colección llamada `Cortador`,
   con nombres del tipo `P2-L5`: piso 2, lámina 5. Las láminas se numeran
   dando la vuelta al piso, así que la L4 siempre está entre la L3 y la L5.
5. Elige carpeta y pulsa **Guardar los STL**.

## Las marcas

Cada pieza lleva grabado en la cara de dentro, con medio milímetro de hondo,
su propio nombre en el centro y, más pequeño, el de la pieza que va pegada
por arriba, por abajo, por la izquierda y por la derecha:

```
            P1/L3
     P2/L2  P2/L3  P2/L4
            P3/L3
```

Así una pieza suelta encima de la mesa ya dice dónde va y por dónde sigue,
sin plano ni lista. Va en la cara de dentro, que no se ve con la figura
montada, y nunca en la cara de corte: esa es la que se pega, y en una figura
hueca es una tira de tres milímetros donde no cabe ni una letra.

## Qué hace por dentro

En tres vueltas, y en este orden porque es el que menos juntas deja:

1. **Pisos.** Parte la figura en pisos de la **misma** altura. Si mide 60 cm y
   en la máquina caben 25, hace tres de 20 y no dos de 25 más uno de 10: tres
   piezas iguales se imprimen en tandas idénticas y no sobra un trozo raro.
2. **Gajos.** Abre cada piso en gajos, como una naranja. No en cuadrícula: una
   cuadrícula corta por donde se cruzan los cubos y deja piezas pequeñas que
   sólo añaden trabajo de pegado. Y los gajos se cuentan **midiendo** la pieza
   que saldría, no con una fórmula, y se elige el reparto que deja **menos
   piezas**.
3. **Ajuste.** Lo que aun así se pase de la cama se parte por la mitad de su
   lado más largo, y sólo eso. Ni un corte de más «por si acaso».

Las caras de corte se cierran solas y cada pieza sale estanca, lista para el
laminador. En las pruebas el volumen del modelo entero y el de la suma de las
piezas coinciden hasta el último decimal.

En una cama redonda (las delta) no se usa el cuadrado inscrito sino Pitágoras
contra el diámetro: una lámina de 30 mm de fondo cruza una cama de 300 mm hasta
los 298 mm, no los 212 del cuadrado. Por eso salen bastantes menos piezas de
las que saldrían con la cuenta de siempre.

## Lo medido

Sobre modelos hechos con Solidificar, en Blender 5.0:

| modelo | caras | piezas | cerradas | volumen |
|---|---|---|---|---|
| esfera de 1,2 m | 4.096 | 108 | 108 / 108 | exacto |
| toro de 900 mm | 6.144 | 26 | 26 / 26 | exacto |
| Suzanne de 1,5 m | 15.912 | 98 | 98 / 98 | −0,01 % |
| Suzanne de 1,5 m fina | 252.576 | 109 | 109 / 109 | exacto |
| cono de 700 mm | 130 | 26 | 26 / 26 | exacto |

Un modelo de resina de 5,2 millones de triángulos se corta entero en unos
tres minutos y medio con un pico de 5 GB de memoria.
