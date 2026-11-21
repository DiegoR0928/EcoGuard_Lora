/// @brief Protocolo Bluetooth entre la app y el nodo EcoGuard (ver EcoGuard-Node/README.md).
///
/// Los enteros viajan en little-endian y las coordenadas en grados × 1 000 000 (int32). El nodo
/// ofrece un servicio BLE con dos características: una de escritura para los comandos de la app y
/// otra de lectura y notificación para su estado.
library;

import 'dart:typed_data';

/// UUID del servicio BLE del nodo. La app filtra el escaneo por él para ver solo nodos EcoGuard.
const uuidServicio = '4fafc201-1fb5-459e-8fcc-c5c9c331914b';
/// UUID de la característica de comandos. Escritura: app → nodo.
const uuidComandos = 'beb5483e-36e1-4688-b7f5-ea07361b26a8'; // Escritura: app → nodo
/// UUID de la característica de estado. Lectura y notificación: nodo → app.
const uuidEstado = 'd2b0f5a1-7c3e-4b8a-9f61-3a5e8c1d4e72'; // Lectura y notificación: nodo → app

/// Prefijo del nombre BLE: el nodo se anuncia como EcoGuard-XXXX, con los últimos 4 dígitos de su DevEUI.
const prefijoNombreNodo = 'EcoGuard-';

/// @brief Posición GPS en grados decimales (WGS 84).
class Coordenadas {
  /// Latitud en grados.
  final double lat;
  /// Longitud en grados.
  final double lon;
  /// @brief Crea una posición.
  /// @param lat Latitud en grados.
  /// @param lon Longitud en grados.
  const Coordenadas(this.lat, this.lon);
}

/// @brief Comandos que la app escribe en la característica de comandos del nodo.
///
/// Cada valor lleva en `codigo` el primer byte del comando.
enum Comando {
  /// Alerta con la posición del teléfono (código 0x01, 10 bytes).
  sos(0x01),
  /// Solo actualiza la posición durante una alerta (código 0x02, 10 bytes).
  posicion(0x02),
  /// Cancela la alerta activa (código 0x03, 1 byte).
  cancelar(0x03);

  const Comando(this.codigo);
  final int codigo;
}

/// @brief Arma los bytes de un comando para el nodo.
///
/// SOS y posición miden 10 bytes: [comando][banderas][lat][lon]. Sin fix GPS el bit 0 de las
/// banderas va en cero y el nodo ignora las coordenadas (RNF-07: nunca se inventa una posición).
/// @param comando Comando a enviar.
/// @param posicion Posición del teléfono; null si no hay fix GPS. Se ignora en Comando.cancelar.
/// @return Bytes listos para escribir en la característica de comandos.
Uint8List codificarComando(Comando comando, [Coordenadas? posicion]) {
  if (comando == Comando.cancelar) return Uint8List.fromList([Comando.cancelar.codigo]);

  final datos = ByteData(10)..setUint8(0, comando.codigo);
  if (posicion != null) {
    datos
      ..setUint8(1, 0x01)
      ..setInt32(2, (posicion.lat * 1e6).round(), Endian.little)
      ..setInt32(6, (posicion.lon * 1e6).round(), Endian.little);
  }
  return datos.buffer.asUint8List();
}

/// @brief Estado que el nodo notifica: [batería mV, uint16][banderas].
class EstadoNodo {
  /// Voltaje de la batería del nodo, en mV.
  final int bateriaMv;
  /// El nodo tiene sesión LoRaWAN: sus tramas pueden llegar a la central (bandera 0x01).
  final bool unidoARed; // El nodo tiene sesión LoRaWAN: sus tramas pueden llegar a la central
  /// El nodo tiene una alerta activa (bandera 0x02).
  final bool sosActivo;
  /// La central respondió con ACK a la alerta (bandera 0x04, CU-11).
  final bool alertaConfirmada; // La central respondió con ACK (CU-11)

  /// @brief Crea un estado.
  /// @param bateriaMv Voltaje de la batería en mV.
  /// @param unidoARed Si el nodo está unido a la red LoRaWAN.
  /// @param sosActivo Si hay una alerta activa.
  /// @param alertaConfirmada Si la central confirmó la alerta.
  const EstadoNodo({
    required this.bateriaMv,
    required this.unidoARed,
    required this.sosActivo,
    required this.alertaConfirmada,
  });

  /// @brief Decodifica el valor de la característica de estado.
  /// @param bytes Valor notificado por el nodo (3 bytes).
  /// @return El estado del nodo.
  /// @exception FormatException Si el valor mide menos de 3 bytes.
  factory EstadoNodo.desdeBytes(List<int> bytes) {
    if (bytes.length < 3) throw FormatException('Estado del nodo incompleto: ${bytes.length} bytes');
    final banderas = bytes[2];
    return EstadoNodo(
      bateriaMv: bytes[0] | (bytes[1] << 8),
      unidoARed: banderas & 0x01 != 0,
      sosActivo: banderas & 0x02 != 0,
      alertaConfirmada: banderas & 0x04 != 0,
    );
  }
}
