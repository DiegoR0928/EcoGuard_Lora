"""
Gateway + nodo EcoGuard virtuales, para probar ChirpStack sin hardware.

Postman → POST /uplink con JSON sencillo → este simulador arma la misma trama que el firmware
(ver EcoGuard-Node/README.md), hace el join OTAA si hace falta, la cifra como un nodo LoRaWAN 1.0.3
y se la entrega al Gateway Bridge por UDP (protocolo Semtech), igual que un gateway real.
De ahí en adelante todo es real: ChirpStack valida, decodifica con codec.js y la integración
HTTP la manda al webhook de Django.

Los nodos simulados usan LoRaWAN 1.0.3 (una sola llave) para mantener la criptografía simple;
el nodo real usa 1.1.0. Lo que se prueba (ChirpStack → codec → webhook) es igual en ambos.
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

BRIDGE = (os.environ.get('BRIDGE_HOST', 'chirpstack-gateway-bridge'), int(os.environ.get('BRIDGE_PORT', '1700')))
GATEWAY_EUI = bytes.fromhex(os.environ.get('GATEWAY_EUI', '0016C001FF10A235'))
PUERTO_HTTP = int(os.environ.get('PUERTO_HTTP', '8070'))

# US915 sub-banda 2 (canales 8–15), la misma que usan el nodo y ChirpStack
FRECUENCIAS = [round(903.9 + 0.2 * i, 1) for i in range(8)]
DATR_JOIN = 'SF10BW125'   # DR0
DATR_DATOS = 'SF9BW125'   # DR1, el datarate fijo del firmware
PUERTO_LORAWAN = 1

ESPERA_JOIN_ACCEPT = 8.0  # El Join Accept sale en RX1 (5 s) o RX2 (6 s)
ESPERA_ACK = 4.0          # El ACK sale en RX1 (1 s) o RX2 (2 s)


# --- Criptografía LoRaWAN 1.0.x ---

def aes_ecb(llave, datos):
    cifrador = Cipher(algorithms.AES(llave), modes.ECB()).encryptor()
    return cifrador.update(datos) + cifrador.finalize()


def mic(llave, datos):
    c = CMAC(algorithms.AES(llave))
    c.update(datos)
    return c.finalize()[:4]


def join_request(join_eui, dev_eui, dev_nonce, app_key):
    # Los EUI viajan en little-endian
    msg = b'\x00' + join_eui[::-1] + dev_eui[::-1] + struct.pack('<H', dev_nonce)
    return msg + mic(app_key, msg)


def procesar_join_accept(phy, app_key, dev_nonce):
    # El servidor "descifra" con AES, así que el nodo cifra para recuperar el texto claro
    claro = aes_ecb(app_key, phy[1:])
    if mic(app_key, phy[:1] + claro[:-4]) != claro[-4:]:
        raise ValueError('El MIC del Join Accept no coincide: el AppKey no es el registrado en ChirpStack')
    app_nonce, net_id, dev_addr = claro[0:3], claro[3:6], claro[6:10]
    base = app_nonce + net_id + struct.pack('<H', dev_nonce) + bytes(7)
    return dev_addr, aes_ecb(app_key, b'\x01' + base), aes_ecb(app_key, b'\x02' + base)


def cifrar_payload(app_skey, dev_addr, fcnt, payload):
    salida = bytearray()
    for i in range(0, len(payload), 16):
        bloque = b'\x01' + bytes(4) + b'\x00' + dev_addr + struct.pack('<I', fcnt) + b'\x00' + bytes([i // 16 + 1])
        salida += bytes(a ^ b for a, b in zip(payload[i:i + 16], aes_ecb(app_skey, bloque)))
    return bytes(salida)


@dataclass
class Sesion:
    dev_addr: bytes  # Tal como viaja en la trama (little-endian)
    nwk_skey: bytes
    app_skey: bytes
    fcnt: int = 0

    def uplink(self, payload, confirmada):
        mhdr = b'\x80' if confirmada else b'\x40'
        fhdr = self.dev_addr + b'\x00' + struct.pack('<H', self.fcnt & 0xFFFF)  # FCtrl sin ADR, como el firmware
        msg = mhdr + fhdr + bytes([PUERTO_LORAWAN]) + cifrar_payload(self.app_skey, self.dev_addr, self.fcnt, payload)
        b0 = b'\x49' + bytes(4) + b'\x00' + self.dev_addr + struct.pack('<I', self.fcnt) + b'\x00' + bytes([len(msg)])
        return msg + mic(self.nwk_skey, b0 + msg)


def trama_ecoguard(sos, cancelado, bateria_mv, lat, lon):
    """Mismo formato que enviarTrama() del firmware."""
    con_gps = lat is not None and lon is not None
    banderas = (0x01 if sos else 0) | (0x02 if con_gps else 0) | (0x04 if cancelado else 0)
    trama = struct.pack('<BH', banderas, bateria_mv)
    if con_gps:
        trama += struct.pack('<ii', round(lat * 1e6), round(lon * 1e6))
    return trama


# --- Gateway virtual (protocolo UDP de Semtech, el del packet forwarder) ---

class Gateway:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', 0))
        self.candado = threading.Lock()
        self.esperas = {}  # 'join' o DevAddr → (evento, lista donde se deja el downlink)
        threading.Thread(target=self._escuchar, daemon=True).start()
        threading.Thread(target=self._mantener_vivo, daemon=True).start()

    def _enviar(self, tipo, cuerpo=b'', token=None):
        cabecera = b'\x02' + (token or random.randbytes(2)) + bytes([tipo]) + GATEWAY_EUI
        self.sock.sendto(cabecera + cuerpo, BRIDGE)

    def _mantener_vivo(self):
        # PULL_DATA periódico: le dice al bridge a qué dirección mandar los downlinks
        while True:
            try:
                self._enviar(0x02)
            except OSError as e:
                print(f'[gateway] Bridge no disponible todavía: {e}', flush=True)
            time.sleep(10)

    def _escuchar(self):
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
        espera = (threading.Event(), [])
        with self.candado:
            self.esperas[clave] = espera
        return espera

    def cancelar_espera(self, clave):
        with self.candado:
            self.esperas.pop(clave, None)

    def recibir(self, phy, datr, rssi, snr):
        rxpk = {
            'tmst': int(time.monotonic() * 1e6) & 0xFFFFFFFF,
            'time': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'chan': 0, 'rfch': 0, 'freq': random.choice(FRECUENCIAS), 'stat': 1,
            'modu': 'LORA', 'datr': datr, 'codr': '4/5', 'rssi': rssi, 'lsnr': snr,
            'size': len(phy), 'data': base64.b64encode(phy).decode(),
        }
        self._enviar(0x00, json.dumps({'rxpk': [rxpk]}).encode())


gateway = Gateway()
sesiones = {}  # DevEUI (hex en mayúsculas) → Sesion
candado_join = threading.Lock()


class ErrorSimulador(Exception):
    def __init__(self, estado, mensaje):
        super().__init__(mensaje)
        self.estado = estado


def leer_hex(cuerpo, campo, largo, obligatorio=True):
    valor = str(cuerpo.get(campo, '')).replace(' ', '').upper()
    if not valor and not obligatorio:
        return None
    if not re.fullmatch(f'[0-9A-F]{{{largo * 2}}}', valor):
        raise ErrorSimulador(400, f'"{campo}" debe tener {largo * 2} dígitos hexadecimales')
    return bytes.fromhex(valor)


def unirse(dev_eui, app_key, join_eui, rssi, snr):
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
    dev_eui = leer_hex(cuerpo, 'dev_eui', 8)
    app_key = leer_hex(cuerpo, 'app_key', 16)
    join_eui = leer_hex(cuerpo, 'join_eui', 8, obligatorio=False) or bytes(8)
    sesion = unirse(dev_eui, app_key, join_eui, int(cuerpo.get('rssi', -80)), float(cuerpo.get('snr', 7.5)))
    return {'dev_eui': dev_eui.hex().upper(), 'dev_addr': sesion.dev_addr[::-1].hex().upper()}


class Manejador(BaseHTTPRequestHandler):
    def _responder(self, estado, datos):
        cuerpo = json.dumps(datos, ensure_ascii=False).encode()
        self.send_response(estado)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        self._responder(200, {
            'gateway_eui': GATEWAY_EUI.hex().upper(),
            'nodos_con_sesion': {eui: {'dev_addr': s.dev_addr[::-1].hex().upper(), 'siguiente_f_cnt': s.fcnt}
                                 for eui, s in sesiones.items()},
        })

    def do_POST(self):
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
