# backend/geolocalizacion/views.py
import json
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.gis.geos import Point
from django.utils.dateparse import parse_datetime
from django.utils.timezone import now
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from rest_framework.decorators import api_view
from rest_framework.response import Response
from .serializers import IncidenteActivoSerializer

from .models import Dispositivo, Gateway, ZonaGeografica, Incidente, RegistroGPS

@csrf_exempt
def chirpstack_webhook(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Solo se acepta POST'}, status=405)

    try:
        # 1. Leer el JSON entrante
        data = json.loads(request.body)

        # Ignorar cualquier evento de ChirpStack que no sea de subida de datos ("up")
        event = request.GET.get('event', '')
        if event and event != 'up':
            return JsonResponse({'status': f'Evento {event} ignorado'}, status=200)

        # 2. Extraer datos del dispositivo (ChirpStack manda el EUI en minúsculas)
        device_info = data.get('deviceInfo', {})
        dev_eui = (device_info.get('devEui') or '').upper()

        if not dev_eui:
            return JsonResponse({'error': 'No se encontró el devEui'}, status=400)

        # ChirpStack omite los campos en cero, así que la primera trama llega sin fCnt
        fcnt = data.get('fCnt', 0)

        # 3. Extraer la telemetría decodificada
        obj = data.get('object', {})
        lat = obj.get('latitude')
        lon = obj.get('longitude')
        es_sos = bool(obj.get('sos', False))
        bateria_mv = obj.get('battery_mv')

        # 4. Extraer calidad de señal y concentrador
        rx_info = (data.get('rxInfo') or [{}])[0]
        rssi = rx_info.get('rssi')
        snr = rx_info.get('snr')
        gateway_eui = (rx_info.get('gatewayId') or '').upper()

        # 5. Crear el punto geográfico (PostGIS usa Longitud, Latitud).
        # Sin fix GPS la trama se guarda igual, con punto nulo
        punto = Point(float(lon), float(lat), srid=4326) if lat is not None and lon is not None else None
        recibido_en = parse_datetime(data.get('time')) if data.get('time') else now()

        with transaction.atomic():
            # 6. Buscar o crear el dispositivo. Se bloquea su fila para que dos tramas
            # simultáneas no abran dos incidentes
            dispositivo, _ = Dispositivo.objects.select_for_update().get_or_create(
                dev_eui=dev_eui,
                defaults={'nombre': f'Heltec {dev_eui[-4:]}'}
            )
            dispositivo.ultimo_contacto = recibido_en
            if bateria_mv is not None:
                dispositivo.ultima_bateria_mv = bateria_mv
            dispositivo.save(update_fields=['ultimo_contacto', 'ultima_bateria_mv'])

            # 7. La trama pertenece al incidente abierto del nodo; si no hay uno y es SOS, se abre
            incidente = dispositivo.incidentes.filter(estado__in=Incidente.ABIERTOS).first()
            if incidente is None and es_sos:
                incidente = Incidente.objects.create(
                    dispositivo=dispositivo,
                    asignacion=dispositivo.asignaciones.filter(fecha_devolucion__isnull=True).first(),
                    abierto_en=recibido_en
                )

            if incidente and punto:
                incidente.ultima_posicion = punto
                # En geography, ST_Covers es el equivalente de ST_Contains
                if incidente.zona is None:
                    incidente.zona = ZonaGeografica.objects.filter(area__covers=punto).first()
                incidente.save(update_fields=['ultima_posicion', 'zona'])

            # 8. Guardar en la base de datos
            RegistroGPS.objects.create(
                dispositivo=dispositivo,
                incidente=incidente,
                gateway=Gateway.objects.filter(gateway_eui=gateway_eui).first() if gateway_eui else None,
                punto=punto,
                es_sos=es_sos,
                bateria_mv=bateria_mv,
                rssi=rssi,
                snr=snr,
                fcnt=fcnt,
                recibido_en=recibido_en
            )

        # 9. EMITIR LA ALERTA EN TIEMPO REAL POR WEBSOCKETS (REDIS)
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                'alertas_parque',
                {
                    'type': 'enviar_actualizacion', # Función que se ejecuta en el consumer
                    'datos': {
                        'dev_eui': dev_eui,
                        'id_incidente': incidente.id_incidente if incidente else None,
                        'lat': punto.y if punto else None,
                        'lon': punto.x if punto else None,
                        'es_sos': es_sos,
                        'bateria_mv': bateria_mv,
                        'tiempo': recibido_en.isoformat()
                    }
                }
            )

        return JsonResponse({'status': 'success', 'mensaje': 'Trama guardada y alerta emitida'}, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@api_view(['GET'])
def listar_incidentes_activos(request):
    """
    Devuelve los incidentes abiertos (activos o en atención) de los nodos habilitados.
    """
    incidentes = (
        Incidente.objects
        .filter(estado__in=Incidente.ABIERTOS, dispositivo__activo=True)
        .select_related('dispositivo')
    )
    serializer = IncidenteActivoSerializer(incidentes, many=True)
    return Response(serializer.data)
