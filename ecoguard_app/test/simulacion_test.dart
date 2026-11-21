// Modo simulación: la app completa con el nodo y el GPS virtuales
import 'package:ecoguard_app/main.dart';
import 'package:ecoguard_app/pantallas/monitoreo.dart';
import 'package:ecoguard_app/servicios/simulacion.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Recorre emparejamiento, alerta confirmada, situaciones de prueba y cancelación', (tester) async {
    tester.view.physicalSize = const Size(1170, 2532);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);

    Future<void> avanzar(Duration tiempo) async {
      for (var t = Duration.zero; t < tiempo; t += const Duration(milliseconds: 250)) {
        await tester.pump(const Duration(milliseconds: 250));
      }
    }

    await tester.pumpWidget(EcoGuardApp(simulacion: Simulacion()));
    expect(find.text('MODO SIMULACIÓN · Sin nodo ni GPS reales'), findsOneWidget);

    // CU-09: los nodos aparecen uno a uno
    await tester.tap(find.text('Buscar nodos'));
    await avanzar(const Duration(seconds: 3));
    expect(find.text('EcoGuard-3B60'), findsOneWidget);
    expect(find.text('Señal débil'), findsOneWidget);
    await tester.tap(find.text('EcoGuard-3B60'));
    await avanzar(const Duration(seconds: 2));
    expect(find.text('Estado: Conectado'), findsOneWidget);
    expect(find.text('Batería: 66%'), findsOneWidget);

    // CU-11: el nodo se une a la red y la central confirma la alerta
    await avanzar(const Duration(seconds: 3));
    final gesto = await tester.startGesture(tester.getCenter(find.byType(BotonSos)));
    await avanzar(const Duration(milliseconds: 3500));
    await gesto.up();
    await avanzar(const Duration(seconds: 2));
    expect(find.text('SOS Activo'), findsOneWidget);
    expect(find.text('Ubicación enviada'), findsOneWidget);
    await avanzar(const Duration(seconds: 5));
    expect(find.text('La central recibió su alerta'), findsOneWidget);

    // CU-10, FA1 desde el menú de situaciones de prueba
    await tester.tap(find.byTooltip('Situaciones de prueba'));
    await avanzar(const Duration(seconds: 1));
    await tester.tap(find.widgetWithText(CheckedPopupMenuItem<VoidCallback>, 'Batería del nodo baja'));
    await avanzar(const Duration(seconds: 1));
    expect(find.text('Batería: 13%'), findsOneWidget);
    expect(find.text('Batería del nodo baja'), findsOneWidget);

    // CU-12
    await tester.tap(find.text('Cancelar Alerta'));
    await avanzar(const Duration(seconds: 1));
    await tester.tap(find.text('Confirmar'));
    await avanzar(const Duration(seconds: 1));
    expect(find.byType(BotonSos), findsOneWidget);
    expect(find.text('Alerta cancelada'), findsOneWidget);

    await tester.pumpWidget(const SizedBox());
  });
}
