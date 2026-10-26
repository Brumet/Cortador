# Encargo: estudiar LuBan a fondo y traer lo que valga al complemento

Este documento es para quien retome el trabajo —persona o sesión nueva— sin
haber estado en las conversaciones anteriores. Dice qué se pide, qué está ya
decidido, qué está ya hecho y medido, y dónde están los agujeros.

**El encargo en una frase:** analizar LuBan en su totalidad y meter en el
complemento de Blender todo lo suyo que le falte a Cortador y merezca la pena.

---

## 1. Lo que ya está decidido (no hay que volver a discutirlo)

**Cortador es un complemento de Blender, no una aplicación aparte.** Lo decidió
el dueño del proyecto con sus palabras: *«no quiero más la aplicación
independiente, quiero que sea un plugin para Blender para aprovechar al máximo
su motor»* y *«es peor decirle a alguien instala mi app que decirle instala
este plugin»*. Queda en el repositorio una carpeta `escritorio/` de la época de
la app de Electron: está muerta, no se toca.

**Nada de ingeniería inversa del binario.** Condición puesta por él mismo:
*«usa solo fuentes públicas y mi propia cuenta; nada de código, logos ni textos
de la app original»*. Se estudia lo publicado —páginas del producto, prensa,
reseñas, documentación, capturas— y lo que se construya se escribe de cero. Las
ideas y los enfoques no son de nadie; el código y los textos sí.

**Todo el trabajo va a la rama `claude/pensive-ramanujan-60hg6o`**, que es la
única rama del repositorio y por tanto la que se clona en cada sesión.

---

## 2. Qué es LuBan exactamente, y qué no

**No es Snapmaker Luban.** Ese es el laminador de las máquinas Snapmaker y no
viene al caso.

**No es el `LuBan_1.exe` que se subió al chat.** Se miró por fuera, sin
ejecutarlo, y es otra cosa: un ejecutable PE32+ de Windows en C++ con
wxWidgets que lleva dentro **DCMTK** (imagen médica DICOM), **CGAL**, dlib,
captura de vídeo y USB Cypress, con clases de metrología (`CRuler`,
`CProtractor`, `CCircleDet`, `CHeightMap`, `CVolume`, `CPolarMap`) y un
`Dlg_Gcode`. Es un programa de medición o microscopía con módulo de impresión.
Si hace falta volver a identificarlo, el fichero ya no está: el contenedor es
efímero y se borró.

**El LuBan que importa** es el programa comercial para imprimir objetos muy
grandes partiéndolos en piezas. Lo que se sabe de fuentes públicas:

- **Editor de corte por planos.** Enseña el modelo en una ventana 3D girable
  donde se van añadiendo planos de corte a mano, los que hagan falta, hasta
  que las porciones entran en la máquina.
- **Conectores automáticos** en cada unión, a elegir entre cuatro formas:
  *plug*, *dowel*, *terrace* y *pyramid*.
- **Guía de montaje**: numera las piezas y da una secuencia de armado.
- **Precio**: 25 USD/mes, 125 USD/año o 625 USD de licencia perpetua, según un
  artículo de 2025. Puede estar desactualizado.
- **Competencia**: Split3r se vende como alternativa barata y anuncia *«Smart
  Splitting by Build Volume – based on your printer's size»*.

Fuentes de partida (verificar que siguen vivas, una devolvía 403):

- https://www.fabbaloo.com/2019/05/luban-3d-printing-very-large-objects
- https://www.fabbaloo.com/news/split3r-launches-as-low-cost-alternative-to-luban-for-large-scale-3d-printing
- https://www.fabbaloo.com/blog/tag/luban

**Esto es lo que falta por hacer de verdad: el recon no está hecho.** Lo de
arriba son cuatro datos sueltos de prensa, no un mapa del producto. Falta
recorrer su web, su documentación, sus vídeos, sus capturas y sus reseñas, y
sacar el inventario completo de lo que hace.

---

## 3. Qué tiene ya Cortador (para no rehacerlo)

Versión 0.6.0. Todo esto está hecho, probado y en la rama.

| | estado |
|---|---|
| Corte en pisos horizontales y gajos radiales por piso | hecho |
| Piezas estancas: tapado por triangulación de Delaunay con regla de *winding* | hecho |
| Ajuste final: parte en dos lo que siga sin caber en la cama | hecho |
| Perfiles de máquina, incluida cama redonda (delta) medida por diagonal | hecho |
| Nombre y vecinas grabados **por dentro** de cada pieza (`P2/L3`) | hecho |
| Plano de montaje en PDF, un render por piso, con tabla de qué va con qué | hecho |
| Diario de rendimiento exportable desde el panel | hecho |
| Filtro de migas, agujas y planos sueltos sin volumen | hecho |
| Aviso y freno si la escala de la escena está mal | hecho |
| **Espigas en las juntas** (taco y agujero) | nuevo, **desactivado** |

Es decir: de las tres cosas que distinguen a LuBan, Cortador ya tenía dos —la
numeración y la guía de montaje, y en PDF—. La tercera, los conectores, se
acaba de empezar.

**El corte de Cortador es automático y el de LuBan es a mano.** No es obvio
cuál es mejor. Para tiradas en serie, que es el caso de uso aquí, lo
automático gana. Pero no hay forma de decirle «este corte aquí no», y eso
puede ser un hueco real.

