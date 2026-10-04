# backend/geolocalizacion/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('webhook/', views.chirpstack_webhook, name='webhook_chirpstack'),
    path('incidentes/activos/', views.listar_incidentes_activos, name='incidentes_activos'),
]