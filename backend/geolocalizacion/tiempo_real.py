# backend/geolocalizacion/tiempo_real.py
"""
@brief Envío de avisos en tiempo real a los paneles conectados por WebSocket.

Los avisos pasan por la capa de canales de Django Channels (Redis): se publican en el grupo
`alertas_parque` y cada AlertaConsumer suscrito los reenvía a su navegador o teléfono.
"""
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def emitir_actualizacion(datos):
    """
    @brief Avisa a todos los paneles conectados por WebSocket que algo cambió.

    Se puede llamar desde código síncrono (vistas, señales, comandos): async_to_sync() espera a que
    Redis acepte el mensaje. Si no hay capa de canales configurada, no hace nada.
    @param datos Diccionario serializable a JSON que reciben los paneles tal cual. registrar_trama()
                 manda los datos de la trama; avisar_paneles() manda el modelo y la clave que cambiaron.
    """
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            'alertas_parque',
            {'type': 'enviar_actualizacion', 'datos': datos}  # enviar_actualizacion se ejecuta en el consumer
        )
