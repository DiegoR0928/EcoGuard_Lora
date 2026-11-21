"""
@brief Gateway + nodo EcoGuard virtuales, para probar ChirpStack sin hardware.

Postman → POST /uplink con JSON sencillo → este simulador arma la misma trama que el firmware
(ver EcoGuard-Node/README.md), hace el join OTAA si hace falta, la cifra como un nodo LoRaWAN 1.0.3
y se la entrega al Gateway Bridge por UDP (protocolo Semtech), igual que un gateway real.
De ahí en adelante todo es real: ChirpStack valida la trama y la integración HTTP la manda al
webhook de Django.

Los nodos simulados usan LoRaWAN 1.0.3 (una sola llave) para mantener la criptografía simple;
el nodo real usa 1.1.0. Lo que se prueba (ChirpStack → webhook) es igual en ambos.

API HTTP del simulador (puerto PUERTO_HTTP):
- POST /uplink: {"dev_eui", "app_key", "join_eui"?, "sos"?, "cancelado"?, "lat"?, "lon"?,
  "battery_mv"?, "rssi"?, "snr"?, "confirmada"?}. Hace el join la primera vez.
- POST /join: fuerza un join nuevo (nueva sesión y contador de tramas en 0).
- GET /: EUI del gateway y nodos con sesión.

Se ejecuta en el contenedor del perfil `chirpstack` de docker-compose.
"""
import base64
import json
import os
import random
import re
import socket
import struct
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.cmac import CMAC

## Dirección (host, puerto UDP) del ChirpStack Gateway Bridge. Variables BRIDGE_HOST y BRIDGE_PORT.
BRIDGE = (os.environ.get('BRIDGE_HOST', 'chirpstack-gateway-bridge'), int(os.environ.get('BRIDGE_PORT', '1700')))
## EUI del gateway virtual (8 bytes). Debe estar registrado en ChirpStack. Variable GATEWAY_EUI.
GATEWAY_EUI = bytes.fromhex(os.environ.get('GATEWAY_EUI', '0016C001FF10A235'))
## Puerto de la API HTTP del simulador. Variable PUERTO_HTTP.
PUERTO_HTTP = int(os.environ.get('PUERTO_HTTP', '8070'))

## Frecuencias de subida en MHz: US915 sub-banda 2 (canales 8 a 15), la misma que usan el nodo y ChirpStack.
FRECUENCIAS = [round(903.9 + 0.2 * i, 1) for i in range(8)]
## Datarate del Join Request: DR0 (SF10, 125 kHz).
DATR_JOIN = 'SF10BW125'   # DR0
## Datarate de las tramas de datos: DR1 (SF9, 125 kHz), el datarate fijo del firmware.
DATR_DATOS = 'SF9BW125'   # DR1, el datarate fijo del firmware
## Puerto LoRaWAN (FPort) de las tramas de EcoGuard.
PUERTO_LORAWAN = 1

## Segundos que se espera el Join Accept, que sale en RX1 (5 s) o RX2 (6 s).
ESPERA_JOIN_ACCEPT = 8.0  # El Join Accept sale en RX1 (5 s) o RX2 (6 s)
## Segundos que se espera el ACK de una trama confirmada, que sale en RX1 (1 s) o RX2 (2 s).
ESPERA_ACK = 4.0          # El ACK sale en RX1 (1 s) o RX2 (2 s)


# --- Criptografía LoRaWAN 1.0.x ---

def aes_ecb(llave, datos):
    """
    @brief Cifra con AES-128 en modo ECB, el bloque básico de la criptografía de LoRaWAN.
    @param llave Llave de 16 bytes.
    @param datos Datos a cifrar; su longitud debe ser múltiplo de 16.
    @return Datos cifrados.
    """
    cifrador = Cipher(algorithms.AES(llave), modes.ECB()).encryptor()
    return cifrador.update(datos) + cifrador.finalize()


