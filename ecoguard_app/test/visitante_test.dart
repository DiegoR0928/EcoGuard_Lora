// Casos de uso CU-09 a CU-12 del SRS con un nodo y un GPS simulados
import 'package:ecoguard_app/protocolo.dart';
import 'package:ecoguard_app/visitante.dart';
import 'package:flutter_test/flutter_test.dart';

import 'simulados.dart';

const parque = Coordenadas(22.7758, -102.5714);
const sosConGps = '0101F8875B0178E2E2F9';

void main() {
  late NodoSimulado nodo;
  late GpsSimulado gps;
  late Visitante visitante;
  late List<String> avisos;

  setUp(() {
    nodo = NodoSimulado();
    gps = GpsSimulado(parque);
    visitante = Visitante(nodo, gps, esperaReconexion: const Duration(milliseconds: 10));
    avisos = [];
    visitante.avisos.listen((aviso) => avisos.add(aviso.texto));
  });

  tearDown(() => visitante.dispose());

  Future<void> emparejar() async {
    await visitante.buscarNodos();
    await visitante.conectar(visitante.encontrados.first);
  }

  List<String> comandos(Comando tipo) => [
        for (final c in nodo.enviados)
          if (c[0] == tipo.codigo) hex(c),
      ];

  group('CU-09 Emparejar nodo', () {
    test('Busca, lista y conecta el nodo elegido', () async {
      await visitante.buscarNodos();
      expect(visitante.encontrados.map((n) => n.nombre), ['EcoGuard-3B60']);
      expect(visitante.fase, Fase.sinNodo);

      await visitante.conectar(visitante.encontrados.first);
      expect(visitante.fase, Fase.conectado);
      expect(visitante.nodo, nodoCercano);
      expect(visitante.bateria, 64); // 3900 mV
      expect(gps.permisoSolicitado, isTrue, reason: 'El permiso se pide antes de una emergencia');
    });

    test('Con el Bluetooth apagado pide activarlo', () async {
      nodo.bluetoothEncendido = false;
      await visitante.buscarNodos();
      await vaciarEventos();
      expect(visitante.encontrados, isEmpty);
      expect(avisos, ['Active el Bluetooth para buscar su nodo']);
    });

    test('FE1: error al conectar', () async {
      nodo.fallarConexion = true;
      await visitante.buscarNodos();
      await visitante.conectar(nodoCercano);
      await vaciarEventos();
      expect(visitante.nodo, isNull);
      expect(visitante.fase, Fase.sinNodo);
      expect(avisos, ['Error al conectar, intente nuevamente']);
    });
  });

  group('CU-10 Estado del nodo', () {
    test('FA1: batería baja', () async {
      await emparejar();
      expect(visitante.bateriaBaja, isFalse);
      nodo.notificar(const EstadoNodo(bateriaMv: 3700, unidoARed: true, sosActivo: false, alertaConfirmada: false));
      await vaciarEventos();
      expect(visitante.bateria, 13);
      expect(visitante.bateriaBaja, isTrue);
    });

    test('FE1: pierde el enlace y reconecta solo al volver a estar cerca', () async {
      await emparejar();
      nodo.fallarConexion = true; // El visitante se alejó
      nodo.perderEnlace();
      await vaciarEventos();
      expect(visitante.enlacePerdido, isTrue);

      await Future<void>.delayed(const Duration(milliseconds: 50));
      expect(visitante.enlacePerdido, isTrue);

      nodo.fallarConexion = false; // Regresó junto al nodo
      await esperarHasta(() => !visitante.enlacePerdido);
      expect(visitante.fase, Fase.conectado);
    });
  });

  group('CU-11 Emitir SOS', () {
    test('Envía la alerta con la ubicación del teléfono', () async {
      await emparejar();
      visitante.prepararUbicacion(); // Al empezar a presionar el botón
      await visitante.emitirSos();
      expect(nodo.enviados.map(hex), [sosConGps]);
      expect(visitante.fase, Fase.sosActivo);
      expect(visitante.ubicacionEnviada, isTrue);
      expect(gps.pedidos, 1, reason: 'Se reutiliza la ubicación pedida al empezar a presionar');

      await vaciarEventos();
      expect(visitante.estadoNodo!.sosActivo, isTrue);
      expect(avisos, ['¡Alerta enviada exitosamente!']);
    });

    test('FA1: sin GPS la alerta sale sin coordenadas', () async {
      gps.posicion = null;
      await emparejar();
      await visitante.emitirSos();
      expect(nodo.enviados.map(hex), ['01000000000000000000']);
      expect(visitante.fase, Fase.sosActivo);
      expect(visitante.ubicacionEnviada, isFalse);
    });

    test('FA1: la posición se envía cuando el GPS la consigue', () async {
      gps.posicion = null;
      await emparejar();
      await visitante.emitirSos();
      gps.movimientos.add(const Coordenadas(22.7765, -102.5720));
      await vaciarEventos();
      expect(comandos(Comando.posicion), ['0201B48A5B0120E0E2F9']);
      expect(visitante.ubicacionEnviada, isTrue);
    });

    test('Reenvía la última posición aunque el visitante no se mueva', () async {
      final rapido = Visitante(nodo, gps, refrescoPosicion: const Duration(milliseconds: 30));
      addTearDown(rapido.dispose);
      await rapido.buscarNodos();
      await rapido.conectar(nodoCercano);
      await rapido.emitirSos();
      await esperarHasta(() => comandos(Comando.posicion).length >= 2);
      expect(comandos(Comando.posicion).first, '0201F8875B0178E2E2F9');
    });

    test('FE1: el nodo no responde', () async {
      await emparejar();
      nodo.fallarEnvio = true;
      await visitante.emitirSos();
      await vaciarEventos();
      expect(visitante.fase, Fase.conectado);
      expect(avisos, ['Falla al comunicar con el nodo, intente presionar el botón físico en el dispositivo']);
    });

    test('No se puede desvincular el nodo durante una emergencia', () async {
      await emparejar();
      await visitante.emitirSos();
      await visitante.desvincular();
      expect(visitante.nodo, nodoCercano);
      expect(nodo.conectado, isTrue);
    });
  });

  group('CU-12 Cancelar falsa alarma', () {
    test('Cancela y vuelve al monitoreo', () async {
      await emparejar();
      await visitante.emitirSos();
      await visitante.cancelarSos();
      expect(hex(nodo.enviados.last), '03');
      expect(visitante.fase, Fase.conectado);

      await vaciarEventos();
      expect(visitante.estadoNodo!.sosActivo, isFalse);
      expect(avisos.last, 'Alerta cancelada');

      // Ya no se siguen enviando posiciones
      final enviados = nodo.enviados.length;
      gps.movimientos.add(const Coordenadas(22.7765, -102.5720));
      await vaciarEventos();
      expect(nodo.enviados, hasLength(enviados));
    });

    test('FE1: la cancelación no llega al nodo', () async {
      await emparejar();
      await visitante.emitirSos();
      nodo.fallarEnvio = true;
      await visitante.cancelarSos();
      await vaciarEventos();
      expect(visitante.fase, Fase.sosActivo);
      expect(avisos.last, 'No se pudo cancelar. Contacte a los vigilantes si se los encuentra');
    });
  });

  group('Sincronización con el nodo', () {
    test('Si el nodo se reinicia durante la emergencia, se le vuelve a ordenar el SOS', () async {
      await emparejar();
      await visitante.emitirSos();
      nodo.estado = const EstadoNodo(bateriaMv: 3900, unidoARed: false, sosActivo: false, alertaConfirmada: false);
      nodo.perderEnlace();
      await esperarHasta(() => comandos(Comando.sos).length == 2);
      expect(comandos(Comando.sos).last, sosConGps);
      expect(visitante.fase, Fase.sosActivo);
      expect(visitante.enlacePerdido, isFalse);
    });

    test('Al reabrir la app con una alerta en curso, la muestra', () async {
      nodo.estado = const EstadoNodo(bateriaMv: 3900, unidoARed: true, sosActivo: true, alertaConfirmada: true);
      await emparejar();
      expect(visitante.fase, Fase.sosActivo);
      expect(nodo.enviados, isEmpty, reason: 'No se duplica la alerta');
    });
  });
}
