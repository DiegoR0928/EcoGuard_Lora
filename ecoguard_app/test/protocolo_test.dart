import 'package:ecoguard_app/bateria.dart';
import 'package:ecoguard_app/protocolo.dart';
import 'package:flutter_test/flutter_test.dart';

import 'simulados.dart';

void main() {
  // Los mismos bytes que se validaron contra el firmware y el simulador de ChirpStack
  group('Comandos hacia el nodo', () {
    test('SOS con GPS', () {
      expect(hex(codificarComando(Comando.sos, const Coordenadas(22.7758, -102.5714))), '0101F8875B0178E2E2F9');
    });

    test('SOS sin GPS: banderas en cero y sin coordenadas inventadas', () {
      expect(hex(codificarComando(Comando.sos)), '01000000000000000000');
    });

    test('Actualización de posición', () {
      expect(hex(codificarComando(Comando.posicion, const Coordenadas(22.7765, -102.5720))), '0201B48A5B0120E0E2F9');
    });

    test('Cancelación de un solo byte', () {
      expect(hex(codificarComando(Comando.cancelar)), '03');
    });
  });

  group('Estado notificado por el nodo', () {
    test('Batería en mV y banderas', () {
      final estado = EstadoNodo.desdeBytes([0x0A, 0x0F, 0x07]);
      expect(estado.bateriaMv, 3850);
      expect([estado.unidoARed, estado.sosActivo, estado.alertaConfirmada], [true, true, true]);
    });

    test('Solo unido a la red', () {
      final estado = EstadoNodo.desdeBytes([0x0A, 0x0F, 0x01]);
      expect([estado.unidoARed, estado.sosActivo, estado.alertaConfirmada], [true, false, false]);
    });

    test('Notificación incompleta', () {
      expect(() => EstadoNodo.desdeBytes([0x0A, 0x0F]), throwsFormatException);
    });
  });

  // La misma curva del panel web (formato.ts): ambos deben mostrar el mismo porcentaje
  test('Curva de batería LiPo', () {
    const esperado = {4300: 100, 4200: 100, 4000: 78, 3900: 64, 3850: 55, 3800: 40, 3750: 25,
        3720: 18, 3700: 13, 3650: 8, 3600: 5, 3500: 3, 3350: 1, 3300: 0, 3100: 0};
    esperado.forEach((mv, pct) => expect(porcentajeBateria(mv), pct, reason: '$mv mV'));
  });
}
