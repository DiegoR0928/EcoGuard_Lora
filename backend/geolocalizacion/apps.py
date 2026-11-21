"""
@brief Configuración de la aplicación de Django geolocalizacion.
"""
from django.apps import AppConfig


class GeolocalizacionConfig(AppConfig):
    """
    @brief Registra la aplicación geolocalizacion, que contiene todo el dominio de EcoGuard.
    """
    ## Tipo de clave primaria para los modelos que no la declaran (todos los de EcoGuard la declaran).
    default_auto_field = 'django.db.models.BigAutoField'
    ## Nombre del paquete de la aplicación.
    name = 'geolocalizacion'

    def ready(self):
        """
        @brief Se ejecuta al arrancar Django: importa signals.py para registrar sus receptores.

        Sin esta importación los avisos en tiempo real a los paneles no se emitirían.
        """
        from . import signals  # noqa: F401  Registra los avisos en tiempo real a los paneles
