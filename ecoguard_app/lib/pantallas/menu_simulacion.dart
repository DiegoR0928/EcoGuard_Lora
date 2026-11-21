/// @brief Menú del modo simulación.
///
/// Provoca las situaciones de los casos de uso que con hardware real son difíciles de reproducir a voluntad.
library;

import 'package:flutter/material.dart';

import '../servicios/simulacion.dart';

/// @brief Botón de la barra superior con las situaciones de prueba del modo simulación.
///
/// Cada opción activa o desactiva una situación: nodo fuera de alcance, batería baja, sin señal GPS,
/// nodo que no responde y sin cobertura LoRaWAN.
class MenuSimulacion extends StatelessWidget {
  /// @brief Crea el menú.
  /// @param key Clave del widget.
  /// @param simulacion Nodo y GPS simulados que el menú controla.
  const MenuSimulacion({super.key, required this.simulacion});

  /// Nodo y GPS simulados.
  final Simulacion simulacion;

  /// @brief Construye el menú.
  /// @param context Contexto del widget.
  /// @return El widget del menú.
  @override
  Widget build(BuildContext context) {
    final nodo = simulacion.enlace;
    final gps = simulacion.ubicacion;

    CheckedPopupMenuItem<VoidCallback> opcion(String texto, bool activa, VoidCallback alternar) =>
        CheckedPopupMenuItem(value: alternar, checked: activa, child: Text(texto));

    return PopupMenuButton<VoidCallback>(
      icon: const Icon(Icons.tune_rounded),
      tooltip: 'Situaciones de prueba',
      onSelected: (alternar) => alternar(),
      itemBuilder: (context) => [
        const PopupMenuItem(enabled: false, child: Text('Situaciones de prueba')),
        opcion('Nodo fuera de alcance', nodo.fueraDeAlcance, nodo.alternarAlcance), // CU-09 FE1, CU-10 FE1
        opcion('Batería del nodo baja', nodo.bateriaBaja, nodo.alternarBateria), // CU-10 FA1
        opcion('Sin señal GPS', gps.sinSenal, gps.alternarSenal), // CU-11 FA1
        opcion('El nodo no responde', nodo.fallarEnvio, nodo.alternarFallaEnvio), // CU-11 FE1, CU-12 FE1
        opcion('Sin cobertura LoRaWAN', nodo.sinCobertura, nodo.alternarCobertura), // La central no confirma
      ],
    );
  }
}
