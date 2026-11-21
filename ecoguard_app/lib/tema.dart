/// @brief Estilo visual de la app: sobrio e institucional. Sigue el modo claro u oscuro del teléfono.
library;

import 'package:flutter/material.dart';

/// Verde institucional del que se deriva la paleta de Material 3.
const _verdeParque = Color(0xFF1F5C4A);

/// Rojo del botón SOS y de la barra en emergencia. Es el mismo en ambos modos: es una señal, no decoración.
const rojoEmergencia = Color(0xFFC62828);

/// @brief Colores de estado que el esquema de Material no trae (extensión de ColorScheme).
extension ColoresEcoGuard on ColorScheme {
  /// Verde para lo que salió bien (p. ej. "La central recibió su alerta").
  Color get exito => brightness == Brightness.light ? const Color(0xFF1E6B3A) : const Color(0xFF81C995);
  /// Ámbar para advertencias que no son errores (p. ej. el nodo busca señal).
  Color get advertencia => brightness == Brightness.light ? const Color(0xFF8A5300) : const Color(0xFFFFB95C);
}

/// @brief Tema de Material 3 de EcoGuard.
///
/// Botones de al menos 48 px de alto, tarjetas sin sombra con borde y avisos flotantes.
/// @param brillo Brightness.light o Brightness.dark.
/// @return El tema para MaterialApp.theme o MaterialApp.darkTheme.
ThemeData temaEcoGuard(Brightness brillo) {
  final colores = ColorScheme.fromSeed(
    seedColor: _verdeParque,
    brightness: brillo,
    dynamicSchemeVariant: DynamicSchemeVariant.fidelity, // Conserva el verde original, sin tonos pastel
  );
  final claro = brillo == Brightness.light;
  final forma = RoundedRectangleBorder(borderRadius: BorderRadius.circular(8));
  // Se parte de la tipografía del tema para conservar la fuente del sistema
  final textoBoton = ThemeData(colorScheme: colores).textTheme.labelLarge?.copyWith(
        fontSize: 16,
        fontWeight: FontWeight.w600,
      );

  return ThemeData(
    colorScheme: colores,
    scaffoldBackgroundColor: claro ? colores.surfaceContainerLow : colores.surface,
    appBarTheme: AppBarTheme(
      backgroundColor: claro ? colores.primary : colores.surfaceContainerHigh,
      foregroundColor: claro ? colores.onPrimary : colores.onSurface,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
    ),
    cardTheme: CardThemeData(
      color: claro ? colores.surfaceContainerLowest : colores.surfaceContainer,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: colores.outlineVariant),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(minimumSize: const Size(64, 48), shape: forma, textStyle: textoBoton),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(minimumSize: const Size(64, 48), shape: forma, textStyle: textoBoton),
    ),
    textButtonTheme: TextButtonThemeData(style: TextButton.styleFrom(shape: forma)),
    dialogTheme: DialogThemeData(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
    snackBarTheme: SnackBarThemeData(behavior: SnackBarBehavior.floating, shape: forma),
    dividerTheme: DividerThemeData(color: colores.outlineVariant, space: 1),
  );
}
