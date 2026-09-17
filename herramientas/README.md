# Herramientas

Cosas que no son la app, pero que hacen falta para mantenerla.

## `preparar_arte.py`

Deja utilizables las imagenes que salen de una IA (Grok, Gemini, la que sea).

```bash
python herramientas/preparar_arte.py crudo/ --salida cortador/web/static
```

- **Esferas** → matcap de 512x512 recortado al circulo, que es lo que usa el
  visor 3D para sombrear las piezas.
- **Todo lo demas** → fondo JPEG de 1200 px, progresivo y ligero.

Adivina cual es cual mirando la imagen; con `--tipo matcap` o `--tipo fondo`
se fuerza. Necesita `pip install pillow`.

Reglas para generar el material, aprendidas a golpes:

- Sin texto, sin letras y sin logos: la IA los deforma, y el logo va encima
  por codigo.
- La esfera del matcap tiene que llenar el cuadro y no llevar fondo detras.
- Fondos muy oscuros o muy claros, de poco contraste: encima va la interfaz.
- Nada de colores de marca quemados en la imagen si el material se va a
  reutilizar en otra app: el color lo pone cada app.