def mic(llave, datos):
    """
    @brief Calcula el MIC (código de integridad) de LoRaWAN: los primeros 4 bytes del AES-CMAC.
    @param llave Llave de 16 bytes (AppKey para el join, NwkSKey para los datos).
    @param datos Bytes sobre los que se calcula.
    @return MIC de 4 bytes.
    """
    c = CMAC(algorithms.AES(llave))
    c.update(datos)
    return c.finalize()[:4]


def join_request(join_eui, dev_eui, dev_nonce, app_key):
    """
    @brief Arma un Join Request de LoRaWAN 1.0.x.

    Formato: MHDR (0x00) | JoinEUI | DevEUI | DevNonce | MIC. Los EUI viajan en little-endian.
    @param join_eui JoinEUI de 8 bytes, en el orden en que se escribe (big-endian).
    @param dev_eui DevEUI de 8 bytes, en el orden en que se escribe.
    @param dev_nonce Número de 16 bits que no debe repetirse entre joins.
    @param app_key AppKey de 16 bytes.
    @return Trama PHY lista para enviar.
    """
    # Los EUI viajan en little-endian
    msg = b'\x00' + join_eui[::-1] + dev_eui[::-1] + struct.pack('<H', dev_nonce)
    return msg + mic(app_key, msg)


def procesar_join_accept(phy, app_key, dev_nonce):
    """
    @brief Descifra y valida un Join Accept y deriva las llaves de sesión de LoRaWAN 1.0.x.

    El servidor "descifra" con AES, así que el nodo cifra para recuperar el texto claro. Las llaves
    se derivan como AES(AppKey, 0x01 o 0x02 | AppNonce | NetID | DevNonce | relleno).
    @param phy Trama PHY del Join Accept recibida del gateway.
    @param app_key AppKey de 16 bytes.
    @param dev_nonce DevNonce que se usó en el Join Request.
    @return Tupla (DevAddr en little-endian, NwkSKey, AppSKey).
    @exception ValueError Si el MIC no coincide (el AppKey no es el registrado en ChirpStack).
    """
    # El servidor "descifra" con AES, así que el nodo cifra para recuperar el texto claro
    claro = aes_ecb(app_key, phy[1:])
    if mic(app_key, phy[:1] + claro[:-4]) != claro[-4:]:
        raise ValueError('El MIC del Join Accept no coincide: el AppKey no es el registrado en ChirpStack')
    app_nonce, net_id, dev_addr = claro[0:3], claro[3:6], claro[6:10]
    base = app_nonce + net_id + struct.pack('<H', dev_nonce) + bytes(7)
    return dev_addr, aes_ecb(app_key, b'\x01' + base), aes_ecb(app_key, b'\x02' + base)


