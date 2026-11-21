"""
@brief Punto de entrada WSGI del proyecto (solo HTTP).

EcoGuard se sirve por ASGI (asgi.py) porque necesita WebSocket; este archivo se conserva por si se
despliega solo la API con un servidor WSGI. Ver
https://docs.djangoproject.com/en/5.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecoguard.settings')

## Aplicación WSGI de Django.
application = get_wsgi_application()
