"""
@brief Consumidor WebSocket de Django Channels que reenvía los avisos a los paneles y a la app.
"""
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class AlertaConsumer(AsyncWebsocketConsumer):
    """
    @brief Conexión WebSocket de un panel o de la app en `ws://<servidor>:8000/ws/alertas/`.

    Cada conexión se suscribe al grupo `alertas_parque` de Redis. Cuando emitir_actualizacion()
    publica un aviso en el grupo, Channels llama a enviar_actualizacion() de cada conexión, que lo
    reenvía como texto JSON. La comunicación es de un solo sentido: el servidor no espera mensajes
    del cliente.
    """
    async def connect(self):
        """
        @brief Acepta la conexión y la suscribe al grupo de alertas.
        """
        ## Nombre del grupo de Redis al que se suscriben todas las conexiones.
        self.grupo_alertas = 'alertas_parque'

        # Suscribir esta conexión al grupo en Redis
        await self.channel_layer.group_add(
            self.grupo_alertas,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        """
        @brief Retira la conexión del grupo cuando el cliente se desconecta.
        @param close_code Código de cierre del WebSocket.
        """
        await self.channel_layer.group_discard(
            self.grupo_alertas,
            self.channel_name
        )

    async def enviar_actualizacion(self, event):
        """
        @brief Reenvía al cliente un aviso publicado en el grupo.

        Channels la llama por el campo "type" del mensaje que publica emitir_actualizacion().
        @param event Mensaje del grupo: {"type": "enviar_actualizacion", "datos": {...}}.
        """
        datos = event['datos']

        # Se envían por el WebSocket al panel (Svelte) o a la app (Flutter)
        await self.send(text_data=json.dumps(datos))
