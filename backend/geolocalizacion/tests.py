import base64
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.gis.geos import Point
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from .management.commands.escuchar_ttn import Command as EscucharTTN
from .models import Asignacion, Dispositivo, Gateway, Incidente, RegistroGPS, Visitante
from .tramas import TramaInvalida, decodificar_carga, desde_ttn, registrar_trama


class DatosDelVisitanteTests(TestCase):
    """
    El panel muestra quién lleva cada nodo: la ficha completa mientras la emergencia está abierta
    y solo el nombre en el historial.
    """

    def setUp(self):
        self.nodo = Dispositivo.objects.create(dev_eui='EC000000000000AA', nombre='Nodo prueba')
        self.visitante = Visitante.objects.create(
            nombre='Ana',
            apellido='Torres',
            tipo_sangre='O+',
            contacto_emergencia='Luis Torres, 492 123 4567',
            notas_medicas='Alérgica a la penicilina',
        )

    def prestar(self):
        return Asignacion.objects.create(visitante=self.visitante, dispositivo=self.nodo)

    def test_alerta_activa_trae_la_ficha_completa(self):
        Incidente.objects.create(dispositivo=self.nodo, asignacion=self.prestar())
        alerta = self.client.get('/api/incidentes/activos/').json()[0]
        self.assertEqual(alerta['visitante'], 'Ana Torres')
        ficha = alerta['asignacion']['visitante']
        self.assertEqual(ficha['tipo_sangre'], 'O+')
        self.assertEqual(ficha['contacto_emergencia'], 'Luis Torres, 492 123 4567')
        self.assertEqual(ficha['notas_medicas'], 'Alérgica a la penicilina')

    def test_historial_solo_trae_el_nombre(self):
        Incidente.objects.create(
            dispositivo=self.nodo,
            asignacion=self.prestar(),
            estado=Incidente.Estado.RESUELTO,
            cerrado_en=timezone.now(),
        )
        registro = self.client.get('/api/incidentes/historial/').json()[0]
        self.assertEqual(registro['visitante'], 'Ana Torres')
        self.assertNotIn('asignacion', registro)

    def test_prestamo_registrado_despues_de_la_alerta_se_vincula(self):
        incidente = Incidente.objects.create(dispositivo=self.nodo)
        prestamo = self.prestar()
        incidente.refresh_from_db()
        self.assertEqual(incidente.asignacion, prestamo)

    def test_alerta_sin_prestamo(self):
        Incidente.objects.create(dispositivo=self.nodo)
        alerta = self.client.get('/api/incidentes/activos/').json()[0]
        self.assertIsNone(alerta['visitante'])
        self.assertIsNone(alerta['asignacion'])

    def test_nodo_indica_quien_lo_lleva(self):
        self.prestar()
        self.assertEqual(self.client.get('/api/dispositivos/').json()[0]['prestado_a'], 'Ana Torres')
        Asignacion.objects.filter(dispositivo=self.nodo).update(fecha_devolucion=timezone.now())
        self.assertIsNone(self.client.get('/api/dispositivos/').json()[0]['prestado_a'])


