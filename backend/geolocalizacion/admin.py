"""
@brief Registro de los modelos en el administrador de Django (/admin/).

Los modelos con geometría usan GISModelAdmin, que muestra y edita la posición sobre un mapa de
OpenStreetMap. El administrador sirve para cargar catálogos (gateways, zonas, vigilantes) y revisar
datos; la operación diaria se hace desde el panel.
"""
from django.contrib.gis import admin
from .models import (
    Visitante, Vigilante, Dispositivo, Gateway, Asignacion, ZonaGeografica, PuntoControl, Incidente, RegistroGPS,
)

@admin.register(Visitante)
class VisitanteAdmin(admin.ModelAdmin):
    """
    @brief Visitantes registrados en los préstamos.
    """
    ## Columnas del listado.
    list_display = ('nombre', 'apellido', 'tipo_sangre', 'contacto_emergencia')
    ## Campos de la búsqueda.
    search_fields = ('nombre', 'apellido')

@admin.register(Vigilante)
class VigilanteAdmin(admin.ModelAdmin):
    """
    @brief Vigilantes y el usuario de Django con el que inician sesión.
    """
    ## Columnas del listado.
    list_display = ('nombre', 'apellido', 'usuario')
    ## Campos de la búsqueda.
    search_fields = ('nombre', 'apellido', 'usuario__username')

@admin.register(Dispositivo)
class DispositivoAdmin(admin.ModelAdmin):
    """
    @brief Nodos registrados, con su última batería y último contacto.
    """
    ## Columnas del listado.
    list_display = ('dev_eui', 'nombre', 'activo', 'ultima_bateria_mv', 'ultimo_contacto', 'creado_en')
    ## Campos de la búsqueda.
    search_fields = ('dev_eui', 'nombre')
    ## Filtros de la barra lateral.
    list_filter = ('activo',)

@admin.register(Gateway)
class GatewayAdmin(admin.GISModelAdmin):
    """
    @brief Gateways LoRaWAN; su ubicación se marca en el mapa.
    """
    ## Columnas del listado.
    list_display = ('gateway_eui', 'nombre')
    ## Campos de la búsqueda.
    search_fields = ('gateway_eui', 'nombre')

@admin.register(Asignacion)
class AsignacionAdmin(admin.ModelAdmin):
    """
    @brief Préstamos de nodos a visitantes, vigentes y devueltos.
    """
    ## Columnas del listado.
    list_display = ('dispositivo', 'visitante', 'fecha_asignacion', 'fecha_devolucion')
    ## Filtros de la barra lateral.
    list_filter = ('dispositivo',)
    ## Campos de la búsqueda.
    search_fields = ('visitante__nombre', 'visitante__apellido', 'dispositivo__nombre')

@admin.register(ZonaGeografica)
class ZonaGeograficaAdmin(admin.GISModelAdmin):
    """
    @brief Zonas del parque; el polígono se dibuja en el mapa.
    """
    ## Columnas del listado.
    list_display = ('nombre', 'tipo')
    ## Filtros de la barra lateral.
    list_filter = ('tipo',)

@admin.register(PuntoControl)
class PuntoControlAdmin(admin.GISModelAdmin):
    """
    @brief Puntos de control de la ruta piloto.

    Se cargan con `manage.py cargar_ruta_piloto`; los cambios hechos aquí se pierden al volver a
    cargar el archivo.
    """
    ## Columnas del listado.
    list_display = ('codigo', 'nombre', 'orden', 'levantado_en_sitio')
    ## Filtros de la barra lateral.
    list_filter = ('levantado_en_sitio',)

@admin.register(Incidente)
class IncidenteAdmin(admin.GISModelAdmin):
    """
    @brief Incidentes abiertos y cerrados, con su última posición en el mapa.
    """
    ## Columnas del listado.
    list_display = ('id_incidente', 'dispositivo', 'estado', 'zona', 'abierto_en', 'cerrado_en', 'vigilante')
    ## Filtros de la barra lateral.
    list_filter = ('estado', 'zona')

@admin.register(RegistroGPS)
class RegistroGPSAdmin(admin.GISModelAdmin):
    """
    @brief Todas las tramas recibidas, con su posición en el mapa.

    Usa GISModelAdmin en lugar del ModelAdmin tradicional para mostrar el mapa de OpenStreetMap.
    """
    ## Columnas del listado.
    list_display = ('dispositivo', 'incidente', 'recibido_en', 'es_sos', 'bateria_mv', 'rssi', 'snr', 'fcnt')
    ## Filtros de la barra lateral.
    list_filter = ('es_sos', 'dispositivo')
