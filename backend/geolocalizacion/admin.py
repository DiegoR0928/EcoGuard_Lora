from django.contrib.gis import admin
from .models import (
    Visitante, Vigilante, Dispositivo, Gateway, Asignacion, ZonaGeografica, Incidente, RegistroGPS,
)

@admin.register(Visitante)
class VisitanteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'apellido', 'tipo_sangre', 'contacto_emergencia')
    search_fields = ('nombre', 'apellido')

@admin.register(Vigilante)
class VigilanteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'apellido', 'usuario')
    search_fields = ('nombre', 'apellido', 'usuario__username')

@admin.register(Dispositivo)
class DispositivoAdmin(admin.ModelAdmin):
    list_display = ('dev_eui', 'nombre', 'activo', 'ultima_bateria_mv', 'ultimo_contacto', 'creado_en')
    search_fields = ('dev_eui', 'nombre')
    list_filter = ('activo',)

@admin.register(Gateway)
class GatewayAdmin(admin.GISModelAdmin):
    list_display = ('gateway_eui', 'nombre')
    search_fields = ('gateway_eui', 'nombre')

@admin.register(Asignacion)
class AsignacionAdmin(admin.ModelAdmin):
    list_display = ('dispositivo', 'visitante', 'fecha_asignacion', 'fecha_devolucion')
    list_filter = ('dispositivo',)
    search_fields = ('visitante__nombre', 'visitante__apellido', 'dispositivo__nombre')

@admin.register(ZonaGeografica)
class ZonaGeograficaAdmin(admin.GISModelAdmin):
    list_display = ('nombre', 'tipo')
    list_filter = ('tipo',)

@admin.register(Incidente)
class IncidenteAdmin(admin.GISModelAdmin):
    list_display = ('id_incidente', 'dispositivo', 'estado', 'zona', 'abierto_en', 'cerrado_en', 'vigilante')
    list_filter = ('estado', 'zona')

@admin.register(RegistroGPS)
class RegistroGPSAdmin(admin.GISModelAdmin):
    """
    Usar GISModelAdmin en lugar del ModelAdmin tradicional que muestra mapa de OpenStreetMap en el panel.
    """
    list_display = ('dispositivo', 'incidente', 'recibido_en', 'es_sos', 'bateria_mv', 'rssi', 'snr', 'fcnt')
    list_filter = ('es_sos', 'dispositivo')
