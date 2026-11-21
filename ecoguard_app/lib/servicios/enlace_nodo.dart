/// @brief Enlace Bluetooth LE con el nodo EcoGuard.
///
/// EnlaceNodo define lo que la app necesita del nodo; EnlaceBluetooth lo implementa con
/// flutter_blue_plus y EnlaceSimulado (simulacion.dart), sin hardware.
library;

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import '../protocolo.dart';

/// @brief Nodo EcoGuard encontrado en un escaneo Bluetooth.
class NodoEncontrado {
  /// Identificador del dispositivo para conectarse (dirección MAC en Android, UUID en iOS).
  final String id;
  /// Nombre BLE del nodo, p. ej. EcoGuard-3B60.
  final String nombre;
  /// Intensidad de la señal en dBm: más cerca de 0, más cerca está el nodo.
  final int rssi; // Intensidad de la señal en dBm: más cerca de 0, más cerca está el nodo

  /// @brief Crea el resultado de un escaneo.
  /// @param id Identificador del dispositivo.
  /// @param nombre Nombre BLE.
  /// @param rssi Intensidad de la señal en dBm.
  const NodoEncontrado(this.id, this.nombre, this.rssi);
}

/// @brief Lo que la app necesita del nodo. Las pruebas lo sustituyen por un nodo simulado.
abstract class EnlaceNodo {
  /// @brief Indica si el Bluetooth del teléfono está encendido; en Android pide encenderlo si no lo está.
  /// @return true si el Bluetooth está disponible.
  Future<bool> bluetoothDisponible();

  /// @brief Busca nodos EcoGuard e informa la lista cada vez que cambia (CU-09).
  /// @param alEncontrar Se llama con la lista de nodos encontrados, del más cercano al más lejano.
  /// @param duracion Tiempo que dura el escaneo.
  /// @return Se completa al terminar el escaneo.
  Future<void> buscar(void Function(List<NodoEncontrado>) alEncontrar, {Duration duracion});

  /// @brief Conecta con un nodo y se suscribe a su estado.
  /// @param id Identificador del nodo (NodoEncontrado.id).
  /// @return El estado inicial del nodo.
  /// @exception Exception Si la conexión falla o el dispositivo no es un nodo EcoGuard.
  Future<EstadoNodo> conectar(String id);

  /// @brief Cierra la conexión con el nodo. Una desconexión pedida no cuenta como pérdida del enlace.
  /// @return Se completa al cerrarse la conexión.
  Future<void> desconectar();

  /// @brief Escribe un comando en el nodo y espera su confirmación de recepción.
  /// @param comando Bytes del comando (codificarComando()).
  /// @return Se completa cuando el nodo confirma que recibió el comando.
  /// @exception StateError Si no hay un nodo conectado o el nodo no respondió.
  Future<void> enviar(Uint8List comando);

  /// Cada notificación de estado del nodo (batería, red, SOS, confirmación de la central).
  Stream<EstadoNodo> get estados;

  /// Se emite cuando el enlace se cae sin que la app lo haya pedido (CU-10, FE1).
  Stream<void> get perdidas;
}

/// @brief Enlace real con el nodo por Bluetooth LE (paquete flutter_blue_plus).
class EnlaceBluetooth implements EnlaceNodo {
  /// Emite cada estado notificado por el nodo.
  final _estados = StreamController<EstadoNodo>.broadcast();
  /// Emite cada pérdida del enlace.
  final _perdidas = StreamController<void>.broadcast();
  /// Nodo conectado; null si no hay conexión.
  BluetoothDevice? _dispositivo;
  /// Característica de comandos del nodo conectado.
  BluetoothCharacteristic? _comandos;
  /// Suscripción al estado de la conexión, para detectar pérdidas del enlace.
  StreamSubscription<BluetoothConnectionState>? _vigilancia;

  /// Cada notificación de estado del nodo.
  @override
  Stream<EstadoNodo> get estados => _estados.stream;

  /// Se emite cuando el enlace se cae sin que la app lo haya pedido.
  @override
  Stream<void> get perdidas => _perdidas.stream;