---

## 4. Lo medido, con números

Batería en Blender 5.0.1, figuras solidificadas hacia dentro:

| figura | caras | piezas | cerradas | caben | material |
|---|---|---|---|---|---|
| esfera 1,2 m | 4 096 | 116 | 116/116 | 116/116 | exacto |
| toro 900 mm | 6 144 | 24 | 24/24 | 24/24 | exacto |
| suzanne 1,5 m | 15 912 | 80 | 80/80 | 80/80 | exacto |
| suzanne 1,5 m fina | 252 576 | 80 | 80/80 | 80/80 | exacto |
| cono 700 mm | 130 | 26 | 26/26 | 26/26 | exacto |

**Aprovechamiento de la cama** (área de la pieza contra los 256 × 256 de una
Bambu A1): mediana del **41–45 %** en figuras tipo estatua, **78 %** en un
cilindro ancho. Esta es la queja repetida del dueño —*«las láminas son muy
delgadas, la idea es usar toda la superficie de la impresora lo mejor
posible»*— y sigue sin resolver.

**Espigas**: en figura limpia encajan 228 de 243 (94 %). Las que fallan se
quedan sin taco, que no estorba; un taco sin agujero sí estorba, y por eso se
taladra primero y sólo después se sacan los tacos que tienen agujero.

---

## 5. Lo que está abierto

1. **Aprovechamiento de la cama al 41 %.** Lo más valioso que queda. Mejorarlo
   es rediseñar el reparto de gajos, probablemente añadiendo cortes a radio
   constante (planos perpendiculares a la bisectriz del gajo) para que una
   figura ancha no dependa del troceado ciego del ajuste final. Varias horas y
   con riesgo de romper lo que funciona: avisar antes de meterse.
2. **El gorila de 4 062 piezas.** Un escaneo real de 296 000 caras a 950 mm
   salió en 4 062 piezas y 18 minutos. No se pudo reproducir: un escaneo
   sintético rugoso de un millón de caras sale en 33 piezas y 11 s. El STL se
   perdió al reiniciarse el contenedor. **Hay que pedírselo otra vez.**
3. **El cono no recibe ninguna espiga.** Sus tiras de pegado dan 0,5 mm de
   holgura al centro y el taco más fino pide 1,2. Sin diagnosticar del todo.
4. **Las espigas no están verificadas en malla auto-intersecada**, que es lo
   que deja Solidificar en cualquier recoveco. La prueba de encaje usa
   `closest_point_on_mesh`, que en esas mallas no es de fiar. Hace falta otra
   forma de medirlo.
5. **Conectores con forma.** LuBan ofrece cuatro; Cortador sólo hace el
   cilindro. Cola de milano y escalón (*terrace*) resisten tracción, que un
   cilindro no.

---

## 6. Cómo probar sin Blender abierto

Blender corre como módulo de Python. Hace falta Python 3.11:

```bash
python3.11 -m venv bpyenv
./bpyenv/bin/pip install bpy numpy       # bpy 5.0.1, ~500 MB
./bpyenv/bin/python mi_prueba.py
```

En el script: `sys.path.insert(0, '/home/user/Cortador/blender')`, luego
`import cortador_blender as addon; addon.register()`, montar la figura,
`es.cortador.*` para los ajustes, `interfaz._ajustes(bpy.context)` y recorrer
`proceso.Trabajo(ob, aj).pasos()`.

**No empujar nada sin pasar la batería del apartado 4.** Esas cinco figuras
tienen que seguir dando el mismo número de piezas, todas cerradas, todas
cabiendo y el material exacto.

---

## 7. Qué skills de `replica-*` sirven aquí y cuáles no

Están instaladas en `.claude/skills/` del repositorio (MIT, de Jake
Schincariol). El paquete está pensado para clonar una aplicación web desde
cero, y aquí no se clona nada: se estudia un competidor y se mejora un
complemento que ya existe.

- **`replica-recon`** — sí, es justo el primer paso que falta: el mapa
  completo de LuBan desde fuentes públicas.
- **`replica-entrepreneur`** — sí, y puede que sea la más útil: lee reseñas
  reales y saca qué le reprochan los usuarios a LuBan y a Split3r. Ahí es
  donde está el hueco que nadie cubre.
- **`replica-diff`** — a medias: su puntuación de paridad sirve para saber qué
  le falta a Cortador frente a LuBan; su comparador de capturas, no.
- **`replica-architect`, `-design`, `-build`, `-backend`, `-launch`,
  `-deploy`, `-brand`, `-test`** — no. Son para levantar una app web con su
  base de datos, su Stripe y su dominio. Aquí hay un complemento de Blender en
  Python que ya existe.

---

## 8. Cómo trabaja este proyecto

- Código y comentarios **en español, sin tildes dentro del código**.
- Los comentarios explican *por qué*, no *qué*. Si hubo un número medido, va
  en el comentario.
- Mensajes de commit largos y en español, contando qué fallaba y con qué
  números se arregló.
- El `LEEME.md` de `blender/` es para el usuario final: taller de impresión,
  no programadores.
- Los dos zips (`cortador-extension.zip` para Blender 4.2+ y
  `cortador-blender.zip` para 3.6–4.1) se reconstruyen a mano y están en
  `.gitignore`.
- Nada de inventar resultados: si algo no se pudo medir, se dice.
