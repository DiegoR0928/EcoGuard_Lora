/// @brief Pantalla de monitoreo con el botón SOS (CU-10 y CU-11).
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../tema.dart';
import '../visitante.dart';

/// @brief Pantalla principal con el nodo emparejado: el botón SOS y la opción de cambiar de nodo.
class Monitoreo extends StatelessWidget {
  /// @brief Crea la pantalla.
  /// @param key Clave del widget.
  /// @param visitante Estado de la app.
  const Monitoreo({super.key, required this.visitante});

  /// Estado de la app.
  final Visitante visitante;

  /// @brief Construye la pantalla.
  /// @param context Contexto del widget.
  /// @return El widget de la pantalla.
  @override
  Widget build(BuildContext context) {
    final tema = Theme.of(context);
    return Column(
      children: [
        BotonSos(alIniciar: visitante.prepararUbicacion, alCompletar: visitante.emitirSos),
        const SizedBox(height: 24),
        Text(
          'Mantenga presionado el botón 3 segundos para solicitar ayuda',
          textAlign: TextAlign.center,
          style: tema.textTheme.bodyLarge?.copyWith(color: tema.colorScheme.onSurfaceVariant),
        ),
        const SizedBox(height: 16),
        TextButton.icon(
          onPressed: visitante.desvincular,
          icon: const Icon(Icons.link_off_rounded, size: 18),
          label: const Text('Cambiar de nodo'),
        ),
      ],
    );
  }
}

/// @brief Botón SOS que hay que mantener presionado para emitir la alerta (CU-11, paso 1).
///
/// Evita activaciones accidentales con el teléfono en el bolsillo (RNF-09): un anillo se llena
/// durante la pulsación y, si se suelta antes de tiempo, no pasa nada.
class BotonSos extends StatefulWidget {
  /// @brief Crea el botón.
  /// @param key Clave del widget.
  /// @param alIniciar Se llama al empezar a presionar (para adelantar la búsqueda del GPS).
  /// @param alCompletar Se llama al cumplirse la duración (emite la alerta).
  /// @param duracion Tiempo que hay que mantenerlo presionado.
  const BotonSos({
    super.key,
    required this.alIniciar,
    required this.alCompletar,
    this.duracion = const Duration(seconds: 3),
  });

  /// Se llama al empezar a presionar el botón.
  final VoidCallback alIniciar;
  /// Se llama cuando el botón estuvo presionado toda la duración.
  final VoidCallback alCompletar;
  /// Tiempo que hay que mantener presionado el botón.
  final Duration duracion;

  /// @brief Crea el estado del botón.
  /// @return El estado, con la animación de la pulsación.
  @override
  State<BotonSos> createState() => _BotonSosState();
}

/// @brief Estado del botón SOS: anima el anillo de progreso mientras se mantiene presionado.
class _BotonSosState extends State<BotonSos> with SingleTickerProviderStateMixin {
  /// Rojo más oscuro del botón mientras se presiona.
  static const _rojoPresionado = Color(0xFF8E1B1B);

  /// Animación de la pulsación, de 0 a 1 en widget.duracion. Al completarse vibra, se reinicia y
  /// llama a alCompletar.
  late final AnimationController _progreso = AnimationController(vsync: this, duration: widget.duracion)
    ..addStatusListener((estado) {
      if (estado == AnimationStatus.completed) {
        HapticFeedback.heavyImpact();
        _progreso.reset();
        widget.alCompletar();
      }
    });

  /// @brief Inicio de la pulsación: avisa, vibra y arranca el anillo.
  void _presionar() {
    widget.alIniciar();
    HapticFeedback.selectionClick();
    _progreso.forward(from: 0);
  }

  /// @brief Fin de la pulsación antes de tiempo: el anillo vuelve a cero y no se emite nada.
  void _soltar() {
    if (_progreso.isAnimating) _progreso.reset();
  }

  /// @brief Libera la animación.
  @override
  void dispose() {
    _progreso.dispose();
    super.dispose();
  }

  /// @brief Construye el botón.
  /// @param context Contexto del widget.
  /// @return El widget del botón.
  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: 'Botón SOS. Mantenga presionado 3 segundos para solicitar ayuda',
      child: GestureDetector(
        onTapDown: (_) => _presionar(),
        onTapUp: (_) => _soltar(),
        onTapCancel: _soltar,
        child: AnimatedBuilder(
          animation: _progreso,
          builder: (context, _) {
            final presionando = _progreso.value > 0;
            return SizedBox.square(
              dimension: 232,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  // Anillo que se llena durante los 3 segundos
                  SizedBox.expand(
                    child: CircularProgressIndicator(
                      value: _progreso.value,
                      strokeWidth: 6,
                      color: rojoEmergencia,
                      backgroundColor: rojoEmergencia.withValues(alpha: 0.15),
                    ),
                  ),
                  Container(
                    width: 204,
                    height: 204,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: presionando ? _rojoPresionado : rojoEmergencia,
                      boxShadow: const [BoxShadow(color: Color(0x33000000), blurRadius: 8, offset: Offset(0, 3))],
                    ),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Text(
                          'SOS',
                          style: TextStyle(color: Colors.white, fontSize: 56, fontWeight: FontWeight.w700, letterSpacing: 3),
                        ),
                        Text(
                          presionando ? 'Siga presionando…' : 'Mantener 3 s',
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.9),
                            fontSize: 14,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}
