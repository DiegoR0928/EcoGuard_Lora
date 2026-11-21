# backend/geolocalizacion/routing.py
"""
@brief Rutas WebSocket de Django Channels. ecoguard/asgi.py las monta para el protocolo "websocket".
"""

from django.urls import re_path
from . import consumers

## Única ruta WebSocket: `ws://<servidor>:8000/ws/alertas/`, a la que se conectan el panel (Svelte) y
## la app (Flutter) para recibir los avisos en tiempo real de AlertaConsumer.
websocket_urlpatterns = [
    re_path(r'ws/alertas/$', consumers.AlertaConsumer.as_asgi()),
]
