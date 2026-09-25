"""El panel y los botones. Todo lo que el usuario ve.

Dos decisiones de fondo:

* **El corte va en un operador modal, no de un tiron.** Blender solo redibuja
  la ventana entre una llamada y la siguiente, asi que un corte de cinco
  millones de triangulos hecho de golpe deja el programa dos minutos como
  muerto, sin barra ni cursor, y cualquiera lo da por colgado y lo mata. El
  trabajo esta escrito como un generador y el operador le pide un paso cada
  vez que salta el reloj, con lo que la barra de abajo va contando lo que
  lleva hecho.
* **Nada de hilos.** La API de Blender no es segura entre hilos: tocar datos
  desde un hilo aparte es la receta conocida para un cierre inesperado sin
  mensaje. El reloj del operador modal hace el mismo papel y no tiene ese
  riesgo.
"""

from __future__ import annotations

import datetime
import os
import time
from typing import Optional

import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty, StringProperty)
from bpy.types import Operator, Panel, PropertyGroup

from . import perfiles, plan, plano, proceso, registro
from .plan import Ajustes


def _lista_de_maquinas(self, contexto):
    """Las maquinas, para el desplegable.

    Tiene que ser una funcion de verdad con nombre, no una lambda: Blender
    guarda la referencia y la llama mas tarde desde su propio contexto, y una
    lambda ahi dentro se queda sin ver el resto del modulo.
    """
    return perfiles.para_enum()


def milimetros_por_unidad(escena) -> float:
    """Cuantos milimetros vale una unidad de Blender en esta escena."""
    return max(escena.unit_settings.scale_length, 1e-9) * 1000.0


class CortadorAjustes(PropertyGroup):
    """Los ajustes, colgados de la escena para que se guarden con el archivo."""

    perfil: EnumProperty(
        name="Maquina",
        description="La impresora donde van a salir las piezas",
        items=_lista_de_maquinas,
    )
    modo_pisos: EnumProperty(
        name="Pisos",
        items=[
            ("AUTO", "Los que hagan falta",
             "Los minimos para que la figura quepa de alto"),
            ("NUMERO", "Un numero fijo", "Tantos pisos, todos iguales"),
            ("ALTURA", "Por altura",
             "Pisos de la altura que se diga; el ultimo se reparte igual"),
        ],
        default="AUTO",
    )
    pisos: IntProperty(name="Cuantos pisos", default=3, min=1, max=60)
    alto_piso: FloatProperty(
        name="Alto de piso", default=200.0, min=1.0, max=5000.0,
        description="En milimetros, medidos sobre la figura ya escalada",
    )
    modo_gajos: EnumProperty(
        name="Gajos",
        items=[
            ("AUTO", "Los que hagan falta",
             "Los minimos para que el gajo quepa en la cama"),
            ("NUMERO", "Un numero fijo", "Tantos cortes radiales por piso"),
            ("NINGUNO", "Ninguno", "Dejar los pisos enteros"),
        ],
        default="AUTO",
    )
    gajos: IntProperty(name="Cortes por piso", default=3, min=1, max=24)
    pared: FloatProperty(
        name="Pared", default=3.0, min=0.1, max=100.0,
        description="El espesor que le pusiste con Solidificar, en milimetros. "
                    "Solo se usa para calcular si el gajo cabe en la cama",
    )
    giro: FloatProperty(
        name="Giro", default=0.0, min=-180.0, max=180.0,
        description="Gira el reparto de gajos, para que un corte no caiga "
                    "justo en la cara de la figura",
    )
    tope: IntProperty(
        name="Tope de piezas", default=plan.TOPE_PIEZAS, min=10, max=200000,
        description="Si el plan pasa de aqui, el corte no empieza y avisa. "
                    "Casi siempre que sale un numero disparatado es que la "
                    "escala de la escena no es la que crees",
    )
    minimo: FloatProperty(
        name="Esquirla", default=5.0, min=0.0, max=200.0,
        description="Lo que salga del corte y no llegue a esto de ancho en dos "
                    "direcciones se tira: son migas y planos sueltos de malla "
                    "rota, no piezas",
    )
    marcar: BoolProperty(
        name="Marcar las piezas", default=True,
        description="Graba en la cara interior el nombre de la pieza y el de "
                    "las que van pegadas a ella",
    )
    hondo: FloatProperty(
        name="Hondo de la marca", default=0.3, min=0.05, max=3.0,
        description="Cuanto se hunde el grabado, en milimetros. Es un maximo: "
                    "en una pieza fina se graba menos, para no atravesarla",
    )
    carpeta: StringProperty(
        name="Carpeta", subtype="DIR_PATH",
        description="Donde se guardan los STL de las piezas",
    )


