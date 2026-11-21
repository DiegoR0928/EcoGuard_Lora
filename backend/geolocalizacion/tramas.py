# backend/geolocalizacion/tramas.py
"""
@brief Tramas de los nodos, las entregue quien las entregue.

Cada servidor de red tiene su traductor a Trama (desde_ttn(), desde_chirpstack()) y todas terminan
en registrar_trama(), que aplica las reglas del incidente.

Los cambios en nodos e incidentes avisan a los paneles desde signals.py; registrar_trama() además
emite la alerta con sus datos (posición, SOS, batería).

Formato de la carga útil que envía el firmware por el puerto LoRaWAN 1 (little-endian):

| Bytes | Campo    | Tipo   | Contenido                                                  |
|-------|----------|--------|------------------------------------------------------------|
| 0     | banderas | uint8  | 0x01 SOS, 0x02 trae posición GPS, 0x04 cancelación         |
| 1-2   | batería  | uint16 | Voltaje de la batería en mV                                |
| 3-6   | latitud  | int32  | Grados × 1 000 000 (solo con la bandera 0x02)              |
| 7-10  | longitud | int32  | Grados × 1 000 000 (solo con la bandera 0x02)              |

Sin posición GPS la trama mide 3 bytes; con posición, 11.
"""
import base64
import struct
from dataclasses import dataclass
from datetime import datetime

from django.contrib.gis.geos import Point
from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils.timezone import now

from .models import Dispositivo, Gateway, Incidente, RegistroGPS, ZonaGeografica
from .tiempo_real import emitir_actualizacion

## Puerto LoRaWAN (FPort) por el que el firmware envía sus tramas (PUERTO_LORAWAN del firmware).
## Las tramas de otros puertos, o sin carga útil, no son del nodo y se ignoran.
PUERTO_LORAWAN = 1  # PUERTO_LORAWAN del firmware


class TramaInvalida(ValueError):
    """
    @brief Error de una trama mal formada: incompleta o sin DevEUI.

    El webhook la responde con 400 y escuchar_ttn la registra en el log sin detenerse.
    """
    pass


@dataclass
class Trama:
    """
    @brief Trama de un nodo ya decodificada, independiente del servidor de red que la entregó.
    """
    ## DevEUI del nodo, en mayúsculas.
    dev_eui: str
    ## Contador de tramas de subida de LoRaWAN (FCnt).
    fcnt: int
    ## Verdadero si la trama lleva la bandera SOS (0x01).
    es_sos: bool
    ## Verdadero si la trama lleva la bandera de cancelación (0x04): el visitante canceló su alerta.
    cancelado: bool
    ## Voltaje de la batería en mV; None si no se conoce.
    bateria_mv: int | None
    ## Latitud en grados; None si la alerta salió sin fix GPS.
    lat: float | None  # Nulas si la alerta salió sin fix GPS
    ## Longitud en grados; None si la alerta salió sin fix GPS.
    lon: float | None
    ## Intensidad de la señal en el gateway, en dBm.
    rssi: int | None
    ## Relación señal/ruido en el gateway, en dB.
    snr: float | None
    ## EUI del gateway que recibió la trama, en mayúsculas; cadena vacía si no se conoce.
    gateway_eui: str
    ## Fecha y hora de recepción según el servidor de red.
    recibido_en: datetime


