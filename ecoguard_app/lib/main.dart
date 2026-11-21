/// @brief Punto de entrada de la app del visitante: tema, avisos y elección de la pantalla según la fase.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'pantallas/emparejamiento.dart';
import 'pantallas/encabezado.dart';
import 'pantallas/menu_simulacion.dart';
import 'pantallas/monitoreo.dart';
import 'pantallas/sos_activo.dart';
import 'servicios/enlace_nodo.dart';
import 'servicios/simulacion.dart';
import 'servicios/ubicacion.dart';
import 'tema.dart';
import 'visitante.dart';

/// @brief Arranca la app.
///
/// Usa el modo simulación (nodo y GPS virtuales) con --dart-define=SIMULACION=true, y siempre fuera
/// de Android e iOS, donde no hay Bluetooth con el nodo (Windows, navegador).
void main() {
  final simular = const bool.fromEnvironment('SIMULACION') ||
      kIsWeb ||
      !(defaultTargetPlatform == TargetPlatform.android || defaultTargetPlatform == TargetPlatform.iOS);
  runApp(EcoGuardApp(simulacion: simular ? Simulacion() : null));
}

/// @brief Widget raíz de la app.
class EcoGuardApp extends StatefulWidget {
  /// @brief Crea la app.
  /// @param key Clave del widget.
  /// @param visitante Estado a usar; las pruebas inyectan uno con un nodo y un GPS simulados. Si es
  ///        null, la app crea el suyo con el Bluetooth y el GPS reales o los de simulacion.
  /// @param simulacion Nodo y GPS simulados; null con hardware real.
  const EcoGuardApp({super.key, this.visitante, this.simulacion});

  /// Estado inyectado por las pruebas; null en uso normal.
  final Visitante? visitante;
  /// Nodo y GPS simulados; null con hardware real.
  final Simulacion? simulacion;

  /// @brief Crea el estado de la app.
  /// @return El estado, que guarda al visitante y muestra sus avisos.
  @override
  State<EcoGuardApp> createState() => _EcoGuardAppState();
}

/// @brief Estado de la app: crea al visitante, muestra sus avisos y dibuja la pantalla principal.
class _EcoGuardAppState extends State<EcoGuardApp> {
  /// Estado del visitante: el inyectado o uno nuevo con el enlace y el GPS reales o simulados.
  late final Visitante _visitante = widget.visitante ??
      Visitante(widget.simulacion?.enlace ?? EnlaceBluetooth(), widget.simulacion?.ubicacion ?? UbicacionGps());
  /// Acceso al ScaffoldMessenger para mostrar los avisos como SnackBar.
  final _mensajero = GlobalKey<ScaffoldMessengerState>();
  /// Suscripción a los avisos del visitante.
  late final StreamSubscription<Aviso> _avisos;

  /// Color de fondo de cada tipo de aviso; legibles sobre fondo claro y oscuro.
  static const _colorAviso = {
    TipoAviso.exito: Color(0xFF1E6B3A),
    TipoAviso.error: Color(0xFFB3261E),
    TipoAviso.informacion: Color(0xFF37474F),
  };

  /// Ícono de cada tipo de aviso.
  static const _iconoAviso = {
    TipoAviso.exito: Icons.check_circle_outline_rounded,
    TipoAviso.error: Icons.error_outline_rounded,
    TipoAviso.informacion: Icons.info_outline_rounded,
  };

  /// @brief Se suscribe a los avisos del visitante para mostrarlos como SnackBar (6 s los errores, 4 s el resto).
  @override
  void initState() {
    super.initState();
    _avisos = _visitante.avisos.listen((aviso) {
      _mensajero.currentState
        ?..hideCurrentSnackBar()
        ..showSnackBar(
          SnackBar(
            content: Row(
              children: [
                Icon(_iconoAviso[aviso.tipo], color: Colors.white),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(aviso.texto, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500)),
                ),
              ],
            ),
            backgroundColor: _colorAviso[aviso.tipo],
            duration: Duration(seconds: aviso.tipo == TipoAviso.error ? 6 : 4),
          ),
        );
    });
  }

  /// @brief Cancela la suscripción y libera al visitante si lo creó la app.
  @override
  void dispose() {
    _avisos.cancel();
    if (widget.visitante == null) _visitante.dispose();
    super.dispose();
  }

  /// @brief Construye la app.
  /// @param context Contexto del widget.
  /// @return El widget de la app.
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'EcoGuard',
      debugShowCheckedModeBanner: false,
      scaffoldMessengerKey: _mensajero,
      theme: temaEcoGuard(Brightness.light),
      darkTheme: temaEcoGuard(Brightness.dark),
      home: ListenableBuilder(
        listenable: _visitante,
        builder: (context, _) => PantallaPrincipal(visitante: _visitante, simulacion: widget.simulacion),
      ),
    );
  }
}

