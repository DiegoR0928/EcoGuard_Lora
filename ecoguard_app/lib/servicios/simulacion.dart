/// @brief Modo simulación: nodo y GPS virtuales para ver y demostrar la app sin hardware.
///
/// Se comportan como el firmware: el nodo se une a la red LoRaWAN unos segundos después de conectar
/// y la central confirma el SOS poco después de recibirlo. Nada sale del teléfono: no llega a
/// ChirpStack ni al panel. Se activa con --dart-define=SIMULACION=true y siempre fuera de Android e iOS.
library;

import 'dart:async';
import 'dart:typed_data';

import '../protocolo.dart';
import 'enlace_nodo.dart';
import 'ubicacion.dart';

/// @brief Nodo y GPS simulados que comparten la app y el menú de simulación.
class Simulacion {
  /// Nodo simulado.
  final enlace = EnlaceSimulado();
  /// GPS simulado.
  final ubicacion = UbicacionSimulada();
}

/// @brief Nodo EcoGuard simulado.
///
/// Las banderas públicas (fueraDeAlcance, sinCobertura, fallarEnvio) provocan las situaciones de los
/// casos de uso desde el menú de simulación.
class EnlaceSimulado implements EnlaceNodo {
  /// Nodos que "aparecen" en el escaneo, del más cercano al más lejano.
  static const _cercanos = [
    NodoEncontrado('simulado-3B60', 'EcoGuard-3B60', -58),
    NodoEncontrado('simulado-A1F2', 'EcoGuard-A1F2', -74),
    NodoEncontrado('simulado-07C9', 'EcoGuard-07C9', -89),
  ];
  /// Voltaje de batería normal, en mV (66 %).
  static const _bateriaNormal = 3920;
  /// Voltaje de batería baja, en mV (13 %, por debajo de umbralBateriaBaja).
  static const _bateriaBaja = 3700;

  /// Emite cada estado notificado por el nodo simulado.
  final _estados = StreamController<EstadoNodo>.broadcast();
  /// Emite cada pérdida del enlace.
  final _perdidas = StreamController<void>.broadcast();
  /// Hay una app conectada al nodo.
  bool _conectado = false;
  /// Voltaje actual de la batería, en mV.
  int _bateriaMv = _bateriaNormal;
  /// El nodo está unido a la red LoRaWAN.
  bool _unido = false;
  /// El nodo tiene una alerta activa.
  bool _sos = false;
  /// La central confirmó la alerta.
  bool _confirmada = false;

  /// El nodo no responde a la conexión y, si estaba conectado, se pierde el enlace (CU-09 FE1, CU-10 FE1).
  bool fueraDeAlcance = false;
  /// El nodo no tiene cobertura LoRaWAN: no se une a la red y la central no confirma.
  bool sinCobertura = false;
  /// El nodo no responde a los comandos (CU-11 FE1, CU-12 FE1).
  bool fallarEnvio = false;
  /// Verdadero si la batería simulada está baja (CU-10 FA1).
  bool get bateriaBaja => _bateriaMv == _bateriaBaja;

  /// Estado actual del nodo simulado, como lo notificaría el nodo real.
  EstadoNodo get _estado =>
      EstadoNodo(bateriaMv: _bateriaMv, unidoARed: _unido, sosActivo: _sos, alertaConfirmada: _confirmada);

  /// Cada notificación de estado del nodo simulado.
  @override
  Stream<EstadoNodo> get estados => _estados.stream;

  /// Se emite cuando el nodo simulado queda fuera de alcance.
  @override
  Stream<void> get perdidas => _perdidas.stream;

  @override
  Future<bool> bluetoothDisponible() async => true;

