# backend/geolocalizacion/routing.py

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Ruta a la que se conectarán Svelte y Flutter: ws://localhost:8000/ws/alertas/
    re_path(r'ws/alertas/$', consumers.AlertaConsumer.as_asgi()),
]