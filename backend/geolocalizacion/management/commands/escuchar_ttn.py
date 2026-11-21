"""
@brief Comando `manage.py escuchar_ttn`: recibe las tramas de The Things Network por MQTT (opcional).

Es la alternativa al webhook de ChirpStack. La conexión sale del backend hacia TTN, así que el
servidor no necesita una dirección pública. En docker-compose corre en el servicio `ttn`, que solo
arranca con `docker compose --profile ttn up -d`.
"""
import json
import traceback

import paho.mqtt.client as mqtt
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from geolocalizacion.tramas import desde_ttn, registrar_trama

## Puerto del servidor MQTT de TTN con TLS.
PUERTO_MQTT_TLS = 8883


class Command(BaseCommand):
    """
    @brief Cliente MQTT que se suscribe a las subidas de todos los nodos de la aplicación de TTN.

    Usa paho-mqtt 2.x. Cada mensaje se traduce con desde_ttn() y se guarda con registrar_trama(),
    igual que las tramas del webhook de ChirpStack.
    """
    ## Descripción que muestra `manage.py help escuchar_ttn`.
    help = ('Recibe las tramas de los nodos desde The Things Network por MQTT. La conexión sale del '
            'backend hacia TTN, así que el servidor no necesita una dirección pública.')

    def handle(self, *args, **options):
        """
        @brief Conecta con TTN y escucha hasta que se detenga el proceso.

        Si la red o TTN se caen, paho-mqtt reintenta la conexión, también la primera.
        @param args Argumentos posicionales del comando (no se usan).
        @param options Opciones del comando (no se usan).
        @exception CommandError Si faltan TTN_USUARIO o TTN_API_KEY en el archivo .env.
        """
        if not settings.TTN_USUARIO or not settings.TTN_API_KEY:
            raise CommandError('Faltan TTN_USUARIO y TTN_API_KEY en el archivo .env (ver .env.example)')

        cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        cliente.username_pw_set(settings.TTN_USUARIO, settings.TTN_API_KEY)
        cliente.tls_set()
        cliente.on_connect = self.al_conectar
        cliente.on_disconnect = self.al_desconectar
        cliente.on_message = self.al_recibir

        self.stdout.write(f'Conectando a {settings.TTN_HOST} como {settings.TTN_USUARIO}')
        cliente.connect_async(settings.TTN_HOST, PUERTO_MQTT_TLS, keepalive=60)
        # Reintenta solo si se cae la red o TTN, también en la primera conexión
        cliente.loop_forever(retry_first_connection=True)

    def al_conectar(self, cliente, datos, banderas, resultado, propiedades):
        """
        @brief Callback de conexión: se suscribe al topic de subidas `v3/<usuario>/devices/+/up`.

        Se suscribe en cada conexión porque, tras una reconexión, el servidor olvida las suscripciones.
        @param cliente Cliente MQTT.
        @param datos Datos de usuario del cliente (no se usan).
        @param banderas Banderas de la respuesta CONNACK.
        @param resultado Código de resultado; si es un fallo (credenciales incorrectas) no se suscribe.
        @param propiedades Propiedades MQTT 5 (no se usan).
        """
        if resultado.is_failure:
            self.stderr.write(f'TTN rechazó la conexión ({resultado}): revisa TTN_USUARIO y TTN_API_KEY')
            return
        topico = f'v3/{settings.TTN_USUARIO}/devices/+/up'
        cliente.subscribe(topico)
        self.stdout.write(f'Conectado a TTN, escuchando {topico}')

    def al_desconectar(self, cliente, datos, banderas, resultado, propiedades):
        """
        @brief Callback de desconexión: solo lo informa; paho-mqtt reconecta solo.
        @param cliente Cliente MQTT.
        @param datos Datos de usuario del cliente (no se usan).
        @param banderas Banderas de la desconexión.
        @param resultado Motivo de la desconexión.
        @param propiedades Propiedades MQTT 5 (no se usan).
        """
        self.stderr.write(f'Se perdió la conexión con TTN ({resultado}); reintentando')

    def al_recibir(self, cliente, datos, mensaje):
        """
        @brief Callback de mensaje: traduce y guarda una trama de subida.

        Cualquier error se registra en el log sin detener la escucha: una trama dañada o una caída
        momentánea de la base de datos no deben dejar al parque sin alertas.
        @param cliente Cliente MQTT.
        @param datos Datos de usuario del cliente (no se usan).
        @param mensaje Mensaje MQTT; su payload es el JSON de la subida de TTN.
        """
        # Este proceso no termina nunca: cada trama revisa que la conexión a la base siga viva
        close_old_connections()
        try:
            trama = desde_ttn(json.loads(mensaje.payload))
            if trama is None:
                return
            registrar_trama(trama)
            self.stdout.write(
                f'{trama.dev_eui} fCnt {trama.fcnt} SOS={trama.es_sos} cancelado={trama.cancelado} '
                f'lat={trama.lat} lon={trama.lon} RSSI={trama.rssi} SNR={trama.snr}'
            )
        except Exception:
            # Una trama dañada o una caída momentánea de la base no deben detener la escucha
            self.stderr.write(f'No se pudo procesar la trama:\n{traceback.format_exc()}')