def _ajustes(contexto) -> Ajustes:
    """Pasa lo que hay en el panel a lo que entiende el planificador."""
    datos = contexto.scene.cortador
    mm = milimetros_por_unidad(contexto.scene)
    perfil = perfiles.perfil(datos.perfil).en_unidades(mm)
    return Ajustes(
        perfil=perfil,
        secciones=datos.pisos if datos.modo_pisos == "NUMERO" else 0,
        alto_seccion=(datos.alto_piso / mm
                      if datos.modo_pisos == "ALTURA" else 0.0),
        gajos=(datos.gajos if datos.modo_gajos == "NUMERO"
               else (-1 if datos.modo_gajos == "NINGUNO" else 0)),
        pared=datos.pared / mm,
        giro=datos.giro * 3.14159265358979 / 180.0,
        minimo=datos.minimo / mm,
        marcar=datos.marcar,
        hondo=datos.hondo / mm,
    )


def _figura(contexto) -> Optional[bpy.types.Object]:
    objeto = contexto.active_object
    if objeto is not None and objeto.type == "MESH":
        return objeto
    return None


class CORTADOR_OT_escala_mm(Operator):
    """Pone la escena en milimetros: una unidad de Blender pasa a ser 1 mm"""

    bl_idname = "cortador.escala_mm"
    bl_label = "Poner la escena en milimetros"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, contexto):
        contexto.scene.unit_settings.system = "METRIC"
        contexto.scene.unit_settings.scale_length = 0.001
        contexto.scene.unit_settings.length_unit = "MILLIMETERS"
        self.report({"INFO"}, "Una unidad de Blender es ahora 1 mm")
        return {"FINISHED"}


class CORTADOR_OT_analizar(Operator):
    """Cuenta el plan sin tocar nada: cuantos pisos, cuantos gajos y que mide cada pieza"""

    bl_idname = "cortador.analizar"
    bl_label = "Ver el plan"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, contexto):
        return _figura(contexto) is not None

    def execute(self, contexto):
        objeto = _figura(contexto)
        ajustes = _ajustes(contexto)
        mm = milimetros_por_unidad(contexto.scene)
        pisos = plan.pisos(objeto, ajustes)
        piezas = sum(max(p.piezas, 1) for p in pisos)
        lineas = [f"{len(pisos)} pisos, unas {piezas} piezas"]
        for piso in pisos:
            sobra = max(piso.piezas - 2 * piso.gajos, 0)
            lineas.append(
                f"piso {piso.indice + 1}: {piso.alto * mm:.0f} mm de alto, "
                f"{max(2 * piso.gajos, 1)} gajos"
                + (f" y {sobra} cortes mas para que quepan" if sobra else ""))
        if piezas > contexto.scene.cortador.tope:
            grande = max(d * mm for d in objeto.dimensions)
            lineas.insert(0, f"ojo: {grande:.0f} mm de largo")
            if grande > plan.DEMASIADO_GRANDE:
                lineas.insert(1, "revisa la escala de la escena")
        contexto.scene.cortador_informe = "\n".join(lineas)
        self.report({"INFO"}, lineas[0])
        return {"FINISHED"}


