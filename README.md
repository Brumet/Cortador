# Cortador

**Corta modelos 3D para gran formato.** Metes una malla (STL, OBJ, PLY, 3MF...),
dices cuanto mide tu impresora y Cortador la parte en piezas que **si caben**, o en
**laminas del espesor que quieras** (3 mm, 5 mm, 18 mm...). Cada pieza sale
**marcada con su nombre grabado** y, si quieres, con **pasadores de alineacion**,
para que luego puedas armar el modelo entero sin volverte loco.

![panel de Cortador](docs/panel.png)

---

## Que resuelve

Quieres imprimir una figura de 1,80 m y tu impresora hace 22 x 22 x 25 cm. O quieres
construirla por capas de MDF de 5 mm cortadas a laser. En los dos casos el problema es
el mismo: partir la malla bien, que las piezas encajen y **saber cual va con cual**
cuando tengas 200 trozos encima de la mesa.

Cortador hace las tres cosas:

1. **Parte** la malla en una rejilla calculada a partir del volumen de tu maquina.
2. **Marca** cada pieza con su nombre (`A2-L07`) grabado en una cara de corte, que
   queda oculta al pegar.
3. **Documenta** el despiece: guia de armado, CSV, manifiesto JSON y vista previa 3D.

---

## Instalacion

```bash
git clone https://github.com/Brumet/Cortador.git
cd Cortador
python -m venv .venv
source .venv/bin/activate        # en Windows:  .venv\Scripts\activate
pip install -e ".[web]"
```

Requiere Python 3.9 o superior. Las dependencias pesadas (`trimesh`, `manifold3d`,
`shapely`) se instalan solas con `pip`, no hace falta compilar nada.

---

## Uso: la interfaz web

```bash
cortador web
```

Abre `http://127.0.0.1:8000` en el navegador (se abre solo). Todo ocurre en tu
maquina: no se sube nada a ningun sitio.

- Arrastra el modelo al visor.
- Ajusta el volumen de la impresora en el panel izquierdo. Tienes atajos para
  maquinas comunes (Ender 3, Bambu X1, Neptune 4 Max, Modix...).
- La rejilla de corte se dibuja **en vivo** sobre el modelo: ves cuantas piezas
  van a salir antes de cortar nada.
- Pulsa **Cortar**. Al terminar tienes la vista explosionada, el filtro por capa,
  la lista del despiece (haz clic en una pieza para ver sus vecinas) y el **ZIP**
  con todo.

El visor es WebGL escrito a mano: no descarga ninguna libreria, funciona sin internet.

---

## Uso: linea de comandos

```bash
# que hay dentro del archivo
cortador info figura.stl

# ver el plan sin generar nada
cortador plan figura.stl -i 220x220x250 --margen 3

# cortar en trozos que quepan, marcando cada pieza y con espigas de alineacion
cortador cortar figura.stl -i 220x220x250 --margen 3 --kerf 0.3 \
    --marca-tam 12 --espigas agujeros -o salida/ --zip

# laminas de 5 mm apiladas en Z, contorno plano para corte laser
cortador cortar figura.stl -i 600x400x200 --modo laminas --espesor 5 \
    --estilo-lamina placa -o laminas/

# escalar a 1,80 m de alto y luego cortar
cortador cortar figura.stl --tamano 1800 -i 256x256x256
```

---

## Los dos modos de corte

### `trozos` - para imprimir en 3D

Divide la malla en una rejilla NxNxN calculada para que **cada trozo quepa** en el
volumen de impresion. Conserva toda la geometria original.

```
   modelo 930 x 302 x 1800        impresora 220x220x250
   +----------------+             +--+--+--+--+--+
   |                |             |A1|B1|C1|D1|E1|  L08
   |     figura     |    --->     +--+--+--+--+--+
   |                |             |A1|B1|C1|D1|E1|  L07
   +----------------+             +--+--+--+--+--+   ...
                                   5 x 2 x 8 = 55 piezas
```

### `laminas` - para construir por capas

Corta el modelo en rebanadas del espesor exacto que le digas. Dos estilos:

| Estilo | Que hace | Para que sirve |
|---|---|---|
| `solido` | Rebanada real del modelo: conserva el relieve dentro del espesor | Impresion 3D por capas gruesas, moldes |
| `placa` | Extruye el **contorno** de la seccion: placa plana de espesor constante | Corte laser, CNC, carton, MDF, contrachapado |

![modo laminas](docs/laminas.png)

