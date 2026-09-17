# Modelos de ejemplo

- **`brumo.stl`** — Brumo, la mascota de Brumet, tal como la subio su autor.
  Viene en escala unidad (0,7 x 0,7 x 1 mm): se escala con la altura final que
  pidas en la app. Tiene **15 aristas no manifold** (aristas compartidas por mas
  de dos caras), asi que Cortador avisa de que la malla sigue abierta. Se corta
  igual, pero para imprimir conviene cerrarla antes.

- **`brumo_reparado.stl`** — el mismo modelo ya cerrado. Es el que se uso para
  las capturas del README: a 1,80 m de alto salen 224 piezas para una FLSUN
  V400, con 57,8 litros de material frente a 901 macizo.

Para cerrarlo se uso MeshFix, que es AGPL y por eso **no viene dentro de
Cortador**: meterlo obligaria a cambiar la licencia MIT del proyecto entero. En
Windows, 3D Builder hace lo mismo con dos clics, y la app tiene el boton que lo
abre.