class CORTADOR_OT_cortar(Operator):
    """Corta la figura en piezas que caben en la maquina"""

    bl_idname = "cortador.cortar"
    bl_label = "Cortar"
    bl_options = {"REGISTER", "UNDO"}

    _reloj = None
    _trabajo = None
    _pasos = None
    _marca = 0.0
    _ultimo = ""

    @classmethod
    def poll(cls, contexto):
        return _figura(contexto) is not None

    def execute(self, contexto):
        return self.invoke(contexto, None)

    def invoke(self, contexto, evento):
        objeto = _figura(contexto)
        if objeto is None:
            self.report({"ERROR"}, "Selecciona la figura primero")
            return {"CANCELLED"}
        if objeto.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        ajustes = _ajustes(contexto)
        mm = milimetros_por_unidad(contexto.scene)
        diario = registro.DIARIO
        diario.nuevo("corte")
        registro.de_la_escena(contexto.scene, mm)
        diario.titulo("La figura")
        registro.de_la_figura(objeto, mm)
        diario.titulo("Ajustes")
        registro.de_los_ajustes(contexto.scene.cortador, ajustes, mm)
        # Antes de tocar nada: si el plan sale disparatado no se empieza. Un
        # corte de un millon de piezas no acaba nunca, y la causa es siempre
        # la misma -la escala-, asi que mas vale decirlo que ponerse a cortar.
        previstas = sum(max(p.piezas, 1) for p in plan.pisos(objeto, ajustes))
        tope = contexto.scene.cortador.tope
        if previstas > tope:
            grande = max(d * mm for d in objeto.dimensions)
            aviso = (f"El plan da unas {previstas} piezas, mas del tope de "
                     f"{tope}. La figura mide {grande:.0f} mm de largo")
            if grande > plan.DEMASIADO_GRANDE:
                aviso += (f" ({grande / 1000:.1f} m): revisa la escala de la "
                          "escena, con el boton de milimetros del panel")
            else:
                aviso += ". Sube el tope si de verdad quieres tantas"
            diario.linea("NO se corto: " + aviso)
            diario.al_bloque()
            self.report({"ERROR"}, aviso)
            return {"CANCELLED"}

        self._trabajo = proceso.Trabajo(objeto, ajustes)
        self._pasos = self._trabajo.pasos()
        self._marca = time.perf_counter()
        self._ultimo = "arrancando"
        contexto.window_manager.progress_begin(0.0, 1.0)
        self._reloj = contexto.window_manager.event_timer_add(
            0.01, window=contexto.window)
        contexto.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, contexto, evento):
        if evento.type == "ESC":
            registro.DIARIO.linea(f"cancelado por el usuario en: {self._ultimo}")
            registro.DIARIO.al_bloque()
            self.report({"WARNING"}, "Corte cancelado")
            return self._acabar(contexto, {"CANCELLED"})
        if evento.type != "TIMER":
            return {"PASS_THROUGH"}
        try:
            texto, avance = next(self._pasos)
        except StopIteration:
            return self._acabar(contexto, {"FINISHED"}, contar=True)
        except Exception as fallo:            # el corte fallo de verdad
            registro.DIARIO.fallo(fallo)
            registro.DIARIO.al_bloque()
            self.report({"ERROR"},
                        f"El corte fallo: {fallo}. Esta apuntado en el "
                        "registro: guardalo y mandalo.")
            return self._acabar(contexto, {"CANCELLED"})
        # Cuanto tardo el paso anterior. Lo lento queda apuntado aunque todo
        # acabe bien: es lo unico que dice despues por que parecia colgado.
        ahora = time.perf_counter()
        tardo = ahora - self._marca
        self._marca = ahora
        if tardo > 3.0:
            registro.DIARIO.linea(f"paso lento, {tardo:.1f} s: {self._ultimo}")
        self._ultimo = texto
        print(f"Cortador | {avance * 100:3.0f}%  {texto}")
        contexto.window_manager.progress_update(avance)
        contexto.workspace.status_text_set(
            f"Cortador: {texto}  ·  Esc para parar")
        return {"RUNNING_MODAL"}

    def _acabar(self, contexto, estado, contar=False):
        gestor = contexto.window_manager
        if self._reloj is not None:
            gestor.event_timer_remove(self._reloj)
            self._reloj = None
        gestor.progress_end()
        contexto.workspace.status_text_set(None)
        if contar and self._trabajo is not None:
            res = self._trabajo.resultado
            registro.del_resultado(res, milimetros_por_unidad(contexto.scene))
            registro.DIARIO.al_bloque()
            contexto.scene.cortador_informe = _contar(res)
            self.report({"INFO"}, f"{len(res.piezas)} piezas")
            for aviso in res.avisos:
                self.report({"WARNING"}, aviso)
        return estado


def _contar(resultado) -> str:
    lineas = [f"{len(resultado.piezas)} piezas en "
              f"{len(resultado.pisos)} pisos"]
    if resultado.abiertas:
        lineas.append(f"{len(resultado.abiertas)} piezas no cerraron del todo")
    if resultado.no_caben:
        lineas.append(f"{len(resultado.no_caben)} piezas no caben")
    lineas += resultado.avisos
    return "\n".join(lineas)