  @override
  Future<void> buscar(void Function(List<NodoEncontrado>) alEncontrar, {Duration? duracion}) async {
    // Los nodos aparecen uno a uno, como en un escaneo real
    for (var i = 1; i <= _cercanos.length; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 700));
      alEncontrar(_cercanos.take(i).toList());
    }
    await Future<void>.delayed(const Duration(milliseconds: 600));
  }

  @override
  Future<EstadoNodo> conectar(String id) async {
    await Future<void>.delayed(const Duration(milliseconds: 1200));
    if (fueraDeAlcance) throw StateError('Nodo fuera de alcance');
    _conectado = true;
    _unirseALaRed();
    return _estado;
  }

  @override
  Future<void> desconectar() async => _conectado = false;

  @override
  Future<void> enviar(Uint8List comando) async {
    await Future<void>.delayed(const Duration(milliseconds: 300));
    if (!_conectado || fallarEnvio) throw StateError('El nodo no respondió');
    if (comando[0] == Comando.sos.codigo && !_sos) {
      _sos = true;
      _confirmada = false;
      _notificar();
      _esperarConfirmacion();
    } else if (comando[0] == Comando.cancelar.codigo) {
      _sos = false;
      _confirmada = false;
      _notificar();
    }
  }

  /// @brief Pone o quita el nodo fuera de alcance. Si estaba conectado, se pierde el enlace y la app reintenta.
  void alternarAlcance() {
    fueraDeAlcance = !fueraDeAlcance;
    if (fueraDeAlcance && _conectado) {
      _conectado = false;
      _perdidas.add(null); // La app reintenta conectar cada pocos segundos
    }
  }

  /// @brief Alterna la batería entre normal y baja.
  void alternarBateria() {
    _bateriaMv = bateriaBaja ? _bateriaNormal : _bateriaBaja;
    _notificar();
  }

  /// @brief Quita o devuelve la cobertura LoRaWAN. Al volver, el nodo se une otra vez a la red.
  void alternarCobertura() {
    sinCobertura = !sinCobertura;
    if (sinCobertura) {
      _unido = false;
      _notificar();
    } else {
      _unirseALaRed();
    }
  }

  /// @brief Hace que el nodo deje de responder a los comandos, o que vuelva a hacerlo.
  void alternarFallaEnvio() => fallarEnvio = !fallarEnvio;

  /// @brief Simula el join OTAA, que tarda unos segundos.
  void _unirseALaRed() {
    if (_unido) return;
    Timer(const Duration(seconds: 3), () {
      if (_unido || sinCobertura) return;
      _unido = true;
      _notificar();
      _esperarConfirmacion();
    });
  }

  /// @brief Simula el ACK de la central, que llega en la siguiente ventana de recepción tras el SOS.
  void _esperarConfirmacion() {
    if (!_sos || !_unido || _confirmada) return;
    Timer(const Duration(seconds: 4), () {
      if (!_sos || !_unido || _confirmada) return;
      _confirmada = true;
      _notificar();
    });
  }

  /// @brief Notifica el estado a la app, si está conectada.
  void _notificar() {
    if (_conectado) _estados.add(_estado);
  }
}

/// @brief GPS simulado que recorre la ruta piloto.
class UbicacionSimulada implements Ubicacion {
  /// Puntos de control de la ruta piloto en el Campus UAZ Siglo XXI (pruebas/ruta_piloto.geojson).
  static const _ruta = [
    Coordenadas(22.77227, -102.64472), // Plaza LILEX
    Coordenadas(22.77146, -102.64380), // Explanada central
    Coordenadas(22.76969, -102.64384), // Andador auditorio
    Coordenadas(22.76889, -102.64588), // Cancha de futbol americano
  ];

  /// Sin señal GPS: obtener() agota el tiempo de espera y seguir() no emite posiciones.
  bool sinSenal = false;

  /// @brief Quita o devuelve la señal GPS (CU-11 FA1).
  void alternarSenal() => sinSenal = !sinSenal;

  @override
  Future<bool> solicitarPermiso() async => true;

  @override
  Future<Coordenadas?> obtener(Duration limite) async {
    // Sin señal se agota el tiempo de espera y la alerta sale sin posición (CU-11, FA1)
    await Future<void>.delayed(sinSenal ? limite : const Duration(milliseconds: 1500));
    return sinSenal ? null : _ruta.first;
  }

  /// @brief El visitante avanza al siguiente punto de la ruta cada 15 s.
  /// @return Flujo con las posiciones de la ruta.
  @override
  Stream<Coordenadas> seguir() => Stream.periodic(const Duration(seconds: 15), (i) => _ruta[(i + 1) % _ruta.length])
      .where((_) => !sinSenal);
}
