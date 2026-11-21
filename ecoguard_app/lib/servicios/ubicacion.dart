/// @brief Ubicación satelital del teléfono.
///
/// Funciona en modo avión: el GPS no necesita red (RNF-01), aunque sin datos el primer fix tarda más.
library;

import 'dart:async';

import 'package:geolocator/geolocator.dart';

import '../protocolo.dart';

/// @brief Lo que la app necesita del GPS. Las pruebas y el modo simulación lo sustituyen por uno simulado.
abstract class Ubicacion {
  /// @brief Pide el permiso de ubicación.
  ///
  /// Se llama al emparejar, para no interrumpir una emergencia con el diálogo.
  /// @return true si el servicio de ubicación está encendido y el permiso concedido.
  Future<bool> solicitarPermiso();

  /// @brief Obtiene la posición actual (CU-11, FA1).
  /// @param limite Tiempo máximo de espera para conseguir un fix.
  /// @return La posición, o null si no hay fix dentro del límite o falta el permiso.
  Future<Coordenadas?> obtener(Duration limite);

  /// @brief Sigue la posición mientras el visitante se mueve.
  /// @return Flujo con cada posición nueva.
  Stream<Coordenadas> seguir();
}

/// @brief Ubicación real con el GPS del teléfono (paquete geolocator).
class UbicacionGps implements Ubicacion {
  @override
  Future<bool> solicitarPermiso() async {
    if (!await Geolocator.isLocationServiceEnabled()) return false;
    var permiso = await Geolocator.checkPermission();
    if (permiso == LocationPermission.denied) permiso = await Geolocator.requestPermission();
    return _concedido(permiso);
  }

  @override
  Future<Coordenadas?> obtener(Duration limite) async {
    if (!await Geolocator.isLocationServiceEnabled() || !_concedido(await Geolocator.checkPermission())) {
      return null;
    }
    try {
      final posicion = await Geolocator.getCurrentPosition(
        locationSettings: LocationSettings(accuracy: LocationAccuracy.high, timeLimit: limite),
      );
      return Coordenadas(posicion.latitude, posicion.longitude);
    } on TimeoutException {
      return null;
    }
  }

  @override
  Stream<Coordenadas> seguir() => Geolocator.getPositionStream(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.high, distanceFilter: 10),
      ).map((p) => Coordenadas(p.latitude, p.longitude)).handleError((_) {});

  /// @brief Indica si un permiso permite usar el GPS con la app abierta.
  /// @param permiso Permiso actual de ubicación.
  /// @return true si el permiso es "mientras se usa" o "siempre".
  bool _concedido(LocationPermission permiso) =>
      permiso == LocationPermission.whileInUse || permiso == LocationPermission.always;
}