class CORTADOR_OT_exportar(Operator):
    """Guarda cada pieza en su propio STL, listas para el laminador"""

    bl_idname = "cortador.exportar"
    bl_label = "Guardar los STL"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, contexto):
        return bpy.data.collections.get(proceso.COLECCION) is not None

    def execute(self, contexto):
        carpeta = bpy.path.abspath(contexto.scene.cortador.carpeta or "//")
        if not carpeta or not os.path.isdir(carpeta):
            self.report({"ERROR"}, "Elige una carpeta que exista")
            return {"CANCELLED"}
        coleccion = bpy.data.collections.get(proceso.COLECCION)
        piezas = [o for o in coleccion.objects if o.type == "MESH"]
        if not piezas:
            self.report({"ERROR"}, "No hay piezas que guardar")
            return {"CANCELLED"}
        antes = [o for o in contexto.selected_objects]
        try:
            for pieza in piezas:
                for otro in contexto.selected_objects:
                    otro.select_set(False)
                pieza.select_set(True)
                contexto.view_layer.objects.active = pieza
                bpy.ops.wm.stl_export(
                    filepath=os.path.join(carpeta, f"{pieza.name}.stl"),
                    export_selected_objects=True, ascii_format=False)
        except Exception as fallo:
            registro.DIARIO.fallo(fallo)
            registro.DIARIO.al_bloque()
            self.report({"ERROR"}, f"Fallo al guardar: {fallo}")
            return {"CANCELLED"}
        registro.DIARIO.linea(f"guardados {len(piezas)} STL")
        for otro in contexto.selected_objects:
            otro.select_set(False)
        for otro in antes:
            otro.select_set(True)
        self.report({"INFO"}, f"{len(piezas)} piezas guardadas en {carpeta}")
        return {"FINISHED"}


class CORTADOR_OT_plano(Operator):
    """Dibuja el plano de montaje en PDF, con un render de cada piso"""

    bl_idname = "cortador.plano"
    bl_label = "Hacer el plano (PDF)"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, contexto):
        return proceso.vigente() is not None

    def execute(self, contexto):
        resultado = proceso.vigente()
        if resultado is None:
            self.report({"ERROR"}, "Corta la figura primero")
            return {"CANCELLED"}
        carpeta = bpy.path.abspath(contexto.scene.cortador.carpeta or "//")
        if not carpeta or not os.path.isdir(carpeta):
            self.report({"ERROR"}, "Elige una carpeta que exista")
            return {"CANCELLED"}
        ruta = os.path.join(carpeta, "plan-de-montaje.pdf")
        try:
            plano.montar(resultado, _ajustes(contexto),
                         milimetros_por_unidad(contexto.scene), ruta,
                         resultado.figura)
        except Exception as fallo:
            registro.DIARIO.fallo(fallo)
            registro.DIARIO.al_bloque()
            self.report({"ERROR"}, f"No se pudo hacer el plano: {fallo}")
            return {"CANCELLED"}
        registro.DIARIO.linea(f"plano guardado en {os.path.basename(ruta)}")
        self.report({"INFO"}, f"Plano guardado en {ruta}")
        return {"FINISHED"}


class CORTADOR_OT_registro_copiar(Operator):
    """Copia el registro al portapapeles, listo para pegarlo donde haga falta"""

    bl_idname = "cortador.registro_copiar"
    bl_label = "Copiar el registro"
    bl_options = {"REGISTER"}

    def execute(self, contexto):
        cuantas = registro.DIARIO.al_portapapeles()
        registro.DIARIO.al_bloque()
        self.report({"INFO"}, f"{cuantas} lineas copiadas. Pegalo donde quieras")
        return {"FINISHED"}


class CORTADOR_OT_registro_guardar(Operator):
    """Guarda el registro en un archivo de texto para poder mandarlo"""

    bl_idname = "cortador.registro_guardar"
    bl_label = "Guardar el registro"
    bl_options = {"REGISTER"}

    def execute(self, contexto):
        carpeta = bpy.path.abspath(contexto.scene.cortador.carpeta or "//")
        if not carpeta or not os.path.isdir(carpeta):
            self.report({"ERROR"}, "Elige antes una carpeta que exista")
            return {"CANCELLED"}
        marca = datetime.datetime.now().strftime("%Y%m%d-%H%M")
        ruta = os.path.join(carpeta, f"cortador-registro-{marca}.txt")
        try:
            registro.DIARIO.guardar(ruta)
        except Exception as fallo:
            self.report({"ERROR"}, f"No se pudo guardar: {fallo}")
            return {"CANCELLED"}
        registro.DIARIO.al_bloque()
        self.report({"INFO"}, f"Registro guardado en {ruta}")
        return {"FINISHED"}


class CORTADOR_OT_registro_revisar(Operator):
    """Revisa la figura y apunta como esta, sin cortar nada"""

    bl_idname = "cortador.registro_revisar"
    bl_label = "Revisar la figura"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, contexto):
        return _figura(contexto) is not None

    def execute(self, contexto):
        objeto = _figura(contexto)
        mm = milimetros_por_unidad(contexto.scene)
        diario = registro.DIARIO
        diario.nuevo("revision")
        registro.de_la_escena(contexto.scene, mm)
        diario.titulo("La figura")
        try:
            registro.de_la_figura(objeto, mm)
            diario.titulo("Ajustes")
            registro.de_los_ajustes(contexto.scene.cortador, _ajustes(contexto), mm)
        except Exception as fallo:
            diario.fallo(fallo)
        diario.al_bloque()
        self.report({"INFO"}, "Figura revisada; mira el registro en el panel")
        return {"FINISHED"}


