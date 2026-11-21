/// @brief Encabezado con el estado de la conexión y la batería del nodo (CU-10), visible en todas las pantallas.
library;

import 'package:flutter/material.dart';

import '../tema.dart';
import '../visitante.dart';

/// @brief Tarjeta con el estado del enlace con el nodo y su batería.
///
/// Verde si está conectado, rojo si se perdió el enlace (CU-10, FE1). Debajo muestra el aviso de
/// batería baja (CU-10, FA1).
class EncabezadoEstado extends StatelessWidget {
  /// @brief Crea el encabezado.
  /// @param key Clave del widget.
  /// @param visitante Estado de la app.
  const EncabezadoEstado({super.key, required this.visitante});

  /// Estado de la app.
  final Visitante visitante;

  /// @brief Ícono de batería según el porcentaje de carga.
  /// @param porcentaje Carga de 0 a 100.
  /// @return Ícono de Material con las barras correspondientes.
  static IconData _iconoBateria(int porcentaje) => switch (porcentaje) {
        >= 90 => Icons.battery_full,
        >= 75 => Icons.battery_6_bar,
        >= 60 => Icons.battery_5_bar,
        >= 45 => Icons.battery_4_bar,
        >= 30 => Icons.battery_3_bar,
        >= 20 => Icons.battery_2_bar,
        >= 10 => Icons.battery_1_bar,
        _ => Icons.battery_0_bar,
      };

  /// @brief Construye la tarjeta.
  /// @param context Contexto del widget.
  /// @return El widget de la tarjeta.
  @override
  Widget build(BuildContext context) {
    final tema = Theme.of(context);
    final colores = tema.colorScheme;
    final emparejado = visitante.nodo != null;
    final conectado = emparejado && !visitante.enlacePerdido;
    final bateria = visitante.bateria;
    final colorBateria = visitante.bateriaBaja ? colores.error : colores.onSurfaceVariant;
    // FE1 de CU-10: al perder el enlace el estado cambia a rojo
    final (texto, color, icono) = conectado
        ? ('Estado: Conectado', colores.exito, Icons.bluetooth_connected_rounded)
        : emparejado
            ? ('Nodo desconectado. Acérquese al dispositivo', colores.error, Icons.bluetooth_disabled_rounded)
            : ('Sin nodo emparejado', colores.onSurfaceVariant, Icons.bluetooth_rounded);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Row(
              children: [
                Icon(icono, color: color),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(texto, style: tema.textTheme.titleSmall?.copyWith(color: color, fontWeight: FontWeight.w600)),
                      if (emparejado)
                        Text(
                          visitante.nodo!.nombre,
                          style: tema.textTheme.bodySmall?.copyWith(color: colores.onSurfaceVariant),
                        ),
                    ],
                  ),
                ),
                if (conectado && bateria != null) ...[
                  Icon(_iconoBateria(bateria), size: 20, color: colorBateria),
                  const SizedBox(width: 4),
                  Text(
                    'Batería: $bateria%',
                    style: tema.textTheme.labelLarge?.copyWith(
                      color: visitante.bateriaBaja ? colores.error : colores.onSurface,
                    ),
                  ),
                ],
              ],
            ),

            // FA1 de CU-10: advertencia de batería baja
            if (conectado && visitante.bateriaBaja) ...[
              const Padding(padding: EdgeInsets.symmetric(vertical: 12), child: Divider()),
              Row(
                children: [
                  Icon(Icons.warning_amber_rounded, color: colores.error),
                  const SizedBox(width: 12),
                  Flexible(
                    child: Text(
                      'Batería del nodo baja',
                      style: tema.textTheme.bodyMedium?.copyWith(color: colores.error, fontWeight: FontWeight.w600),
                    ),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}