/// @brief Estructura común de la app: barra superior, encabezado de estado, pantalla de la fase y pie.
///
/// Elige la pantalla: emparejamiento sin nodo (CU-09), alerta durante una emergencia (CU-11 y CU-12)
/// y monitoreo en los demás casos (CU-10 y CU-11). En emergencia la barra se vuelve roja.
class PantallaPrincipal extends StatelessWidget {
  /// @brief Crea la pantalla.
  /// @param key Clave del widget.
  /// @param visitante Estado de la app.
  /// @param simulacion Nodo y GPS simulados; si no es null, se muestran el menú y el aviso de simulación.
  const PantallaPrincipal({super.key, required this.visitante, this.simulacion});

  /// Estado de la app.
  final Visitante visitante;
  /// Nodo y GPS simulados; null con hardware real.
  final Simulacion? simulacion;

  /// @brief Construye la pantalla.
  /// @param context Contexto del widget.
  /// @return El widget de la pantalla.
  @override
  Widget build(BuildContext context) {
    final emergencia = visitante.enEmergencia;
    final Widget contenido;
    if (visitante.nodo == null) {
      contenido = Emparejamiento(visitante: visitante); // CU-09
    } else if (emergencia) {
      contenido = SosActivo(visitante: visitante); // CU-11 y CU-12
    } else {
      contenido = Monitoreo(visitante: visitante); // CU-10 y CU-11
    }

    return Scaffold(
      appBar: AppBar(
        // En emergencia la barra se vuelve roja: el estado se reconoce de un vistazo
        backgroundColor: emergencia ? rojoEmergencia : null,
        foregroundColor: emergencia ? Colors.white : null,
        title: Row(
          children: [
            const Icon(Icons.health_and_safety_outlined),
            const SizedBox(width: 12),
            Flexible(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('EcoGuard', style: TextStyle(fontWeight: FontWeight.w600)),
                  Text(
                    emergencia ? 'Alerta en curso' : 'Asistencia al visitante',
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w400),
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [if (simulacion != null) MenuSimulacion(simulacion: simulacion!)],
        bottom: simulacion == null ? null : const _AvisoSimulacion(),
      ),
      body: SafeArea(
        child: LayoutBuilder(
          // Desplazable para pantallas pequeñas o letra grande; si cabe, el contenido queda centrado
          builder: (context, limites) => SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 12),
            // En pantallas anchas (escritorio, tableta) se conserva el ancho de un teléfono
            child: Center(
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: limites.maxHeight - 28, maxWidth: 480),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    EncabezadoEstado(visitante: visitante),
                    Padding(padding: const EdgeInsets.symmetric(vertical: 24), child: contenido),
                    const _PiePagina(),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// @brief Pie de página que recuerda que la app funciona sin internet.
///
/// La app no usa internet ni datos: solo Bluetooth con el nodo y el GPS del teléfono (RNF-01).
class _PiePagina extends StatelessWidget {
  /// @brief Crea el pie de página.
  const _PiePagina();

  /// @brief Construye el pie de página.
  /// @param context Contexto del widget.
  /// @return El widget del pie de página.
  @override
  Widget build(BuildContext context) {
    final tema = Theme.of(context);
    final estilo = tema.textTheme.bodySmall?.copyWith(color: tema.colorScheme.onSurfaceVariant);
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(Icons.cloud_off_outlined, size: 16, color: estilo?.color),
        const SizedBox(width: 6),
        Flexible(child: Text('Funciona sin conexión a internet', style: estilo)),
      ],
    );
  }
}

/// @brief Franja ámbar bajo la barra superior en modo simulación.
///
/// Deja claro que nada de lo que se ve viene de un nodo real.
class _AvisoSimulacion extends StatelessWidget implements PreferredSizeWidget {
  /// @brief Crea la franja.
  const _AvisoSimulacion();

  /// Alto de la franja: 28 px.
  @override
  Size get preferredSize => const Size.fromHeight(28);

  /// @brief Construye la franja.
  /// @param context Contexto del widget.
  /// @return El widget de la franja.
  @override
  Widget build(BuildContext context) {
    return Container(
      height: preferredSize.height,
      color: const Color(0xFFFFB300),
      alignment: Alignment.center,
      child: const Text(
        'MODO SIMULACIÓN · Sin nodo ni GPS reales',
        style: TextStyle(color: Color(0xFF3E2723), fontSize: 12, fontWeight: FontWeight.w600, letterSpacing: 0.5),
      ),
    );
  }
}