class CORTADOR_PT_panel(Panel):
    bl_label = "Cortador"
    bl_idname = "CORTADOR_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Cortador"

    def draw(self, contexto):
        trazo = self.layout
        datos = contexto.scene.cortador
        objeto = _figura(contexto)

        trazo.prop(datos, "perfil")
        perfil = perfiles.perfil(datos.perfil)
        caja = trazo.box()
        caja.label(text=f"Cama {perfil.x:.0f} x {perfil.y:.0f} x {perfil.z:.0f} mm"
                        + (" (redonda)" if perfil.redonda else ""))
        caja.label(text=f"Pared recomendada {perfil.pared():.2f} mm")

        if objeto is None:
            trazo.label(text="Selecciona la figura", icon="ERROR")
            return
        mm = milimetros_por_unidad(contexto.scene)
        ancho, fondo, alto = (d * mm for d in objeto.dimensions)
        trazo.label(text=f"{objeto.name}: {ancho:.0f} x {fondo:.0f} x "
                         f"{alto:.0f} mm, {len(objeto.data.polygons)} caras")
        if max(ancho, fondo, alto) > plan.DEMASIADO_GRANDE:
            caja = trazo.box()
            caja.alert = True
            caja.label(text=f"Esta figura mide {max(ancho, fondo, alto) / 1000:.1f} "
                            "metros", icon="ERROR")
            caja.label(text="Si la modelaste en milimetros, la escena")
            caja.label(text="esta mal: 1 unidad vale "
                            f"{mm:g} mm ahora mismo.")
            caja.operator("cortador.escala_mm", icon="DRIVER_DISTANCE")

        columna = trazo.column(align=True)
        columna.prop(datos, "modo_pisos")
        if datos.modo_pisos == "NUMERO":
            columna.prop(datos, "pisos")
        elif datos.modo_pisos == "ALTURA":
            columna.prop(datos, "alto_piso")

        columna = trazo.column(align=True)
        columna.prop(datos, "modo_gajos")
        if datos.modo_gajos == "NUMERO":
            columna.prop(datos, "gajos")
        if datos.modo_gajos != "NINGUNO":
            columna.prop(datos, "giro")

        trazo.prop(datos, "pared")
        trazo.prop(datos, "minimo")
        trazo.prop(datos, "tope")
        trazo.prop(datos, "marcar")
        if datos.marcar:
            trazo.prop(datos, "hondo")

        trazo.operator("cortador.analizar", icon="INFO")
        trazo.operator("cortador.cortar", icon="MOD_BEVEL")

        informe = contexto.scene.cortador_informe
        if informe:
            caja = trazo.box()
            for linea in informe.split("\n"):
                caja.label(text=linea)

        trazo.separator()
        trazo.prop(datos, "carpeta")
        trazo.operator("cortador.exportar", icon="EXPORT")
        trazo.operator("cortador.plano", icon="FILE_IMAGE")

        trazo.separator()
        caja = trazo.box()
        fila = caja.row()
        fila.label(text="Registro", icon="TEXT")
        fila.operator("cortador.registro_revisar", text="", icon="VIEWZOOM")
        ultimas = registro.DIARIO.ultimas(8)
        if not ultimas:
            caja.label(text="todavia no hay nada apuntado")
        for linea in ultimas:
            caja.label(text=linea[:64])
        fila = caja.row(align=True)
        fila.operator("cortador.registro_copiar", icon="COPYDOWN")
        fila.operator("cortador.registro_guardar", icon="FILE_TEXT")


CLASES = (CortadorAjustes, CORTADOR_OT_escala_mm, CORTADOR_OT_analizar,
          CORTADOR_OT_cortar,
          CORTADOR_OT_exportar, CORTADOR_OT_plano,
          CORTADOR_OT_registro_copiar, CORTADOR_OT_registro_guardar,
          CORTADOR_OT_registro_revisar, CORTADOR_PT_panel)


def registrar() -> None:
    for clase in CLASES:
        bpy.utils.register_class(clase)
    bpy.types.Scene.cortador = PointerProperty(type=CortadorAjustes)
    bpy.types.Scene.cortador_informe = StringProperty(default="")


def olvidar() -> None:
    del bpy.types.Scene.cortador_informe
    del bpy.types.Scene.cortador
    for clase in reversed(CLASES):
        bpy.utils.unregister_class(clase)
