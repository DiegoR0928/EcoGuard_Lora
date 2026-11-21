// Nodo y GPS simulados para probar la app sin hardware. El nodo responde a los comandos como el
// firmware: el SOS lo pone en modo alerta y la cancelación lo saca.
import 'dart:async';
import 'dart:typed_data';

import 'package:ecoguard_app/protocolo.dart';
import 'package:ecoguard_app/servicios/enlace_nodo.dart';
import 'package:ecoguard_app/servicios/ubicacion.dart';

const nodoCercano = NodoEncontrado('AA:BB:CC:DD:EE:01', 'EcoGuard-3B60', -60);

class NodoSimulado implements EnlaceNodo {
  final _estados = StreamController<EstadoNodo>.broadcast();
  final _perdidas = StreamController<void>.broadcast();
  final List<Uint8List> enviados = [];

  bool bluetoothEncendido = true;
  bool fallarConexion = false;
  bool fallarEnvio = false;
  bool conectado = false;
  EstadoNodo estado = const EstadoNodo(bateriaMv: 3900, unidoARed: true, sosActivo: false, alertaConfirmada: false);

  @override
  Stream<EstadoNodo> get estados => _estados.stream;

  @override
  Stream<void> get perdidas => _perdidas.stream;

  @override
  Future<bool> bluetoothDisponible() async => bluetoothEncendido;

  @override
  Future<void> buscar(void Function(List<NodoEncontrado>) alEncontrar, {Duration? duracion}) async =>
      alEncontrar([nodoCercano]);

  @override
  Future<EstadoNodo> conectar(String id) async {
    if (fallarConexion) throw Exception('Conexión rechazada por interferencia');
    conectado = true;
    return estado;
  }

  @override
  Future<void> desconectar() async => conectado = false;

  @override
  Future<void> enviar(Uint8List comando) async {
    if (fallarEnvio || !conectado) throw Exception('Sin respuesta del nodo');
    enviados.add(comando);
    if (comando[0] == Comando.sos.codigo) notificar(_con(sosActivo: true));
    if (comando[0] == Comando.cancelar.codigo) notificar(_con(sosActivo: false));
  }

  void notificar(EstadoNodo nuevo) {
    estado = nuevo;
    _estados.add(nuevo);
  }

  void perderEnlace() {
    conectado = false;
    _perdidas.add(null);
  }

  EstadoNodo _con({int? bateriaMv, bool? sosActivo, bool? alertaConfirmada}) => EstadoNodo(
        bateriaMv: bateriaMv ?? estado.bateriaMv,
        unidoARed: estado.unidoARed,
        sosActivo: sosActivo ?? estado.sosActivo,
        alertaConfirmada: alertaConfirmada ?? estado.alertaConfirmada,
      );
}

class GpsSimulado implements Ubicacion {
  final movimientos = StreamController<Coordenadas>.broadcast();
  Coordenadas? posicion;
  int pedidos = 0;
  bool permisoSolicitado = false;

  GpsSimulado([this.posicion]);

  @override
  Future<bool> solicitarPermiso() async => permisoSolicitado = true;

  @override
  Future<Coordenadas?> obtener(Duration limite) async {
    pedidos++;
    return posicion;
  }

  @override
  Stream<Coordenadas> seguir() => movimientos.stream;
}

String hex(List<int> bytes) => bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join().toUpperCase();

// Deja correr las notificaciones y avisos pendientes
Future<void> vaciarEventos() async {
  for (var i = 0; i < 10; i++) {
    await Future<void>.delayed(Duration.zero);
  }
}

Future<void> esperarHasta(bool Function() condicion, {Duration limite = const Duration(seconds: 2)}) async {
  final fin = DateTime.now().add(limite);
  while (!condicion()) {
    if (DateTime.now().isAfter(fin)) throw StateError('La condición no se cumplió a tiempo');
    await Future<void>.delayed(const Duration(milliseconds: 5));
  }
}
