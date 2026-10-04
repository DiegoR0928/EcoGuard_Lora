# backend/geolocalizacion/serializers.py
from rest_framework import serializers
from .models import Dispositivo, Incidente

class DispositivoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dispositivo
        fields = ['id_dispositivo', 'dev_eui', 'nombre', 'activo', 'ultima_bateria_mv', 'ultimo_contacto', 'creado_en']


class IncidenteActivoSerializer(serializers.ModelSerializer):
    latitud = serializers.SerializerMethodField()
    longitud = serializers.SerializerMethodField()
    nombre_dispositivo = serializers.CharField(source='dispositivo.nombre', read_only=True)
    dev_eui = serializers.CharField(source='dispositivo.dev_eui', read_only=True)
    bateria_mv = serializers.IntegerField(source='dispositivo.ultima_bateria_mv', read_only=True)

    class Meta:
        model = Incidente
        fields = [
            'id_incidente',
            'dispositivo',
            'nombre_dispositivo',
            'dev_eui',
            'estado',
            'latitud',
            'longitud',
            'bateria_mv',
            'abierto_en'
        ]

    # Nulas si la alerta llegó sin posición satelital: la interfaz debe mostrar "ubicación desconocida"
    def get_latitud(self, obj):
        return obj.ultima_posicion.y if obj.ultima_posicion else None  # En PostGIS, Y es la Latitud

    def get_longitud(self, obj):
        return obj.ultima_posicion.x if obj.ultima_posicion else None  # En PostGIS, X es la Longitud