En modo `placa` se exportan ademas los contornos en **SVG y DXF** (capa `CORTE`
para el contorno y capa `MARCA` para el texto), listos para la laser.

Si una lamina es mas grande que la maquina, se subdivide tambien en XY
(se puede desactivar con `--no-subdividir-laminas`).

---

## Marcas de armado

Sin marcas, 200 piezas identicas son un rompecabezas imposible. Cortador graba el
nombre de cada pieza con una **tipografia de trazo incluida en el paquete** (no
necesita fuentes del sistema).

- **Nomenclatura `grid`** (por defecto): `A2-L07` = columna **A**, fila **2**,
  capa **07** contando desde abajo. Los ejes que no se dividen se omiten del nombre.
- **Nomenclatura `numeric`**: `X01Y02Z03`.
- Se graba **en una cara de corte**, que queda escondida al montar. Si la pieza no
  tiene caras de corte se usa la cara mas grande.
- `--marca-caras cortes` graba una marca **en cada cara de corte** indicando la
  pieza vecina (`B1-L03>C1-L03`): ideal para modelos grandes.
- `--marca-estilo relieve` saca el texto en relieve en vez de grabado.
- El texto se ajusta solo: si no cabe, se encoge; si la cara es alta y estrecha,
  se gira 90 grados. Si aun asi no cabe, se avisa en la guia y en el CSV.

```
cara de corte de la pieza B1-L03
+-----------------------+
|                       |
|      B1-L03           |   <- grabado 0,8 mm de profundidad
|                       |
+-----------------------+
```

---

## Pasadores de alineacion

Opcional, pero hace el pegado mucho mas facil y fuerte.

| `--espigas` | Que genera |
|---|---|
| `ninguna` | nada (por defecto) |
| `agujeros` | agujeros ciegos en **las dos** piezas + un STL de espiga suelta para imprimir en la carpeta `espigas/` |
| `machohembra` | espiga solidaria a una pieza y su alojamiento en la otra |

Los puntos se eligen dentro de la seccion comun a las dos piezas, separados del
borde (`--espiga-num` por cara). Si una cara es demasiado estrecha para el pasador,
se salta y se anota en la guia.

---

## Que genera

```
salida/
├── piezas/              A1-L01.stl, A1-L02.stl, ...   (una por pieza, marcadas y en el origen)
├── 2d/                  A1-L01.svg / .dxf             (solo en modo lamina plana)
├── espigas/             espiga_d6mm.stl + LEEME.txt   (solo con --espigas agujeros)
├── GUIA_DE_ARMADO.md    orden de montaje, capa por capa, con las vecinas de cada pieza
├── despiece.csv         tabla para la hoja de calculo (medidas, volumen, vecinas)
├── cortador.json        manifiesto completo (configuracion + plan + piezas)
└── vista_previa.glb     el despiece coloreado, para abrir en cualquier visor 3D
```

---

## Opciones principales

| Opcion | Que hace |
|---|---|
| `-i, --impresora AxBxC` | volumen util de la maquina en mm (`220x220x250`) |
| `--margen N` | margen de seguridad descontado a cada eje |
| `--modo trozos\|laminas` | tipo de corte |
| `--espesor N` | espesor de lamina en mm |
| `--eje x\|y\|z` | eje de apilado de las laminas |
| `--estilo-lamina solido\|placa` | rebanada real o placa plana extruida |
| `--kerf N` | holgura entre piezas (se reparte entre las dos caras del corte) |
| `--divisiones NxNxN` | forzar divisiones (`3x-x4` deja un eje en automatico) |
| `--tamano N --tamano-eje z` | reescalar el modelo antes de cortar |
| `--unidades mm\|cm\|m\|in` | unidades del archivo de entrada |
| `--sin-marcas` | no grabar nombres |
| `--marca-tam / --marca-prof / --marca-trazo` | altura, profundidad y grosor del texto |
| `--marca-caras auto\|cortes\|abajo` | donde se graba |
| `--prefijo TEXTO` | texto delante de cada nombre (`GOKU-A1-L03`) |
| `--espigas ninguna\|agujeros\|machohembra` | pasadores de alineacion |
| `--formato stl\|obj\|ply\|3mf` | formato de salida |
| `--en-sitio` | exportar las piezas en su posicion dentro del modelo |
| `--motor auto\|planos\|booleano` | motor de corte (ver abajo) |
| `--no-unir` | no fundir los cuerpos superpuestos del modelo |
| `--zip` | comprimir la carpeta al terminar |

`cortador cortar --help` lista todas.

---