def decodificar_carga(carga):
    """
    @brief Decodifica la carga útil binaria que envía el firmware.

    Formato little-endian: [banderas][batería mV, uint16][lat int32][lon int32], con las
    coordenadas en grados × 1 000 000. Sin fix GPS mide 3 bytes. Es el mismo formato que descifra
    EcoGuard-Node/chirpstack/codec.js.
    @param carga Bytes de la carga útil (FRMPayload), ya descifrados por el servidor de red.
    @return Diccionario con es_sos, cancelado, bateria_mv, lat y lon. lat y lon son None si la trama
            no trae la bandera 0x02 o no alcanza los 11 bytes.
    @exception TramaInvalida Si la carga mide menos de 3 bytes.
    """
    if len(carga) < 3:
        raise TramaInvalida(f'Trama EcoGuard incompleta: {len(carga)} bytes')

    banderas, bateria_mv = struct.unpack_from('<BH', carga)
    lat = lon = None
    if banderas & 0x02 and len(carga) >= 11:
        lat_e6, lon_e6 = struct.unpack_from('<ii', carga, 3)
        lat, lon = lat_e6 / 1e6, lon_e6 / 1e6

    return {
        'es_sos': bool(banderas & 0x01),
        'cancelado': bool(banderas & 0x04),
        'bateria_mv': bateria_mv,
        'lat': lat,
        'lon': lon,
    }


def desde_ttn(mensaje):
    """
    @brief Traduce un mensaje de subida de The Things Network (MQTT, topic v3/.../up).

    La calidad de radio y el gateway se toman del primer gateway que recibió la trama.
    @param mensaje JSON del mensaje ya convertido a diccionario.
    @return La Trama, o None si no trae datos del nodo (otro puerto o solo comandos MAC de LoRaWAN).
    @exception TramaInvalida Si el mensaje no trae dev_eui o la carga está incompleta.
    """
    subida = mensaje.get('uplink_message') or {}
    if subida.get('f_port') != PUERTO_LORAWAN or not subida.get('frm_payload'):
        return None

    dev_eui = ((mensaje.get('end_device_ids') or {}).get('dev_eui') or '').upper()
    if not dev_eui:
        raise TramaInvalida('El mensaje de TTN no trae dev_eui')

    recepcion = (subida.get('rx_metadata') or [{}])[0]
    return Trama(
        dev_eui=dev_eui,
        fcnt=subida.get('f_cnt', 0),  # TTN omite los campos en cero, como ChirpStack
        rssi=recepcion.get('rssi'),
        snr=recepcion.get('snr'),
        gateway_eui=((recepcion.get('gateway_ids') or {}).get('eui') or '').upper(),
        recibido_en=parse_datetime(subida.get('received_at') or mensaje.get('received_at') or '') or now(),
        **decodificar_carga(base64.b64decode(subida['frm_payload'])),
    )


def desde_chirpstack(data):
    """
    @brief Traduce el JSON del evento "up" de la integración HTTP de ChirpStack v4.

    Si trae los bytes de la trama ("data", en base64) se decodifican aquí, igual que con TTN, así que
    ChirpStack no necesita codec. Las peticiones de Postman sin ChirpStack mandan solo "object", ya
    decodificado, con los campos sos, cancelado, battery_mv, latitude y longitude.
    @param data JSON del evento ya convertido a diccionario.
    @return La Trama, o None si la trama no es del puerto del nodo.
    @exception TramaInvalida Si falta deviceInfo.devEui o la carga está incompleta.
    """
    # ChirpStack manda el EUI en minúsculas
    dev_eui = (data.get('deviceInfo', {}).get('devEui') or '').upper()
    if not dev_eui:
        raise TramaInvalida('No se encontró el devEui')

    if data.get('data'):
        if data.get('fPort') != PUERTO_LORAWAN:
            return None
        campos = decodificar_carga(base64.b64decode(data['data']))
    else:
        obj = data.get('object', {})
        campos = {
            'es_sos': bool(obj.get('sos', False)),
            'cancelado': bool(obj.get('cancelado', False)),
            'bateria_mv': obj.get('battery_mv'),
            'lat': obj.get('latitude'),
            'lon': obj.get('longitude'),
        }

    recepcion = (data.get('rxInfo') or [{}])[0]
    return Trama(
        dev_eui=dev_eui,
        fcnt=data.get('fCnt', 0),  # ChirpStack omite los campos en cero: la primera trama llega sin fCnt
        rssi=recepcion.get('rssi'),
        snr=recepcion.get('snr'),
        gateway_eui=(recepcion.get('gatewayId') or '').upper(),
        recibido_en=parse_datetime(data.get('time')) if data.get('time') else now(),
        **campos,
    )


