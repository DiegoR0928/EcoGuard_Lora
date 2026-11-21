// Pantallas de la app con un nodo y un GPS simulados
import 'package:ecoguard_app/main.dart';
import 'package:ecoguard_app/pantallas/monitoreo.dart';
import 'package:ecoguard_app/protocolo.dart';
import 'package:ecoguard_app/visitante.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'simulados.dart';

void main() {
  // Pantalla de un teléfono común (390 × 844)
  void usarTelefono(WidgetTester tester) {
    tester.view.physicalSize = const Size(1170, 2532);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
  }

  // Las animaciones del botón y del latido no terminan nunca: se avanza el tiempo a mano
  Future<void> esperar(WidgetTester tester, [Duration tiempo = const Duration(milliseconds: 400)]) async {
    await tester.pump();
    await tester.pump(tiempo);
  }

  group('Botón SOS (RNF-09)', () {
    late int iniciados;
    late int completados;

    Future<TestGesture> presionar(WidgetTester tester) async {
      iniciados = 0;
      completados = 0;
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Center(child: BotonSos(alIniciar: () => iniciados++, alCompletar: () => completados++)),
        ),
      ));
      final gesto = await tester.startGesture(tester.getCenter(find.byType(BotonSos)));
      await tester.pump();
      return gesto;
    }

    testWidgets('Emite la alerta solo al cumplir 3 s presionado', (tester) async {
      final gesto = await presionar(tester);
      expect(iniciados, 1, reason: 'El GPS empieza a buscar al tocar el botón');

      await tester.pump(const Duration(seconds: 1));
      expect(find.text('Siga presionando…'), findsOneWidget);
      await tester.pump(const Duration(milliseconds: 1800));
      expect(completados, 0);

      await tester.pump(const Duration(milliseconds: 1300));
      expect(completados, 1);
      await gesto.up();
      await tester.pump();
      expect(completados, 1);
    });

    testWidgets('Soltarlo antes de tiempo no emite nada', (tester) async {
      final gesto = await presionar(tester);
      await tester.pump(const Duration(seconds: 2));
      await gesto.up();
      await tester.pump(const Duration(seconds: 3));
      expect(completados, 0);
      expect(find.text('Siga presionando…'), findsNothing);
    });
  });

  testWidgets('Flujo completo: emparejar, pedir ayuda y cancelar (CU-09, CU-11, CU-12)', (tester) async {
    usarTelefono(tester);
    final nodo = NodoSimulado();
    final visitante = Visitante(nodo, GpsSimulado(const Coordenadas(22.7758, -102.5714)));
    await tester.pumpWidget(EcoGuardApp(visitante: visitante));
    expect(find.text('Sin nodo emparejado'), findsOneWidget);

    // CU-09
    await tester.tap(find.text('Buscar nodos'));
    await esperar(tester);
    expect(find.text('Señal fuerte'), findsOneWidget);
    await tester.tap(find.text('EcoGuard-3B60'));
    await esperar(tester);
    expect(find.text('Estado: Conectado'), findsOneWidget);
    expect(find.text('Batería: 64%'), findsOneWidget);

    // CU-11
    final gesto = await tester.startGesture(tester.getCenter(find.byType(BotonSos)));
    for (var i = 0; i < 8; i++) {
      await tester.pump(const Duration(milliseconds: 500));
    }
    await gesto.up();
    await esperar(tester);
    expect(find.text('SOS Activo'), findsOneWidget);
    expect(find.text('¡Alerta enviada exitosamente!'), findsOneWidget);
    expect(find.text('Ubicación enviada'), findsOneWidget);
    expect(nodo.enviados.map(hex), ['0101F8875B0178E2E2F9']);

    // CU-12, FA1: «Regresar» mantiene la alerta activa
    await tester.tap(find.text('Cancelar Alerta'));
    await esperar(tester);
    expect(find.text('¿Desea cancelar el rescate?'), findsOneWidget);
    await tester.tap(find.text('Regresar'));
    await esperar(tester);
    expect(find.text('SOS Activo'), findsOneWidget);
    expect(nodo.enviados, hasLength(1));

    // CU-12: «Confirmar» cancela y vuelve al monitoreo
    await tester.tap(find.text('Cancelar Alerta'));
    await esperar(tester);
    await tester.tap(find.text('Confirmar'));
    await esperar(tester);
    expect(hex(nodo.enviados.last), '03');
    expect(find.byType(BotonSos), findsOneWidget);
    expect(find.text('Alerta cancelada'), findsOneWidget);

    await tester.pumpWidget(const SizedBox());
    visitante.dispose();
  });

  testWidgets('CU-10: batería baja y enlace perdido', (tester) async {
    usarTelefono(tester);
    final nodo = NodoSimulado()
      ..estado = const EstadoNodo(bateriaMv: 3700, unidoARed: true, sosActivo: false, alertaConfirmada: false);
    final visitante = Visitante(nodo, GpsSimulado());
    await tester.pumpWidget(EcoGuardApp(visitante: visitante));
    await tester.tap(find.text('Buscar nodos'));
    await esperar(tester);
    await tester.tap(find.text('EcoGuard-3B60'));
    await esperar(tester);
    expect(find.text('Batería: 13%'), findsOneWidget);
    expect(find.text('Batería del nodo baja'), findsOneWidget);

    // FE1: el visitante se aleja del nodo
    nodo.perderEnlace();
    await esperar(tester);
    expect(find.text('Nodo desconectado. Acérquese al dispositivo'), findsOneWidget);
    expect(find.text('Batería: 13%'), findsNothing);

    // Al acercarse, la app reconecta sola
    await esperar(tester, const Duration(seconds: 6));
    expect(find.text('Estado: Conectado'), findsOneWidget);

    await tester.pumpWidget(const SizedBox());
    visitante.dispose();
  });
}
