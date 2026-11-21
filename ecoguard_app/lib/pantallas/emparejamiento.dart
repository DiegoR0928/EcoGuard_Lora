/// @brief Pantalla de emparejamiento: buscar el nodo asignado y emparejarlo (CU-09).
library;

import 'package:flutter/material.dart';

import '../servicios/enlace_nodo.dart';
import '../visitante.dart';

/// @brief Pantalla para buscar el nodo y elegirlo de la lista de nodos cercanos (CU-09).
///
/// Mientras se busca o conecta muestra un indicador de progreso; si el nodo esperado no aparece, el
/// visitante puede escanear de nuevo (FA1).
class Emparejamiento extends StatelessWidget {
  /// @brief Crea la pantalla.
  /// @param key Clave del widget.
  /// @param visitante Estado de la app.
  const Emparejamiento({super.key, required this.visitante});

  /// Estado de la app.
  final Visitante visitante;

  /// @brief Construye la pantalla.
  /// @param context Contexto del widget.
  /// @return El widget de la pantalla.
  @override
  Widget build(BuildContext context) {
    final tema = Theme.of(context);
    final buscando = visitante.fase == Fase.buscando;
    final conectando = visitante.fase == Fase.conectando;
    final nodos = visitante.encontrados;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Icon(Icons.bluetooth_searching_rounded, size: 56, color: tema.colorScheme.primary),
        const SizedBox(height: 16),
        Text(
          'Vincular nodo',
          textAlign: TextAlign.center,
          style: tema.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 8),
        Text(
          'Encienda el nodo que le entregaron en el parque y manténgalo cerca del teléfono.',
          textAlign: TextAlign.center,
          style: tema.textTheme.bodyMedium?.copyWith(color: tema.colorScheme.onSurfaceVariant),
        ),
        const SizedBox(height: 24),

        if (buscando || conectando)
          _Progreso(conectando ? 'Conectando con el nodo…' : 'Buscando nodos EcoGuard cercanos…'),

        // CU-09, paso 3: nodos disponibles; el visitante elige el suyo (paso 4)
        if (nodos.isNotEmpty && !conectando) ...[
          Text('Seleccione el nodo que le entregaron:', style: tema.textTheme.titleSmall),
          const SizedBox(height: 8),
          for (final nodo in nodos)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _TarjetaNodo(nodo: nodo, alElegir: () => visitante.conectar(nodo)),
            ),
        ],

        if (!buscando && !conectando) ...[
          if (nodos.isEmpty)
            FilledButton.icon(
              icon: const Icon(Icons.bluetooth_searching_rounded),
              label: const Text('Buscar nodos'),
              onPressed: visitante.buscarNodos,
            ),
          const SizedBox(height: 8),
          // FA1 de CU-09: el nodo esperado no aparece
          TextButton(onPressed: visitante.buscarNodos, child: const Text('Escanear de nuevo')),
        ],
      ],
    );
  }
}

/// @brief Indicador de progreso con un texto, p. ej. "Buscando nodos EcoGuard cercanos…".
class _Progreso extends StatelessWidget {
  /// @brief Crea el indicador.
  /// @param texto Texto junto al indicador.
  const _Progreso(this.texto);

  /// Texto junto al indicador.
  final String texto;

  /// @brief Construye el indicador.
  /// @param context Contexto del widget.
  /// @return El widget del indicador.
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2.5)),
          const SizedBox(width: 12),
          Flexible(child: Text(texto, style: Theme.of(context).textTheme.bodyMedium)),
        ],
      ),
    );
  }
}

/// @brief Tarjeta de un nodo encontrado, con su nombre y la intensidad de la señal.
class _TarjetaNodo extends StatelessWidget {
  /// @brief Crea la tarjeta.
  /// @param nodo Nodo encontrado.
  /// @param alElegir Se llama cuando el visitante toca la tarjeta (CU-09, paso 4).
  const _TarjetaNodo({required this.nodo, required this.alElegir});

  /// Nodo encontrado.
  final NodoEncontrado nodo;
  /// Se llama cuando el visitante elige este nodo.
  final VoidCallback alElegir;

  /// Texto e ícono de la intensidad de la señal: ayuda a reconocer el nodo propio entre varios
  /// cercanos. Fuerte desde -65 dBm, media desde -80 dBm y débil por debajo.
  (String, IconData) get _senal => nodo.rssi >= -65
      ? ('Señal fuerte', Icons.signal_cellular_alt)
      : nodo.rssi >= -80
          ? ('Señal media', Icons.signal_cellular_alt_2_bar)
          : ('Señal débil', Icons.signal_cellular_alt_1_bar);

  /// @brief Construye la tarjeta.
  /// @param context Contexto del widget.
  /// @return El widget de la tarjeta.
  @override
  Widget build(BuildContext context) {
    final colores = Theme.of(context).colorScheme;
    final (senal, iconoSenal) = _senal;

    return Card(
      clipBehavior: Clip.antiAlias,
      child: ListTile(
        leading: Icon(Icons.sensors_rounded, color: colores.primary),
        title: Text(nodo.nombre, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(senal),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(iconoSenal, size: 20, color: colores.onSurfaceVariant),
            const SizedBox(width: 4),
            Icon(Icons.chevron_right_rounded, color: colores.onSurfaceVariant),
          ],
        ),
        onTap: alElegir,
      ),
    );
  }
}
