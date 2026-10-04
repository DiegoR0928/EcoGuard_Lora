import json
from channels.generic.websocket import AsyncWebsocketConsumer

class AlertaConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        #  Nombre de grupo para alertas de geolocalización
        self.grupo_alertas = 'alertas_parque'

        # Suscribir esta conexión al grupo en Redis
        await self.channel_layer.group_add(
            self.grupo_alertas,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # Desuscribirse del grupo al cerrar la app
        await self.channel_layer.group_discard(
            self.grupo_alertas,
            self.channel_name
        )

    # Esta función es llamada por Redis cuando hay una nueva alerta
    async def enviar_actualizacion(self, event):
        # Extraemos los datos del evento
        datos = event['datos']

        # Los enviamos por el cable del WebSocket a Svelte/Flutter
        await self.send(text_data=json.dumps(datos))