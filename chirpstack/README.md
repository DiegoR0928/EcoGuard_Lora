# Servidor de red LoRaWAN (ChirpStack v4)

Se levanta junto con el backend (`docker compose up -d` en `EcoGuard_Lora`): el `docker-compose.yml`
de la raíz incluye el de esta carpeta. Región **US915 sub-banda 2** (canales 8–15), la misma del nodo.

| Servicio | Puerto | Para qué |
|---|---|---|
| `chirpstack` | [localhost:8080](http://localhost:8080) | Interfaz web (usuario `admin` / `admin`) |
| `chirpstack-rest-api` | [localhost:8090](http://localhost:8090) | API REST (carpeta 3 de Postman) |
| `chirpstack-gateway-bridge` | 1700/UDP | Aquí se conecta el gateway real |
| `simulador-lorawan` | [localhost:8070](http://localhost:8070) | Gateway + nodo virtuales (carpeta 4 de Postman) |
| `mosquitto` | 1883 | Broker MQTT interno entre el bridge y ChirpStack |
| `chirpstack-postgres`, `chirpstack-redis` | — | Base de datos propia de ChirpStack |

Ya quedan registrados la aplicación **EcoGuard** (con la integración HTTP a `http://web:8000/api/webhook/`),
los perfiles de dispositivo (con `EcoGuard-Node/chirpstack/codec.js`), el gateway simulado y el nodo simulado
`EC00000000000001`. Para usar la API REST desde Postman crea un API key en la interfaz (*API keys → Add*)
y pégalo en la variable `cs_token`.

## Probar sin gateway

El simulador arma la misma trama que el firmware, hace el join OTAA, la cifra y se la entrega a ChirpStack
por el Gateway Bridge, igual que un gateway real. Desde Postman (carpeta 4) o con:

```bash
curl -X POST http://localhost:8070/uplink -H "Content-Type: application/json" -d "{\"dev_eui\":\"EC00000000000001\",\"app_key\":\"<sim_app_key de Postman>\",\"sos\":true,\"lat\":22.7758,\"lon\":-102.5714,\"battery_mv\":3850}"
```

Los nodos simulados usan LoRaWAN 1.0.3 (criptografía más simple); el nodo real usa 1.1.0.
Lo que se prueba, ChirpStack → codec → webhook, es igual en ambos.

## Cuando llegue el gateway

1. Configura su *packet forwarder* (Semtech UDP) hacia la IP de esta PC, puerto **1700**, en la sub-banda 2 de US915.
2. Regístralo en ChirpStack (*Gateways → Add*) con su Gateway ID.
3. Registra el nodo Heltec (carpeta 3 de Postman, peticiones 3.9 y 3.10) con las llaves de `EcoGuard-Node/include/lorawan_config.h`.
4. Si el firewall de Windows pregunta por Docker, permite el puerto 1700/UDP en la red privada.

## Antes de producción

Cambia la contraseña de `admin`, el `secret` de `configuration/chirpstack/chirpstack.toml` y el acceso anónimo de Mosquitto.