def cifrar_payload(app_skey, dev_addr, fcnt, payload):
    """
    @brief Cifra la carga útil de una trama de subida (FRMPayload) en modo contador.

    Cada bloque de 16 bytes se combina (XOR) con AES(AppSKey, A_i), donde A_i incluye la dirección,
    el contador de tramas y el número de bloque. Cifrar y descifrar son la misma operación.
    @param app_skey AppSKey de la sesión.
    @param dev_addr DevAddr en little-endian.
    @param fcnt Contador de tramas de subida.
    @param payload Carga útil en claro.
    @return Carga útil cifrada, del mismo largo.
    """
    salida = bytearray()
    for i in range(0, len(payload), 16):
        bloque = b'\x01' + bytes(4) + b'\x00' + dev_addr + struct.pack('<I', fcnt) + b'\x00' + bytes([i // 16 + 1])
        salida += bytes(a ^ b for a, b in zip(payload[i:i + 16], aes_ecb(app_skey, bloque)))
    return bytes(salida)


@dataclass
class Sesion:
    """
    @brief Sesión LoRaWAN de un nodo simulado, creada por el join.
    """
    ## Dirección del nodo en la red, tal como viaja en la trama (little-endian).
    dev_addr: bytes  # Tal como viaja en la trama (little-endian)
    ## Llave de sesión de red: firma las tramas (MIC).
    nwk_skey: bytes
    ## Llave de sesión de aplicación: cifra la carga útil.
    app_skey: bytes
    ## Contador de la siguiente trama de subida.
    fcnt: int = 0

    def uplink(self, payload, confirmada):
        """
        @brief Arma una trama de datos de subida firmada y cifrada.

        Formato: MHDR | DevAddr | FCtrl (sin ADR, como el firmware) | FCnt | FPort | FRMPayload | MIC.
        No incrementa fcnt: lo hace quien la envía.
        @param payload Carga útil en claro (trama_ecoguard()).
        @param confirmada Verdadero para una trama confirmada (MHDR 0x80), que pide ACK.
        @return Trama PHY lista para enviar.
        """
        mhdr = b'\x80' if confirmada else b'\x40'
        fhdr = self.dev_addr + b'\x00' + struct.pack('<H', self.fcnt & 0xFFFF)  # FCtrl sin ADR, como el firmware
        msg = mhdr + fhdr + bytes([PUERTO_LORAWAN]) + cifrar_payload(self.app_skey, self.dev_addr, self.fcnt, payload)
        b0 = b'\x49' + bytes(4) + b'\x00' + self.dev_addr + struct.pack('<I', self.fcnt) + b'\x00' + bytes([len(msg)])
        return msg + mic(self.nwk_skey, b0 + msg)


def trama_ecoguard(sos, cancelado, bateria_mv, lat, lon):
    """
    @brief Arma la carga útil de EcoGuard, con el mismo formato que enviarTrama() del firmware.
    @param sos Verdadero para una alerta (bandera 0x01).
    @param cancelado Verdadero para una cancelación (bandera 0x04).
    @param bateria_mv Voltaje de la batería en mV.
    @param lat Latitud en grados, o None sin posición.
    @param lon Longitud en grados, o None sin posición.
    @return 11 bytes con posición (bandera 0x02) o 3 bytes sin ella.
    """
    con_gps = lat is not None and lon is not None
    banderas = (0x01 if sos else 0) | (0x02 if con_gps else 0) | (0x04 if cancelado else 0)
    trama = struct.pack('<BH', banderas, bateria_mv)
    if con_gps:
        trama += struct.pack('<ii', round(lat * 1e6), round(lon * 1e6))
    return trama


# --- Gateway virtual (protocolo UDP de Semtech, el del packet forwarder) ---

class Gateway:
    """
    @brief Gateway virtual que habla con el ChirpStack Gateway Bridge por el protocolo UDP de Semtech.

    Envía las subidas como PUSH_DATA y recibe las bajadas (Join Accept, ACK) como PULL_RESP. Dos
    hilos en segundo plano escuchan las bajadas y mandan el PULL_DATA periódico.
    """
    def __init__(self):
        """
        @brief Abre el socket UDP y arranca los hilos de escucha y de mantenimiento.
        """
        ## Socket UDP hacia el Gateway Bridge.
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', 0))
        ## Protege el diccionario esperas, que usan varios hilos.
        self.candado = threading.Lock()
        ## Bajadas esperadas: 'join' o DevAddr → (evento, lista donde se deja el downlink).
        self.esperas = {}  # 'join' o DevAddr → (evento, lista donde se deja el downlink)
        threading.Thread(target=self._escuchar, daemon=True).start()
        threading.Thread(target=self._mantener_vivo, daemon=True).start()

    def _enviar(self, tipo, cuerpo=b'', token=None):
        """
        @brief Envía un paquete del protocolo Semtech: versión 2 | token | tipo | EUI del gateway | cuerpo.
        @param tipo Identificador del paquete (0x00 PUSH_DATA, 0x02 PULL_DATA, 0x05 TX_ACK).
        @param cuerpo JSON ya codificado, o vacío.
        @param token Token de 2 bytes; si es None se genera uno aleatorio.
        """
        cabecera = b'\x02' + (token or random.randbytes(2)) + bytes([tipo]) + GATEWAY_EUI
        self.sock.sendto(cabecera + cuerpo, BRIDGE)

    def _mantener_vivo(self):
        """
        @brief Hilo que manda PULL_DATA cada 10 s: le dice al bridge a qué dirección mandar las bajadas.
        """
        while True:
            try:
                self._enviar(0x02)
            except OSError as e:
                print(f'[gateway] Bridge no disponible todavía: {e}', flush=True)
            time.sleep(10)

    def _escuchar(self):
        """
        @brief Hilo que recibe las bajadas (PULL_RESP), las confirma con TX_ACK y despierta a quien las espera.

        Un Join Accept (tipo 1) se entrega a la espera 'join'; una trama de datos de bajada (tipo 3 o
        5) a la espera de su DevAddr.
        """
        while True:
            datos, _ = self.sock.recvfrom(4096)
            if len(datos) < 4 or datos[3] != 0x03:  # Solo interesa PULL_RESP (downlink)
                continue
            txpk = json.loads(datos[4:])['txpk']
            self._enviar(0x05, json.dumps({'txpk_ack': {'error': 'NONE'}}).encode(), token=datos[1:3])
            phy = base64.b64decode(txpk['data'])
            tipo = phy[0] >> 5
            clave = 'join' if tipo == 1 else bytes(phy[1:5]) if tipo in (3, 5) else None
            print(f'[gateway] Downlink tipo {tipo} ({len(phy)} bytes)', flush=True)
            with self.candado:
                espera = self.esperas.pop(clave, None)
            if espera:
                espera[1].append(phy)
                espera[0].set()

    def preparar_espera(self, clave):
        """
        @brief Registra que se espera una bajada, antes de enviar la subida que la provoca.
        @param clave 'join' para un Join Accept, o el DevAddr para un ACK.
        @return Tupla (evento que se activa al llegar, lista donde se deja la trama).
        """
        espera = (threading.Event(), [])
        with self.candado:
            self.esperas[clave] = espera
        return espera

    def cancelar_espera(self, clave):
        """
        @brief Retira una espera que ya no se necesita (llegó o se agotó el tiempo).
        @param clave La misma que se pasó a preparar_espera().
        """
        with self.candado:
            self.esperas.pop(clave, None)

    def recibir(self, phy, datr, rssi, snr):
        """
        @brief Simula que el gateway recibió una trama por radio y la reenvía al bridge (PUSH_DATA).
        @param phy Trama PHY.
        @param datr Datarate, p. ej. "SF9BW125".
        @param rssi RSSI simulado en dBm.
        @param snr SNR simulado en dB.
        """
        rxpk = {
            'tmst': int(time.monotonic() * 1e6) & 0xFFFFFFFF,
            'time': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'chan': 0, 'rfch': 0, 'freq': random.choice(FRECUENCIAS), 'stat': 1,
            'modu': 'LORA', 'datr': datr, 'codr': '4/5', 'rssi': rssi, 'lsnr': snr,
            'size': len(phy), 'data': base64.b64encode(phy).decode(),
        }
        self._enviar(0x00, json.dumps({'rxpk': [rxpk]}).encode())


## Único gateway virtual del simulador.
gateway = Gateway()
## Sesiones de los nodos simulados: DevEUI (hex en mayúsculas) → Sesion.
sesiones = {}  # DevEUI (hex en mayúsculas) → Sesion
## Evita dos joins simultáneos: el Join Accept no dice para qué DevEUI es.
candado_join = threading.Lock()


class ErrorSimulador(Exception):
    """
    @brief Error que se responde al cliente HTTP con un código y un mensaje.
    """
    def __init__(self, estado, mensaje):
        """
        @brief Crea el error.
        @param estado Código HTTP de la respuesta (400, 502, 504...).
        @param mensaje Explicación para el usuario.
        """
        super().__init__(mensaje)
        ## Código HTTP de la respuesta.
        self.estado = estado


def leer_hex(cuerpo, campo, largo, obligatorio=True):
    """
    @brief Lee un campo hexadecimal del JSON de la petición (DevEUI, AppKey...).
    @param cuerpo JSON de la petición.
    @param campo Nombre del campo.
    @param largo Largo esperado en bytes.
    @param obligatorio Si es falso y el campo falta, devuelve None.
    @return Los bytes del campo.
    @exception ErrorSimulador 400 si el campo no tiene el largo o no es hexadecimal.
    """
    valor = str(cuerpo.get(campo, '')).replace(' ', '').upper()
    if not valor and not obligatorio:
        return None
    if not re.fullmatch(f'[0-9A-F]{{{largo * 2}}}', valor):
        raise ErrorSimulador(400, f'"{campo}" debe tener {largo * 2} dígitos hexadecimales')
    return bytes.fromhex(valor)


def unirse(dev_eui, app_key, join_eui, rssi, snr):
    """
    @brief Hace el join OTAA de un nodo simulado y guarda su sesión.
    @param dev_eui DevEUI de 8 bytes.
    @param app_key AppKey de 16 bytes.
    @param join_eui JoinEUI de 8 bytes.
    @param rssi RSSI simulado del Join Request.
    @param snr SNR simulado del Join Request.
    @return La Sesion nueva.
    @exception ErrorSimulador 504 si ChirpStack no responde; 502 si el Join Accept no es válido.
    """
    with candado_join:  # Un join a la vez: el Join Accept no dice para qué DevEUI es
        dev_nonce = random.randint(0, 0xFFFF)  # En 1.0.3 ChirpStack solo exige que no se repita
        evento, caja = gateway.preparar_espera('join')
        gateway.recibir(join_request(join_eui, dev_eui, dev_nonce, app_key), DATR_JOIN, rssi, snr)
        if not evento.wait(ESPERA_JOIN_ACCEPT):
            gateway.cancelar_espera('join')
            raise ErrorSimulador(504, 'ChirpStack no respondió el join. Revisa que el gateway y el dispositivo '
                                      'estén registrados, que el perfil sea LoRaWAN 1.0.3 y que el AppKey coincida')
        try:
            dev_addr, nwk_skey, app_skey = procesar_join_accept(caja[0], app_key, dev_nonce)
        except ValueError as e:
            raise ErrorSimulador(502, str(e))
    sesion = Sesion(dev_addr, nwk_skey, app_skey)
    sesiones[dev_eui.hex().upper()] = sesion
    print(f'[nodo {dev_eui.hex().upper()}] Join OK, DevAddr {dev_addr[::-1].hex().upper()}', flush=True)
    return sesion


def enviar_uplink(cuerpo):
    """
    @brief Atiende POST /uplink: envía una trama de EcoGuard como si viniera del nodo.

    Si el nodo no tiene sesión hace el join primero (necesita app_key). Igual que el firmware, las
    alertas y cancelaciones van confirmadas y se espera el ACK.
    @param cuerpo JSON de la petición.
    @return Resumen: DevEUI, DevAddr, si hubo join, FCnt usado, trama en hexadecimal y si llegó el ACK.
    @exception ErrorSimulador Si un campo es inválido o el join falla.
    """
    dev_eui = leer_hex(cuerpo, 'dev_eui', 8)
    rssi = int(cuerpo.get('rssi', -80))
    snr = float(cuerpo.get('snr', 7.5))
    sesion = sesiones.get(dev_eui.hex().upper())
    hizo_join = sesion is None
    if hizo_join:
        app_key = leer_hex(cuerpo, 'app_key', 16)
        join_eui = leer_hex(cuerpo, 'join_eui', 8, obligatorio=False) or bytes(8)
        sesion = unirse(dev_eui, app_key, join_eui, rssi, snr)

    sos = bool(cuerpo.get('sos', False))
    cancelado = bool(cuerpo.get('cancelado', False))
    lat, lon = cuerpo.get('lat'), cuerpo.get('lon')
    trama = trama_ecoguard(sos, cancelado, int(cuerpo.get('battery_mv', 3900)),
                           None if lat is None else float(lat), None if lon is None else float(lon))
    # Igual que el firmware: las alertas y cancelaciones van confirmadas
    confirmada = bool(cuerpo.get('confirmada', sos or cancelado))

    evento, caja = gateway.preparar_espera(sesion.dev_addr)
    fcnt = sesion.fcnt
    gateway.recibir(sesion.uplink(trama, confirmada), DATR_DATOS, rssi, snr)
    sesion.fcnt += 1

    ack = None
    if confirmada:
        ack = evento.wait(ESPERA_ACK) and bool(caja[0][5] & 0x20)  # Bit ACK del FCtrl
    gateway.cancelar_espera(sesion.dev_addr)

    return {
        'dev_eui': dev_eui.hex().upper(),
        'dev_addr': sesion.dev_addr[::-1].hex().upper(),
        'join': 'nuevo' if hizo_join else 'sesion existente',
        'f_cnt': fcnt,
        'trama': trama.hex().upper(),
        'confirmada': confirmada,
        'ack': ack,
    }


def forzar_join(cuerpo):
    """
    @brief Atiende POST /join: hace un join nuevo aunque el nodo ya tenga sesión.
    @param cuerpo JSON con dev_eui, app_key y, opcionalmente, join_eui, rssi y snr.
    @return DevEUI y DevAddr de la sesión nueva.
    @exception ErrorSimulador Si un campo es inválido o el join falla.
    """
    dev_eui = leer_hex(cuerpo, 'dev_eui', 8)
    app_key = leer_hex(cuerpo, 'app_key', 16)
    join_eui = leer_hex(cuerpo, 'join_eui', 8, obligatorio=False) or bytes(8)
    sesion = unirse(dev_eui, app_key, join_eui, int(cuerpo.get('rssi', -80)), float(cuerpo.get('snr', 7.5)))
    return {'dev_eui': dev_eui.hex().upper(), 'dev_addr': sesion.dev_addr[::-1].hex().upper()}


class Manejador(BaseHTTPRequestHandler):
    """
    @brief Servidor HTTP del simulador: atiende GET /, POST /uplink y POST /join.
    """
    def _responder(self, estado, datos):
        """
        @brief Envía una respuesta JSON.
        @param estado Código HTTP.
        @param datos Diccionario a serializar.
        """
        cuerpo = json.dumps(datos, ensure_ascii=False).encode()
        self.send_response(estado)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        """
        @brief GET /: muestra el EUI del gateway virtual y los nodos con sesión y su siguiente FCnt.
        """
        self._responder(200, {
            'gateway_eui': GATEWAY_EUI.hex().upper(),
            'nodos_con_sesion': {eui: {'dev_addr': s.dev_addr[::-1].hex().upper(), 'siguiente_f_cnt': s.fcnt}
                                 for eui, s in sesiones.items()},
        })

    def do_POST(self):
        """
        @brief POST /uplink y POST /join. Responde 404 en otras rutas y 400 si el JSON es inválido.
        """
        rutas = {'/uplink': enviar_uplink, '/join': forzar_join}
        if self.path not in rutas:
            return self._responder(404, {'error': 'Rutas: POST /uplink, POST /join, GET /'})
        try:
            largo = int(self.headers.get('Content-Length', 0))
            cuerpo = json.loads(self.rfile.read(largo) or b'{}')
            self._responder(200, rutas[self.path](cuerpo))
        except json.JSONDecodeError:
            self._responder(400, {'error': 'JSON inválido'})
        except ErrorSimulador as e:
            self._responder(e.estado, {'error': str(e)})


if __name__ == '__main__':
    print(f'Simulador escuchando en :{PUERTO_HTTP}, gateway {GATEWAY_EUI.hex().upper()} → {BRIDGE[0]}:{BRIDGE[1]}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PUERTO_HTTP), Manejador).serve_forever()