def registrar_trama(trama):
    """
    @brief Guarda la trama, abre o actualiza el incidente del nodo y avisa a los paneles.

    Pasos, dentro de una transacción:
    -# Bloquea la fila del nodo (o la crea si el DevEUI es nuevo) y actualiza su último contacto y batería.
    -# Si el nodo no tiene incidente abierto y la trama es SOS, abre uno vinculado al préstamo vigente.
    -# Si hay incidente y la trama trae posición, actualiza la última posición y, la primera vez, la zona.
    -# Si la trama es de cancelación, cierra el incidente como CANCELADO.
    -# Guarda la trama en RegistroGPS.

    Al terminar emite la alerta por WebSocket con emitir_actualizacion().
    @param trama Trama decodificada por desde_ttn() o desde_chirpstack().
    @return El Incidente al que pertenece la trama, o None si es un reporte sin emergencia.
    """
    # PostGIS usa Longitud, Latitud. Sin fix GPS la trama se guarda igual, con punto nulo
    punto = Point(float(trama.lon), float(trama.lat), srid=4326) if trama.lat is not None and trama.lon is not None else None

    with transaction.atomic():
        # Se bloquea la fila del dispositivo para que dos tramas simultáneas no abran dos incidentes
        dispositivo, _ = Dispositivo.objects.select_for_update().get_or_create(
            dev_eui=trama.dev_eui,
            defaults={'nombre': f'Heltec {trama.dev_eui[-4:]}'}
        )
        dispositivo.ultimo_contacto = trama.recibido_en
        if trama.bateria_mv is not None:
            dispositivo.ultima_bateria_mv = trama.bateria_mv
        dispositivo.save(update_fields=['ultimo_contacto', 'ultima_bateria_mv'])

        # La trama pertenece al incidente abierto del nodo; si no hay uno y es SOS, se abre
        incidente = dispositivo.incidentes.filter(estado__in=Incidente.ABIERTOS).first()
        if incidente is None and trama.es_sos and not trama.cancelado:
            incidente = Incidente.objects.create(
                dispositivo=dispositivo,
                asignacion=dispositivo.asignaciones.filter(fecha_devolucion__isnull=True).first(),
                abierto_en=trama.recibido_en
            )

        if incidente and punto:
            incidente.ultima_posicion = punto
            # En geography, ST_Covers es el equivalente de ST_Contains
            if incidente.zona is None:
                incidente.zona = ZonaGeografica.objects.filter(area__covers=punto).first()
            incidente.save(update_fields=['ultima_posicion', 'zona'])

        # La cancelación la emite el visitante desde la app (CU-12); por eso no se asigna
        # vigilante, a diferencia de la falsa alarma, que la declara el operador
        if incidente and trama.cancelado:
            incidente.estado = Incidente.Estado.CANCELADO
            incidente.cerrado_en = trama.recibido_en
            incidente.save(update_fields=['estado', 'cerrado_en'])

        RegistroGPS.objects.create(
            dispositivo=dispositivo,
            incidente=incidente,
            gateway=Gateway.objects.filter(gateway_eui=trama.gateway_eui).first() if trama.gateway_eui else None,
            punto=punto,
            es_sos=trama.es_sos,
            bateria_mv=trama.bateria_mv,
            rssi=trama.rssi,
            snr=trama.snr,
            fcnt=trama.fcnt,
            recibido_en=trama.recibido_en
        )

    # Alerta en tiempo real por WebSocket (Redis)
    emitir_actualizacion({
        'dev_eui': trama.dev_eui,
        'id_incidente': incidente.id_incidente if incidente else None,
        'estado': incidente.estado if incidente else None,  # CANCELADO: el panel quita el marcador
        'lat': punto.y if punto else None,
        'lon': punto.x if punto else None,
        'es_sos': trama.es_sos,
        'bateria_mv': trama.bateria_mv,
        'tiempo': trama.recibido_en.isoformat()
    })
    return incidente
