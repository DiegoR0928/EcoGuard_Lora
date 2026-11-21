"""
@brief Comando `manage.py cargar_ruta_piloto`: carga la ruta de pruebas desde un archivo GeoJSON.

El archivo (por defecto `pruebas/ruta_piloto.geojson`) trae Features con la propiedad "tipo":
- "gateway": el gateway, con nombre, edificio y gateway_eui.
- "perimetro": el perímetro del campus, que se guarda como ZonaGeografica de tipo AREA_COMUN.
- "punto_control": los puntos de control, en el orden del recorrido.

Se puede correr varias veces: actualiza lo que existe y borra los puntos que ya no están en el archivo.
"""
import json

from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from geolocalizacion.models import Gateway, PuntoControl, ZonaGeografica


class Command(BaseCommand):
    """
    @brief Sincroniza Gateway, ZonaGeografica y PuntoControl con el archivo GeoJSON de la ruta piloto.
    """
    ## Descripción que muestra `manage.py help cargar_ruta_piloto`.
    help = ('Carga la ruta piloto desde pruebas/ruta_piloto.geojson: gateway, perímetro del campus '
            '(como zona geográfica) y puntos de control. Vuelve a correrlo cada vez que cambie el archivo.')

    def add_arguments(self, parser):
        """
        @brief Declara el argumento opcional `archivo`.

        Por defecto es /pruebas/ruta_piloto.geojson: docker-compose monta EcoGuard_Lora/pruebas en
        /pruebas dentro del contenedor.
        @param parser Analizador de argumentos (argparse) del comando.
        """
        parser.add_argument('archivo', nargs='?', default='/pruebas/ruta_piloto.geojson')

    def handle(self, archivo, **opciones):
        """
        @brief Lee el archivo y actualiza las tablas en una sola transacción.

        Los gateways sin gateway_eui se omiten con un aviso. El orden de los puntos de control en el
        archivo es el orden del recorrido.
        @param archivo Ruta del archivo GeoJSON.
        @param opciones Resto de opciones del comando (no se usan).
        @exception CommandError Si el archivo no existe.
        """
        try:
            with open(archivo, encoding='utf-8') as f:
                features = json.load(f)['features']
        except FileNotFoundError:
            raise CommandError(f'No se encontró {archivo}')

        def de_tipo(tipo):
            return [f for f in features if f['properties']['tipo'] == tipo]

        def geometria(feature):
            return GEOSGeometry(json.dumps(feature['geometry']), srid=4326)

        with transaction.atomic():
            for f in de_tipo('gateway'):
                p = f['properties']
                if not p.get('gateway_eui'):
                    self.stderr.write(f"Gateway \"{p['nombre']}\" sin gateway_eui: se omite")
                    continue
                Gateway.objects.update_or_create(
                    gateway_eui=p['gateway_eui'].upper(),
                    defaults={'nombre': f"{p['nombre']} ({p['edificio']})", 'ubicacion': geometria(f)}
                )

            # El perímetro se guarda como zona: así cada incidente dentro del campus queda asociado a ella
            for f in de_tipo('perimetro'):
                ZonaGeografica.objects.update_or_create(
                    nombre=f['properties']['nombre'],
                    defaults={'tipo': ZonaGeografica.Tipo.AREA_COMUN, 'area': geometria(f)}
                )

            # El orden del archivo es el orden del recorrido
            codigos = []
            for orden, f in enumerate(de_tipo('punto_control'), start=1):
                p = f['properties']
                codigos.append(p['id'])
                PuntoControl.objects.update_or_create(
                    codigo=p['id'],
                    defaults={'nombre': p['nombre'], 'orden': orden, 'punto': geometria(f),
                              'levantado_en_sitio': p.get('levantado_en_sitio', False)}
                )
            eliminados, _ = PuntoControl.objects.exclude(codigo__in=codigos).delete()

        self.stdout.write(self.style.SUCCESS(
            f"Ruta piloto cargada: {len(de_tipo('gateway'))} gateway, {len(de_tipo('perimetro'))} perímetro, "
            f"{len(codigos)} puntos de control ({eliminados} eliminados)"
        ))