## Como aguanta modelos "de internet"

La mayoria de los modelos descargados no son un solido limpio: son 20 piezas
superpuestas (pelo, ropa, brazos), con agujeros o con caras invertidas. Cortar eso
directamente produce piezas abiertas que ningun laminador imprime bien. Cortador:

1. **Repara** al cargar: suelda vertices, quita caras degeneradas y duplicadas,
   corrige normales y tapa agujeros pequenos.
2. **Funde los cuerpos superpuestos** con CSG antes de cortar (se puede desactivar
   con `--no-unir`). Este paso es el que salva la mayoria de los modelos.
3. **Corta con planos** (rapido) y, si una pieza sale abierta, **repite el corte
   con booleanas** automaticamente (`--motor auto`, por defecto).

Aun asi, si la malla de entrada esta muy rota conviene pasarla antes por un
reparador (Meshmixer, Netfabb, `3D Builder`). Cortador avisa en el panel y en la
guia cuando detecta que la malla no es estanca.

---

## Uso como libreria

```python
from cortador import (LabelOptions, PrinterSpec, SliceConfig,
                      export_result, load_mesh, slice_model)

malla = load_mesh("figura.stl")

cfg = SliceConfig(
    printer=PrinterSpec(220, 220, 250, clearance=3),
    mode="slabs",             # o "chunks"
    slab_thickness=5.0,
    slab_style="prism",       # placa plana para laser
    kerf=0.2,
    target_size=1800,         # escalar a 1,80 m de alto
    labels=LabelOptions(size=10, depth=0.8),
)

resultado = slice_model(malla, cfg, progress=lambda h, t, m: print(f"{m} {h}/{t}"))
print(resultado.count, "piezas")

for pieza in resultado.pieces:
    print(pieza.name, pieza.size, pieza.neighbors)

export_result(resultado, "salida/", mesh_format="stl", model_name="figura")
```

---

## Consejos practicos

- **Kerf**: si las piezas quedan justas al pegar, prueba `--kerf 0.2` o `0.3`.
  Con impresion FDM lo normal es 0,2-0,4 mm.
- **Marcas**: en piezas pequenas baja `--marca-tam` a 5-6 mm; la profundidad
  `--marca-prof 0.6` ya se lee bien y no debilita la pieza.
- **Espigas**: radio 3 mm y profundidad 6-8 mm funcionan para piezas de 20 cm.
  Imprime las espigas con 100 % de relleno.
- **Laminas de 3 mm en una figura de 1,8 m** son 600 capas: mira antes el numero de
  piezas con `cortador plan` para no llevarte un susto.
- **Orden de montaje**: la guia va capa por capa desde `L01`. Pega primero cada
  capa completa en plano y luego apila.
- Cada pieza se guarda **en el origen**, lista para arrastrarla al laminador. Si
  prefieres conservar su posicion dentro del modelo (para revisar el conjunto en
  un visor), usa `--en-sitio` o desmarca la casilla en el panel.

---

## Limitaciones conocidas

- No hace *nesting* (no coloca automaticamente las piezas 2D en la plancha para
  aprovechar material); cada lamina se exporta en su propio SVG/DXF.
- El corte es siempre **ortogonal** (planos perpendiculares a los ejes): no hay
  cortes en diagonal ni por superficies curvas.
- No reorienta las piezas para optimizar la impresion.
- Los modelos con auto-intersecciones muy severas pueden necesitar reparacion
  externa previa.

---

## Desarrollo

```bash
pip install -e ".[web,dev]"
pytest -q                                   # 112 pruebas
python examples/figura_demo.py figura.stl   # modelo de prueba de 1,8 m
```

Estructura:

| Archivo | Responsabilidad |
|---|---|
| `cortador/config.py` | opciones y validacion |
| `cortador/meshio.py` | carga, reparacion, escalado, exportacion |
| `cortador/planner.py` | donde van los planos de corte y como se llama cada pieza |
| `cortador/geometry.py` | recortes por caja, secciones, booleanas tolerantes |
| `cortador/slicer.py` | el motor: rejilla -> piezas |
| `cortador/font.py` | tipografia de trazo incluida |
| `cortador/labels.py` | grabado y relieve del texto |
| `cortador/joinery.py` | espigas y agujeros |
| `cortador/exporters.py` | STL/OBJ/SVG/DXF, guia, CSV, manifiesto, vista previa |
| `cortador/cli.py` | linea de comandos |
| `cortador/web/` | servidor FastAPI + panel y visor WebGL |

## Licencia

MIT.
