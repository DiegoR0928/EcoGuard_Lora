# EcoGuard-Node

Firmware del nodo EcoGuard para **Heltec WiFi LoRa 32 V4** (ESP32-S3 + SX1262 + amplificador).
Recibe la alerta del celular del visitante por Bluetooth LE y la retransmite por LoRaWAN a ChirpStack,
que la entrega al webhook del backend.

## Puesta en marcha

1. **ChirpStack**
   - Device profile: región **US915**, MAC version **LoRaWAN 1.1.0**, OTAA.
   - En la pestaña *Codec* del perfil, elige *JavaScript functions* y pega [`chirpstack/codec.js`](chirpstack/codec.js).
   - Registra el dispositivo con su DevEUI (lo muestra la pantalla del nodo al encender) y genera sus llaves OTAA.
2. **Llaves**: copia `include/lorawan_config.example.h` como `include/lorawan_config.h`, pon el AppKey y el NwkKey
   y ajusta `LORAWAN_SUB_BANDA` a la sub-banda de tu gateway. Ese archivo no se sube a git.
3. **Admin de EcoGuard**: registra el mismo DevEUI en *Dispositivos* (o deja que el webhook lo cree en la primera trama).
4. Compila y sube con PlatformIO (`pio run -t upload`).

Si borras la flash del nodo (`pio run -t erase`), usa *Flush OTAA device nonces* en ChirpStack antes de volver a unirte:
el nodo pierde sus contadores de join y ChirpStack rechazaría los nonces repetidos.

## Probar sin gateway

El entorno `sin_gateway` de `platformio.ini` compila el mismo firmware sin join: cada trama se imprime
por serial (en hexadecimal, para probarla contra el codec) y se simula el ACK de la central. Sirve para
probar la pantalla y el Bluetooth con el celular. Al encender muestra "MODO SIMULACION".

```bash
pio run -e sin_gateway -t upload -t monitor
```

Los botones Build/Upload sin elegir entorno siguen compilando solo el firmware real.

## Comportamiento

| Situación | Qué envía | Cada cuánto |
|---|---|---|
| Normal | Reporte con batería (y posición si el celular la mandó hace menos de 5 min) | 10 min |
| SOS activo | Trama con `sos=1`, **confirmada** (la central responde con ACK) | 30 s, hasta que el visitante cancele |
| Cancelación | Trama con `cancelado=1`, confirmada | Hasta 3 intentos o hasta recibir el ACK |

- Mientras el SOS está activo **todas** las tramas llevan `sos=1`: si la primera se pierde, cualquiera de las siguientes abre el incidente.
- El SOS sigue activo aunque el celular se desconecte; el nodo sigue enviando la última posición mientras tenga menos de 5 min.
- Clic corto en el botón PRG: muestra el estado. Mantenerlo 3 s: apaga (deep sleep). Al encender de nuevo recupera la sesión LoRaWAN sin repetir el join.

## Protocolo Bluetooth (app ↔ nodo)

Servicio `4fafc201-1fb5-459e-8fcc-c5c9c331914b`. El nodo se anuncia como `EcoGuard-XXXX` (últimos 4 dígitos del DevEUI).
Todos los enteros van en **little-endian**; las coordenadas en grados × 1 000 000 (`int32`).

### Comandos: característica `beb5483e-36e1-4688-b7f5-ea07361b26a8` (escritura)

| Byte | Contenido |
|---|---|
| 0 | Comando: `0x01` SOS, `0x02` actualizar posición, `0x03` cancelar |
| 1 | Banderas: bit 0 = el celular tiene fix GPS |
| 2–5 | Latitud (`int32`) |
| 6–9 | Longitud (`int32`) |

`0x01` y `0x02` miden 10 bytes (si no hay fix, bit 0 en cero y el resto se ignora). `0x03` puede ser de 1 byte.
Durante una emergencia, la app debe mandar `0x02` cada vez que obtenga una posición nueva.

### Estado: característica `d2b0f5a1-7c3e-4b8a-9f61-3a5e8c1d4e72` (lectura y notificación)

| Byte | Contenido |
|---|---|
| 0–1 | Batería en mV (`uint16`) |
| 2 | Banderas: bit 0 = unido a la red LoRaWAN, bit 1 = SOS activo, bit 2 = la central confirmó la alerta |

El bit 2 es el que permite a la app mostrar "alerta recibida" (CU-11).

## Trama LoRaWAN (nodo → ChirpStack), puerto 1

| Byte | Contenido |
|---|---|
| 0 | Banderas: bit 0 = SOS, bit 1 = incluye posición, bit 2 = cancelación |
| 1–2 | Batería en mV (`uint16`) |
| 3–6 | Latitud (`int32`), solo si bit 1 |
| 7–10 | Longitud (`int32`), solo si bit 1 |

3 bytes sin posición, 11 con posición: cabe en cualquier datarate de US915 (DR0 admite hasta 11).
El nodo usa DR1 (SF9) fijo, sin ADR, porque se mueve con el visitante.
