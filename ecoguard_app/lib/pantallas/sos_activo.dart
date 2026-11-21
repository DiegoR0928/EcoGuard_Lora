/// @brief Pantalla de la alerta en curso (CU-11) con la opción de cancelarla (CU-12).
library;

import 'package:flutter/material.dart';

import '../tema.dart';
import '../visitante.dart';

/// @brief Pantalla de la alerta en curso.
///
/// Muestra el avance de la alerta: el nodo la recibió, la central la confirmó (o el nodo busca
/// señal) y la ubicación se envió. Permite cancelarla con confirmación.
class SosActivo extends StatelessWidget {
  /// @brief Crea la pantalla.
  /// @param key Clave del widget.
  /// @param visitante Estado de la app.
  const SosActivo({super.key, required this.visitante});

  /// Estado de la app.
  final Visitante visitante;

  /// @brief Pide confirmación antes de cancelar la alerta (CU-12, pasos 3 y 4, y FA1).
  ///
  /// Si el visitante presiona «Regresar», la alerta sigue activa.
  /// @param context Contexto para mostrar el diálogo.
  /// @return Se completa al cerrarse el diálogo y, si se confirmó, al terminar la cancelación.
  Future<void> _confirmarCancelacion(BuildContext context) async {
    final colores = Theme.of(context).colorScheme;
    final confirmado = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('¿Desea cancelar el rescate?'),
        content: const Text('Use esta opción solo si la alerta fue accidental o ya no necesita ayuda.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Regresar')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: colores.error, foregroundColor: colores.onError),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Confirmar'),
          ),
        ],
      ),
    );
    if (confirmado == true) await visitante.cancelarSos();
  }

  /// @brief Construye la pantalla.
  /// @param context Contexto del widget.
  /// @return El widget de la pantalla.
  @override
  Widget build(BuildContext context) {
    final tema = Theme.of(context);
    final colores = tema.colorScheme;
    final fase = visitante.fase;
    final estado = visitante.estadoNodo;
    final puedeCancelar = fase == Fase.sosActivo;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Card(
          color: colores.errorContainer,
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              children: [
                Icon(Icons.emergency_share_rounded, size: 48, color: colores.onErrorContainer),
                const SizedBox(height: 12),
                Text(
                  fase == Fase.enviandoSos ? 'Enviando alerta…' : 'SOS Activo',
                  textAlign: TextAlign.center,
                  style: tema.textTheme.headlineMedium?.copyWith(
                    color: colores.onErrorContainer,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Permanezca en su ubicación si es seguro hacerlo.',
                  textAlign: TextAlign.center,
                  style: tema.textTheme.bodyMedium?.copyWith(color: colores.onErrorContainer),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),

        Card(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Column(
              children: fase == Fase.enviandoSos
                  ? const [_Paso('Obteniendo su ubicación y avisando al nodo…', _Avance.pendiente)]
                  : [
                      const _Paso('El nodo recibió su alerta', _Avance.listo),
                      const Divider(indent: 56),
                      // Lo que el nodo reporta de la red: si la central ya confirmó, el visitante lo sabe
                      if (estado?.alertaConfirmada ?? false)
                        const _Paso('La central recibió su alerta', _Avance.listo)
                      else if (estado != null && !estado.unidoARed)
                        const _Paso('El nodo busca señal: su alerta saldrá en cuanto la encuentre', _Avance.aviso)
                      else
                        const _Paso('Enviando su alerta a la central…', _Avance.pendiente),
                      const Divider(indent: 56),
                      visitante.ubicacionEnviada
                          ? const _Paso('Ubicación enviada', _Avance.listo)
                          : const _Paso('Buscando su ubicación GPS…', _Avance.pendiente),
                    ],
            ),
          ),
        ),
        const SizedBox(height: 24),

        OutlinedButton.icon(
          style: OutlinedButton.styleFrom(
            foregroundColor: colores.error,
            side: BorderSide(color: puedeCancelar ? colores.error : colores.outlineVariant),
          ),
          icon: fase == Fase.cancelando
              ? SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2, color: colores.error))
              : const Icon(Icons.cancel_outlined),
          label: const Text('Cancelar Alerta'),
          onPressed: puedeCancelar ? () => _confirmarCancelacion(context) : null,
        ),
      ],
    );
  }
}

/// @brief Estado de un paso de la alerta; define su ícono.
enum _Avance {
  /// Completado (palomita verde).
  listo,
  /// En curso (indicador de progreso).
  pendiente,
  /// Detenido por una condición externa, p. ej. sin cobertura (ícono ámbar).
  aviso,
}

/// @brief Renglón con un paso de la alerta y su estado.
class _Paso extends StatelessWidget {
  /// @brief Crea el renglón.
  /// @param texto Descripción del paso.
  /// @param avance Estado del paso.
  const _Paso(this.texto, this.avance);

  /// Descripción del paso.
  final String texto;
  /// Estado del paso.
  final _Avance avance;

  /// @brief Construye el renglón.
  /// @param context Contexto del widget.
  /// @return El widget del renglón.
  @override
  Widget build(BuildContext context) {
    final colores = Theme.of(context).colorScheme;
    return ListTile(
      leading: switch (avance) {
        _Avance.listo => Icon(Icons.check_circle_rounded, color: colores.exito),
        _Avance.aviso => Icon(Icons.error_outline_rounded, color: colores.advertencia),
        _Avance.pendiente => const SizedBox.square(
            dimension: 24,
            child: Padding(padding: EdgeInsets.all(3), child: CircularProgressIndicator(strokeWidth: 2.5)),
          ),
      },
      title: Text(texto),
    );
  }
}