  @override
  Future<bool> bluetoothDisponible() async {
    if (Platform.isAndroid && FlutterBluePlus.adapterStateNow != BluetoothAdapterState.on) {
      try {
        await FlutterBluePlus.turnOn();
      } catch (_) {
        return false; // El visitante rechazó encenderlo
      }
    }
    // En iOS el estado arranca en "desconocido" hasta que el sistema lo informa
    final estado = await FlutterBluePlus.adapterState
        .firstWhere((e) => e != BluetoothAdapterState.unknown)
        .timeout(const Duration(seconds: 3), onTimeout: () => BluetoothAdapterState.unknown);
    return estado == BluetoothAdapterState.on;
  }

  @override
  Future<void> buscar(void Function(List<NodoEncontrado>) alEncontrar,
      {Duration duracion = const Duration(seconds: 8)}) async {
    final resultados = FlutterBluePlus.onScanResults.listen(
      (lista) => alEncontrar([
        for (final r in lista)
          NodoEncontrado(
            r.device.remoteId.str,
            r.advertisementData.advName.isNotEmpty ? r.advertisementData.advName : r.device.platformName,
            r.rssi,
          ),
      ]..sort((a, b) => b.rssi.compareTo(a.rssi))),
      onError: (_) {},
    );
    try {
      // El nodo anuncia el UUID de su servicio: filtrar por él deja solo nodos EcoGuard
      await FlutterBluePlus.startScan(withServices: [Guid(uuidServicio)], timeout: duracion);
      await FlutterBluePlus.isScanning.firstWhere((escaneando) => !escaneando);
    } finally {
      await resultados.cancel();
    }
  }

  @override
  Future<EstadoNodo> conectar(String id) async {
    await desconectar();
    final dispositivo = BluetoothDevice.fromId(id);
    // flutter_blue_plus exige declarar la licencia: la no comercial cubre uso educativo (tesis UAZ).
    // Si EcoGuard se comercializa, hay que adquirir la licencia comercial (License.commercial).
    await dispositivo.connect(license: License.nonprofit, timeout: const Duration(seconds: 10));
    try {
      final servicio = (await dispositivo.discoverServices()).firstWhere((s) => s.uuid == Guid(uuidServicio));
      final comandos = servicio.characteristics.firstWhere((c) => c.uuid == Guid(uuidComandos));
      final estado = servicio.characteristics.firstWhere((c) => c.uuid == Guid(uuidEstado));

      final notificaciones = estado.onValueReceived.listen(_recibirEstado);
      dispositivo.cancelWhenDisconnected(notificaciones);
      await estado.setNotifyValue(true);
      final inicial = EstadoNodo.desdeBytes(await estado.read());

      _dispositivo = dispositivo;
      _comandos = comandos;
      _vigilancia = dispositivo.connectionState.listen((conexion) {
        if (conexion == BluetoothConnectionState.disconnected) _perdidas.add(null);
      });
      return inicial;
    } catch (_) {
      await dispositivo.disconnect();
      rethrow;
    }
  }

  /// @brief Decodifica una notificación de estado del nodo y la publica en estados.
  ///
  /// Una notificación incompleta se descarta y se espera la siguiente.
  /// @param bytes Valor notificado.
  void _recibirEstado(List<int> bytes) {
    try {
      _estados.add(EstadoNodo.desdeBytes(bytes));
    } on FormatException {
      // Notificación incompleta: se espera la siguiente
    }
  }

  @override
  Future<void> desconectar() async {
    // Se deja de vigilar antes de desconectar: una desconexión pedida no es una pérdida de enlace
    await _vigilancia?.cancel();
    _vigilancia = null;
    _comandos = null;
    await _dispositivo?.disconnect();
    _dispositivo = null;
  }

  @override
  Future<void> enviar(Uint8List comando) async {
    final comandos = _comandos;
    if (comandos == null) throw StateError('No hay un nodo conectado');
    // Escritura con respuesta: si vuelve sin error, el nodo recibió el comando
    await comandos.write(comando, withoutResponse: false, timeout: 5);
  }
}
