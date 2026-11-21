# backend/ecoguard/urls.py
"""
@brief Rutas HTTP raíz del proyecto: el administrador de Django y la API de EcoGuard.
"""
from django.contrib import admin
from django.urls import path, include

## /admin/ es el administrador de Django; /api/ incluye las rutas de geolocalizacion/urls.py.
urlpatterns = [
    path('admin/', admin.site.urls),

    path('api/', include('geolocalizacion.urls')),
]