class PrestamosTests(TestCase):
    """CU-13 (registrar préstamo) y CU-14 (registrar devolución)."""

    DATOS = {
        'dev_eui': 'ec000000000000bb',
        'nombre': 'Ana',
        'apellido': 'Torres',
        'contacto_emergencia': 'Luis Torres, 492 123 4567',
        'tipo_sangre': 'O+',
        'notas_medicas': 'Alérgica a la penicilina',
    }

    def setUp(self):
        self.nodo = Dispositivo.objects.create(dev_eui='EC000000000000BB', nombre='Nodo prueba')

    def prestar(self, **cambios):
        return self.client.post('/api/prestamos/', {**self.DATOS, **cambios}, content_type='application/json')

    def test_prestamo_registra_visitante_sin_devolver_datos_de_salud(self):
        respuesta = self.prestar()
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.json()['visitante'], 'Ana Torres')
        self.assertNotIn('notas_medicas', respuesta.json())
        visitante = Asignacion.objects.get().visitante
        self.assertEqual((visitante.tipo_sangre, visitante.notas_medicas), ('O+', 'Alérgica a la penicilina'))
        vigentes = self.client.get('/api/prestamos/').json()
        self.assertEqual([p['nombre_dispositivo'] for p in vigentes], ['Nodo prueba'])
        self.assertNotIn('tipo_sangre', vigentes[0])

    def test_datos_de_salud_son_opcionales(self):
        self.assertEqual(self.prestar(tipo_sangre='', notas_medicas='').status_code, 201)

    def test_contacto_de_emergencia_obligatorio(self):
        respuesta = self.prestar(contacto_emergencia='')
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.json()['contacto_emergencia'], ['Escribe el contacto de emergencia.'])
        self.assertFalse(Visitante.objects.exists())

    def test_nodo_ya_prestado(self):
        self.prestar()
        respuesta = self.prestar(nombre='Otra')
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.json()['dev_eui'], ['El nodo ya está prestado.'])

    def test_nodo_inhabilitado(self):
        Dispositivo.objects.filter(pk=self.nodo.pk).update(activo=False)
        self.assertEqual(self.prestar().json()['dev_eui'], ['El nodo está inhabilitado.'])

    def test_prestamo_tardio_se_vincula_a_la_alerta_abierta(self):
        incidente = Incidente.objects.create(dispositivo=self.nodo)
        self.assertEqual(self.prestar().status_code, 201)
        incidente.refresh_from_db()
        self.assertEqual(str(incidente.asignacion.visitante), 'Ana Torres')

    def test_devolucion_libera_el_nodo(self):
        id_prestamo = self.prestar().json()['id_asignacion']
        respuesta = self.client.post(f'/api/prestamos/{id_prestamo}/devolucion/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertIsNotNone(respuesta.json()['fecha_devolucion'])
        self.assertEqual(self.client.get('/api/prestamos/').json(), [])
        self.assertEqual(self.client.post(f'/api/prestamos/{id_prestamo}/devolucion/').status_code, 409)
        self.assertEqual(self.prestar(nombre='Otra').status_code, 201)

    def test_devolucion_bloqueada_con_emergencia_abierta(self):
        id_prestamo = self.prestar().json()['id_asignacion']
        Incidente.objects.create(dispositivo=self.nodo, asignacion_id=id_prestamo)
        self.assertTrue(self.client.get('/api/prestamos/').json()[0]['emergencia_abierta'])
        respuesta = self.client.post(f'/api/prestamos/{id_prestamo}/devolucion/')
        self.assertEqual(respuesta.status_code, 409)
        self.assertIsNone(Asignacion.objects.get().fecha_devolucion)


# Tramas reales del firmware: banderas, batería 3850 mV y, con GPS, 22.7758, -102.5714
SOS_CON_GPS = '030A0FF8875B0178E2E2F9'
SOS_SIN_GPS = '010A0F'
CANCELACION = '040A0F'
REPORTE = '020A0FF8875B0178E2E2F9'


def mensaje_ttn(carga_hex, **subida):
    return {
        'end_device_ids': {'device_id': 'heltec-1', 'dev_eui': 'F85B1BFFFEA23B60'},
        'received_at': '2026-11-02T18:30:00.123456789Z',
        'uplink_message': {
            'f_port': 1,
            'f_cnt': 7,
            'frm_payload': base64.b64encode(bytes.fromhex(carga_hex)).decode(),
            'rx_metadata': [{'gateway_ids': {'gateway_id': 'gw-uaz', 'eui': 'AA555A0000000001'}, 'rssi': -71, 'snr': 8.25}],
            'received_at': '2026-11-02T18:30:00.123456789Z',
            **subida,
        },
    }


@override_settings(CHIRPSTACK_TOKEN='')
class TramasTests(TestCase):
    """Tramas reales que llegan por The Things Network, y el webhook de ChirpStack con la misma lógica."""

    def setUp(self):
        emision = patch('geolocalizacion.tramas.emitir_actualizacion')
        self.emitir = emision.start()
        self.addCleanup(emision.stop)

    def test_decodifica_coordenadas_negativas(self):
        carga = decodificar_carga(bytes.fromhex(SOS_CON_GPS))
        self.assertTrue(carga['es_sos'])
        self.assertFalse(carga['cancelado'])
        self.assertEqual(carga['bateria_mv'], 3850)
        self.assertAlmostEqual(carga['lat'], 22.7758)
        self.assertAlmostEqual(carga['lon'], -102.5714)

    def test_trama_incompleta(self):
        with self.assertRaises(TramaInvalida):
            decodificar_carga(b'\x01')

    def test_sos_de_ttn_abre_incidente_y_guarda_la_senal(self):
        gateway = Gateway.objects.create(gateway_eui='AA555A0000000001', nombre='UAZ', ubicacion=Point(-102.64, 22.77, srid=4326))
        incidente = registrar_trama(desde_ttn(mensaje_ttn(SOS_CON_GPS)))

        self.assertEqual(incidente.estado, Incidente.Estado.ACTIVO)
        self.assertEqual(incidente.dispositivo.dev_eui, 'F85B1BFFFEA23B60')
        self.assertAlmostEqual(incidente.ultima_posicion.y, 22.7758)
        registro = RegistroGPS.objects.get()
        self.assertEqual((registro.fcnt, registro.rssi, registro.snr), (7, -71, 8.25))
        self.assertEqual(registro.gateway, gateway)
        self.assertEqual(registro.recibido_en.microsecond, 123456)  # TTN manda nanosegundos
        self.assertEqual(self.emitir.call_args.args[0]['dev_eui'], 'F85B1BFFFEA23B60')

    def test_sos_sin_gps_no_inventa_posicion(self):
        incidente = registrar_trama(desde_ttn(mensaje_ttn(SOS_SIN_GPS)))
        self.assertIsNone(incidente.ultima_posicion)
        self.assertIsNone(RegistroGPS.objects.get().punto)

    def test_cancelacion_cierra_el_incidente(self):
        incidente = registrar_trama(desde_ttn(mensaje_ttn(SOS_CON_GPS)))
        registrar_trama(desde_ttn(mensaje_ttn(CANCELACION, f_cnt=8)))
        incidente.refresh_from_db()
        self.assertEqual(incidente.estado, Incidente.Estado.CANCELADO)

    def test_reporte_periodico_no_abre_incidente(self):
        self.assertIsNone(registrar_trama(desde_ttn(mensaje_ttn(REPORTE))))
        self.assertEqual(Dispositivo.objects.get().ultima_bateria_mv, 3850)

    def test_primera_trama_llega_sin_f_cnt(self):
        mensaje = mensaje_ttn(REPORTE)
        del mensaje['uplink_message']['f_cnt']
        self.assertEqual(desde_ttn(mensaje).fcnt, 0)

    def test_ignora_otros_puertos_y_tramas_solo_mac(self):
        self.assertIsNone(desde_ttn(mensaje_ttn(SOS_CON_GPS, f_port=2)))
        mensaje = mensaje_ttn(SOS_CON_GPS)
        del mensaje['uplink_message']['frm_payload']
        self.assertIsNone(desde_ttn(mensaje))

    def test_escuchador_registra_la_trama_y_sobrevive_a_una_danada(self):
        comando = EscucharTTN()
        with patch('geolocalizacion.management.commands.escuchar_ttn.close_old_connections'):
            comando.al_recibir(None, None, SimpleNamespace(payload=b'esto no es JSON'))
            comando.al_recibir(None, None, SimpleNamespace(payload=json.dumps(mensaje_ttn(SOS_CON_GPS))))
        self.assertEqual(Incidente.objects.count(), 1)

    @override_settings(TTN_USUARIO='', TTN_API_KEY='')
    def test_escuchador_exige_credenciales(self):
        with self.assertRaises(CommandError):
            call_command('escuchar_ttn')

    def test_webhook_de_chirpstack_sigue_funcionando(self):
        respuesta = self.client.post('/api/webhook/', {
            'deviceInfo': {'devEui': 'ec00000000000001'},
            'fCnt': 3,
            'object': {'sos': True, 'latitude': 22.77227, 'longitude': -102.64472, 'battery_mv': 3850},
            'rxInfo': [{'gatewayId': '0016c001ff10a235', 'rssi': -97, 'snr': 7.5}],
        }, content_type='application/json')
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(Incidente.objects.get().dispositivo.dev_eui, 'EC00000000000001')

    def test_webhook_de_chirpstack_sin_dev_eui(self):
        respuesta = self.client.post('/api/webhook/', {'object': {}}, content_type='application/json')
        self.assertEqual(respuesta.status_code, 400)


@override_settings(CHIRPSTACK_TOKEN='')
class WebhookChirpStackTests(TestCase):
    """ChirpStack de la Raspberry: manda los bytes de la trama ("data") y un token en la cabecera."""

    def setUp(self):
        emision = patch('geolocalizacion.tramas.emitir_actualizacion')
        emision.start()
        self.addCleanup(emision.stop)

    def subida(self, carga_hex, **extra):
        return {
            'deviceInfo': {'devEui': 'f85b1bfffea23b60'},
            'fCnt': 5,
            'fPort': 1,
            'data': base64.b64encode(bytes.fromhex(carga_hex)).decode(),
            'rxInfo': [{'gatewayId': 'aa555a0000000001', 'rssi': -80, 'snr': 9.0}],
            'time': '2026-11-16T18:00:00.123456Z',
            **extra,
        }

    def enviar(self, cuerpo, **cabeceras):
        return self.client.post('/api/webhook/?event=up', cuerpo, content_type='application/json', **cabeceras)

    def test_decodifica_la_trama_sin_codec(self):
        self.assertEqual(self.enviar(self.subida(SOS_CON_GPS)).status_code, 201)
        incidente = Incidente.objects.get()
        self.assertEqual(incidente.dispositivo.dev_eui, 'F85B1BFFFEA23B60')
        self.assertAlmostEqual(incidente.ultima_posicion.x, -102.5714)
        self.assertEqual((RegistroGPS.objects.get().fcnt, RegistroGPS.objects.get().rssi), (5, -80))

    def test_ignora_tramas_de_otro_puerto(self):
        self.assertEqual(self.enviar(self.subida(SOS_CON_GPS, fPort=2)).status_code, 200)
        self.assertFalse(RegistroGPS.objects.exists())

    @override_settings(CHIRPSTACK_TOKEN='token-de-prueba')
    def test_exige_el_token_configurado(self):
        self.assertEqual(self.enviar(self.subida(SOS_SIN_GPS)).status_code, 401)
        self.assertEqual(self.enviar(self.subida(SOS_SIN_GPS), HTTP_AUTHORIZATION='Bearer otro').status_code, 401)
        self.assertFalse(RegistroGPS.objects.exists())
        respuesta = self.enviar(self.subida(SOS_SIN_GPS), HTTP_AUTHORIZATION='Bearer token-de-prueba')
        self.assertEqual(respuesta.status_code, 201)
