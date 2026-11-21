# backend/ecoguard/asgi.py
"""
@brief Punto de entrada ASGI del backend: `manage.py runserver` lo sirve con Daphne, que está en INSTALLED_APPS.

Reparte las conexiones por protocolo: HTTP va a Django y WebSocket a las rutas de
geolocalizacion/routing.py. Los WebSocket solo se aceptan desde los orígenes de ALLOWED_HOSTS.
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecoguard.settings')

## Aplicación HTTP de Django. Se crea antes de importar Channels y las rutas, que necesitan Django ya configurado.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from geolocalizacion.routing import websocket_urlpatterns

## Aplicación ASGI que sirve el backend: HTTP y WebSocket.
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        URLRouter(websocket_urlpatterns)
    ),
})
