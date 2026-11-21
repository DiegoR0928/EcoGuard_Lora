# backend/geolocalizacion/urls.py
"""
@brief Rutas HTTP de la aplicación geolocalizacion. ecoguard/urls.py las monta bajo /api/.

Cada ruta apunta a una función de views.py; el nombre (name) permite construir la URL con reverse().
"""
from django.urls import path
from . import views

## Rutas de la API. Ver views.py para el método HTTP y la respuesta de cada una.
urlpatterns = [
    path('webhook/', views.chirpstack_webhook, name='webhook_chirpstack'),
    path('incidentes/activos/', views.listar_incidentes_activos, name='incidentes_activos'),
    path('incidentes/historial/', views.historial_incidentes, name='historial_incidentes'),
    path('incidentes/<int:id_incidente>/estado/', views.cambiar_estado_incidente, name='cambiar_estado_incidente'),
    path('dispositivos/', views.dispositivos, name='dispositivos'),
    path('dispositivos/<str:dev_eui>/', views.dispositivo_detalle, name='dispositivo_detalle'),
    path('prestamos/', views.prestamos, name='prestamos'),
    path('prestamos/<int:id_asignacion>/devolucion/', views.registrar_devolucion, name='registrar_devolucion'),
    path('ruta-piloto/', views.ruta_piloto, name='ruta_piloto'),
]
