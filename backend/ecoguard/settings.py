"""
@brief Configuración de Django para el backend de EcoGuard.

Generado con `django-admin startproject` (Django 5.0.14) y adaptado al proyecto. Los valores que
cambian entre equipos se leen de variables de entorno (django-environ); docker-compose.yml las toma
del archivo `.env` (ver `.env.example`).

Variables de entorno que usa:
- DATABASE_URL: conexión a PostgreSQL/PostGIS.
- CHANNEL_LAYERS_REDIS_URL: Redis para los avisos en tiempo real.
- ALLOWED_HOSTS_EXTRA: IP de la PC en la red local, para el webhook de la Raspberry.
- CHIRPSTACK_TOKEN: token que debe traer el webhook.
- TTN_HOST, TTN_USUARIO y TTN_API_KEY: conexión opcional con The Things Network.

Referencias: https://docs.djangoproject.com/en/5.0/topics/settings/ y
https://docs.djangoproject.com/en/5.0/ref/settings/
"""

from pathlib import Path

import environ
import os

## Lector de variables de entorno (django-environ).
env = environ.Env()

## Carpeta backend/ (raíz del proyecto de Django). Las rutas se construyen como BASE_DIR / 'subcarpeta'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-lvk#)%d*mx$rjopjyyx(1*b)xc9awn4vlc@07(*2qrz_cy$7a2'

## Modo de depuración: muestra errores detallados. Debe ser False en producción.
DEBUG = True

## Nombres de servidor que Django acepta en la cabecera Host.
## "web" es el nombre del contenedor: así llama ChirpStack al webhook dentro de la red de Docker.
## ALLOWED_HOSTS_EXTRA (en .env) es la IP de esta PC en la red local, a la que el ChirpStack de la
## Raspberry entrega el webhook. Sin ella Django rechaza esas peticiones (Bad Request).
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]', 'web'] + env.list('ALLOWED_HOSTS_EXTRA', default=[])


# Application definition

## Aplicaciones activas. daphne va primero para que runserver sirva ASGI (WebSocket); django.contrib.gis
## habilita GeoDjango; geolocalizacion es la aplicación de EcoGuard.
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',

    # 1. Registrar GeoDjango
    'django.contrib.gis',

    # 2. Librerías de terceros
    'rest_framework',

    # 3. Aplicación de rastreo
    'geolocalizacion',
]

## Capas que procesan cada petición HTTP. CorsMiddleware permite que el panel (otro puerto) llame a la API.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

## Módulo con las rutas HTTP raíz (ecoguard/urls.py).
ROOT_URLCONF = 'ecoguard.urls'

## Motor de plantillas de Django; solo lo usa el administrador.
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

## Aplicación WSGI (solo HTTP); EcoGuard usa ASGI_APPLICATION.
WSGI_APPLICATION = 'ecoguard.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

## Base de datos espacial PostgreSQL/PostGIS. La conexión se lee de DATABASE_URL; el valor por defecto
## apunta al contenedor "db" de docker-compose. El motor se fuerza a PostGIS para tener GeoDjango.
## @hideinitializer
DATABASES = {
    'default': env.db('DATABASE_URL', default='postgis://postgres:postgres@db:5432/ecoguard')
}
# Forzamos que use el motor espacial de PostGIS
DATABASES['default']['ENGINE'] = 'django.contrib.gis.db.backends.postgis'


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

## Reglas para las contraseñas de los usuarios de Django (los vigilantes).
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

## Idioma de los textos de Django.
LANGUAGE_CODE = 'en-us'

## Zona horaria del servidor. Las fechas se guardan en UTC y los clientes las muestran en su hora local.
TIME_ZONE = 'UTC'

## Activa la traducción de los textos de Django.
USE_I18N = True

## Guarda las fechas con zona horaria (aware).
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

## Prefijo de las URL de los archivos estáticos (CSS y JavaScript del administrador).
STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

## Tipo de clave primaria automática por defecto.
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

## Aplicación ASGI que atiende HTTP y WebSocket (ecoguard/asgi.py).
ASGI_APPLICATION = 'ecoguard.asgi.application'

## URL de Redis para la capa de canales (variable CHANNEL_LAYERS_REDIS_URL); None fuera de Docker.
REDIS_CANALES = env('CHANNEL_LAYERS_REDIS_URL', default=None)
## Capa de canales de Django Channels.
## Va en Redis, como en el SDD: los avisos llegan a los paneles aunque el cambio venga de otro proceso
## (la consola, comandos de manage.py o varios workers). docker-compose define la URL; sin ella
## (Django fuera de Docker) se usa la capa en memoria, que solo funciona dentro del mismo proceso.
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        # channels_redis espera mensajes bloqueando 5 s en Redis (BZPOPMIN) y redis-py 8 corta la lectura
        # también a los 5 s: sin un margen mayor, cada espera vacía termina en TimeoutError y cierra el
        # WebSocket del panel. Se mantiene finito para que una caída de Redis sí produzca error y reconexión.
        "CONFIG": {"hosts": [{"address": REDIS_CANALES, "socket_timeout": 10}]},
    } if REDIS_CANALES else {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    }
}

## Permite que cualquier origen llame a la API (el panel corre en otro puerto). En producción debe
## limitarse a la dirección del panel.
CORS_ALLOW_ALL_ORIGINS = True  # En producción cambiaremos esto por la IP de tu servidor

## Token que ChirpStack manda en la cabecera Authorization del webhook (`Bearer <token>`). Vacío: no se exige.
## @hideinitializer
CHIRPSTACK_TOKEN = env('CHIRPSTACK_TOKEN', default='')

## Servidor MQTT de The Things Network (manage.py escuchar_ttn, opcional). Ver .env.example.
TTN_HOST = env('TTN_HOST', default='nam1.cloud.thethings.network')
## Usuario MQTT de TTN: el identificador de la aplicación seguido de "@ttn".
TTN_USUARIO = env('TTN_USUARIO', default='')
## Clave de API de TTN, que funciona como contraseña MQTT.
## @hideinitializer
TTN_API_KEY = env('TTN_API_KEY', default='')

## Política de la cabecera Referer. OpenStreetMap bloquea los mosaicos pedidos sin Referer y el valor
## por defecto de Django ("same-origin") lo omite, así que el mapa del admin mostraba "Access blocked".
## Con esta política solo se envía el origen (sin la ruta) a otros dominios.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
